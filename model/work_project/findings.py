from datetime import datetime

from sqlalchemy import Column, Index, String
from sqlmodel import Field, SQLModel

from schema.work_project.findings import (
    WorkProjectFindingSeverity,
    WorkProjectFindingStatus,
)


class WorkProjectFinding(SQLModel, table=True):
    __tablename__ = "work_project_findings"
    __table_args__ = (
        Index("ix_work_project_findings_project_status", "project_id", "status"),
        Index("ix_work_project_findings_project_severity", "project_id", "severity"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")
    asset_id: int | None = Field(default=None, foreign_key="work_project_assets.id", index=True, ondelete="SET NULL")
    edge_id: int | None = Field(default=None, foreign_key="work_project_graph_edges.id", index=True, ondelete="SET NULL")
    title: str = Field(default="", index=True)
    severity: WorkProjectFindingSeverity = Field(default=WorkProjectFindingSeverity.INFO, sa_column=Column(String(32), nullable=False))
    status: WorkProjectFindingStatus = Field(default=WorkProjectFindingStatus.SUSPECTED, sa_column=Column(String(32), nullable=False))
    description: str = Field(default="")
    impact: str = Field(default="")
    created_by_agent_code: str = Field(default="", index=True)
    created_from_session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    validated_at: datetime | None = Field(default=None)
