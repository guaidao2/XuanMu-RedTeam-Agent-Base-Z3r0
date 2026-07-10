"""Per-conversation Agent runtime: turn execution and pool lifecycle."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agents import Runner

from config import get_config
from core.agent.registry import AgentRegistry, AgentToolSnapshot, SessionAgentGraph
from core.conversation.context_budget import build_context_run_config
from core.runtime.context import AgentRuntimeContext, main_agent_instance_id
from core.runtime.input_items import build_user_message_item, display_text_from_content
from core.runtime.live_projection import LiveEventProjection
from core.runtime.timeline import TimelineLogWriter, is_persistable, timeline_item_key
from core.runtime.notification_dispatch import signal_target_notifications
from core.runtime.partial_context import DeltaBuffer, discard_partial_stream, incomplete_segment_events, track_delta
from core.runtime.streaming import StreamIdleTimeout, next_segment_scope
from core.task_runtime import InterruptSignal, TurnTrigger, iter_interruptible_events, replace_trigger, run_until_idle
from core.conversation.store import XuanMuSession
from core.delegation.subagents import cancel_sandbox_subagent_runs, cancel_session_subagent_runs
from core.sandbox.command_jobs import cancel_sandbox_async_commands, cancel_session_async_sandbox_commands
from database import get_engine
from logger import get_logger
from schema.agent.events import (
    AgentEventSchema,
    AgentInputPart,
    DoneEvent,
    ErrorEvent,
    RunStateEvent,
    TurnBoundaryEvent,
    UserMessageEvent,
)
from schema.agent.notifications import AgentNotificationSnapshot
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)

_SUBSCRIBER_REBASE_THRESHOLD = 512
# Self-heal bound: how many times a driver may relaunch itself to drain
# outstanding work after an abnormal loop exit before it gives up and cancels
# the remaining work (prevents a hot relaunch loop on a persistent fault).
_MAX_DRIVER_RELAUNCH = 5
_DRIVER_RELAUNCH_BACKOFF_SECONDS = 0.5
_SubscriberQueue = asyncio.Queue[AgentEventSchema | None]


class AgentSession:
    def __init__(self, session_id: str, registry: AgentRegistry) -> None:
        self.session_id = session_id
        self._registry = registry
        self._start_lock = asyncio.Lock()
        self._turn_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self._subscribers: set[_SubscriberQueue] = set()
        self._live_projection = LiveEventProjection()
        # per-session timeline log: monotonic seq counter + first-seen key map
        self._seq: int = 0
        self._item_seq: dict[str, int] = {}
        self._timeline_loaded = False
        self._log_writer = TimelineLogWriter(session_id)
        self._main_agent_code: str = ""
        self._tool_snapshot: AgentToolSnapshot | None = None
        self._agent_graph: SessionAgentGraph | None = None

    def is_running(self) -> bool:
        task = self._current_task
        return task is not None and not task.done()

    @property
    def timeline_loaded(self) -> bool:
        return self._timeline_loaded

    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    async def subscribe(
        self,
        include: Callable[[AgentEventSchema], bool] | None = None,
    ) -> _SubscriberQueue:
        snapshot = self._live_projection.snapshot(include)
        queue: _SubscriberQueue = asyncio.Queue()
        for event in snapshot:
            queue.put_nowait(event)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: _SubscriberQueue) -> None:
        self._subscribers.discard(queue)

    async def start_turn(
        self,
        content: list[AgentInputPart],
        agent_code: str,
        context: AgentRuntimeContext,
    ) -> list[AgentEventSchema]:
        async with self._start_lock:
            if self.is_running():
                return await self._enqueue_user_message(content, agent_code, context)
            await _mark_session_running(
                self.session_id,
                agent_code=agent_code,
                sandbox_container_id=context.sandbox_container_id,
                sandbox_container_generation=context.sandbox_container_generation,
            )
            await self._ensure_timeline_loaded()
            events: list[AgentEventSchema] = [self._publish_run_state(True)]
            events.append(await self._publish(UserMessageEvent(
                created_at=datetime.now(),
                content=content,
                display_text=display_text_from_content(content),
                target_agent_code=agent_code,
            )))
            task = asyncio.create_task(
                self._drive(content, agent_code, context, initial_user_event_published=True),
                name=f"agent-turn-{self.session_id}",
            )
            self._current_task = task
            return events

    async def _enqueue_user_message(
        self,
        content: list[AgentInputPart],
        agent_code: str,
        context: AgentRuntimeContext,
    ) -> list[AgentEventSchema]:
        # Queue a high-priority notification (instead of interrupting) so the
        # running loop preempts at its next safe point without losing state.
        target_instance = context.agent_instance_id or main_agent_instance_id(
            context.session_id, context.user.id, agent_code,
        )
        display_text = display_text_from_content(content)
        serialized_content = [part.model_dump() for part in content]
        await agent_notifications.enqueue_user_message_notification(
            session_id=self.session_id,
            target_agent_code=agent_code,
            target_agent_instance_id=target_instance,
            user_content=serialized_content,
            user_display_text=display_text,
            user_requested_agent_code=agent_code,
            sandbox_container_id=context.sandbox_container_id,
            sandbox_container_generation=context.sandbox_container_generation,
            sandbox_skill_metadata=context.sandbox_skill_metadata,
        )
        await signal_target_notifications(target_instance)
        event = await self._publish(UserMessageEvent(
            created_at=datetime.now(),
            content=content,
            display_text=display_text,
            target_agent_code=agent_code,
        ))
        return [event]

    async def start_notification_recovery(self, context: AgentRuntimeContext, *, recovered: bool = True) -> bool:
        # Launch a driver that drains pending main notifications with no initial
        # turn. recovered=True (boot) surfaces queued user bubbles never shown in
        # this process; recovered=False is the in-process resume kick.
        async with self._start_lock:
            if self.is_running():
                return False
            if not await agent_notifications.has_pending_main_agent_notification(
                session_id=self.session_id,
            ):
                return False
            await _mark_session_running(
                self.session_id,
                agent_code=context.agent_code,
                sandbox_container_id=context.sandbox_container_id,
                sandbox_container_generation=context.sandbox_container_generation,
            )
            await self._ensure_timeline_loaded()
            self._publish_run_state(True)
            task = asyncio.create_task(
                self._drive(None, context.agent_code or "", context, recovered=recovered),
                name=f"agent-recovery-{self.session_id}",
            )
            self._current_task = task
            return True

    async def interrupt(self) -> list[AgentEventSchema]:
        task = self._current_task
        if task is None or task.done():
            return []
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # The cancelled task's ``_finalize_interrupted_turn`` has already
        # published a boundary ``*Complete`` event for any in-flight segment
        # plus a ``DoneEvent`` so the live projection ends in a finalised
        # state. We only need to (a) drop main-agent notifications the user
        # explicitly abandoned and (b) update session liveness; freshly
        # enqueued USER_MESSAGE notifications are preserved so the next
        # idle cycle still honours them.
        await agent_notifications.cancel_main_agent_interrupted_notifications(
            self.session_id,
            "Discarded by user interrupt.",
        )
        await _mark_session_stopped(self.session_id)
        event = await self._publish_idle_if_inactive()
        return [event] if event is not None else []

    async def cancel_all(self) -> list[AgentEventSchema]:
        events: list[AgentEventSchema] = []
        task = self._current_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await _mark_session_stopped(self.session_id)
            events.append(await self._publish(DoneEvent(created_at=datetime.now())))
        await cancel_session_subagent_runs(self.session_id)
        await cancel_session_async_sandbox_commands(self.session_id)
        await agent_notifications.cancel_session_notifications(
            self.session_id,
            "Agent session tasks canceled by user.",
        )
        await _force_mark_session_stopped(self.session_id)
        events.append(self._publish_run_state(False))
        return events

    async def shutdown(self) -> None:
        await self.cancel_all()
        await self.close()

    async def close(self) -> None:
        self._close_subscribers()
        await self._log_writer.stop()
        self._timeline_loaded = False
        await self._dispose_agent_graph()

    def _close_subscribers(self) -> None:
        for queue in tuple(self._subscribers):
            queue.put_nowait(None)
        self._subscribers.clear()

    async def flush_timeline(self) -> None:
        if self._timeline_loaded:
            await self._log_writer.flush()

    def uses_sandbox_container(self, container_id: int) -> bool:
        return self._tool_snapshot is not None and self._tool_snapshot.sandbox_container_id == container_id

    async def invalidate_tool_binding(self) -> None:
        await self.cancel_all()
        self._tool_snapshot = None
        await self._dispose_agent_graph()

    async def _execute_turn(
        self,
        trigger: TurnTrigger,
        agent_code: str,
        context: AgentRuntimeContext,
    ) -> Any:
        """Run a single agent turn described by *trigger*.

        Returns the SDK stream result on normal completion.
        Raises ``InterruptSignal`` when preempted by a pending notification.

        Context derivation, user-event emission, and nested-event tagging
        are all governed by the ``TurnTrigger``; callers set those flags
        via ``replace_trigger`` before passing the trigger in.
        """
        if trigger.has_notification:
            turn_context = _context_for_notification(context, trigger.notification)
            turn_agent_code = trigger.notification.target_agent_code
        else:
            turn_context = context
            turn_agent_code = agent_code

        def _tag(event: AgentEventSchema) -> AgentEventSchema:
            return _tag_notification_event(event, turn_context) if trigger.has_notification else event

        # Setup phase (graph bind, compaction, runner build) runs under the same
        # exception protection as the stream: a failure here is surfaced as a
        # finalized Error+Done turn instead of escaping and tearing down the
        # session driver. Interrupt/cancel must still propagate.
        try:
            graph = await self._ensure_agent_graph(turn_agent_code, turn_context)
            agent = graph.get(turn_agent_code)
            turn_scope = _next_turn_scope(turn_context)

            if trigger.emit_user_event:
                await self._publish(UserMessageEvent(
                    created_at=datetime.now(),
                    content=trigger.content,
                    display_text=display_text_from_content(trigger.content),
                    target_agent_code=turn_agent_code,
                ))
            elif trigger.has_notification and not trigger.notification.is_user_message:
                # A continuation driven by a hidden notification (e.g. a subagent
                # completion fed back as a user-role context item) starts a new
                # agent turn with no visible user bubble. Emit a turn boundary so
                # the transcript separates it from the previous turn, matching the
                # boundary a real user message would create.
                await self._publish(_tag(
                    TurnBoundaryEvent(created_at=datetime.now(), agent_name=agent.name),
                ))

            memory_session = XuanMuSession(
                session_id=self.session_id,
                engine=get_engine(),
                viewing_agent_code=turn_agent_code,
                agent_code_to_name=graph.code_to_name(),
                nested_for_agent_code=turn_context.nested_for_agent_code,
                nested_call_id=turn_context.nested_call_id,
            )

            user_input = [build_user_message_item(trigger.content)]
            agent_config = get_config().agents.get(turn_agent_code)
            if agent_config is not None:
                await memory_session.compact_if_needed(
                    agent_config=agent_config,
                    incoming_items=user_input,
                )

            stream = Runner.run_streamed(
                starting_agent=agent,
                session=memory_session,
                input=user_input,
                context=turn_context,
                max_turns=get_config().agent_runtime.main_max_turns,
                run_config=build_context_run_config(agent_config) if agent_config is not None else None,
            )
        except (InterruptSignal, asyncio.CancelledError):
            raise
        except Exception as exc:
            logger.exception("agent turn setup failed session=%s: %s", self.session_id, exc)
            await self._publish(_tag(ErrorEvent(
                created_at=datetime.now(),
                agent_name=turn_agent_code,
                message=str(exc) or "agent turn setup failed",
            )))
            await self._publish(_tag(DoneEvent(created_at=datetime.now(), agent_name=turn_agent_code)))
            return None

        buffers: dict[str, DeltaBuffer] = {}
        stream_error: ErrorEvent | None = None
        try:
            async for event in iter_interruptible_events(
                stream,
                session_id=self.session_id,
                agent_instance_id=turn_context.agent_instance_id,
                current_agent_name=agent.name,
                segment_scope=turn_scope,
            ):
                track_delta(buffers, event)
                await self._publish(_tag(event))
            # Finalize segments left open by providers without a text-done event
            # (e.g. Chat Completions); otherwise the text is never persisted.
            for finalize_event in incomplete_segment_events(buffers, agent_name=agent.name):
                await self._publish(_tag(finalize_event))
            buffers.clear()
        except (InterruptSignal, asyncio.CancelledError):
            # Both paths end the turn mid-flight; emit boundary + done so the
            # live projection sees in-flight deltas as finalized and clients
            # don't get a dangling stream on reconnect. Partial buffers are
            # intentionally dropped (see ``discard_partial_stream``).
            await self._finalize_interrupted_turn(
                stream=stream,
                buffers=buffers,
                tag=_tag,
                agent_name=agent.name,
            )
            raise
        except StreamIdleTimeout as exc:
            await discard_partial_stream(stream, buffers, log_label="agent")
            logger.warning(
                "agent stream idle timeout session=%s agent=%s phase=%s timeout=%d",
                self.session_id, turn_agent_code, exc.phase, exc.timeout_seconds,
            )
            stream_error = ErrorEvent(created_at=datetime.now(), agent_name=agent.name, message=str(exc))
        except Exception as exc:
            await discard_partial_stream(stream, buffers, log_label="agent")
            logger.exception("agent stream failed session=%s: %s", self.session_id, exc)
            stream_error = ErrorEvent(created_at=datetime.now(), agent_name=agent.name, message=str(exc))

        if stream_error is not None:
            await self._publish(_tag(stream_error))
        await self._publish(_tag(DoneEvent(created_at=datetime.now(), agent_name=agent.name)))
        return stream

    async def _finalize_interrupted_turn(
        self,
        *,
        stream: Any,
        buffers: dict[str, DeltaBuffer],
        tag: Callable[[AgentEventSchema], AgentEventSchema],
        agent_name: str,
    ) -> None:
        boundary_events = incomplete_segment_events(buffers, agent_name=agent_name)
        await discard_partial_stream(stream, buffers, log_label="agent")
        for evt in boundary_events:
            await self._publish(tag(evt))
        await self._publish(tag(DoneEvent(created_at=datetime.now(), agent_name=agent_name)))

    async def _ensure_agent_graph(self, agent_code: str, context: AgentRuntimeContext) -> SessionAgentGraph:
        tool_snapshot = AgentToolSnapshot.from_context(context)
        if (
            self._agent_graph is None
            or self._main_agent_code != agent_code
            or self._tool_snapshot != tool_snapshot
        ):
            await self._dispose_agent_graph()
            self._main_agent_code = agent_code
            self._tool_snapshot = tool_snapshot
            self._agent_graph = self._registry.bind(tool_snapshot)
            logger.debug(
                "agent graph bound session=%s agent=%s knowledge_generation=%d sandbox=%s generation=%d",
                self.session_id,
                agent_code,
                tool_snapshot.knowledge_generation,
                tool_snapshot.sandbox_container_id,
                tool_snapshot.sandbox_container_generation,
            )
        return self._agent_graph

    async def _dispose_agent_graph(self) -> None:
        if self._agent_graph is None:
            return
        await self._agent_graph.close()
        self._agent_graph = None
        self._main_agent_code = ""

    async def _drive(
        self,
        content: list[AgentInputPart] | None,
        agent_code: str,
        context: AgentRuntimeContext,
        *,
        attempt: int = 0,
        recovered: bool = False,
        initial_user_event_published: bool = False,
    ) -> None:
        # The single main-session driver (true-async, non-blocking): run the
        # optional initial turn, drain ready notifications, then end. On delegation
        # it ends and goes idle while children run; a child's completion kicks
        # resume_session. The finally only reconciles a post-drain claim race.
        async with self._turn_lock:
            task = asyncio.current_task()
            self._current_task = task
            canceled = False
            try:
                context.agent_code = agent_code
                if not context.agent_instance_id:
                    context.agent_instance_id = main_agent_instance_id(
                        context.session_id, context.user.id, agent_code,
                    )

                is_initial = content is not None and not initial_user_event_published

                async def _run_turn(trigger: TurnTrigger) -> Any:
                    nonlocal is_initial
                    if recovered and trigger.notification is not None and trigger.notification.is_user_message:
                        # Boot recovery: the bubble was never published in this
                        # process, so surface it as the turn is consumed.
                        trigger = replace_trigger(trigger, emit_user_event=True)
                    elif is_initial and not trigger.has_notification:
                        trigger = replace_trigger(trigger, emit_user_event=True)
                    is_initial = False
                    return await self._execute_turn(trigger, agent_code, context)

                await run_until_idle(
                    session_id=self.session_id,
                    agent_instance_id=context.agent_instance_id,
                    initial_content=content,
                    run_turn=_run_turn,
                )
            except asyncio.CancelledError:
                canceled = True
                raise
            except Exception as exc:
                logger.exception("agent driver failed session=%s", self.session_id)
                await self._publish(ErrorEvent(created_at=datetime.now(), message=str(exc) or "agent turn failed"))
                await self._publish(DoneEvent(created_at=datetime.now()))
            finally:
                relaunched = False
                if not canceled:
                    relaunched = await self._reconcile_driver(agent_code, context, attempt)
                if self._current_task is task and not relaunched:
                    self._current_task = None
                if not canceled and not relaunched:
                    await _mark_session_stopped(self.session_id)
                    await self._publish_idle_if_inactive()

    async def _reconcile_driver(
        self,
        agent_code: str,
        context: AgentRuntimeContext,
        attempt: int,
    ) -> bool:
        # Relaunch (under _start_lock) only if a claimable PENDING landed after the
        # final drain; AWAITING obligations (running children) keep the session
        # idle, not driving. Returns whether relaunched.
        async with self._start_lock:
            if not await agent_notifications.has_pending_notification(
                session_id=self.session_id,
                target_agent_instance_id=context.agent_instance_id,
            ):
                return False
            if attempt >= _MAX_DRIVER_RELAUNCH:
                logger.error(
                    "agent driver relaunch budget exhausted session=%s target=%s; canceling outstanding work",
                    self.session_id, context.agent_instance_id,
                )
                await agent_notifications.cancel_session_notifications(
                    self.session_id, "Agent driver could not make progress.",
                )
                return False
            new_task = asyncio.create_task(
                self._relaunch_driver(
                    _DRIVER_RELAUNCH_BACKOFF_SECONDS * attempt, agent_code, context, attempt + 1,
                ),
                name=f"agent-driver-relaunch-{self.session_id}",
            )
            self._current_task = new_task
            return True

    async def _relaunch_driver(
        self,
        delay: float,
        agent_code: str,
        context: AgentRuntimeContext,
        attempt: int,
    ) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        await self._drive(None, agent_code, context, attempt=attempt)

    def _publish_run_state(self, running: bool) -> RunStateEvent:
        event = RunStateEvent(created_at=datetime.now(), running=running)
        if running:
            self._live_projection.reset(event)
        else:
            self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            self._enqueue_or_rebase(queue, event)
        if not running:
            self._live_projection.reset(event)
        return event

    async def _publish_idle_if_inactive(self) -> RunStateEvent | None:
        # Live run-state tracks the main agent only (idle-live UX): once it ends
        # with no claimable PENDING turn, go idle even while sub-agents stream.
        if self.is_running():
            return None
        if await agent_notifications.has_pending_main_agent_notification(session_id=self.session_id):
            return None
        return self._publish_run_state(False)

    async def _publish(self, event: AgentEventSchema) -> AgentEventSchema:
        self.publish_external(event)
        return event

    async def _ensure_timeline_loaded(self) -> None:
        """Resume the seq counter + key map from the durable log, then start the writer.

        Loading the existing key→seq map lets a re-pooled or recovered session
        re-emit an already-persisted item (e.g. a running subagent_task) under
        its original seq so live and stored frames keep one identity space.
        """
        if self._timeline_loaded:
            return
        from service.agent.event_log import load_timeline_head

        max_seq, item_seq = await load_timeline_head(self.session_id)
        if self._timeline_loaded:
            return
        self._seq = max(self._seq, max_seq)
        for key, seq in item_seq.items():
            self._item_seq.setdefault(key, seq)
        self._timeline_loaded = True
        self._log_writer.start()

    def _stamp_event(self, event: AgentEventSchema) -> str | None:
        """Stamp ``event.seq`` in place; return its durable item_key or None.

        Keyless events (user_message/turn_boundary/error) consume a fresh seq
        per emission; keyed events reuse the first-seen seq for their item_key.
        Deltas and control frames receive a seq for ordering but are not stored.
        """
        if isinstance(event, (RunStateEvent, DoneEvent)):
            return None
        key = timeline_item_key(event)
        if key is None:
            self._seq += 1
            event.seq = self._seq
            persist_key = f"{event.type}:{self._seq}"
        else:
            seq = self._item_seq.get(key)
            if seq is None:
                self._seq += 1
                seq = self._seq
                self._item_seq[key] = seq
            event.seq = seq
            persist_key = key
        if not is_persistable(event):
            return None
        return persist_key

    def publish_external(self, event: AgentEventSchema) -> bool:
        """Inject an event into the session's unified event bus.

        Used internally by ``_publish`` and externally via ``AgentSessionPool.publish``.
        Returns whether a persistable event was accepted by the durable writer;
        non-persistable control/delta frames return ``True`` once delivered to
        subscribers/projection.
        """
        persist_key = self._stamp_event(event)
        self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            self._enqueue_or_rebase(queue, event)
        if persist_key is not None and self._timeline_loaded:
            return self._log_writer.enqueue(persist_key, event.seq, event.model_dump_json(), event.created_at)
        return persist_key is None

    def _enqueue_or_rebase(self, queue: _SubscriberQueue, event: AgentEventSchema) -> None:
        if queue.qsize() < _SUBSCRIBER_REBASE_THRESHOLD:
            queue.put_nowait(event)
            return

        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        snapshot = self._live_projection.snapshot()
        if isinstance(event, RunStateEvent) and not event.running:
            snapshot = [item for item in snapshot if not isinstance(item, RunStateEvent)]
            snapshot.append(event)
        for item in snapshot:
            queue.put_nowait(item)


@dataclass
class _PooledSession:
    session: AgentSession
    last_used_at: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class _EvictionCandidate:
    session_id: str
    entry: _PooledSession
    last_used_at: float


class AgentSessionPool:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        cfg = get_config().agent_pool
        self._registry = registry or AgentRegistry()
        self._max_size = cfg.max_size
        self._ttl = cfg.ttl_seconds
        self._sweep_interval = cfg.sweep_interval_seconds
        self._pool: dict[str, _PooledSession] = {}
        self._sweeper_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    async def start(self) -> None:
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweep_loop(), name="agent-pool-sweeper")
        logger.debug(
            "agent pool started (ttl=%ds, interval=%ds, max_size=%d)",
            self._ttl, self._sweep_interval, self._max_size,
        )

    async def stop(self) -> None:
        task, self._sweeper_task = self._sweeper_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            entries = list(self._pool.values())
            session_ids = list(self._pool.keys())
            self._pool.clear()
        await asyncio.gather(*(entry.session.shutdown() for entry in entries), return_exceptions=True)
        await _mark_sessions_stopped(session_ids)
        logger.debug("agent pool stopped")

    async def get_or_create(self, session_id: str) -> AgentSession:
        async with self._lock:
            session = self._get_or_create_locked(session_id)
        await self._enforce_capacity(protected_session_id=session_id)
        return session

    async def _enforce_capacity(self, *, protected_session_id: str = "") -> None:
        async with self._lock:
            candidates = self._capacity_candidates_locked(protected_session_id=protected_session_id)
            overflow = max(0, len(self._pool) - self._max_size)
        evicted = await self._claim_inactive_evictions(candidates, limit=overflow)
        await self._close_evicted(evicted, reason="LRU")

    def _get_or_create_locked(self, session_id: str) -> AgentSession:
        entry = self._pool.get(session_id)
        if entry is None:
            entry = _PooledSession(session=AgentSession(session_id, self._registry))
            self._pool[session_id] = entry
            logger.debug("agent pool created session=%s", session_id)
        else:
            entry.last_used_at = time.monotonic()
        return entry.session

    async def discard(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.pop(session_id, None)
        if entry is None:
            await _force_mark_session_stopped(session_id)
            return
        await entry.session.shutdown()
        logger.debug("agent pool discarded session=%s", session_id)

    async def invalidate_session_tool_binding(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            return
        await entry.session.invalidate_tool_binding()

    async def flush_timeline(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is not None:
            await entry.session.flush_timeline()

    async def try_interrupt(self, session_id: str) -> list[AgentEventSchema]:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            return []
        return await entry.session.interrupt()

    async def subscribe(
        self,
        session_id: str,
        include: Callable[[AgentEventSchema], bool] | None = None,
    ) -> tuple[AgentSession, _SubscriberQueue]:
        session = await self.get_or_create(session_id)
        return session, await session.subscribe(include)

    def publish(self, session_id: str, event: AgentEventSchema) -> bool:
        """Route an external event to the session's unified event bus.

        Lock-free: dict.get and attribute assignment are atomic in asyncio's
        single-threaded model. Returns ``True`` when a pooled session with a
        loaded timeline received and durably stored the event; ``False`` lets
        the caller fall back to a direct persist (e.g. boot-time subagent
        status changes for sessions that are not pooled yet).
        """
        entry = self._pool.get(session_id)
        if entry is None:
            return False
        entry.last_used_at = time.monotonic()
        return entry.session.publish_external(event)

    async def resume_session(self, session_id: str) -> None:
        # Main-agent arm of resume_target_instance: rebuild the runtime context
        # from persisted meta and start a non-blocking driver. With no pending
        # main work (e.g. a canceled task) settle idle instead of starting a turn;
        # no-op while a driver already runs.
        from middleware.auth import AuthUser
        from service.agent import sessions as agent_sessions
        from service.agent.runtime import build_runtime_context
        from service.system_user.users import query_system_user_by_id

        if not await agent_notifications.has_pending_main_agent_notification(session_id=session_id):
            await self._settle_session_idle(session_id)
            return
        meta = await agent_sessions.get_session_meta(session_id)
        if meta is None:
            return
        user = await query_system_user_by_id(meta.owner_id)
        if user is None:
            return
        auth_user = AuthUser(id=user.id, role=user.role, email=user.email, username=user.username)
        agent_code = meta.runtime_agent_code or meta.agent_code
        context = await build_runtime_context(
            session_id, auth_user, meta.runtime_sandbox_container_id, agent_code,
        )
        session = await self.get_or_create(session_id)
        await session.start_notification_recovery(context, recovered=False)

    async def _settle_session_idle(self, session_id: str) -> None:
        # Wind down a session with no pending main turn (e.g. a canceled task):
        # mark the DB run stopped (no-op while other work is active) and publish
        # run_state=false for a pooled, non-running session.
        entry = self._pool.get(session_id)
        if entry is not None and entry.session.is_running():
            return
        await _mark_session_stopped(session_id)
        if entry is not None:
            await entry.session._publish_idle_if_inactive()

    async def cancel_all(self, session_id: str) -> list[AgentEventSchema]:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            await cancel_session_subagent_runs(session_id)
            await cancel_session_async_sandbox_commands(session_id)
            await agent_notifications.cancel_session_notifications(
                session_id,
                "Agent session tasks canceled by user.",
            )
            await _force_mark_session_stopped(session_id)
            return []
        return await entry.session.cancel_all()

    async def invalidate_tool_bindings(self, container_id: int | None = None) -> None:
        async with self._lock:
            entries = [
                entry for entry in self._pool.values()
                if container_id is None or entry.session.uses_sandbox_container(container_id)
            ]
        tasks = [entry.session.invalidate_tool_binding() for entry in entries]
        if container_id is not None:
            tasks.extend([
                cancel_sandbox_subagent_runs(container_id),
                cancel_sandbox_async_commands(container_id),
            ])
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug("agent pool invalidated tool bindings container=%s count=%d", container_id, len(entries))

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                async with self._lock:
                    expired = self._sweep_expired_candidates_locked(time.monotonic())
                expired = await self._claim_inactive_evictions(expired)
                await self._close_evicted(expired, reason="idle")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent pool sweep iteration failed")

    def _sweep_expired_candidates_locked(self, now: float) -> list[_EvictionCandidate]:
        if self._ttl <= 0:
            return []
        return [
            _EvictionCandidate(sid, entry, entry.last_used_at) for sid, entry in self._pool.items()
            if (
                not entry.session.is_running()
                and not entry.session.has_subscribers()
                and now - entry.last_used_at > self._ttl
            )
        ]

    def _capacity_candidates_locked(self, *, protected_session_id: str = "") -> list[_EvictionCandidate]:
        # only idle entries are evicted; running sessions may briefly exceed the cap
        overflow = len(self._pool) - self._max_size
        if overflow <= 0:
            return []
        return sorted(
            (
                _EvictionCandidate(sid, entry, entry.last_used_at)
                for sid, entry in self._pool.items()
                if (
                    sid != protected_session_id
                    and not entry.session.is_running()
                    and not entry.session.has_subscribers()
                )
            ),
            key=lambda item: item.last_used_at,
        )

    async def _claim_inactive_evictions(
        self,
        candidates: list[_EvictionCandidate],
        limit: int | None = None,
    ) -> list[tuple[str, _PooledSession]]:
        if not candidates or limit == 0:
            return []
        eviction_ids: list[str] = []
        for candidate in candidates:
            if limit is not None and len(eviction_ids) >= limit:
                break
            sid = candidate.session_id
            entry = candidate.entry
            if entry.session.is_running() or entry.session.has_subscribers():
                continue
            if entry.last_used_at != candidate.last_used_at:
                continue
            if await agent_notifications.has_active_session_notifications(session_id=sid):
                continue
            eviction_ids.append(sid)
        if not eviction_ids:
            return []

        observed_last_used = {candidate.session_id: candidate.last_used_at for candidate in candidates}
        evicted: list[tuple[str, _PooledSession]] = []
        async with self._lock:
            for sid in eviction_ids:
                entry = self._pool.get(sid)
                if entry is None:
                    continue
                if entry.session.is_running() or entry.session.has_subscribers():
                    continue
                observed = observed_last_used.get(sid)
                if observed is None or entry.last_used_at != observed:
                    continue
                evicted.append((sid, self._pool.pop(sid)))
        return evicted

    async def _close_evicted(self, evicted: list[tuple[str, _PooledSession]], *, reason: str) -> None:
        if not evicted:
            return
        await asyncio.gather(*(entry.session.close() for _, entry in evicted), return_exceptions=True)
        for sid, _ in evicted:
            logger.debug("agent pool evicted %s session=%s", reason, sid)


_pool: AgentSessionPool | None = None


def get_agent_pool() -> AgentSessionPool:
    global _pool
    if _pool is None:
        _pool = AgentSessionPool()
    return _pool


def replace_agent_pool(pool: AgentSessionPool | None = None) -> AgentSessionPool:
    global _pool
    _pool = pool or AgentSessionPool()
    return _pool


def get_agent_registry() -> AgentRegistry:
    return get_agent_pool().registry


def _context_for_notification(
    base: AgentRuntimeContext,
    notification: AgentNotificationSnapshot,
) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        session_id=base.session_id,
        user=base.user,
        agent_code=notification.target_agent_code,
        agent_instance_id=notification.target_agent_instance_id,
        nested_for_agent_code=notification.nested_for_agent_code,
        nested_call_id=notification.nested_call_id,
        knowledge_generation=base.knowledge_generation,
        sandbox_container_id=notification.sandbox_container_id,
        sandbox_container_generation=notification.sandbox_container_generation,
        sandbox_skill_metadata=notification.sandbox_skill_metadata,
        work_project_id=base.work_project_id,
    )


def _tag_notification_event(event: AgentEventSchema, context: AgentRuntimeContext) -> AgentEventSchema:
    if not context.nested_for_agent_code or not hasattr(event, "nested_for"):
        return event
    return event.model_copy(update={
        "nested_for": context.nested_for_agent_code,
        "nested_call_id": context.nested_call_id,
    })


def _next_turn_scope(context: AgentRuntimeContext) -> str:
    owner = context.agent_instance_id or main_agent_instance_id(
        context.session_id,
        context.user.id,
        context.agent_code,
    )
    return next_segment_scope(owner)


async def _mark_session_running(
    session_id: str,
    *,
    agent_code: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
) -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_running(
        session_id,
        agent_code=agent_code,
        sandbox_container_id=sandbox_container_id,
        sandbox_container_generation=sandbox_container_generation,
    )


async def _mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_stopped(session_id, error=error)


async def _force_mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.force_mark_session_stopped(session_id, error=error)


async def _mark_sessions_stopped(session_ids: list[str], *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_sessions_stopped(session_ids, error=error)
