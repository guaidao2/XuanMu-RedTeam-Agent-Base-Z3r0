from datetime import datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class ManagedHost(SQLModel, table=True):
    __tablename__ = "managed_hosts"

    id: int | None = Field(default=None, primary_key=True)
    ip_address: str = Field(default="", index=True)
    ssh_port: int = Field(default=22)
    host_account: str = Field(default="")
    host_password: str = Field(default="")
    docker_management_port: int = Field(default=2375)
    docker_tls_enabled: bool = Field(default=False)
    docker_client_ca_cert: str = Field(default="", sa_column=Column(Text, nullable=False))
    docker_client_cert: str = Field(default="", sa_column=Column(Text, nullable=False))
    docker_client_key: str = Field(default="", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
