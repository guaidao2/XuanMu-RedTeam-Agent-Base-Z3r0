from datetime import datetime

from sqlalchemy import Column, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

from schema.work_project.assets import (
    WorkProjectAssetExtraSchema,
    WorkProjectAssetOrigin,
    WorkProjectAssetType,
)


class WorkProjectAssetExtraJson(TypeDecorator):
    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value: object, dialect) -> object:
        if value is None:
            return WorkProjectAssetExtraSchema().model_dump(mode="json")
        extra = WorkProjectAssetExtraSchema.model_validate(value)
        return extra.model_dump(mode="json")

    def process_result_value(self, value: object, dialect) -> WorkProjectAssetExtraSchema:
        if value is None:
            return WorkProjectAssetExtraSchema()
        return WorkProjectAssetExtraSchema.model_validate(value)


class WorkProjectAsset(SQLModel, table=True):
    __tablename__ = "work_project_assets"
    __table_args__ = (
        UniqueConstraint("project_id", "type", "identifier", name="uq_work_project_asset_identity"),
        Index("ix_work_project_assets_project_type", "project_id", "type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="work_projects.id", index=True, ondelete="CASCADE")
    type: WorkProjectAssetType = Field(sa_column=Column(String(32), nullable=False))
    origin: WorkProjectAssetOrigin = Field(
        default=WorkProjectAssetOrigin.DISCOVERED,
        sa_column=Column(String(32), nullable=False, index=True),
    )
    identifier: str = Field(sa_column=Column(String(700), nullable=False, index=True))
    host: str = Field(default="", index=True)
    port: int | None = Field(default=None, index=True)
    path: str = Field(default="")
    extra: WorkProjectAssetExtraSchema = Field(
        default_factory=WorkProjectAssetExtraSchema,
        sa_column=Column(WorkProjectAssetExtraJson, nullable=False),
    )
    created_by_agent_code: str = Field(default="", index=True)
    created_from_session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
