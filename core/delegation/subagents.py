"""Persistent background execution for delegated subagent tasks."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from agents import Agent, RunContextWrapper, Runner, Tool, function_tool

from config import get_config
from core.conversation.context_budget import build_context_run_config
from core.runtime.context import (
    SUBAGENT_INSTANCE_PREFIX,
    AgentRuntimeContext,
    subagent_instance_id,
)
from core.runtime.notification_dispatch import forget_target_notifications, is_main_agent_instance
from core.runtime.input_items import build_user_message_item, text_input_content
from core.runtime.partial_context import DeltaBuffer, discard_partial_stream, incomplete_segment_events, track_delta
from core.runtime.streaming import StreamIdleTimeout, next_segment_scope
from core.task_runtime import InterruptSignal, TurnTrigger, iter_interruptible_events, run_until_idle
from core.sandbox.command_jobs import cancel_agent_async_sandbox_commands
from core import extract_message_text
from core.conversation.store import XuanMuSession, fetch_stored_items
from database import get_async_session, get_engine
from logger import get_logger
from schema.agent.events import (
    AgentEventSchema,
    AgentInputPart,
    DoneEvent,
    ErrorEvent,
    SubagentTaskEvent,
    TextCompleteEvent,
    ThinkingCompleteEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from schema.agent.subordinates import (
    SUBAGENT_TASK_EVENT_PREVIEW_CHARS,
    SUBAGENT_TASK_RESULT_CHUNK_CHARS,
    AgentSubordinateTaskSnapshot,
    AgentSubordinateTaskToolItem,
    AgentSubordinateTaskToolResult,
)
from service.agent import notifications as agent_notifications
from service.agent import subordinates as agent_subordinates

if TYPE_CHECKING:
    # Type-only import: avoids a runtime cycle with core.agent.registry.
    from core.agent.registry import AgentRegistry, SessionAgentGraph


logger = get_logger(__name__)


@dataclass
class _SubagentDriver:
    # Resumable per-instance driver. ``task`` is the live drive (None while
    # dormant) and ``start_lock`` serialises launch/relaunch/cancel transitions.
    # ``graph`` is owned solely by this driver and closed at terminal state.
    snapshot: AgentSubordinateTaskSnapshot
    child_agent: Agent
    graph: "SessionAgentGraph"
    code_to_name: dict[str, str]
    context: AgentRuntimeContext
    start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task[None] | None = None
    relaunch_attempts: int = 0

    @property
    def run_id(self) -> str:
        return self.snapshot.run_id

    @property
    def session_id(self) -> str:
        return self.snapshot.session_id

    @property
    def agent_instance_id(self) -> str:
        return self.context.agent_instance_id

    @property
    def parent_agent_instance_id(self) -> str:
        return self.snapshot.parent_agent_instance_id

    @property
    def sandbox_container_id(self) -> int | None:
        return self.context.sandbox_container_id


_drivers: dict[str, _SubagentDriver] = {}
_session_starters: dict[str, set[asyncio.Task[AgentSubordinateTaskSnapshot]]] = defaultdict(set)
_drivers_lock = asyncio.Lock()

_CANCEL_MESSAGE = "Subagent task canceled."
# Hot-loop guard for self-relaunch after a claim race; on exhaustion the run fails.
_MAX_SUBAGENT_RELAUNCH = 5
_RELAUNCH_FAILURE_MESSAGE = "subagent driver could not make progress"


def build_subagent_tools(
    parent_code: str,
    mounted_codes: Iterable[str],
    *,
    registry: "AgentRegistry",
) -> list[Tool]:
    allowed = frozenset(mounted_codes)
    allowed_codes = ", ".join(sorted(allowed))

    async def start_subagent_task(ctx: RunContextWrapper[AgentRuntimeContext], agent_code: str, brief: str) -> str:
        """Start a configured subagent task in the background.

        Args:
            agent_code: str code of the configured subagent to run.
            brief: str self-contained task brief for the subagent.
                In WorkProject sessions, include the relevant task_id/task_title and instruct the subagent
                to update its WorkProject summary immediately after findings, useful negative results,
                blockers, decisions, or progress changes, before continuing to more tools when practical.

        Returns:
            JSON status including run_id, agent_code, status, timestamps, and automatic completion resume guidance.
        """
        code = agent_code.strip()
        if code not in allowed:
            return _tool_response(message=f"unknown subagent '{code}'. allowed: {allowed_codes}")
        body = brief.strip()
        if not body:
            return _tool_response(message="brief is required")

        starter = asyncio.create_task(
            start_subagent_task_run(
                registry=registry,
                context=ctx.context,
                parent_agent_code=parent_code,
                agent_code=code,
                brief=body,
                nested_call_id=getattr(ctx, "tool_call_id", "") or "",
            ),
            name=f"subagent-starter-{code}",
        )
        await _track_subagent_starter(ctx.context.session_id, starter)
        try:
            snapshot = await asyncio.shield(starter)
        except asyncio.CancelledError:
            starter.add_done_callback(_log_subagent_start_result)
            raise
        return _tool_response(
            task=snapshot,
            message=(
                "subagent task started; end this turn now. The task will resume automatically when "
                "the subagent finishes. Use read/list/cancel only if the user later asks for progress, "
                "task history, or cancellation."
            ),
        )

    async def read_subagent_task(
        ctx: RunContextWrapper[AgentRuntimeContext],
        run_id: str,
        offset: int = 0,
    ) -> str:
        """Read the latest state of a subagent task in the current session.

        Args:
            run_id: str subagent run id returned by start_subagent_task or list_subagent_tasks.
            offset: int starting position into the task's result/error (default 0).
                Repeat with ``offset=next_offset`` until the response omits ``next_offset``
                to read the full body.

        Returns:
            JSON status with the task status, progress, the requested slice of result/error,
            total sizes (``result_chars``/``error_chars``), and ``next_offset`` (the field is
            omitted once the body is fully read).
        """
        snapshot = await _resolve_task(ctx, run_id)
        if snapshot is None:
            return _tool_response(message="subagent task not found")
        return _tool_response(task=snapshot, offset=offset)

    async def list_subagent_tasks(ctx: RunContextWrapper[AgentRuntimeContext], limit: int = 20) -> str:
        """List recent subagent tasks visible to the current session user.

        Args:
            limit: int maximum number of recent subagent tasks to return.

        Returns:
            JSON status with recent task snapshots including run id, agent code, status, progress, and timestamps.
        """
        tasks = await agent_subordinates.list_subagent_tasks(
            session_id=ctx.context.session_id,
            user_id=ctx.context.user.id,
            user_role=ctx.context.user.role,
            limit=limit,
        )
        return _tool_response(tasks=tasks)

    async def cancel_subagent_task(ctx: RunContextWrapper[AgentRuntimeContext], run_id: str) -> str:
        """Request cancellation for a running subagent task in the current session.

        Args:
            run_id: str subagent run id returned by start_subagent_task or list_subagent_tasks.

        Returns:
            JSON status with the latest task state after cancellation is requested.
        """
        snapshot = await _resolve_task(ctx, run_id)
        if snapshot is None:
            return _tool_response(message="subagent task not found")
        latest = await cancel_subagent_task_run(snapshot)
        return _tool_response(task=latest, message="subagent task cancel requested")

    tools = [
        function_tool(
            start_subagent_task,
            name_override="start_subagent_task",
            description_override=(
                "Start a configured subagent task.\n\n"
                "Args:\n"
                f"    agent_code: str subagent code, one of {allowed_codes}.\n"
                "    brief: str self-contained task brief with objective, constraints, expected output, and relevant context.\n\n"
                "Returns:\n"
                "    JSON status with a persistent run id. This agent is resumed automatically after the subagent finishes. "
                "For WorkProject tasks, include task_id/task_title and require summary/progress updates after "
                "findings, blockers, decisions, or progress changes."
            ),
        ),
        function_tool(
            read_subagent_task,
            name_override="read_subagent_task",
            description_override=(
                "Read a subagent task in the current session.\n\n"
                "Args:\n"
                "    run_id: str persistent subagent run id returned by start_subagent_task or list_subagent_tasks.\n"
                "    offset: int starting character offset into result/error, default 0.\n\n"
                "Returns:\n"
                "    JSON status with progress, requested result/error slice, total sizes, and optional next_offset. "
                "Repeat with offset=next_offset until the response omits next_offset."
            ),
        ),
        function_tool(
            list_subagent_tasks,
            name_override="list_subagent_tasks",
            description_override=(
                "List recent subagent tasks visible in the current session.\n\n"
                "Args:\n"
                "    limit: int maximum number of recent tasks to return.\n\n"
                "Returns:\n"
                "    JSON status with task snapshots containing run id, agent code, status, progress, and timestamps."
            ),
        ),
        function_tool(
            cancel_subagent_task,
            name_override="cancel_subagent_task",
            description_override=(
                "Request cancellation for a subagent task.\n\n"
                "Args:\n"
                "    run_id: str persistent subagent run id returned by start_subagent_task or list_subagent_tasks.\n\n"
                "Returns:\n"
                "    JSON status with the latest task state after cancellation is requested."
            ),
        ),
    ]
    return tools


async def _resolve_task(ctx: RunContextWrapper[AgentRuntimeContext], run_id: str) -> AgentSubordinateTaskSnapshot | None:
    return await agent_subordinates.get_subagent_task(
        run_id=run_id.strip(),
        session_id=ctx.context.session_id,
        user_id=ctx.context.user.id,
        user_role=ctx.context.user.role,
    )


def _tool_response(
    task: AgentSubordinateTaskSnapshot | None = None,
    tasks: list[AgentSubordinateTaskSnapshot] | None = None,
    message: str = "",
    *,
    offset: int = 0,
) -> str:
    return AgentSubordinateTaskToolResult(
        task=_task_tool_item(task, offset=offset, include_body=True),
        tasks=[_task_tool_item(item, include_body=False) for item in tasks or []],
        message=message,
    ).model_dump_json(
        exclude_none=True,
        exclude_defaults=True,
    )


def _task_tool_item(
    snapshot: AgentSubordinateTaskSnapshot | None,
    *,
    offset: int = 0,
    include_body: bool,
) -> AgentSubordinateTaskToolItem | None:
    if snapshot is None:
        return None
    if include_body:
        # Result and error are mutually exclusive across terminal statuses, so a
        # single offset / next_offset pointer is unambiguous.
        result, result_next = _slice_chunk(snapshot.result, offset)
        error, error_next = _slice_chunk(snapshot.error, offset)
        next_offset = result_next if result_next is not None else error_next
    else:
        result, error, next_offset = "", "", None
    return AgentSubordinateTaskToolItem(
        run_id=snapshot.run_id,
        agent_code=snapshot.agent_code,
        agent_name=snapshot.agent_name,
        status=snapshot.status,
        result=result,
        error=error,
        result_chars=len(snapshot.result),
        error_chars=len(snapshot.error),
        next_offset=next_offset,
        progress=snapshot.progress,
    )


def _slice_chunk(value: str, offset: int) -> tuple[str, int | None]:
    """Return a fixed-size chunk starting at ``offset`` and the next pagination offset.

    ``next_offset`` is ``None`` once the value is fully consumed (EOF or empty body).
    """
    start = max(offset, 0)
    if start >= len(value):
        return "", None
    end = min(start + SUBAGENT_TASK_RESULT_CHUNK_CHARS, len(value))
    return value[start:end], end if end < len(value) else None


def _event_preview(value: str) -> tuple[str, bool]:
    """UI-event preview: short slice + ``truncated`` flag for the frontend timeline."""
    if len(value) <= SUBAGENT_TASK_EVENT_PREVIEW_CHARS:
        return value, False
    return value[:SUBAGENT_TASK_EVENT_PREVIEW_CHARS], True


def _log_subagent_start_result(task: asyncio.Task[AgentSubordinateTaskSnapshot]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("subagent task starter was canceled before scheduling completed")
    except Exception:
        logger.exception("subagent task starter failed after parent turn cancellation")


async def start_subagent_task_run(
    *,
    registry: "AgentRegistry",
    context: AgentRuntimeContext,
    parent_agent_code: str,
    agent_code: str,
    brief: str,
    nested_call_id: str,
) -> AgentSubordinateTaskSnapshot:
    # Each driver owns a dedicated graph (Agent + httpx client) bound from the
    # current snapshot, so churn elsewhere can't kill this sub-agent's stream.
    from core.agent.registry import AgentToolSnapshot

    own_graph = registry.bind(AgentToolSnapshot.from_context(context))
    try:
        child_agent = own_graph.get(agent_code)
        code_to_name = registry.code_to_name()
        snapshot = await agent_subordinates.create_subagent_task(
            session_id=context.session_id,
            parent_agent_code=parent_agent_code,
            parent_agent_instance_id=context.agent_instance_id,
            agent_code=agent_code,
            agent_name=code_to_name.get(agent_code, child_agent.name),
            brief=brief,
            nested_call_id=nested_call_id,
            owner_id=context.user.id,
            sandbox_container_id=context.sandbox_container_id,
            sandbox_container_generation=context.sandbox_container_generation,
            sandbox_skill_metadata=context.sandbox_skill_metadata,
        )
        await _mark_parent_session_running(snapshot, context)
        driver = _SubagentDriver(
            snapshot=snapshot,
            child_agent=child_agent,
            graph=own_graph,
            code_to_name=code_to_name,
            context=_subagent_context(context, snapshot, agent_code),
        )
        # Spawn + register atomically: peers only ever see a populated ``task``.
        async with _drivers_lock:
            driver.task = _spawn_subagent_drive(driver, text_input_content(snapshot.brief))
            _drivers[snapshot.run_id] = driver
    except BaseException:
        # Pre-registration failure: graph hasn't been handed off yet.
        await _safe_close_graph(own_graph)
        raise

    await _publish_task_snapshot(snapshot)
    logger.info("subagent task scheduled: %s agent=%s", snapshot.run_id, agent_code)
    return snapshot


async def _safe_close_graph(graph: "SessionAgentGraph") -> None:
    try:
        await graph.close()
    except Exception:
        logger.exception("failed to dispose subagent graph")


def _spawn_subagent_drive(
    driver: _SubagentDriver,
    initial_content: list[AgentInputPart] | None,
) -> asyncio.Task[None]:
    return asyncio.create_task(
        _drive_subagent(driver, initial_content),
        name=f"subagent-{driver.snapshot.agent_code}-{driver.run_id}",
    )


async def cancel_subagent_task_run(snapshot: AgentSubordinateTaskSnapshot) -> AgentSubordinateTaskSnapshot:
    async with _drivers_lock:
        driver = _drivers.get(snapshot.run_id)
    if driver is not None:
        task = await _stop_driver_task(driver)
        if task is not None:
            # Live drive handles teardown in its own except path.
            await asyncio.gather(task, return_exceptions=True)
            return await _latest_snapshot(snapshot)
        # Dormant: no live task, so run teardown directly.
        await _cancel_subagent(driver)
        return await _latest_snapshot(snapshot)

    latest = await agent_subordinates.cancel_subagent_task_record(snapshot.run_id, _CANCEL_MESSAGE)
    snapshot = latest or snapshot
    await _publish_task_snapshot(snapshot)
    return snapshot


async def _stop_driver_task(driver: _SubagentDriver) -> asyncio.Task[None] | None:
    """Cancel the driver's live drive task, if any. Returns the task to await."""
    async with driver.start_lock:
        task = driver.task
        if task is not None and not task.done():
            task.cancel()
            return task
    return None


