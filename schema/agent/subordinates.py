from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# UI event preview length (timeline / side panel).
SUBAGENT_TASK_EVENT_PREVIEW_CHARS = 3000
# Default slice length returned by ``read_subagent_task``; agents page with offset.
SUBAGENT_TASK_RESULT_CHUNK_CHARS = 3000


class AgentSubordinateStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class AgentSubordinateTaskSnapshot(BaseModel):
    run_id: str
    session_id: str
    parent_agent_code: str
    parent_agent_instance_id: str = ""
    agent_code: str
    agent_name: str = ""
    status: AgentSubordinateStatus
    brief: str = ""
    result: str = ""
    error: str = ""
    progress: str = ""
    nested_call_id: str = ""
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentSubordinateTaskToolItem(BaseModel):
    run_id: str
    agent_code: str
    agent_name: str = ""
    status: AgentSubordinateStatus
    # ``result`` / ``error`` carry a slice starting at the offset passed to
    # ``read_subagent_task`` (default 0). ``next_offset`` is the offset to use
    # for the following slice and is ``None`` once the body has been fully read.
    # ``list_subagent_tasks`` omits the bodies entirely.
    result: str = ""
    error: str = ""
    result_chars: int = 0
    error_chars: int = 0
    next_offset: int | None = None
    progress: str = ""


class AgentSubordinateTaskToolResult(BaseModel):
    task: AgentSubordinateTaskToolItem | None = None
    tasks: list[AgentSubordinateTaskToolItem] = Field(default_factory=list)
    message: str = ""
