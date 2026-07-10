from dataclasses import dataclass
from datetime import datetime
from typing import Any

from logger import get_logger
from schema.agent.events import (
    AgentEventSchema,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
)


logger = get_logger(__name__)
_DELTA_TYPES: tuple[type, ...] = (TextDeltaEvent, ThinkingDeltaEvent)
_COMPLETE_TYPES: tuple[type, ...] = (TextCompleteEvent, ThinkingCompleteEvent)


@dataclass
class DeltaBuffer:
    is_thinking: bool
    segment_id: str
    content: str = ""
    complete: bool = False


def track_delta(buffers: dict[str, DeltaBuffer], event: AgentEventSchema) -> None:
    if isinstance(event, _DELTA_TYPES):
        buf = buffers.get(event.segment_id)
        if buf is None:
            buf = DeltaBuffer(is_thinking=isinstance(event, ThinkingDeltaEvent), segment_id=event.segment_id)
            buffers[event.segment_id] = buf
        buf.content += event.delta
    elif isinstance(event, _COMPLETE_TYPES):
        buf = buffers.get(event.segment_id)
        if buf is None:
            buf = DeltaBuffer(is_thinking=isinstance(event, ThinkingCompleteEvent), segment_id=event.segment_id)
            buffers[event.segment_id] = buf
        buf.content = event.text
        buf.complete = True


async def discard_partial_stream(
    result: Any,
    buffers: dict[str, DeltaBuffer],
    *,
    log_label: str,
) -> None:
    """Cancel an in-flight SDK stream and drop in-flight delta buffers.

    Mid-turn termination intentionally discards everything that has not
    been finalised by the SDK itself. Persisting partial text into the
    session store would (a) accumulate "half-finished" assistant
    messages across repeated interrupts and (b) bias the next turn's
    LLM into continuing the abandoned answer instead of responding to
    the user's new input. Anything already emitted as a complete
    response by the model is preserved by the SDK on its own.
    """
    if result is None or getattr(result, "is_complete", True):
        buffers.clear()
        return
    try:
        result.cancel(mode="immediate")
    except Exception:
        logger.warning("failed to cancel %s SDK stream", log_label, exc_info=True)
    buffers.clear()


def incomplete_segment_events(
    buffers: dict[str, DeltaBuffer],
    *,
    agent_name: str = "",
) -> list[AgentEventSchema]:
    """Build ``*Complete`` events for streaming segments interrupted mid-flight.

    Must be called **before** ``discard_partial_stream`` (which clears
    *buffers*). The returned events should be published to the live
    bus so that ``LiveEventProjection`` promotes in-flight deltas to
    completed entries, making WS snapshots reliable on reconnect even
    though the partial text is not persisted to history.
    """
    now = datetime.now()
    events: list[AgentEventSchema] = []
    for buf in buffers.values():
        if not buf.content or buf.complete:
            continue
        cls = ThinkingCompleteEvent if buf.is_thinking else TextCompleteEvent
        events.append(cls(
            created_at=now,
            agent_name=agent_name,
            segment_id=buf.segment_id,
            text=buf.content,
        ))
    return events
