from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BlackboardNodeType(StrEnum):
    FACT = "fact"
    INTENT = "intent"
    HINT = "hint"


class BlackboardNodeStatus(StrEnum):
    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BlackboardNodeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    node_type: BlackboardNodeType
    status: BlackboardNodeStatus
    description: str
    parent_ids: str = "[]"  # JSON array
    creator_agent_code: str = ""
    session_id: str = ""
    confidence: float = 1.0
    extra: str = "{}"  # JSON
    created_at: datetime
    updated_at: datetime


class BlackboardCreateNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: BlackboardNodeType
    description: str = Field(min_length=1)
    parent_ids: list[int] = Field(default_factory=list)
    creator_agent_code: str = Field(default="", max_length=64)
    session_id: str = Field(default="", max_length=64)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extra: str = Field(default="{}")

    @field_validator("description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class BlackboardUpdateNodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BlackboardNodeStatus | None = None
    description: str | None = None
    parent_ids: list[int] | None = None
    confidence: float | None = None
    extra: str | None = None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class BlackboardSnapshotSchema(BaseModel):
    """Full blackboard graph for a project — all nodes + metadata."""

    project_id: int
    nodes: list[BlackboardNodeSchema]
    total_count: int
