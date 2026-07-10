from datetime import datetime

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from schema.work_project.projects import WorkProjectStatus, WorkProjectType


class WorkProject(SQLModel, table=True):
    __tablename__ = "work_projects"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="")
    description: str = Field(default="")
    tasks: list[dict] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    agent_summaries: dict[str, dict] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    progress: float = Field(default=0)
    status: WorkProjectStatus = Field(default=WorkProjectStatus.WORKING)
    type: WorkProjectType = Field(default=WorkProjectType.PENETRATION_TEST)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorkProjectOwner(SQLModel, table=True):
    __tablename__ = "work_project_owners"

    project_id: int = Field(
        foreign_key="work_projects.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    user_id: int = Field(
        foreign_key="system_users.id",
        primary_key=True,
        index=True,
        ondelete="CASCADE",
    )
    position: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)


class WorkProjectSandboxContainer(SQLModel, table=True):
    __tablename__ = "work_project_sandbox_containers"

    project_id: int = Field(
        foreign_key="work_projects.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    sandbox_container_id: int = Field(
        foreign_key="sandbox_containers.id",
        primary_key=True,
        index=True,
        ondelete="CASCADE",
    )
    position: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
