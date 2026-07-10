from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from schema.sandbox.containers import SandboxContainerEgressMode, SandboxContainerStatus


class SandboxContainer(SQLModel, table=True):
    __tablename__ = "sandbox_containers"

    id: int | None = Field(default=None, primary_key=True)
    host_id: int = Field(default=0, foreign_key="managed_hosts.id", index=True)
    container_name: str = Field(default="")
    container_hash: str = Field(default="")
    owner_id: int = Field(default=0, foreign_key="system_users.id", index=True)
    image_id: int = Field(default=0, foreign_key="sandbox_images.id", index=True)
    egress_mode: SandboxContainerEgressMode = Field(default=SandboxContainerEgressMode.DIRECT, index=True)
    egress_proxy_id: int | None = Field(default=None, foreign_key="egress_proxies.id", index=True)
    control_proxy_host_port: int = Field(default=0)
    control_proxy_token: str = Field(default="")
    port_mappings: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: SandboxContainerStatus = Field(default=SandboxContainerStatus.CREATED)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