async def _latest_snapshot(snapshot: AgentSubordinateTaskSnapshot) -> AgentSubordinateTaskSnapshot:
    latest = await agent_subordinates.get_subagent_task_internal(snapshot.run_id)
    return latest or snapshot


async def cancel_sandbox_subagent_runs(container_id: int) -> bool:
    return await _cancel_drivers(lambda driver: driver.sandbox_container_id == container_id)


async def cancel_session_subagent_runs(session_id: str) -> bool:
    starter_tasks = await _cancel_session_starters(session_id)
    if starter_tasks:
        await asyncio.gather(*starter_tasks, return_exceptions=True)
    drivers_canceled = await _cancel_drivers(lambda driver: driver.session_id == session_id)

    snapshots = await agent_subordinates.cancel_running_subagent_tasks_for_session(
        session_id,
        _CANCEL_MESSAGE,
    )
    for snapshot in snapshots:
        await _publish_task_snapshot(snapshot)

    return bool(starter_tasks) or drivers_canceled or bool(snapshots)


async def _cancel_drivers(predicate: Callable[[_SubagentDriver], bool]) -> bool:
    """Cancel matching drivers (live via their except path, dormant inline)."""
    async with _drivers_lock:
        matched = [driver for driver in _drivers.values() if predicate(driver)]
    if not matched:
        return False
    live: list[asyncio.Task[None]] = []
    dormant: list[_SubagentDriver] = []
    for driver in matched:
        task = await _stop_driver_task(driver)
        if task is not None:
            live.append(task)
        else:
            dormant.append(driver)
    if live:
        await asyncio.gather(*live, return_exceptions=True)
    for driver in dormant:
        await _cancel_subagent(driver)
    return True


