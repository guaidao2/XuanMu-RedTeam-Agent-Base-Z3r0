from datetime import datetime

from sqlmodel import Field, SQLModel

from schema.egress_proxy.proxies import EgressProxyType


class EgressProxy(SQLModel, table=True):
    __tablename__ = "egress_proxies"

    id: int | None = Field(default=None, primary_key=True)
    proxy_type: EgressProxyType = Field(default=EgressProxyType.HTTP, index=True)
    proxy_host: str = Field(default="", index=True)
    proxy_port: int = Field(default=0)
    proxy_account: str = Field(default="")
    proxy_password: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
