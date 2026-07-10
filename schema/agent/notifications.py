from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentNotificationKind(StrEnum):
    SUBAGENT_FINISHED = "subagent_finished"
    SANDBOX_ASYNC_JOB_FINISHED = "sandbox_async_job_finished"
    USER_MESSAGE = "user_message"


class AgentNotificationStatus(StrEnum):
    # Obligation registered for an in-flight background task that will later
    # produce a result. Counts as outstanding work but is not claimable.
    AWAITING = "awaiting"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# Statuses that represent work the session driver must still wait for: an
# unfinished obligation (AWAITING), a ready-but-unclaimed item (PENDING), or an
# item currently being handled (PROCESSING). This is the single source of truth
# for session liveness / idle detection.
OUTSTANDING_NOTIFICATION_STATUSES = (
    AgentNotificationStatus.AWAITING,
    AgentNotificationStatus.PENDING,
    AgentNotificationStatus.PROCESSING,
)


USER_MESSAGE_PRIORITY = 10
SYSTEM_NOTIFICATION_PRIORITY = 0


class AgentNotificationSnapshot(BaseModel):
    id: str
    session_id: str
    target_agent_code: str
    target_agent_instance_id: str
    nested_for_agent_code: str = ""
    nested_call_id: str = ""
    kind: AgentNotificationKind
    status: AgentNotificationStatus
    priority: int = SYSTEM_NOTIFICATION_PRIORITY
    run_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    sandbox_container_id: int | None = None
    sandbox_container_generation: int = 0
    sandbox_skill_metadata: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # --- User-message-specific fields (populated only for USER_MESSAGE) ---
    user_content: list[dict[str, Any]] | None = None
    user_display_text: str = ""
    user_requested_agent_code: str = ""

    @property
    def is_user_message(self) -> bool:
        return self.kind == AgentNotificationKind.USER_MESSAGE
