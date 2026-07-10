from fastapi import APIRouter, Depends, Query, WebSocket

from handler.agent.sessions import (
    cancel_agent_session_tasks_handler,
    create_agent_session_turn_handler,
    delete_agent_session_handler,
    handle_agent_stream,
    interrupt_agent_session_handler,
    list_agent_events_handler,
    list_agent_sessions_handler,
    submit_agent_session_turn_handler,
    update_agent_session_sandbox_container_handler,
    update_agent_session_title_handler,
)
from middleware.auth import AuthUser, require_user
from router.common.responses import COMMON_ERROR_RESPONSES, not_found_response
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


# the websocket route does its own token check because browsers cannot attach
# custom auth headers to native WebSocket upgrades, so http auth is added per-route here
# rather than at router scope
router = APIRouter(prefix="/agent-sessions", tags=["agent-sessions"])

async def list_agent_sessions_route(
    limit: int = Query(default=100, ge=1, le=100),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListAgentSessionsResponse]:
    return await list_agent_sessions_handler(limit=limit, user=user)


async def create_agent_session_turn_route(
    request: AgentTurnRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[AgentTurnResponse]:
    return await create_agent_session_turn_handler(request=request, user=user)


async def submit_agent_session_turn_route(
    session_id: str,
    request: AgentTurnRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[AgentTurnResponse]:
    return await submit_agent_session_turn_handler(
        session_id=session_id,
        request=request,
        user=user,
    )


async def interrupt_agent_session_route(
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[AgentTurnResponse]:
    return await interrupt_agent_session_handler(session_id=session_id, user=user)


async def cancel_agent_session_tasks_route(
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[AgentTurnResponse]:
    return await cancel_agent_session_tasks_handler(session_id=session_id, user=user)


async def delete_agent_session_route(
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await delete_agent_session_handler(session_id=session_id, user=user)


async def update_agent_session_title_route(
    session_id: str,
    request: UpdateAgentSessionTitleRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await update_agent_session_title_handler(session_id=session_id, request=request, user=user)


async def update_agent_session_sandbox_container_route(
    session_id: str,
    request: UpdateAgentSessionSandboxContainerRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await update_agent_session_sandbox_container_handler(session_id=session_id, request=request, user=user)


async def list_agent_events_route(
    session_id: str,
    before_seq: int | None = Query(default=None, ge=1),
    limit: int = Query(default=80, ge=1, le=200),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListAgentEventsResponse]:
    return await list_agent_events_handler(
        session_id=session_id,
        user=user,
        before_seq=before_seq,
        limit=limit,
    )


router.add_api_route(
    "",
    list_agent_sessions_route,
    methods=["GET"],
    response_model=CommonResponse[ListAgentSessionsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{session_id}/events",
    list_agent_events_route,
    methods=["GET"],
    response_model=CommonResponse[ListAgentEventsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/turns",
    create_agent_session_turn_route,
    methods=["POST"],
    response_model=CommonResponse[AgentTurnResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{session_id}/turns",
    submit_agent_session_turn_route,
    methods=["POST"],
    response_model=CommonResponse[AgentTurnResponse],
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)

router.add_api_route(
    "/{session_id}/interrupt",
    interrupt_agent_session_route,
    methods=["POST"],
    response_model=CommonResponse[AgentTurnResponse],
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)

router.add_api_route(
    "/{session_id}/cancel-all",
    cancel_agent_session_tasks_route,
    methods=["POST"],
    response_model=CommonResponse[AgentTurnResponse],
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)

router.add_api_route(
    "/{session_id}/title",
    update_agent_session_title_route,
    methods=["PATCH"],
    response_model=CommonResponse[AgentSessionSummarySchema],
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)

router.add_api_route(
    "/{session_id}/sandbox-container",
    update_agent_session_sandbox_container_route,
    methods=["PATCH"],
    response_model=CommonResponse[AgentSessionSummarySchema],
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)

router.add_api_route(
    "/{session_id}",
    delete_agent_session_route,
    methods=["DELETE"],
    response_model=CommonResponse,
    responses={**COMMON_ERROR_RESPONSES, **not_found_response("Agent session")},
)


@router.websocket("/{session_id}/stream")
async def agent_session_stream(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(default=""),
) -> None:
    await handle_agent_stream(websocket=websocket, session_id=session_id, token=token)