async def _track_subagent_starter(session_id: str, task: asyncio.Task[AgentSubordinateTaskSnapshot]) -> None:
    async with _drivers_lock:
        _session_starters[session_id].add(task)

    def _forget_starter(completed: asyncio.Task[AgentSubordinateTaskSnapshot]) -> None:
        starters = _session_starters.get(session_id)
        if starters is None:
            return
        starters.discard(completed)
        if not starters:
            _session_starters.pop(session_id, None)

    task.add_done_callback(_forget_starter)


async def _cancel_session_starters(session_id: str) -> list[asyncio.Task[AgentSubordinateTaskSnapshot]]:
    async with _drivers_lock:
        starters = list(_session_starters.pop(session_id, ()))
    pending = [task for task in starters if not task.done()]
    for task in pending:
        task.cancel()
    return pending


async def start_subagent_runtime() -> None:
    await agent_notifications.reset_processing_notifications_all()
    # Failing a stale task flips its parent obligation to PENDING atomically;
    # only the dead sub-agent's own obligations need clearing here.
    stale_snapshots = await agent_subordinates.mark_stale_running_subagent_tasks_failed()
    for snapshot in stale_snapshots:
        await agent_notifications.cancel_session_notifications(
            snapshot.session_id,
            snapshot.error,
            target_agent_instance_id=subagent_instance_id(snapshot.run_id),
        )


