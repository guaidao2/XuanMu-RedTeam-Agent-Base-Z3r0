from pydantic import BaseModel, Field

from schema.sandbox.async_jobs import SandboxAsyncJobStatus


class SandboxCommandResultMetadata(BaseModel):
    status: SandboxAsyncJobStatus
    exit_code: int | None = None
    output_file: str | None = None
    output_bytes: int = Field(default=0, ge=0)
    output_lines: int = Field(default=0, ge=0)
    run_id: str | None = None
    error: str | None = None


class SandboxCommandOutputChunk(BaseModel):
    output_file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = ""
