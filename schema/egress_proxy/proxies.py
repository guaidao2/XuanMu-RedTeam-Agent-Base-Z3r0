from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schema.common.responses import PaginatedResponse


class EgressProxyType(StrEnum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class EgressProxySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proxy_type: EgressProxyType
    proxy_host: str
    proxy_port: int
    proxy_account: str
    proxy_password: str
    created_at: datetime
    updated_at: datetime


class CreateEgressProxyRequest(BaseModel):
    proxy_type: EgressProxyType = EgressProxyType.HTTP
    proxy_host: str = Field(min_length=1, max_length=255)
    proxy_port: int = Field(ge=1, le=65535)
    proxy_account: str = Field(default="", max_length=255)
    proxy_password: str = Field(default="", max_length=512)

    @field_validator("proxy_host", "proxy_account", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UpdateEgressProxyRequest(BaseModel):
    proxy_type: EgressProxyType | None = None
    proxy_host: str | None = Field(default=None, min_length=1, max_length=255)
    proxy_port: int | None = Field(default=None, ge=1, le=65535)
    proxy_account: str | None = Field(default=None, max_length=255)
    proxy_password: str | None = Field(default=None, max_length=512)

    @field_validator("proxy_host", "proxy_account", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_has_updates(self):
        if all(
            value is None
            for value in (
                self.proxy_type,
                self.proxy_host,
                self.proxy_port,
                self.proxy_account,
                self.proxy_password,
            )
        ):
            raise ValueError("at least one field must be provided")
        return self


class DeleteEgressProxyResponse(BaseModel):
    id: int


class TestEgressProxyResponse(BaseModel):
    id: int
    success: bool
    status_code: int | None = None
    elapsed_ms: int
    message: str


class QueryEgressProxiesResponse(PaginatedResponse[EgressProxySchema]):
    pass