async def stop_subagent_runtime() -> None:
    async with _drivers_lock:
        starter_tasks = [task for tasks in _session_starters.values() for task in tasks if not task.done()]
        _session_starters.clear()
        driver_tasks = [driver.task for driver in _drivers.values() if driver.task is not None]
        _drivers.clear()
    for task in (*starter_tasks, *driver_tasks):
        if not task.done():
            task.cancel()
    await asyncio.gather(*starter_tasks, *driver_tasks, return_exceptions=True)

    snapshots = await agent_subordinates.cancel_running_subagent_tasks(_CANCEL_MESSAGE)
    for snapshot in snapshots:
        await _publish_task_snapshot(snapshot)


def _publish_event(session_id: str, event: AgentEventSchema) -> None:
    """Publish an event through the unified session event bus."""
    from core.runtime.session import get_agent_pool

    get_agent_pool().publish(session_id, event)


async def _publish_task_snapshot(snapshot: AgentSubordinateTaskSnapshot) -> None:
    from core.runtime.session import get_agent_pool

    event = _task_event(snapshot)
    if not get_agent_pool().publish(snapshot.session_id, event):
        # No pooled session (e.g. boot-time stale failure): persist directly.
        from service.agent.event_log import persist_subagent_event_unpooled

        await persist_subagent_event_unpooled(snapshot.session_id, event)


