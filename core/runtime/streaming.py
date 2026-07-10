"""Shared SDK stream consumption helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from agents.stream_events import AgentUpdatedStreamEvent, RunItemStreamEvent

from config import get_config
from core.runtime.events import SdkStreamEventNormalizer
from schema.agent.events import AgentEventSchema


_TOOL_EVENT_IDLE_TIMEOUT_SECONDS = 450


class StreamIdleTimeout(TimeoutError):
    def __init__(self, phase: str, timeout_seconds: int) -> None:
        self.phase = phase
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{phase} was idle for more than {timeout_seconds} seconds")


async def iter_normalized_stream_events(
    stream: Any,
    *,
    current_agent_name: str,
    segment_scope: str = "",
) -> AsyncIterator[AgentEventSchema]:
    normalizer = SdkStreamEventNormalizer(segment_scope=segment_scope)
    sdk_events = stream.stream_events().__aiter__()
    pending_tool_calls = 0

    while True:
        try:
            sdk_event = await asyncio.wait_for(
                sdk_events.__anext__(),
                timeout=_event_timeout_seconds(pending_tool_calls),
            )
        except StopAsyncIteration:
            break
        except TimeoutError as exc:
            phase = "tool execution" if pending_tool_calls else "model stream"
            raise StreamIdleTimeout(phase, _event_timeout_seconds(pending_tool_calls)) from exc

        if isinstance(sdk_event, AgentUpdatedStreamEvent):
            continue

        event = normalizer.event_from_sdk_stream(sdk_event, current_agent_name)
        pending_tool_calls = _next_pending_tool_calls(pending_tool_calls, sdk_event)
        if event is not None:
            yield event


def _event_timeout_seconds(pending_tool_calls: int) -> int:
    model_timeout = get_config().agent_runtime.model_stream_idle_timeout_seconds
    if pending_tool_calls <= 0:
        return model_timeout
    return max(model_timeout, _TOOL_EVENT_IDLE_TIMEOUT_SECONDS)


def _next_pending_tool_calls(current: int, sdk_event: Any) -> int:
    if not isinstance(sdk_event, RunItemStreamEvent):
        return current
    if sdk_event.name == "tool_called":
        return current + 1
    if sdk_event.name == "tool_output" and current > 0:
        return current - 1
    return current


def next_segment_scope(owner: str) -> str:
    """Generate a unique segment scope identifier from an owner string."""
    normalized = "".join(ch if ch.isalnum() else "_" for ch in owner.strip())
    safe = normalized.strip("_") or "agent"
    return f"turn_{safe}_{uuid4().hex}"
