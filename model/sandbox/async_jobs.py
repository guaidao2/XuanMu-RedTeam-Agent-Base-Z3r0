from datetime import datetime

from sqlalchemy import BigInteger, Column, JSON, String
from sqlmodel import Field, SQLModel

from schema.sandbox.async_jobs import SandboxAsyncJobStatus


_ASYNC_JOB_STATUS_COLUMN = Column(String(32), index=True, nullable=False)


class SandboxAsyncJob(SQLModel, table=True):
    """Persistent lifecycle row for a sandbox async command."""

    __tablename__ = "sandbox_async_jobs"

    run_id: str = Field(primary_key=True)
    session_id: str = Field(index=True)
    agent_code: str = Field(default="", index=True)
    agent_instance_id: str = Field(default="", index=True)
    command: str = ""
    output_file: str = ""
    status: SandboxAsyncJobStatus = Field(default=SandboxAsyncJobStatus.RUNNING, sa_column=_ASYNC_JOB_STATUS_COLUMN)
    exit_code: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    output_bytes: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    output_lines: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    error: str = ""
    nested_for_agent_code: str = Field(default="", index=True)
    nested_call_id: str = Field(default="", index=True)
    sandbox_container_id: int | None = Field(default=None, index=True)
    sandbox_container_generation: int = Field(default=0, sa_column=Column(BigInteger, nullable=False))
    sandbox_skill_metadata: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