async def resume_target_instance(session_id: str, agent_instance_id: str) -> None:
    """Wake the owner's driver after a background task flips its obligation to PENDING."""
    if not agent_instance_id:
        return
    if is_main_agent_instance(agent_instance_id):
        from core.runtime.session import get_agent_pool

        await get_agent_pool().resume_session(session_id)
        return
    await resume_subagent_instance(agent_instance_id.removeprefix(SUBAGENT_INSTANCE_PREFIX))


async def resume_subagent_instance(run_id: str) -> None:
    """Relaunch a dormant sub-agent driver so it claims freshly-pending work."""
    async with _drivers_lock:
        driver = _drivers.get(run_id)
    if driver is None:
        return
    async with driver.start_lock:
        if driver.task is not None and not driver.task.done():
            return
        driver.task = _spawn_subagent_drive(driver, None)


async def _drive_subagent(
    driver: _SubagentDriver,
    initial_content: list[AgentInputPart] | None,
) -> None:
    """Drain ready turns then settle (relaunch / dormant / complete)."""
    try:
        await run_until_idle(
            session_id=driver.session_id,
            agent_instance_id=driver.agent_instance_id,
            initial_content=initial_content,
            run_turn=_subagent_run_turn(driver),
        )
        # Settle inside the guard so a late cancel still terminalises the record.
        await _settle_subagent(driver)
    except asyncio.CancelledError:
        await _cancel_subagent(driver)
        raise
    except Exception as exc:
        logger.exception("subagent drive failed: %s", driver.run_id)
        await _fail_subagent(driver, str(exc) or "subagent failed")


