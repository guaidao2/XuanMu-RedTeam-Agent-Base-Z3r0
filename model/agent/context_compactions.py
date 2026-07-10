from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class AgentContextCompaction(SQLModel, table=True):
    """App-owned context summary projection for SDK-managed messages."""

    __tablename__ = "agent_context_compactions"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "viewer_agent_code",
            "nested_for",
            "nested_call_id",
            name="uq_agent_context_compactions_scope",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
        index=True,
    )
    viewer_agent_code: str = Field(index=True)
    nested_for: str = Field(default="", index=True)
    nested_call_id: str = Field(default="", index=True)
    start_message_id: int = Field(index=True)
    end_message_id: int = Field(index=True)
    summary_item: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    source_item_count: int = 0
    source_token_estimate: int = 0
    summary_token_estimate: int = 0
    model: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
