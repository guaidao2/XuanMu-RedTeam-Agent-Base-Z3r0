from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkProjectGraphEdgeType(StrEnum):
    # Structural relations describe the target architecture.
    RELATED = "related"
    RESOLVES_TO = "resolves_to"
    HOSTS = "hosts"
    CONNECTS_TO = "connects_to"
    TRUSTS = "trusts"
    # Offensive relations describe how an attack progresses across the graph.
    EXPLOITS = "exploits"
    PIVOTS_TO = "pivots_to"
    LEADS_TO = "leads_to"


class WorkProjectGraphEdgeCategory(StrEnum):
    STRUCTURAL = "structural"
    OFFENSIVE = "offensive"


# Category is a pure function of edge type, so it is derived rather than stored.
# It is serialized to the frontend contract from this single map by scripts/export_schema.py.
EDGE_TYPE_CATEGORY: dict[WorkProjectGraphEdgeType, WorkProjectGraphEdgeCategory] = {
    WorkProjectGraphEdgeType.RELATED: WorkProjectGraphEdgeCategory.STRUCTURAL,
    WorkProjectGraphEdgeType.RESOLVES_TO: WorkProjectGraphEdgeCategory.STRUCTURAL,
    WorkProjectGraphEdgeType.HOSTS: WorkProjectGraphEdgeCategory.STRUCTURAL,
    WorkProjectGraphEdgeType.CONNECTS_TO: WorkProjectGraphEdgeCategory.STRUCTURAL,
    WorkProjectGraphEdgeType.TRUSTS: WorkProjectGraphEdgeCategory.STRUCTURAL,
    WorkProjectGraphEdgeType.EXPLOITS: WorkProjectGraphEdgeCategory.OFFENSIVE,
    WorkProjectGraphEdgeType.PIVOTS_TO: WorkProjectGraphEdgeCategory.OFFENSIVE,
    WorkProjectGraphEdgeType.LEADS_TO: WorkProjectGraphEdgeCategory.OFFENSIVE,
}


class WorkProjectAttackPathStatus(StrEnum):
    SUSPECTED = "suspected"
    VALIDATED = "validated"
    BLOCKED = "blocked"
    CLOSED = "closed"


class WorkProjectGraphEdgeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    source_asset_id: int
    target_asset_id: int
    type: WorkProjectGraphEdgeType
    label: str = ""
    created_by_agent_code: str = ""
    created_from_session_id: str = ""
    created_at: datetime
    updated_at: datetime


class WorkProjectAttackPathSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    status: WorkProjectAttackPathStatus
    summary: str = ""
    created_by_agent_code: str = ""
    created_from_session_id: str = ""
    created_at: datetime
    updated_at: datetime


class WorkProjectAttackPathStepSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    path_id: int
    sequence: int
    edge_id: int
    created_by_agent_code: str = ""
    created_from_session_id: str = ""
    created_at: datetime
    updated_at: datetime


class WorkProjectGraphEdgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_asset_id: int = Field(gt=0)
    target_asset_id: int = Field(gt=0)
    type: WorkProjectGraphEdgeType = WorkProjectGraphEdgeType.RELATED
    label: str = Field(default="", max_length=255)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_endpoints(self) -> "WorkProjectGraphEdgeRequest":
        if self.source_asset_id == self.target_asset_id:
            raise ValueError("graph edge cannot connect an asset to itself")
        return self


class WorkProjectAttackPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    status: WorkProjectAttackPathStatus = WorkProjectAttackPathStatus.SUSPECTED
    summary: str = Field(default="", max_length=4000)

    @field_validator("title", "summary", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class WorkProjectAttackPathStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(gt=0)
    edge_id: int = Field(gt=0)


class WorkProjectGraphSnapshotSchema(BaseModel):
    edges: list[WorkProjectGraphEdgeSchema]
    attack_paths: list[WorkProjectAttackPathSchema]
    attack_path_steps: list[WorkProjectAttackPathStepSchema]
