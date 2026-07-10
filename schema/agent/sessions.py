from datetime import datetime
from enum import StrEnum

from typing import Any

from pydantic import BaseModel, Field, field_validator

from schema.agent.events import AgentContentEventSchema, AgentEventSchema, AgentInputPart, validate_agent_input_content


# canonical agent session type; reused by the model and by the public schema
class SessionType(StrEnum):
    CHAT = "chat"
    PROJECT = "project"


# agent session summary composed from SDK sessions + session metadata
class AgentSessionSummarySchema(BaseModel):
    session_id: str
    session_type: SessionType = SessionType.CHAT
    title: str = ""
    agent_code: str = ""
    owner_id: int = 0
    project_id: int | None = None
    selected_sandbox_container_id: int | None = None
    selected_sandbox_container_generation: int = 0
    is_running: bool = False
    runtime_agent_code: str = ""
    runtime_sandbox_container_id: int | None = None
    runtime_sandbox_container_generation: int = 0
    run_started_at: datetime | None = None
    run_finished_at: datetime | None = None
    run_error: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


# list agent sessions response schema
class ListAgentSessionsResponse(BaseModel):
    items: list[AgentSessionSummarySchema]


# a page of the persisted UI timeline log, ordered ascending by seq
class ListAgentEventsResponse(BaseModel):
    session_id: str
    items: list[AgentContentEventSchema]
    has_more: bool = False
    next_before_seq: int | None = None


class AgentTurnRequest(BaseModel):
    content: list[AgentInputPart] = Field(min_length=1, max_length=8)
    agent_code: str | None = Field(min_length=1, max_length=32)
    sandbox_container_id: int | None = Field(gt=0)

    @field_validator("content", mode="after")
    @classmethod
    def validate_content(cls, value: list[AgentInputPart]) -> list[AgentInputPart]:
        validate_agent_input_content(value)
        return value


class AgentTurnResponse(BaseModel):
    session_id: str
    session: AgentSessionSummarySchema
    events: list[AgentEventSchema]


class UpdateAgentSessionTitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UpdateAgentSessionSandboxContainerRequest(BaseModel):
    sandbox_container_id: int | None = Field(gt=0)


# one available agent; surfaced to the @-mention picker in the chat input
class AgentInfoSchema(BaseModel):
    code: str
    name: str
    description: str = ""


# list of agents + the default agent for brand-new sessions
class ListAgentsResponse(BaseModel):
    items: list[AgentInfoSchema]
    default_code: str
