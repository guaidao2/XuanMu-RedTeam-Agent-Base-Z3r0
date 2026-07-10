from datetime import datetime
from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schema.common.responses import PaginatedResponse


class ManagedHostSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ip_address: str
    ssh_port: int
    host_account: str
    host_password: str
    docker_management_port: int
    docker_tls_enabled: bool
    docker_client_ca_cert: str
    docker_client_cert: str
    docker_client_key: str
    created_at: datetime
    updated_at: datetime


class CreateManagedHostRequest(BaseModel):
    ip_address: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    host_account: str = Field(min_length=1, max_length=128)
    host_password: str = Field(min_length=1, max_length=512)
    docker_management_port: int = Field(default=2375, ge=1, le=65535)
    docker_tls_enabled: bool = False
    docker_client_ca_cert: str = ""
    docker_client_cert: str = ""
    docker_client_key: str = ""

    @field_validator(
        "ip_address",
        "host_account",
        "docker_client_ca_cert",
        "docker_client_cert",
        "docker_client_key",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str) -> str:
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("ip address must be a valid IPv4 or IPv6 address") from exc

    @model_validator(mode="after")
    def validate_docker_tls_certificates(self):
        if self.docker_tls_enabled and not all((
            self.docker_client_ca_cert,
            self.docker_client_cert,
            self.docker_client_key,
        )):
            raise ValueError("docker TLS CA certificate, client certificate, and client key are required")
        if not self.docker_tls_enabled:
            self.docker_client_ca_cert = ""
            self.docker_client_cert = ""
            self.docker_client_key = ""
        return self


class UpdateManagedHostRequest(BaseModel):
    ip_address: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    host_account: str | None = Field(default=None, min_length=1, max_length=128)
    host_password: str | None = Field(default=None, min_length=1, max_length=512)
    docker_management_port: int | None = Field(default=None, ge=1, le=65535)
    docker_tls_enabled: bool | None = None
    docker_client_ca_cert: str | None = None
    docker_client_cert: str | None = None
    docker_client_key: str | None = None

    @field_validator(
        "ip_address",
        "host_account",
        "docker_client_ca_cert",
        "docker_client_cert",
        "docker_client_key",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("ip address must be a valid IPv4 or IPv6 address") from exc

    @model_validator(mode="after")
    def validate_has_updates(self):
        if all(
            value is None
            for value in (
                self.ip_address,
                self.ssh_port,
                self.host_account,
                self.host_password,
                self.docker_management_port,
                self.docker_tls_enabled,
                self.docker_client_ca_cert,
                self.docker_client_cert,
                self.docker_client_key,
            )
        ):
            raise ValueError("at least one field must be provided")
        return self


class DeleteManagedHostResponse(BaseModel):
    id: int


class QueryManagedHostsResponse(PaginatedResponse[ManagedHostSchema]):
    pass


class ManagedHostImageSchema(BaseModel):
    image_name: str
    image_id: str = ""
    image_hash: str = ""
    image_size: int = Field(default=0, json_schema_extra={"format": "int64"})
    created_at: datetime | None = None


class PullManagedHostImagesRequest(BaseModel):
    image_names: list[str] = Field(min_length=1, max_length=100)

    @field_validator("image_names", mode="after")
    @classmethod
    def normalize_image_names(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            image_name = item.strip() if isinstance(item, str) else ""
            if not image_name or image_name in seen:
                continue
            result.append(image_name)
            seen.add(image_name)
        if not result:
            raise ValueError("at least one image name is required")
        return result


class PullManagedHostImageResultSchema(BaseModel):
    image_name: str
    success: bool
    message: str = ""


class PullManagedHostImagesResponse(BaseModel):
    items: list[PullManagedHostImageResultSchema]


class DeleteManagedHostImageRequest(BaseModel):
    image_id: str = Field(min_length=1, max_length=255)
    force: bool = False


class ListManagedHostImagesResponse(BaseModel):
    items: list[ManagedHostImageSchema]
