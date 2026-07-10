"""Interrupt signal and interruptible event stream for agent turns.

Provides atomicity-aware preemption: notifications arriving during tool
execution are deferred until the tool result is received, preventing
context loss.  Notifications arriving during model inference trigger an
immediate ``InterruptSignal``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from core.runtime.notification_dispatch import (
    target_notification_version,
    wait_for_target_notifications,
)
from core.runtime.streaming import iter_normalized_stream_events
from logger import get_logger
from schema.agent.events import AgentEventSchema, ToolCallEvent, ToolResultEvent
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)

_SIGNAL_POLL_SECONDS = 1.0


class InterruptSignal(Exception):
    """Raised to preempt an agent turn when a notification becomes pending."""


async def iter_interruptible_events(
    stream: Any,
    *,
    session_id: str,
    agent_instance_id: str,
    current_agent_name: str,
    segment_scope: str = "",
) -> AsyncIterator[AgentEventSchema]:
    """Iterate SDK stream events with interrupt-aware preemption.

    Yields normalised events identical to ``iter_normalized_stream_events``.
    In parallel, watches for pending notifications targeting *agent_instance_id*.

    Preemption rules (modeled after CPU interrupt masking):

    * **No pending tool calls** – raise ``InterruptSignal`` immediately.
    * **Pending tool calls > 0** – defer; raise at the first safe point
      after all outstanding tools complete.
    """

    if await agent_notifications.has_pending_notification(
        session_id=session_id,
        target_agent_instance_id=agent_instance_id,
    ):
        raise InterruptSignal

    events = iter_normalized_stream_events(
        stream,
        current_agent_name=current_agent_name,
        segment_scope=segment_scope,
    )

    pending_tool_calls = 0
    deferred = False

    version = await target_notification_version(agent_instance_id)
    event_task: asyncio.Task[AgentEventSchema] = asyncio.create_task(
        _anext(events), name=f"irq-event-{agent_instance_id}",
    )
    signal_task: asyncio.Task[bool] = asyncio.create_task(
        wait_for_target_notifications(
            agent_instance_id, after_version=version, timeout_seconds=_SIGNAL_POLL_SECONDS,
        ),
        name=f"irq-signal-{agent_instance_id}",
    )

    try:
        while True:
            done, _ = await asyncio.wait(
                {event_task, signal_task}, return_when=asyncio.FIRST_COMPLETED,
            )

            # --- notification signal ---
            has_pending = False
            if signal_task in done:
                signal_task.result()
                has_pending = await agent_notifications.has_pending_notification(
                    session_id=session_id,
                    target_agent_instance_id=agent_instance_id,
                )

            # --- stream event ---
            if event_task in done:
                try:
                    event = event_task.result()
                except StopAsyncIteration:
                    return

                if isinstance(event, ToolCallEvent):
                    pending_tool_calls += 1
                elif isinstance(event, ToolResultEvent) and pending_tool_calls > 0:
                    pending_tool_calls -= 1

                yield event

                if deferred and pending_tool_calls == 0:
                    raise InterruptSignal

                event_task = asyncio.create_task(
                    _anext(events), name=f"irq-event-{agent_instance_id}",
                )

            # --- process signal result ---
            if signal_task in done:
                if has_pending:
                    if pending_tool_calls == 0:
                        raise InterruptSignal
                    deferred = True

                version = await target_notification_version(agent_instance_id)
                signal_task = asyncio.create_task(
                    wait_for_target_notifications(
                        agent_instance_id,
                        after_version=version,
                        timeout_seconds=_SIGNAL_POLL_SECONDS,
                    ),
                    name=f"irq-signal-{agent_instance_id}",
                )
    finally:
        for task in (event_task, signal_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(event_task, signal_task, return_exceptions=True)


async def _anext(aiter: AsyncIterator[AgentEventSchema]) -> AgentEventSchema:
    """Typed wrapper so ``asyncio.create_task`` receives an awaitable."""
    return await aiter.__anext__()
