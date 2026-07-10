from sqlmodel import Field, SQLModel


class AgentMessageMeta(SQLModel, table=True):
    """app-level attribution for each SDK-managed agent_messages row"""

    __tablename__ = "agent_message_meta"

    message_id: int = Field(
        primary_key=True,
        foreign_key="agent_messages.id",
        ondelete="CASCADE",
    )
    owner_code: str
    nested_for: str = ""
    nested_call_id: str = ""
