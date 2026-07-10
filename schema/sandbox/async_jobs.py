from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class SandboxAsyncJobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class SandboxAsyncJobSnapshot(BaseModel):
    run_id: str
    session_id: str
    agent_code: str
    agent_instance_id: str
    command: str = ""
    output_file: str = ""
    status: SandboxAsyncJobStatus
    exit_code: int | None = None
    output_bytes: int = 0
    output_lines: int = 0
    error: str = ""
    nested_for_agent_code: str = ""
    nested_call_id: str = ""
    sandbox_container_id: int | None = None
    sandbox_container_generation: int = 0
    sandbox_skill_metadata: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
