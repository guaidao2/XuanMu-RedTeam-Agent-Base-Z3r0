from datetime import datetime

from sqlalchemy import Column, Index, Text
from sqlmodel import Field, SQLModel


class BlackboardNode(SQLModel, table=True):
    """A node in the shared blackboard graph — fact, intent, or hint.

    The blackboard is a shared reasoning graph that all agents read and write
    to coordinate indirectly (Stigmergy). It sits alongside the existing
    WorkProject evidence model (Asset / Finding / GraphEdge) as a process
    layer: "why we looked, what we found, what's next".
    """

    __tablename__ = "blackboard_nodes"
    __table_args__ = (
        Index("ix_bb_project_type", "project_id", "node_type"),
        Index("ix_bb_project_status", "project_id", "status"),
        Index("ix_bb_project_creator", "project_id", "creator_agent_code"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")

    # node type: "fact" | "intent" | "hint"
    node_type: str = Field(sa_column=Column("node_type", Text, nullable=False))
    # lifecycle: proposed | in_progress | confirmed | rejected | superseded
    status: str = Field(default="proposed", sa_column=Column("status", Text, nullable=False))

    description: str = Field(sa_column=Column("description", Text, nullable=False))
    # JSON array of parent node IDs, forming the directed graph edges
    parent_ids: str = Field(default="[]", sa_column=Column("parent_ids", Text, nullable=False))

    creator_agent_code: str = Field(default="", index=True)
    session_id: str = Field(default="", index=True)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    # Arbitrary JSON payload (e.g. tool output refs, evidence links)
    extra: str = Field(default="{}", sa_column=Column("extra_json", Text, nullable=False))

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
