from datetime import datetime

from sqlalchemy import BigInteger, Column, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class AgentEventLog(SQLModel, table=True):
    """Append/upsert log of UI wire events for a session timeline.

    This is the single source of truth for the rendered transcript. Each row
    is one logical timeline item (a text/thinking segment, a tool call, a tool
    result, a subagent task, a user message, a turn boundary, or an error),
    addressed by a stable ``item_key`` so streaming updates upsert in place.

    ``seq`` is a per-session monotonic ordinal assigned at first sight of an
    ``item_key`` and never changes afterwards, so it doubles as the display
    order and the pagination cursor. It is fully decoupled from the SDK's
    ``agent_messages`` (which remain the model context store).
    """

    __tablename__ = "agent_event_log"
    __table_args__ = (
        UniqueConstraint("session_id", "item_key", name="uq_agent_event_log_session_item"),
        Index("ix_agent_event_log_session_seq", "session_id", "seq"),
    )

    id: int | None = Field(default=None, sa_column=Column(BigInteger, primary_key=True, autoincrement=True))
    session_id: str = Field(
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
        index=True,
    )
    seq: int = Field(sa_column=Column(BigInteger, nullable=False))
    item_key: str = Field(sa_column=Column(Text, nullable=False))
    payload: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now)
