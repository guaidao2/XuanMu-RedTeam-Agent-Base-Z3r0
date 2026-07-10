from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schema.agent.sessions import AgentSessionSummarySchema
from schema.common.responses import PaginatedResponse
from schema.sandbox.containers import SandboxContainerSchema
from schema.system_user.users import SystemUserRole
from schema.work_project.assets import WorkProjectAssetRequest, WorkProjectAssetSchema


# canonical work project status; reused by the model and by the public schema
class WorkProjectStatus(StrEnum):
    WORKING = "working"
    COMPLETED = "completed"
    CANCELED = "canceled"


# canonical work project type; reused by the model and by the public schema
class WorkProjectType(StrEnum):
    PENETRATION_TEST = "penetration_test"
    SOURCE_CODE_AUDIT = "source_code_audit"


class WorkProjectTaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


def _new_client_id() -> str:
    return uuid4().hex


class WorkProjectTaskSchema(BaseModel):
    id: str = Field(default_factory=_new_client_id, min_length=1, max_length=64, description="Stable task id.")
    title: str = Field(min_length=1, max_length=255, description="Short task title.")
    status: WorkProjectTaskStatus = Field(default=WorkProjectTaskStatus.TODO, description="Task status.")
    assignee: str = Field(default="", max_length=128, description="Agent code or owner responsible for this task.")
    progress: float = Field(default=0, ge=0, le=100, description="Task progress from 0 to 100 with at most two decimals.")
    summary: str = Field(default="", max_length=4000, description="Current concise task summary.")

    @field_validator("id", "title", "assignee", "summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("progress", mode="after")
    @classmethod
    def validate_progress_precision(cls, value: float) -> float:
        return _two_decimal_progress(value)


class WorkProjectAgentSummaryContentSchema(BaseModel):
    task_id: str = Field(default="", max_length=64, description="Related WorkProject task id when known.")
    task_title: str = Field(default="", max_length=255, description="Related task title when task_id is unavailable.")
    progress: float = Field(default=0, ge=0, le=100, description="This agent's subtask progress from 0 to 100 with at most two decimals.")
    status: str = Field(default="", max_length=2000, description="Current live status of this agent's work.")
    findings: list[str] = Field(default_factory=list, max_length=64, description="Confirmed findings or valuable negative results.")
    decisions: list[str] = Field(default_factory=list, max_length=64, description="Decisions or scope changes made by this agent.")
    blockers: list[str] = Field(default_factory=list, max_length=64, description="Current blockers or unresolved risks.")
    next_steps: list[str] = Field(default_factory=list, max_length=64, description="Concrete next actions.")
    notes: str = Field(default="", max_length=4000, description="Brief extra context that does not fit other fields.")

    @field_validator("task_id", "task_title", "status", "notes", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("findings", "decisions", "blockers", "next_steps", mode="after")
    @classmethod
    def normalize_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @field_validator("progress", mode="after")
    @classmethod
    def validate_progress_precision(cls, value: float) -> float:
        return _two_decimal_progress(value)


class WorkProjectAgentSummarySchema(BaseModel):
    agent_code: str = Field(min_length=1, max_length=32)
    summary: WorkProjectAgentSummaryContentSchema = Field(default_factory=WorkProjectAgentSummaryContentSchema)
    updated_at: datetime | None = None

    @field_validator("agent_code", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class WorkProjectOwnerSchema(BaseModel):
    id: int
    role: SystemUserRole
    username: str


# work project public data schema
class WorkProjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    owner_user_ids: list[int]
    owners: list[WorkProjectOwnerSchema]
    sandbox_container_ids: list[int]
    sandbox_containers: list[SandboxContainerSchema] = Field(default_factory=list)
    assets: list[WorkProjectAssetSchema]
    tasks: list[WorkProjectTaskSchema]
    agent_summaries: list[WorkProjectAgentSummarySchema]
    progress: float = Field(default=0, ge=0, le=100)
    session_count: int = 0
    status: WorkProjectStatus
    can_create_session: bool = False
    can_cancel: bool = False
    can_retry: bool = False
    type: WorkProjectType
    created_at: datetime
    updated_at: datetime

    @field_validator("progress", mode="after")
    @classmethod
    def validate_progress_precision(cls, value: float) -> float:
        return _two_decimal_progress(value)


class WorkProjectMetadataRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    owner_user_ids: list[int] = Field(default_factory=list, max_length=100)
    sandbox_container_ids: list[int] = Field(default_factory=list, max_length=100)
    assets: list[WorkProjectAssetRequest] = Field(min_length=1, max_length=500)
    type: WorkProjectType = WorkProjectType.PENETRATION_TEST

    @field_validator("name", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("owner_user_ids", mode="after")
    @classmethod
    def normalize_owner_user_ids(cls, value: list[int]) -> list[int]:
        return _unique_positive_ids(value)

    @field_validator("sandbox_container_ids", mode="after")
    @classmethod
    def normalize_sandbox_container_ids(cls, value: list[int]) -> list[int]:
        return _unique_positive_ids(value)


class CreateWorkProjectRequest(WorkProjectMetadataRequest):
    pass


class UpdateWorkProjectMetadataRequest(WorkProjectMetadataRequest):
    pass


# delete work project response schema (presence implies success)
class DeleteWorkProjectResponse(BaseModel):
    id: int


class CreateWorkProjectSessionResponse(BaseModel):
    session_id: str


class ListWorkProjectSessionsResponse(BaseModel):
    items: list[AgentSessionSummarySchema]


# query work projects response schema
class QueryWorkProjectsResponse(PaginatedResponse[WorkProjectSchema]):
    pass


def _unique_positive_ids(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value <= 0 or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _two_decimal_progress(value: float) -> float:
    if round(value, 2) != value:
        raise ValueError("progress must have at most two decimal places")
    return value
