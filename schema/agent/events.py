from enum import StrEnum
from datetime import datetime
import base64
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

from schema.agent.subordinates import AgentSubordinateStatus


class AgentEventTypeSchema(StrEnum):
    USER_MESSAGE = "user_message"
    TURN_BOUNDARY = "turn_boundary"
    RUN_STATE = "run_state"
    THINKING_DELTA = "thinking_delta"
    THINKING_COMPLETE = "thinking_complete"
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUBAGENT_TASK = "subagent_task"
    DONE = "done"
    ERROR = "error"


class AgentInputPartTypeSchema(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class AgentImageDetailSchema(StrEnum):
    AUTO = "auto"
    LOW = "low"
    HIGH = "high"


class AgentImageMediaTypeSchema(StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"


_MAX_IMAGE_BASE64_LENGTH = 5 * 1024 * 1024
_MAX_MESSAGE_BASE64_LENGTH = 8 * 1024 * 1024
MAX_AGENT_TEXT_INPUT_CHARS = 20000


class AgentTextInputPart(BaseModel):
    type: Literal[AgentInputPartTypeSchema.TEXT] = AgentInputPartTypeSchema.TEXT
    text: str = Field(min_length=1, max_length=MAX_AGENT_TEXT_INPUT_CHARS)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class AgentImageInputPart(BaseModel):
    type: Literal[AgentInputPartTypeSchema.IMAGE] = AgentInputPartTypeSchema.IMAGE
    media_type: AgentImageMediaTypeSchema
    data: str = Field(min_length=1, max_length=_MAX_IMAGE_BASE64_LENGTH)
    detail: AgentImageDetailSchema = AgentImageDetailSchema.AUTO

    @field_validator("data")
    @classmethod
    def validate_base64_data(cls, value: str) -> str:
        compact = "".join(value.split())
        if compact.startswith("data:"):
            raise ValueError("image data must be raw base64 without a data URL prefix")
        try:
            base64.b64decode(compact, validate=True)
        except Exception as exc:
            raise ValueError("image data must be valid base64") from exc
        return compact


AgentInputPart = Annotated[
    AgentTextInputPart | AgentImageInputPart,
    Field(discriminator="type"),
]


class _AgentScopedEvent(BaseModel):
    created_at: datetime
    # per-session monotonic timeline ordinal stamped by the runtime event bus;
    # 0 for control-only frames (run_state/done) that never enter the timeline
    seq: int = 0
    agent_name: str = ""
    # when set, this event was streamed from inside a nested subagent call.
    # `nested_for` is the parent agent code; `nested_call_id` matches the
    # parent's function_call.call_id so the UI can attach the event to the
    # corresponding ToolCard
    nested_for: str = ""
    nested_call_id: str = ""


class UserMessageEvent(BaseModel):
    type: Literal[AgentEventTypeSchema.USER_MESSAGE] = AgentEventTypeSchema.USER_MESSAGE
    created_at: datetime
    seq: int = 0
    content: list[AgentInputPart] = Field(min_length=1)
    display_text: str = ""
    # the agent this message was @-mentioned to; UI renders it as a "@<name>" chip
    target_agent_code: str = ""


class TurnBoundaryEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TURN_BOUNDARY] = AgentEventTypeSchema.TURN_BOUNDARY


class RunStateEvent(BaseModel):
    type: Literal[AgentEventTypeSchema.RUN_STATE] = AgentEventTypeSchema.RUN_STATE
    created_at: datetime
    seq: int = 0
    running: bool


class TextDeltaEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TEXT_DELTA] = AgentEventTypeSchema.TEXT_DELTA
    segment_id: str
    delta: str
    text: str


class TextCompleteEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TEXT_COMPLETE] = AgentEventTypeSchema.TEXT_COMPLETE
    segment_id: str
    text: str


class ThinkingDeltaEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.THINKING_DELTA] = AgentEventTypeSchema.THINKING_DELTA
    segment_id: str
    delta: str
    text: str


class ThinkingCompleteEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.THINKING_COMPLETE] = AgentEventTypeSchema.THINKING_COMPLETE
    segment_id: str
    text: str


class ToolCallEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TOOL_CALL] = AgentEventTypeSchema.TOOL_CALL
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TOOL_RESULT] = AgentEventTypeSchema.TOOL_RESULT
    call_id: str
    output: str = ""
    is_error: bool = False


class SubagentTaskEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.SUBAGENT_TASK] = AgentEventTypeSchema.SUBAGENT_TASK
    run_id: str
    parent_agent_code: str = ""
    parent_agent_instance_id: str = ""
    agent_code: str
    status: AgentSubordinateStatus
    result_preview: str = ""
    error_preview: str = ""
    result_chars: int = 0
    error_chars: int = 0
    truncated: bool = False
    progress: str = ""


class DoneEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.DONE] = AgentEventTypeSchema.DONE


class ErrorEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.ERROR] = AgentEventTypeSchema.ERROR
    message: str
    code: str = ""


# everything that shows up in stored history (DoneEvent is a stream control signal only)
AgentContentEventSchema = Annotated[
    UserMessageEvent
    | TurnBoundaryEvent
    | TextDeltaEvent
    | TextCompleteEvent
    | ThinkingDeltaEvent
    | ThinkingCompleteEvent
    | ToolCallEvent
    | ToolResultEvent
    | SubagentTaskEvent
    | ErrorEvent,
    Field(discriminator="type"),
]

AgentEventSchema = Annotated[
    UserMessageEvent
    | TurnBoundaryEvent
    | RunStateEvent
    | TextDeltaEvent
    | TextCompleteEvent
    | ThinkingDeltaEvent
    | ThinkingCompleteEvent
    | ToolCallEvent
    | ToolResultEvent
    | SubagentTaskEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


def validate_agent_input_content(content: list[AgentInputPart]) -> None:
    image_count = sum(1 for part in content if isinstance(part, AgentImageInputPart))
    if image_count > 4:
        raise ValueError("at most 4 images are allowed in one message")
    image_bytes = sum(len(part.data) for part in content if isinstance(part, AgentImageInputPart))
    if image_bytes > _MAX_MESSAGE_BASE64_LENGTH:
        raise ValueError("image payload is too large")
