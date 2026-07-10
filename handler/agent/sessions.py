import asyncio
from http import HTTPStatus
from typing import Any

from fastapi.websockets import WebSocketState
from fastapi import WebSocket, WebSocketDisconnect, status as ws_status

from core.runtime.session import get_agent_pool
from handler import authenticate_ws_token, cancel_ws_task as _cancel_task, close_ws_silently as _close_silently
from logger import get_logger
from middleware.auth import AuthUser
from schema.agent.events import AgentEventSchema
from schema.agent.sessions import (
    AgentSessionSummarySchema,
    AgentTurnRequest,
    AgentTurnResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
    UpdateAgentSessionSandboxContainerRequest,
    UpdateAgentSessionTitleRequest,
)
from schema.common.responses import CommonResponse
from service.agent import runtime as agent_runtime
from service.agent import sessions as agent_sessions


logger = get_logger(__name__)


async def create_agent_session_turn_handler(
    request: AgentTurnRequest,
    user: AuthUser,
) -> CommonResponse[AgentTurnResponse]:
    try:
        session_id, events = await agent_runtime.submit_new_chat_turn(
            content=request.content,
            user=user,
            sandbox_container_id=request.sandbox_container_id,
            requested_agent_code=request.agent_code,
        )
    except Exception as exc:
        error = _runtime_error_response(exc)
        if error is not None:
            return error
        raise
    return await _turn_response(session_id, user, events)


async def submit_agent_session_turn_handler(
    session_id: str,
    request: AgentTurnRequest,
    user: AuthUser,
) -> CommonResponse[AgentTurnResponse]:
    try:
        events = await agent_runtime.submit_user_turn(
            session_id=session_id,
            content=request.content,
            user=user,
            sandbox_container_id=request.sandbox_container_id,
            requested_agent_code=request.agent_code,
        )
    except Exception as exc:
        error = _runtime_error_response(exc)
        if error is not None:
            return error
        raise
    return await _turn_response(session_id, user, events)


async def interrupt_agent_session_handler(session_id: str, user: AuthUser) -> CommonResponse[AgentTurnResponse]:
    try:
        events = await agent_runtime.interrupt_turn(session_id=session_id, user=user)
    except Exception as exc:
        error = _runtime_error_response(exc)
        if error is not None:
            return error
        raise
    return await _turn_response(session_id, user, events)


async def cancel_agent_session_tasks_handler(session_id: str, user: AuthUser) -> CommonResponse[AgentTurnResponse]:
    try:
        events = await agent_runtime.cancel_all_tasks(session_id=session_id, user=user)
    except Exception as exc:
        error = _runtime_error_response(exc)
        if error is not None:
            return error
        raise
    return await _turn_response(session_id, user, events)


