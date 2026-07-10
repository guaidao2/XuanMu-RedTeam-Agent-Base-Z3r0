from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

class WorkProjectFindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkProjectFindingStatus(StrEnum):
    SUSPECTED = "suspected"
    VALIDATED = "validated"
    FALSE_POSITIVE = "false_positive"


class WorkProjectFindingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    asset_id: int | None = None
    edge_id: int | None = None
    title: str
    severity: WorkProjectFindingSeverity
    status: WorkProjectFindingStatus
    description: str = ""
    impact: str = ""
    created_by_agent_code: str = ""
    created_from_session_id: str = ""
    created_at: datetime
    updated_at: datetime
    validated_at: datetime | None = None


class WorkProjectFindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int | None = Field(default=None, gt=0, description="Asset this finding is about.")
    edge_id: int | None = Field(default=None, gt=0, description="Relationship edge this finding substantiates, when it backs a relation or attack step.")
    title: str = Field(min_length=1, max_length=255)
    severity: WorkProjectFindingSeverity = WorkProjectFindingSeverity.INFO
    status: WorkProjectFindingStatus = WorkProjectFindingStatus.SUSPECTED
    description: str = Field(default="", max_length=8000)
    impact: str = Field(default="", max_length=8000)

    @field_validator("title", "description", "impact", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value
