from datetime import datetime

from sqlalchemy import BigInteger, Column
from sqlmodel import Field, SQLModel

from schema.agent.sessions import SessionType


class AgentSessionMeta(SQLModel, table=True):
    """1:1 app-level attribution for a SDK agent_sessions row; cascades on delete."""

    __tablename__ = "agent_session_meta"

    session_id: str = Field(
        primary_key=True,
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
    )
    session_type: SessionType = Field(default=SessionType.CHAT, index=True)
    title: str = ""
    agent_code: str = Field(default="")
    owner_id: int = Field(default=0, index=True)
    project_id: int | None = Field(default=None, foreign_key="work_projects.id", index=True)
    selected_sandbox_container_id: int | None = Field(default=None, index=True)
    selected_sandbox_container_generation: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    is_running: bool = Field(default=False, index=True)
    runtime_agent_code: str = Field(default="")
    runtime_sandbox_container_id: int | None = Field(default=None, index=True)
    runtime_sandbox_container_generation: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    run_started_at: datetime | None = Field(default=None)
    run_finished_at: datetime | None = Field(default=None)
    run_error: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
