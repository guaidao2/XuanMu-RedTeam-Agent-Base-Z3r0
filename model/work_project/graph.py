from datetime import datetime

from sqlalchemy import Column, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from schema.work_project.graph import (
    WorkProjectAttackPathStatus,
    WorkProjectGraphEdgeType,
)


class WorkProjectGraphEdge(SQLModel, table=True):
    """A relationship between two project assets. Assets are the graph nodes."""

    __tablename__ = "work_project_graph_edges"
    __table_args__ = (
        UniqueConstraint("project_id", "source_asset_id", "target_asset_id", "type", name="uq_work_project_graph_edge"),
        Index("ix_work_project_graph_edges_project_type", "project_id", "type"),
        Index("ix_work_project_graph_edges_source", "source_asset_id"),
        Index("ix_work_project_graph_edges_target", "target_asset_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")
    source_asset_id: int = Field(foreign_key="work_project_assets.id", index=True, ondelete="CASCADE")
    target_asset_id: int = Field(foreign_key="work_project_assets.id", index=True, ondelete="CASCADE")
    type: WorkProjectGraphEdgeType = Field(default=WorkProjectGraphEdgeType.RELATED, sa_column=Column(String(32), nullable=False))
    label: str = Field(default="")
    created_by_agent_code: str = Field(default="", index=True)
    created_from_session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorkProjectAttackPath(SQLModel, table=True):
    __tablename__ = "work_project_attack_paths"
    __table_args__ = (
        Index("ix_work_project_attack_paths_project_status", "project_id", "status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")
    title: str = Field(default="", index=True)
    status: WorkProjectAttackPathStatus = Field(default=WorkProjectAttackPathStatus.SUSPECTED, sa_column=Column(String(32), nullable=False))
    summary: str = Field(default="")
    created_by_agent_code: str = Field(default="", index=True)
    created_from_session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorkProjectAttackPathStep(SQLModel, table=True):
    """One ordered hop of an attack path, pointing at the relationship edge it traverses."""

    __tablename__ = "work_project_attack_path_steps"
    __table_args__ = (
        UniqueConstraint("path_id", "sequence", name="uq_work_project_attack_path_step_sequence"),
        Index("ix_work_project_attack_path_steps_project_path", "project_id", "path_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")
    path_id: int = Field(foreign_key="work_project_attack_paths.id", index=True, ondelete="CASCADE")
    sequence: int = Field(index=True)
    edge_id: int = Field(foreign_key="work_project_graph_edges.id", index=True, ondelete="CASCADE")
    created_by_agent_code: str = Field(default="", index=True)
    created_from_session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
