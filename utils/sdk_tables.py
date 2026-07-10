from sqlalchemy import Column, Integer, String, TIMESTAMP, Table, Text
from sqlmodel import SQLModel


# placeholder row written by the SDK bootstrap in database.py
BOOTSTRAP_SESSION_ID = "__bootstrap__"

# minimal projection of the SDK-managed session storage tables; registered on
# SQLModel.metadata so app-side FKs (AgentSessionMeta, AgentMessageMeta) can
# resolve in the same metadata. The actual schema is owned by the SDK; SDK
# creates the tables first in database.create_all_tables(), so SQLModel's own
# create_all sees them already present and skips (checkfirst=True default).
metadata = SQLModel.metadata

agent_sessions = Table(
    "agent_sessions",
    metadata,
    Column("session_id", String, primary_key=True),
    Column("created_at", TIMESTAMP(timezone=False), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=False), nullable=False),
    extend_existing=True,
)

agent_messages = Table(
    "agent_messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("message_data", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=False), nullable=False),
    extend_existing=True,
)
