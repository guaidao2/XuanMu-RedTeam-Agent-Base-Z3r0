from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Column, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from schema.agent.notifications import AgentNotificationKind, AgentNotificationStatus, SYSTEM_NOTIFICATION_PRIORITY


_AGENT_NOTIFICATION_KIND_COLUMN = Column(String(64), index=True, nullable=False)
_AGENT_NOTIFICATION_STATUS_COLUMN = Column(String(32), index=True, nullable=False)


class AgentNotification(SQLModel, table=True):
    """Durable inbox item for agent turn resumption.

    Covers system-generated signals (subagent finished, async command done) AND
    user messages queued while the agent loop is already running.
    """

    __tablename__ = "agent_notifications"
    __table_args__ = (
        UniqueConstraint("kind", "run_id", name="uq_agent_notifications_kind_run_id"),
    )

    id: str = Field(primary_key=True)
    session_id: str = Field(
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
        index=True,
    )
    target_agent_code: str = Field(default="", index=True)
    target_agent_instance_id: str = Field(default="", index=True)
    nested_for_agent_code: str = Field(default="", index=True)
    nested_call_id: str = Field(default="", index=True)
    sandbox_container_id: int | None = Field(default=None, index=True)
    sandbox_container_generation: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    sandbox_skill_metadata: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    kind: AgentNotificationKind = Field(
        default=AgentNotificationKind.SUBAGENT_FINISHED,
        sa_column=_AGENT_NOTIFICATION_KIND_COLUMN,
    )
    status: AgentNotificationStatus = Field(
        default=AgentNotificationStatus.PENDING,
        sa_column=_AGENT_NOTIFICATION_STATUS_COLUMN,
    )
    priority: int = Field(default=SYSTEM_NOTIFICATION_PRIORITY, sa_column=Column(Integer, nullable=False, server_default="0"))
    run_id: str = Field(default="", index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
