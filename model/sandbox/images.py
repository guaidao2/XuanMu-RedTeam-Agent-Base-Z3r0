from datetime import datetime

from sqlmodel import Field, SQLModel


class SandboxImage(SQLModel, table=True):
    __tablename__ = "sandbox_images"

    id: int | None = Field(default=None, primary_key=True)
    image_name: str = Field(default="")
    control_proxy_port: int = Field(default=8000)
    supports_tor: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