async def _settle_subagent(driver: _SubagentDriver) -> None:
    """Post-drain fate: relaunch on claim race, go dormant if children run, else finish."""
    inst = driver.agent_instance_id
    async with driver.start_lock:
        if await agent_notifications.has_pending_notification(
            session_id=driver.session_id, target_agent_instance_id=inst,
        ):
            driver.relaunch_attempts += 1
            if driver.relaunch_attempts > _MAX_SUBAGENT_RELAUNCH:
                logger.error("subagent driver relaunch budget exhausted run=%s", driver.run_id)
                driver.task = asyncio.create_task(
                    _fail_subagent(driver, _RELAUNCH_FAILURE_MESSAGE),
                    name=f"subagent-fail-{driver.run_id}",
                )
                return
            driver.task = _spawn_subagent_drive(driver, None)
            return
        if await agent_notifications.has_outstanding_target_notifications(
            session_id=driver.session_id, target_agent_instance_id=inst,
        ):
            # Dormant: children/jobs still running will kick us back on completion.
            driver.relaunch_attempts = 0
            driver.task = None
            return
    await _complete_subagent(driver)


def _subagent_run_turn(driver: _SubagentDriver) -> Callable[[TurnTrigger], Any]:
    """Build a turn executor bound to this driver's agent and memory session."""
    snapshot = driver.snapshot
    child_agent = driver.child_agent
    context = driver.context
    agent_config = get_config().agents.get(snapshot.agent_code)
    max_turns = get_config().agent_runtime.subordinate_max_turns
    memory_session = XuanMuSession(
        session_id=snapshot.session_id,
        engine=get_engine(),
        viewing_agent_code=snapshot.agent_code,
        agent_code_to_name=driver.code_to_name,
        nested_for_agent_code=snapshot.parent_agent_code,
        nested_call_id=snapshot.nested_call_id,
    )

    async def _run_turn(trigger: TurnTrigger) -> Any:
        user_input = [build_user_message_item(trigger.content)]
        if agent_config is not None:
            await memory_session.compact_if_needed(agent_config=agent_config, incoming_items=user_input)
        stream = Runner.run_streamed(
            starting_agent=child_agent,
            input=user_input,
            session=memory_session,
            context=context,
            max_turns=max_turns,
            run_config=build_context_run_config(agent_config) if agent_config is not None else None,
        )
        buffers: dict[str, DeltaBuffer] = {}
        try:
            async for event in iter_interruptible_events(
                stream,
                session_id=snapshot.session_id,
                agent_instance_id=context.agent_instance_id,
                current_agent_name=child_agent.name,
                segment_scope=_next_subagent_segment_scope(context),
            ):
                track_delta(buffers, event)
                _publish_event(snapshot.session_id, _tag_nested(event, snapshot))
                await _update_progress_from_event(snapshot, event)
            # Finalize segments left open by providers that omit text-done events.
            for finalize_event in incomplete_segment_events(buffers, agent_name=child_agent.name):
                _publish_event(snapshot.session_id, _tag_nested(finalize_event, snapshot))
            buffers.clear()
        except (InterruptSignal, asyncio.CancelledError):
            # Mid-flight end: emit boundary + done so the parent finalises cleanly.
            boundary_events = incomplete_segment_events(buffers, agent_name=child_agent.name)
            await discard_partial_stream(stream, buffers, log_label="subagent")
            for evt in boundary_events:
                _publish_event(snapshot.session_id, _tag_nested(evt, snapshot))
            _publish_event(snapshot.session_id, _tag_nested(
                DoneEvent(created_at=datetime.now(), agent_name=child_agent.name), snapshot,
            ))
            raise
        except StreamIdleTimeout as exc:
            await discard_partial_stream(stream, buffers, log_label="subagent")
            raise RuntimeError(str(exc)) from exc
        except Exception:
            await discard_partial_stream(stream, buffers, log_label="subagent")
            raise
        return stream

    return _run_turn


