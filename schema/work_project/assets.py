import ipaddress
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class WorkProjectAssetType(StrEnum):
    SERVICE = "service"
    DOMAIN = "domain"
    NETWORK = "network"
    BINARY = "binary"


class WorkProjectAssetOrigin(StrEnum):
    SCOPE = "scope"
    DISCOVERED = "discovered"


class WorkProjectAssetExtraSchema(BaseModel):
    """Recon metadata attached to an asset. Kept small on purpose."""

    model_config = ConfigDict(extra="forbid")

    banner: str = Field(default="", max_length=512)

    @field_validator("banner", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


def build_asset_identifier(
    asset_type: WorkProjectAssetType,
    host: str,
    port: int | None,
    path: str,
) -> str:
    """Canonical primary identifier used to distinguish assets within a project."""
    host = host.strip().lower()
    path = path.strip()
    if asset_type == WorkProjectAssetType.BINARY:
        return path
    if asset_type == WorkProjectAssetType.SERVICE:
        return f"{host}:{port}" if port else host
    return host


class WorkProjectAssetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    type: WorkProjectAssetType
    origin: WorkProjectAssetOrigin
    identifier: str
    host: str = ""
    port: int | None = None
    path: str = ""
    extra: WorkProjectAssetExtraSchema = Field(default_factory=WorkProjectAssetExtraSchema)
    created_by_agent_code: str = ""
    created_from_session_id: str = ""
    created_at: datetime
    updated_at: datetime


class WorkProjectAssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: WorkProjectAssetType
    host: str = Field(default="", max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    path: str = Field(default="", max_length=500)
    extra: WorkProjectAssetExtraSchema = Field(default_factory=WorkProjectAssetExtraSchema)

    @field_validator("host", "path", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_required_fields(self) -> "WorkProjectAssetRequest":
        if self.type == WorkProjectAssetType.BINARY:
            if not self.path:
                raise ValueError("binary asset path is required")
            self.host = ""
            self.port = None
            return self

        if not self.host:
            raise ValueError(f"{self.type.value} asset host is required")
        self.path = ""
        if self.type == WorkProjectAssetType.DOMAIN:
            self.host = self.host.lower()
            self.port = None
        elif self.type == WorkProjectAssetType.NETWORK:
            self.host = _normalize_network(self.host)
            self.port = None
        else:  # SERVICE
            self.host = self.host.lower()
        return self

    @property
    def identifier(self) -> str:
        return build_asset_identifier(self.type, self.host, self.port, self.path)

    @property
    def identity(self) -> tuple[WorkProjectAssetType, str]:
        """Composite identity that distinguishes assets of different types sharing an identifier."""
        return self.type, self.identifier


def _normalize_network(value: str) -> str:
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError as error:
        raise ValueError("network asset host must be a valid CIDR or IP") from error