async def delete_agent_session_handler(session_id: str, user: AuthUser) -> CommonResponse[None]:
    deleted = await agent_sessions.delete_session(
        session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if not deleted:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(message="agent session deleted")


async def update_agent_session_title_handler(
    session_id: str,
    request: UpdateAgentSessionTitleRequest,
    user: AuthUser,
) -> CommonResponse[AgentSessionSummarySchema]:
    session = await agent_sessions.update_session_title(
        session_id=session_id,
        title=request.title,
        user_id=user.id,
        user_role=user.role,
    )
    if session is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(message="agent session title updated", data=session)


async def update_agent_session_sandbox_container_handler(
    session_id: str,
    request: UpdateAgentSessionSandboxContainerRequest,
    user: AuthUser,
) -> CommonResponse[AgentSessionSummarySchema]:
    try:
        session = await agent_runtime.update_selected_sandbox_container(
            session_id=session_id,
            sandbox_container_id=request.sandbox_container_id,
            user=user,
        )
    except Exception as exc:
        error = _runtime_error_response(exc)
        if error is not None:
            return error
        raise
    return CommonResponse(message="sandbox container updated", data=session)


async def list_agent_sessions_handler(limit: int, user: AuthUser) -> CommonResponse[ListAgentSessionsResponse]:
    sessions = await agent_sessions.list_sessions(
        limit=limit,
        user_id=user.id,
        user_role=user.role,
    )
    return CommonResponse(data=ListAgentSessionsResponse(items=sessions))


async def list_agent_events_handler(
    session_id: str,
    user: AuthUser,
    before_seq: int | None = None,
    limit: int = agent_sessions.DEFAULT_REPLAY_EVENT_PAGE_SIZE,
) -> CommonResponse[ListAgentEventsResponse]:
    result = await agent_sessions.replay_session_events_page(
        session_id=session_id,
        user_id=user.id,
        user_role=user.role,
        before_seq=before_seq,
        limit=limit,
    )
    if result is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    events, has_more, next_before_seq = result
    return CommonResponse(data=ListAgentEventsResponse(
        session_id=session_id,
        items=events,
        has_more=has_more,
        next_before_seq=next_before_seq,
    ))


async def handle_agent_stream(websocket: WebSocket, session_id: str, token: str) -> None:
    user = authenticate_ws_token(token)
    if user is None:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return
    if not await agent_sessions.can_access_session(session_id, user.id, user.role):
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    session = None
    event_queue: asyncio.Queue[AgentEventSchema | None] | None = None
    reader: asyncio.Task | None = None
    forwarder: asyncio.Task | None = None

    try:
        session, event_queue = await get_agent_pool().subscribe(session_id)
        reader = asyncio.create_task(_consume_websocket(websocket), name=f"agent-stream-reader-{session_id}")
        forwarder = asyncio.create_task(_forward_events(
            websocket, event_queue, session_id, user,
        ), name=f"agent-stream-forwarder-{session_id}")
        done, _ = await asyncio.wait(
            {reader, forwarder},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("agent stream failed for session=%s", session_id)
        await _close_silently(websocket)
    finally:
        if session is not None and event_queue is not None:
            session.unsubscribe(event_queue)
        await _cancel_task(reader)
        await _cancel_task(forwarder)


async def _consume_websocket(websocket: WebSocket) -> None:
    while True:
        try:
            message = await websocket.receive()
        except RuntimeError as exc:
            if "disconnect message has been received" not in str(exc):
                raise
            return
        if message.get("type") == "websocket.disconnect":
            return


async def _send_event(
    websocket: WebSocket,
    event: AgentEventSchema,
) -> bool:
    if (
        websocket.client_state != WebSocketState.CONNECTED
        or websocket.application_state != WebSocketState.CONNECTED
    ):
        return False
    try:
        await websocket.send_text(event.model_dump_json())
        return True
    except Exception:
        logger.debug("failed to send agent event to websocket", exc_info=True)
        return False


_ACCESS_CHECK_INTERVAL = 50

async def _forward_events(
    websocket: WebSocket,
    queue: asyncio.Queue[AgentEventSchema | None],
    session_id: str,
    user: AuthUser,
) -> None:
    try:
        events_since_check = 0
        while True:
            event = await queue.get()
            if event is None:
                await _close_silently(websocket, code=ws_status.WS_1000_NORMAL_CLOSURE)
                return
            events_since_check += 1
            if events_since_check >= _ACCESS_CHECK_INTERVAL:
                events_since_check = 0
                if not await agent_sessions.can_access_session(session_id, user.id, user.role):
                    await _close_silently(websocket, code=ws_status.WS_1008_POLICY_VIOLATION)
                    return
            if not await _send_event(websocket, event):
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("agent event forwarding stopped", exc_info=True)


async def _turn_response(
    session_id: str,
    user: AuthUser,
    events: list[AgentEventSchema],
) -> CommonResponse[AgentTurnResponse]:
    summary = await agent_sessions.session_summary(
        session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if summary is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(data=AgentTurnResponse(session_id=session_id, session=summary, events=events))


def _runtime_error_response(exc: Exception) -> CommonResponse[Any] | None:
    if isinstance(exc, agent_runtime.SessionNotRunnableError):
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message="work project is canceled")
    if isinstance(exc, agent_runtime.SandboxContainerUnavailableError):
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=str(exc))
    if isinstance(exc, agent_runtime.AgentUnavailableError):
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=str(exc))
    if isinstance(exc, agent_runtime.SessionBusyError):
        return CommonResponse(code=HTTPStatus.CONFLICT.value, message=str(exc))
    if isinstance(exc, PermissionError):
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return None