async def _complete_subagent(driver: _SubagentDriver) -> None:
    """Commit completion + flip parent obligation atomically, then kick the parent."""
    output = await _subagent_assistant_output(driver.snapshot)
    completed = await agent_subordinates.complete_subagent_task(driver.run_id, output)
    if completed is not None:
        await _publish_task_snapshot(completed)
        await resume_target_instance(driver.session_id, driver.parent_agent_instance_id)
    await _cleanup_subagent(driver)


async def _fail_subagent(driver: _SubagentDriver, message: str) -> None:
    _publish_event(driver.session_id, _tag_nested(
        ErrorEvent(created_at=datetime.now(), agent_name=driver.child_agent.name, message=f"Subagent failed: {message}"),
        driver.snapshot,
    ))
    await _teardown_subtree(driver, message)
    failed = await agent_subordinates.fail_subagent_task(driver.run_id, message)
    if failed is not None:
        await _publish_task_snapshot(failed)
        await resume_target_instance(driver.session_id, driver.parent_agent_instance_id)
    await _cleanup_subagent(driver)


async def _cancel_subagent(driver: _SubagentDriver) -> None:
    await _teardown_subtree(driver, _CANCEL_MESSAGE)
    canceled = await agent_subordinates.cancel_subagent_task_record(driver.run_id, _CANCEL_MESSAGE)
    if canceled is not None:
        await _publish_task_snapshot(canceled)
    # CANCELED resolves silently; still kick so dormant/idle parents re-evaluate.
    await resume_target_instance(driver.session_id, driver.parent_agent_instance_id)
    await _cleanup_subagent(driver)


async def _teardown_subtree(driver: _SubagentDriver, message: str) -> None:
    """Cancel a sub-agent's owned background work (async jobs + child sub-agents)."""
    await cancel_agent_async_sandbox_commands(
        session_id=driver.session_id, agent_instance_id=driver.agent_instance_id,
    )
    await agent_notifications.cancel_session_notifications(
        driver.session_id, message, target_agent_instance_id=driver.agent_instance_id,
    )
    await _cancel_child_subagent_runs(driver.session_id, driver.agent_instance_id, message)


async def _cleanup_subagent(driver: _SubagentDriver) -> None:
    """Drop terminal in-memory state (signals + driver registry + owned graph)."""
    await forget_target_notifications(driver.agent_instance_id)
    async with _drivers_lock:
        if _drivers.get(driver.run_id) is driver:
            _drivers.pop(driver.run_id, None)
    # Only here, at terminal state, does the driver's httpx client get closed.
    await _safe_close_graph(driver.graph)


def _next_subagent_segment_scope(context: AgentRuntimeContext) -> str:
    owner = context.agent_instance_id or context.agent_code or "subagent"
    return next_segment_scope(owner)


async def _cancel_child_subagent_runs(session_id: str, parent_agent_instance_id: str, error: str) -> None:
    await _cancel_drivers(
        lambda driver: driver.session_id == session_id
        and driver.parent_agent_instance_id == parent_agent_instance_id
    )
    snapshots = await agent_subordinates.cancel_running_child_subagent_tasks(
        session_id=session_id,
        parent_agent_instance_id=parent_agent_instance_id,
        error=error,
    )
    for snapshot in snapshots:
        await _publish_task_snapshot(snapshot)


