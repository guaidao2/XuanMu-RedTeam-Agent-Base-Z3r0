"""Normalize live SDK stream events into our wire event schema."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses.response_completed_event import ResponseCompletedEvent
from openai.types.responses.response_created_event import ResponseCreatedEvent
from openai.types.responses.response_error_event import ResponseErrorEvent
from openai.types.responses.response_failed_event import ResponseFailedEvent
from openai.types.responses.response_incomplete_event import ResponseIncompleteEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import ResponseReasoningTextDeltaEvent
from openai.types.responses.response_reasoning_text_done_event import ResponseReasoningTextDoneEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent
from pydantic import BaseModel

from schema.agent.events import (
    AgentEventSchema,
    ErrorEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)


# `incomplete` is a partial output, not an error
_TOOL_ERROR_STATUSES = {"failed", "error"}

_RUN_ITEM_RESPONSE_BOUNDARIES = {
    "message_output_created",
    "reasoning_item_created",
    "tool_called",
    "tool_output",
    "tool_search_called",
    "tool_search_output_created",
    "handoff_requested",
    "handoff_occured",
    "mcp_approval_requested",
    "mcp_approval_response",
    "mcp_list_tools",
}


@dataclass(frozen=True, slots=True)
class _StreamSegmentKey:
    kind: str
    response_index: int = 0
    output_index: int = -1
    content_index: int = -1
    summary_index: int = -1


@dataclass(slots=True)
class _StreamSegment:
    segment_id: str
    text: str = ""
    complete: bool = False


class SdkStreamEventNormalizer:
    """Map SDK stream events to the public app-level event contract."""

    def __init__(self, *, segment_scope: str = "") -> None:
        self._segments: dict[_StreamSegmentKey, _StreamSegment] = {}
        self._next_segment_index = 1
        self._response_index = 0
        self._response_open = False
        self._segment_scope = segment_scope.strip()

    def event_from_sdk_stream(self, sdk_event: Any, current_agent: str) -> AgentEventSchema | None:
        created_at = datetime.now()
        if isinstance(sdk_event, RawResponsesStreamEvent):
            if self._handle_response_lifecycle(sdk_event.data):
                return None
            return _from_raw_response(sdk_event.data, current_agent, created_at, self)
        if isinstance(sdk_event, RunItemStreamEvent):
            event = _from_run_item(sdk_event, current_agent, created_at)
            if sdk_event.name in _RUN_ITEM_RESPONSE_BOUNDARIES:
                self._response_open = False
            return event
        return None

    @property
    def response_index(self) -> int:
        if not self._response_open:
            return self._begin_response()
        return self._response_index

    def segment_id(self, key: _StreamSegmentKey, *, complete: bool) -> str:
        segment = self._segments.get(key)
        if segment is None or (segment.complete and not complete):
            segment = _StreamSegment(segment_id=self._segment_id(key))
            self._segments[key] = segment
            self._next_segment_index += 1
        if complete:
            segment.complete = True
        return segment.segment_id

    def append_delta(self, key: _StreamSegmentKey, delta: str) -> tuple[str, str]:
        segment_id = self.segment_id(key, complete=False)
        segment = self._segments[key]
        segment.text += delta
        return segment_id, segment.text

    def complete_text(self, key: _StreamSegmentKey, text: str) -> str:
        segment_id = self.segment_id(key, complete=True)
        self._segments[key].text = text
        return segment_id

    def _segment_id(self, key: _StreamSegmentKey) -> str:
        return self._scoped_segment_id(key.kind, self._next_segment_index)

    def _scoped_segment_id(self, kind: str, index: int) -> str:
        if not self._segment_scope:
            return f"{kind}_{index}"
        return f"{self._segment_scope}_{kind}_{index}"

    def _handle_response_lifecycle(self, data: Any) -> bool:
        if isinstance(data, ResponseCreatedEvent):
            self._begin_response()
            return True
        if isinstance(data, (ResponseCompletedEvent, ResponseFailedEvent, ResponseIncompleteEvent)):
            self._response_open = False
            return True
        return False

    def _begin_response(self) -> int:
        self._response_index += 1
        self._response_open = True
        return self._response_index


def _from_raw_response(
    data: Any,
    current_agent: str,
    created_at: datetime,
    normalizer: SdkStreamEventNormalizer,
) -> AgentEventSchema | None:
    if isinstance(data, ResponseTextDeltaEvent):
        segment_id, text = normalizer.append_delta(_text_segment_key(data, normalizer.response_index), data.delta)
        return TextDeltaEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=segment_id,
            delta=data.delta,
            text=text,
        )
    if isinstance(data, ResponseTextDoneEvent):
        return TextCompleteEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=normalizer.complete_text(_text_segment_key(data, normalizer.response_index), data.text),
            text=data.text,
        )
    if isinstance(data, ResponseReasoningTextDeltaEvent):
        segment_id, text = normalizer.append_delta(
            _thinking_text_segment_key(data, normalizer.response_index),
            data.delta,
        )
        return ThinkingDeltaEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=segment_id,
            delta=data.delta,
            text=text,
        )
    if isinstance(data, ResponseReasoningTextDoneEvent):
        return ThinkingCompleteEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=normalizer.complete_text(_thinking_text_segment_key(data, normalizer.response_index), data.text),
            text=data.text,
        )
    if isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
        segment_id, text = normalizer.append_delta(
            _thinking_summary_segment_key(data, normalizer.response_index),
            data.delta,
        )
        return ThinkingDeltaEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=segment_id,
            delta=data.delta,
            text=text,
        )
    if isinstance(data, ResponseReasoningSummaryTextDoneEvent):
        return ThinkingCompleteEvent(
            created_at=created_at,
            agent_name=current_agent,
            segment_id=normalizer.complete_text(_thinking_summary_segment_key(data, normalizer.response_index), data.text),
            text=data.text,
        )
    if isinstance(data, ResponseErrorEvent):
        return ErrorEvent(created_at=created_at, agent_name=current_agent, message=data.message, code=data.code or "")
    return None


def _from_run_item(event: RunItemStreamEvent, current_agent: str, created_at: datetime) -> AgentEventSchema | None:
    item = event.item
    agent_name = item.agent.name if item.agent is not None else current_agent

    if event.name == "tool_called" and isinstance(item, ToolCallItem):
        raw = item.raw_item
        return ToolCallEvent(
            created_at=created_at,
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or _read_field(raw, "id") or "",
            name=_read_field(raw, "name") or item.title or "",
            arguments=_parse_tool_arguments(_read_field(raw, "arguments")),
        )
    if event.name == "tool_output" and isinstance(item, ToolCallOutputItem):
        raw = item.raw_item
        return ToolResultEvent(
            created_at=created_at,
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or "",
            output=_normalize_to_str(item.output),
            is_error=_is_tool_error(_read_field(raw, "status")),
        )
    return None


def _text_segment_key(data: Any, response_index: int) -> _StreamSegmentKey:
    return _segment_key("text", data, response_index=response_index, content_index=_int_attr(data, "content_index"))


def _thinking_text_segment_key(data: Any, response_index: int) -> _StreamSegmentKey:
    return _segment_key("thinking", data, response_index=response_index, content_index=_int_attr(data, "content_index"))


def _thinking_summary_segment_key(data: Any, response_index: int) -> _StreamSegmentKey:
    return _segment_key("thinking", data, response_index=response_index, summary_index=_int_attr(data, "summary_index"))


def _segment_key(
    kind: str,
    data: Any,
    *,
    response_index: int = 0,
    content_index: int = -1,
    summary_index: int = -1,
) -> _StreamSegmentKey:
    return _StreamSegmentKey(
        kind=kind,
        response_index=response_index,
        output_index=_int_attr(data, "output_index"),
        content_index=content_index,
        summary_index=summary_index,
    )


def _int_attr(data: Any, key: str) -> int:
    value = getattr(data, key, -1)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return decoded if isinstance(decoded, dict) else {"_value": decoded}


def _normalize_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _is_tool_error(status: Any) -> bool:
    return isinstance(status, str) and status.lower() in _TOOL_ERROR_STATUSES


def _read_field(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)
