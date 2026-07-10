from datetime import datetime

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from schema.agent.subordinates import AgentSubordinateStatus


_AGENT_SUBORDINATE_STATUS_COLUMN = Column(
    String(32),
    index=True,
    nullable=False,
)


class AgentSubordinateTask(SQLModel, table=True):
    """Persistent lifecycle row for a delegated subagent run."""

    __tablename__ = "agent_subordinates"

    run_id: str = Field(primary_key=True)
    session_id: str = Field(
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
        index=True,
    )
    parent_agent_code: str = Field(default="", index=True)
    parent_agent_instance_id: str = Field(default="", index=True)
    agent_code: str = Field(default="", index=True)
    agent_name: str = ""
    status: AgentSubordinateStatus = Field(
        default=AgentSubordinateStatus.RUNNING,
        sa_column=_AGENT_SUBORDINATE_STATUS_COLUMN,
    )
    brief: str = ""
    result: str = ""
    error: str = ""
    progress: str = ""
    nested_call_id: str = Field(default="", index=True)
    owner_id: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