async def _update_progress_from_event(snapshot: AgentSubordinateTaskSnapshot, event: AgentEventSchema) -> None:
    progress = _progress_from_event(event)
    if not progress:
        return
    latest = await agent_subordinates.update_subagent_progress(snapshot.run_id, progress)
    if latest is not None:
        _publish_event(latest.session_id, _task_event(latest))


def _progress_from_event(event: AgentEventSchema) -> str:
    if isinstance(event, ToolCallEvent):
        return f"calling tool: {event.name or event.call_id}"
    if isinstance(event, ToolResultEvent):
        return "tool completed"
    if isinstance(event, TextCompleteEvent):
        return "reported output"
    if isinstance(event, ThinkingCompleteEvent):
        return "completed reasoning"
    return ""


def _task_event(snapshot: AgentSubordinateTaskSnapshot) -> AgentEventSchema:
    result_preview, result_truncated = _event_preview(snapshot.result)
    error_preview, error_truncated = _event_preview(snapshot.error)
    return SubagentTaskEvent(
        created_at=snapshot.updated_at,
        agent_name=snapshot.agent_name,
        nested_for=snapshot.parent_agent_code,
        nested_call_id=snapshot.nested_call_id,
        run_id=snapshot.run_id,
        parent_agent_code=snapshot.parent_agent_code,
        parent_agent_instance_id=snapshot.parent_agent_instance_id,
        agent_code=snapshot.agent_code,
        status=snapshot.status,
        result_preview=result_preview,
        error_preview=error_preview,
        result_chars=len(snapshot.result),
        error_chars=len(snapshot.error),
        truncated=result_truncated or error_truncated,
        progress=snapshot.progress,
    )


def _tag_nested(event: AgentEventSchema, snapshot: AgentSubordinateTaskSnapshot) -> AgentEventSchema:
    if not hasattr(event, "nested_for"):
        return event
    return event.model_copy(update={
        "nested_for": snapshot.parent_agent_code,
        "nested_call_id": snapshot.nested_call_id,
    })


async def _mark_parent_session_running(
    snapshot: AgentSubordinateTaskSnapshot,
    context: AgentRuntimeContext,
) -> None:
    try:
        from service.agent import sessions as agent_sessions

        await agent_sessions.mark_session_running(
            snapshot.session_id,
            agent_code=snapshot.parent_agent_code,
            sandbox_container_id=context.sandbox_container_id,
            sandbox_container_generation=context.sandbox_container_generation,
        )
    except Exception:
        logger.debug("failed to mark parent session running: %s", snapshot.session_id, exc_info=True)


def _subagent_context(
    context: AgentRuntimeContext,
    snapshot: AgentSubordinateTaskSnapshot,
    agent_code: str,
) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        session_id=context.session_id,
        user=context.user,
        agent_code=agent_code,
        agent_instance_id=subagent_instance_id(snapshot.run_id),
        nested_for_agent_code=snapshot.parent_agent_code,
        nested_call_id=snapshot.nested_call_id,
        knowledge_generation=context.knowledge_generation,
        sandbox_container_id=context.sandbox_container_id,
        sandbox_container_generation=context.sandbox_container_generation,
        sandbox_skill_metadata=context.sandbox_skill_metadata,
        work_project_id=context.work_project_id,
    )


async def _subagent_assistant_output(snapshot: AgentSubordinateTaskSnapshot) -> str:
    async with get_async_session() as sess:
        stored_items = await fetch_stored_items(sess, snapshot.session_id)

    sections: list[str] = []
    for stored in stored_items:
        if (
            stored.owner_code != snapshot.agent_code
            or stored.nested_for != snapshot.parent_agent_code
            or stored.nested_call_id != snapshot.nested_call_id
        ):
            continue
        text = _assistant_message_text(stored.item)
        if text:
            sections.append(text)
    return "\n\n".join(sections).strip()


def _assistant_message_text(item: dict[str, Any]) -> str:
    if item.get("type") == "message" and item.get("role") == "assistant":
        return extract_message_text(item.get("content")).strip()
    return ""
