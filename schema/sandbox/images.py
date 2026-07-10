from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schema.common.responses import PaginatedResponse


# sandbox image public data schema
class SandboxImageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_name: str
    control_proxy_port: int = Field(title="Control Port")
    supports_tor: bool
    created_at: datetime
    updated_at: datetime


# create sandbox image request schema
class CreateSandboxImageRequest(BaseModel):
    image_name: str = Field(min_length=1, max_length=255)
    control_proxy_port: int = Field(default=8000, ge=1, le=65535, title="Control Port")
    supports_tor: bool = False

    @field_validator("image_name", mode="before")
    @classmethod
    def normalize_image_name(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


# delete sandbox image response schema (presence implies success)
class DeleteSandboxImageResponse(BaseModel):
    id: int


# query sandbox images response schema
class QuerySandboxImagesResponse(PaginatedResponse[SandboxImageSchema]):
    pass
