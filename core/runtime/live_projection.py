"""In-memory projection of active stream state for reconnect replay."""

from collections.abc import Callable
from dataclasses import dataclass

from schema.agent.events import (
    AgentEventSchema,
    DoneEvent,
    ErrorEvent,
    RunStateEvent,
    SubagentTaskEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnBoundaryEvent,
    UserMessageEvent,
)


@dataclass(frozen=True, slots=True)
class _SegmentKey:
    event_type: str
    segment_id: str
    nested_for: str = ""
    nested_call_id: str = ""


class LiveEventProjection:
    """Reconnect replay for active stream state not yet covered by history."""

    def __init__(self) -> None:
        self._events: list[AgentEventSchema] = []
        self._segment_indexes: dict[_SegmentKey, int] = {}
        self._tool_indexes: dict[tuple[str, str, str], int] = {}
        self._tool_result_indexes: dict[tuple[str, str, str], int] = {}
        self._subagent_indexes: dict[str, int] = {}

    def reset(self, event: RunStateEvent) -> None:
        self._events = [event]
        self._clear_indexes()

    def snapshot(self, include: Callable[[AgentEventSchema], bool] | None = None) -> list[AgentEventSchema]:
        if include is None:
            return list(self._events)
        return [event for event in self._events if include(event)]

    def apply(self, event: AgentEventSchema) -> None:
        if isinstance(event, RunStateEvent):
            self._events = [event] + [item for item in self._events if not isinstance(item, RunStateEvent)]
            self._rebuild_indexes()
            return
        if isinstance(event, (UserMessageEvent, TurnBoundaryEvent)):
            self._events.append(event)
            return
        if isinstance(event, (TextDeltaEvent, ThinkingDeltaEvent)):
            self._apply_segment(event)
            return
        if isinstance(event, (TextCompleteEvent, ThinkingCompleteEvent)):
            self._apply_segment_complete(event)
            return
        if isinstance(event, ToolCallEvent):
            self._apply_tool_call(event)
            return
        if isinstance(event, ToolResultEvent):
            self._apply_tool_result(event)
            return
        if isinstance(event, SubagentTaskEvent):
            self._apply_subagent(event)
            return
        if isinstance(event, DoneEvent):
            if not event.nested_call_id:
                self._events.append(event)
            return
        if isinstance(event, ErrorEvent):
            self._events.append(event)

    def _clear_indexes(self) -> None:
        self._segment_indexes.clear()
        self._tool_indexes.clear()
        self._tool_result_indexes.clear()
        self._subagent_indexes.clear()

    def _apply_segment(self, event: TextDeltaEvent | ThinkingDeltaEvent) -> None:
        key = _SegmentKey(
            event_type="thinking" if event.type == "thinking_delta" else "text",
            segment_id=event.segment_id,
            nested_for=event.nested_for,
            nested_call_id=event.nested_call_id,
        )
        index = self._segment_indexes.get(key)
        if index is None:
            self._segment_indexes[key] = len(self._events)
            self._events.append(event)
            return
        self._events[index] = event

    def _apply_segment_complete(self, event: TextCompleteEvent | ThinkingCompleteEvent) -> None:
        key = _SegmentKey(
            event_type="thinking" if event.type == "thinking_complete" else "text",
            segment_id=event.segment_id,
            nested_for=event.nested_for,
            nested_call_id=event.nested_call_id,
        )
        index = self._segment_indexes.pop(key, None)
        if index is None:
            self._events.append(event)
            return
        self._events[index] = event
        self._rebuild_indexes()

    def _apply_tool_call(self, event: ToolCallEvent) -> None:
        key = (event.call_id, event.nested_for, event.nested_call_id)
        index = self._tool_indexes.get(key)
        if index is None:
            self._tool_indexes[key] = len(self._events)
            self._events.append(event)
            return
        self._events[index] = event

    def _apply_tool_result(self, event: ToolResultEvent) -> None:
        key = (event.call_id, event.nested_for, event.nested_call_id)
        index = self._tool_result_indexes.get(key)
        if index is None:
            self._tool_result_indexes[key] = len(self._events)
            self._events.append(event)
            return
        self._events[index] = event

    def _apply_subagent(self, event: SubagentTaskEvent) -> None:
        index = self._subagent_indexes.get(event.run_id)
        if index is None:
            self._subagent_indexes[event.run_id] = len(self._events)
            self._events.append(event)
            return
        self._events[index] = event

    def _rebuild_indexes(self) -> None:
        self._clear_indexes()
        for index, event in enumerate(self._events):
            if isinstance(event, (TextDeltaEvent, ThinkingDeltaEvent)):
                self._segment_indexes[_SegmentKey(
                    event_type="thinking" if event.type == "thinking_delta" else "text",
                    segment_id=event.segment_id,
                    nested_for=event.nested_for,
                    nested_call_id=event.nested_call_id,
                )] = index
            elif isinstance(event, ToolCallEvent):
                self._tool_indexes[(event.call_id, event.nested_for, event.nested_call_id)] = index
            elif isinstance(event, ToolResultEvent):
                self._tool_result_indexes[(event.call_id, event.nested_for, event.nested_call_id)] = index
            elif isinstance(event, SubagentTaskEvent):
                self._subagent_indexes[event.run_id] = index
