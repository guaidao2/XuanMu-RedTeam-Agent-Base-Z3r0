import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, cast, func, or_, update
from sqlmodel import select

from core.agent.constants import DEFAULT_AGENT_CODE
from database import get_async_session
from logger import get_logger
from model.agent.sessions import AgentSessionMeta
from model.egress_proxy.proxies import EgressProxy
from model.sandbox.containers import SandboxContainer
from model.system_user.users import SystemUser
from model.work_project.assets import WorkProjectAsset
from model.work_project.findings import WorkProjectFinding
from model.work_project.projects import WorkProject, WorkProjectOwner, WorkProjectSandboxContainer
from model.sandbox.images import SandboxImage
from model.host.hosts import ManagedHost
from schema.agent.sessions import AgentSessionSummarySchema, SessionType
from schema.sandbox.containers import SandboxContainerSchema, SandboxContainerStatus
from schema.system_user.users import SystemUserRole
from schema.work_project.assets import WorkProjectAssetOrigin, WorkProjectAssetRequest, WorkProjectAssetType
from schema.work_project.findings import WorkProjectFindingSchema
from schema.work_project.projects import (
    CreateWorkProjectRequest,
    UpdateWorkProjectMetadataRequest,
    WorkProjectAgentSummarySchema,
    WorkProjectOwnerSchema,
    WorkProjectSchema,
    WorkProjectStatus,
    WorkProjectTaskSchema,
)
from schema.work_project.records import WorkProjectRecordSnapshotSchema, WorkProjectRecordsSchema
from service.agent.sessions import cancel_sessions, delete_session, ensure_sdk_session_row, list_sessions
from service.common.pagination import Page, paginate_statement
from service.sandbox.egress import sandbox_egress_label
from service.sandbox.records import sandbox_container_schema
from service.sandbox.types import SandboxContainerRecord
from service.work_project.assets import apply_asset_request
from service.work_project.graph import get_work_project_graph_snapshot_in_tx, purge_edges_touching_asset
from service.work_project.progress import derive_work_project_status


logger = get_logger(__name__)
_PROJECT_SESSION_TITLE_PATTERN = re.compile(r"^session (?P<number>\d+)$")


class WorkProjectSessionCreateResult:
    def __init__(self, session_id: str = "", not_found: bool = False, inactive: bool = False) -> None:
        self.session_id = session_id
        self.not_found = not_found
        self.inactive = inactive


def can_create_work_project_session(status: WorkProjectStatus) -> bool:
    return status != WorkProjectStatus.CANCELED


def can_cancel_work_project(status: WorkProjectStatus) -> bool:
    return status != WorkProjectStatus.CANCELED


def can_retry_work_project(status: WorkProjectStatus) -> bool:
    return status == WorkProjectStatus.CANCELED


async def validate_work_project_metadata(
    request: CreateWorkProjectRequest | UpdateWorkProjectMetadataRequest,
    project_id: int | None = None,
) -> str:
    if not request.assets:
        return "at least one asset is required"
    duplicate_asset = _duplicate_asset_identity(request.assets)
    if duplicate_asset:
        return f"duplicate asset: {duplicate_asset}"

    async with get_async_session() as session:
        if request.owner_user_ids:
            users = (await session.exec(
                select(SystemUser.id).where(SystemUser.id.in_(request.owner_user_ids))
            )).all()
            missing_owner_ids = sorted(set(request.owner_user_ids) - {user_id for user_id in users})
            if missing_owner_ids:
                return f"selected owners not found: {', '.join(str(id) for id in missing_owner_ids)}"

        if request.sandbox_container_ids:
            containers = (await session.exec(
                select(SandboxContainer).where(SandboxContainer.id.in_(request.sandbox_container_ids))
            )).all()
            found_ids = {container.id for container in containers}
            missing_ids = sorted(set(request.sandbox_container_ids) - {id for id in found_ids if id is not None})
            if missing_ids:
                return f"selected sandbox containers not found: {', '.join(str(id) for id in missing_ids)}"
            not_running = [container.id for container in containers if container.status != SandboxContainerStatus.RUNNING]
            if not_running:
                return f"selected sandbox containers are not running: {', '.join(str(id) for id in not_running if id is not None)}"

    return ""


async def work_project_exists(id: int) -> bool:
    async with get_async_session() as session:
        return await session.get(WorkProject, id) is not None


async def create_work_project(request: CreateWorkProjectRequest) -> WorkProjectSchema:
    now = datetime.now()
    project = WorkProject(
        name=request.name,
        description=request.description,
        tasks=[],
        progress=0,
        status=WorkProjectStatus.WORKING,
        type=request.type,
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(project)
        await session.flush()
        project_id = project.id or 0
        _set_project_owner_rows(session, project_id, request.owner_user_ids)
        _set_project_sandbox_container_rows(session, project_id, request.sandbox_container_ids)
        _set_project_asset_rows(session, project_id, request.assets)
        await session.commit()
        await session.refresh(project)
        schema = await _project_schema(session, project)

    logger.info("work project created: %s", project.id)
    return schema


async def get_work_project_record_snapshot_for_user(
    id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> WorkProjectRecordSnapshotSchema | None:
    async with get_async_session() as session:
        if not await _can_access_work_project_in_tx(session, id, user_id, user_role):
            return None
        project = await session.get(WorkProject, id)
        if project is None:
            return None
        project_schema = await _project_schema(session, project)
        assets = project_schema.assets
        findings = (await session.exec(
            select(WorkProjectFinding)
            .where(WorkProjectFinding.project_id == id)
            .order_by(WorkProjectFinding.id)
        )).all()
        graph = await get_work_project_graph_snapshot_in_tx(session, id)

    return WorkProjectRecordSnapshotSchema(
        project=project_schema,
        records=WorkProjectRecordsSchema(
            assets=assets,
            findings=[WorkProjectFindingSchema.model_validate(item) for item in findings],
            graph=graph,
        ),
    )


async def update_work_project_metadata(
    id: int,
    request: UpdateWorkProjectMetadataRequest,
) -> WorkProjectSchema | None:
    async with get_async_session() as session:
        project = await session.get(WorkProject, id)
        if project is None:
            return None
        project.name = request.name
        project.description = request.description
        project.type = request.type
        project.updated_at = datetime.now()
        session.add(project)
        await _replace_project_owners(session, id, request.owner_user_ids)
        await _replace_project_sandbox_containers(session, id, request.sandbox_container_ids)
        await _upsert_project_assets(session, id, request.assets)
        await session.commit()
        await session.refresh(project)
        schema = await _project_schema(session, project)

    logger.info("work project metadata updated: %s", id)
    return schema


async def cancel_work_project(id: int) -> tuple[WorkProjectSchema | None, bool]:
    async with get_async_session() as session:
        project = await session.get(WorkProject, id)
        if project is None:
            return None, False
        if not can_cancel_work_project(project.status):
            return await _project_schema(session, project), False

        project.status = WorkProjectStatus.CANCELED
        project.updated_at = datetime.now()
        session.add(project)
        session_ids = list((await session.exec(
            select(AgentSessionMeta.session_id).where(AgentSessionMeta.project_id == id)
        )).all())
        await session.commit()
        await session.refresh(project)
        schema = await _project_schema(session, project)

    await cancel_sessions(session_ids, "WorkProject canceled.")
    logger.info("work project canceled: %s", id)
    return schema, True


async def delete_work_project(id: int) -> bool:
    async with get_async_session() as session:
        project = await session.get(WorkProject, id)
        if project is None:
            return False
        session_ids = list((await session.exec(
            select(AgentSessionMeta.session_id).where(AgentSessionMeta.project_id == id)
        )).all())

    for session_id in session_ids:
        await delete_session(
            session_id,
            user_role=SystemUserRole.ADMIN,
            allow_project_session=True,
        )

    async with get_async_session() as session:
        project = await session.get(WorkProject, id)
        if project is None:
            return True
        await session.delete(project)
        await session.commit()

    logger.info("work project deleted: %s", id)
    return True


async def retry_work_project(id: int) -> tuple[WorkProjectSchema | None, bool]:
    async with get_async_session() as session:
        project = await session.get(WorkProject, id)
        if project is None:
            return None, False
        if not can_retry_work_project(project.status):
            return await _project_schema(session, project), False

        project.status = derive_work_project_status(project.tasks, WorkProjectStatus.WORKING)
        project.updated_at = datetime.now()
        session.add(project)
        await session.commit()
        await session.refresh(project)
        schema = await _project_schema(session, project)

    logger.debug("work project retried: %s", project.id)
    return schema, True


async def query_work_projects_for_user(
    page: int,
    size: int,
    keyword: str,
    user_id: int,
    user_role: SystemUserRole,
) -> Page[WorkProjectSchema]:
    return await _query_work_projects(
        page=page,
        size=size,
        keyword=keyword,
        owner_user_id=None if user_role == SystemUserRole.ADMIN else user_id,
    )


async def create_work_project_session(
    project_id: int,
    owner_id: int,
    user_role: SystemUserRole,
) -> WorkProjectSessionCreateResult:
    if not await can_access_work_project(project_id, owner_id, user_role):
        return WorkProjectSessionCreateResult(not_found=True)

    session_id = str(uuid4())
    async with get_async_session() as session:
        project = (await session.exec(
            select(WorkProject)
            .where(WorkProject.id == project_id)
            .with_for_update()
        )).first()
        if project is None:
            return WorkProjectSessionCreateResult(not_found=True)
        if not can_create_work_project_session(project.status):
            return WorkProjectSessionCreateResult(inactive=True)
        title = await _next_project_session_title(session, project_id)

        await ensure_sdk_session_row(session, session_id)
        session.add(AgentSessionMeta(
            session_id=session_id,
            session_type=SessionType.PROJECT,
            title=title,
            agent_code=DEFAULT_AGENT_CODE,
            owner_id=owner_id,
            project_id=project_id,
        ))
        await session.commit()

    logger.info("work project session created: project=%s session=%s", project_id, session_id)
    return WorkProjectSessionCreateResult(session_id=session_id)


async def list_work_project_sessions(
    project_id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> list[AgentSessionSummarySchema] | None:
    if not await can_access_work_project(project_id, user_id, user_role):
        return None
    return await list_sessions(
        limit=100,
        user_id=user_id,
        user_role=user_role,
        project_id=project_id,
    )


async def can_run_work_project_session(
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None:
            return False
        if meta.project_id is None:
            return True
        if not await _can_access_work_project_in_tx(session, meta.project_id, user_id, user_role):
            return False
        project = await session.get(WorkProject, meta.project_id)
        return project is not None and can_create_work_project_session(project.status)


async def delete_work_project_session(
    project_id: int,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> bool | None:
    if not await can_access_work_project(project_id, user_id, user_role):
        return None
    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or meta.project_id != project_id:
            return None if await session.get(WorkProject, project_id) is None else False
    return await delete_session(
        session_id,
        user_id=user_id,
        user_role=user_role,
        allow_project_session=True,
    )


async def work_project_allows_sandbox_container(
    project_id: int,
    sandbox_container_id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    if not await can_access_work_project(project_id, user_id, user_role):
        return False
    async with get_async_session() as session:
        row = await session.get(WorkProjectSandboxContainer, (project_id, sandbox_container_id))
        if row is None:
            return False
        container = await session.get(SandboxContainer, sandbox_container_id)
        if container is None or container.status != SandboxContainerStatus.RUNNING:
            return False
        if user_role == SystemUserRole.ADMIN:
            return True
        return container.owner_id == user_id


async def _project_schema(
    session,
    project: WorkProject,
) -> WorkProjectSchema:
    return WorkProjectSchema(**_project_schema_payload(
        project=project,
        owners=await _owners_for_project(session, project.id or 0),
        sandbox_containers=await _sandbox_containers_for_project(session, project.id or 0),
        assets=await _assets_for_project(session, project.id or 0),
        session_count=await _session_count_in_tx(session, project.id or 0),
    ))


async def _session_count_in_tx(session, project_id: int) -> int:
    if project_id <= 0:
        return 0
    return (await _session_counts(session, [project_id])).get(project_id, 0)


async def _next_project_session_title(session, project_id: int) -> str:
    rows = (await session.exec(
        select(AgentSessionMeta.title).where(AgentSessionMeta.project_id == project_id)
    )).all()
    max_number = 0
    for title in rows:
        match = _PROJECT_SESSION_TITLE_PATTERN.match(title or "")
        if match is not None:
            max_number = max(max_number, int(match.group("number")))
    return f"session {max_number + 1}"


async def _session_counts(session, project_ids: list[int]) -> dict[int, int]:
    ids = [project_id for project_id in project_ids if project_id > 0]
    if not ids:
        return {}
    rows = (await session.exec(
        select(AgentSessionMeta.project_id, func.count())
        .where(AgentSessionMeta.project_id.in_(ids))
        .group_by(AgentSessionMeta.project_id)
    )).all()
    return {int(project_id): int(count) for project_id, count in rows if project_id is not None}


async def _query_work_projects(
    page: int,
    size: int,
    keyword: str,
    owner_user_id: int | None = None,
) -> Page[WorkProjectSchema]:
    statement = select(WorkProject).order_by(WorkProject.id)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                WorkProject.name.ilike(pattern),
                WorkProject.description.ilike(pattern),
                cast(WorkProject.status, String).ilike(pattern),
                cast(WorkProject.type, String).ilike(pattern),
            )
        )
    if owner_user_id is not None:
        statement = statement.join(
            WorkProjectOwner,
            WorkProjectOwner.project_id == WorkProject.id,
        ).where(WorkProjectOwner.user_id == owner_user_id)
    page_result = await paginate_statement(statement, page=page, size=size)
    projects = page_result.items

    async with get_async_session() as session:
        counts = await _session_counts(session, [project.id or 0 for project in projects])
        owners = await _owners_by_project(session, [project.id or 0 for project in projects])
        sandbox_containers = await _sandbox_containers_by_project(session, [project.id or 0 for project in projects])
        assets = await _assets_by_project(session, [project.id or 0 for project in projects])

        items = [
            WorkProjectSchema(**_project_schema_payload(
                project=project,
                owners=owners.get(project.id or 0, []),
                sandbox_containers=sandbox_containers.get(project.id or 0, []),
                assets=assets.get(project.id or 0, []),
                session_count=counts.get(project.id or 0, 0),
            ))
            for project in projects
        ]
    return Page(page=page_result.page, size=page_result.size, total=page_result.total, items=items)


def _project_schema_payload(
    project: WorkProject,
    owners: list[WorkProjectOwnerSchema],
    sandbox_containers: list[SandboxContainerSchema],
    assets: list[WorkProjectAsset],
    session_count: int,
) -> dict[str, object]:
    return {
        "id": project.id or 0,
        "name": project.name,
        "description": project.description,
        "owner_user_ids": [owner.id for owner in owners],
        "owners": owners,
        "sandbox_container_ids": [container.id for container in sandbox_containers],
        "sandbox_containers": sandbox_containers,
        "assets": assets,
        "tasks": [WorkProjectTaskSchema.model_validate(item) for item in project.tasks],
        "agent_summaries": [
            WorkProjectAgentSummarySchema.model_validate(summary)
            for summary in (project.agent_summaries or {}).values()
            if isinstance(summary, dict)
        ],
        "progress": project.progress,
        "session_count": session_count,
        "status": project.status,
        "can_create_session": can_create_work_project_session(project.status),
        "can_cancel": can_cancel_work_project(project.status),
        "can_retry": can_retry_work_project(project.status),
        "type": project.type,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


async def _owners_by_project(session, project_ids: list[int]) -> dict[int, list[WorkProjectOwnerSchema]]:
    ids = [project_id for project_id in project_ids if project_id > 0]
    if not ids:
        return {}
    rows = (await session.exec(
        select(WorkProjectOwner, SystemUser)
        .join(SystemUser, SystemUser.id == WorkProjectOwner.user_id)
        .where(WorkProjectOwner.project_id.in_(ids))
        .order_by(WorkProjectOwner.project_id, WorkProjectOwner.position, WorkProjectOwner.user_id)
    )).all()
    result: dict[int, list[WorkProjectOwnerSchema]] = {project_id: [] for project_id in ids}
    for owner, user in rows:
        if user.id is None:
            continue
        result.setdefault(owner.project_id, []).append(_owner_schema(user))
    return result


async def _owners_for_project(session, project_id: int) -> list[WorkProjectOwnerSchema]:
    return (await _owners_by_project(session, [project_id])).get(project_id, [])


async def _sandbox_containers_by_project(session, project_ids: list[int]) -> dict[int, list[SandboxContainerSchema]]:
    ids = [project_id for project_id in project_ids if project_id > 0]
    if not ids:
        return {}
    rows = (await session.exec(
        select(
            WorkProjectSandboxContainer,
            SandboxContainer,
            SandboxImage.image_name,
            SandboxImage.supports_tor,
            SandboxImage.control_proxy_port,
            SystemUser.username,
            ManagedHost.ip_address,
            EgressProxy,
        )
        .join(SandboxContainer, SandboxContainer.id == WorkProjectSandboxContainer.sandbox_container_id)
        .join(SandboxImage, SandboxImage.id == SandboxContainer.image_id)
        .join(SystemUser, SystemUser.id == SandboxContainer.owner_id)
        .join(ManagedHost, ManagedHost.id == SandboxContainer.host_id)
        .outerjoin(EgressProxy, EgressProxy.id == SandboxContainer.egress_proxy_id)
        .where(WorkProjectSandboxContainer.project_id.in_(ids))
        .order_by(WorkProjectSandboxContainer.project_id, WorkProjectSandboxContainer.position, WorkProjectSandboxContainer.sandbox_container_id)
    )).all()
    result: dict[int, list[SandboxContainerSchema]] = {project_id: [] for project_id in ids}
    for link, container, image_name, supports_tor, control_proxy_port, owner_username, host_ip_address, egress_proxy in rows:
        record = SandboxContainerRecord(
            container=container,
            image_name=image_name,
            supports_tor=supports_tor,
            control_proxy_port=control_proxy_port,
            owner_username=owner_username,
            host_ip_address=host_ip_address,
            egress_label=sandbox_egress_label(container, egress_proxy),
        )
        result.setdefault(link.project_id, []).append(sandbox_container_schema(record))
    return result


async def _sandbox_containers_for_project(session, project_id: int) -> list[SandboxContainerSchema]:
    return (await _sandbox_containers_by_project(session, [project_id])).get(project_id, [])


async def _assets_by_project(session, project_ids: list[int]) -> dict[int, list[WorkProjectAsset]]:
    ids = [project_id for project_id in project_ids if project_id > 0]
    if not ids:
        return {}
    rows = (await session.exec(
        select(WorkProjectAsset)
        .where(WorkProjectAsset.project_id.in_(ids))
        .order_by(WorkProjectAsset.project_id, WorkProjectAsset.id)
    )).all()
    result: dict[int, list[WorkProjectAsset]] = {project_id: [] for project_id in ids}
    for asset in rows:
        result.setdefault(asset.project_id, []).append(asset)
    return result


async def _assets_for_project(session, project_id: int) -> list[WorkProjectAsset]:
    return (await _assets_by_project(session, [project_id])).get(project_id, [])


def _owner_schema(user: SystemUser) -> WorkProjectOwnerSchema:
    return WorkProjectOwnerSchema(
        id=user.id or 0,
        role=user.role,
        username=user.username,
    )


def _set_project_owner_rows(session, project_id: int, owner_user_ids: list[int]) -> None:
    for position, user_id in enumerate(owner_user_ids):
        session.add(WorkProjectOwner(project_id=project_id, user_id=user_id, position=position))


async def _replace_project_owners(session, project_id: int, owner_user_ids: list[int]) -> None:
    for owner in (await session.exec(
        select(WorkProjectOwner).where(WorkProjectOwner.project_id == project_id)
    )).all():
        await session.delete(owner)
    _set_project_owner_rows(session, project_id, owner_user_ids)


def _set_project_sandbox_container_rows(session, project_id: int, sandbox_container_ids: list[int]) -> None:
    for position, container_id in enumerate(sandbox_container_ids):
        session.add(WorkProjectSandboxContainer(
            project_id=project_id,
            sandbox_container_id=container_id,
            position=position,
        ))


async def _replace_project_sandbox_containers(session, project_id: int, sandbox_container_ids: list[int]) -> None:
    for link in (await session.exec(
        select(WorkProjectSandboxContainer).where(WorkProjectSandboxContainer.project_id == project_id)
    )).all():
        await session.delete(link)
    _set_project_sandbox_container_rows(session, project_id, sandbox_container_ids)


def _set_project_asset_rows(session, project_id: int, assets: list[WorkProjectAssetRequest]) -> None:
    now = datetime.now()
    seen: set[tuple[WorkProjectAssetType, str]] = set()
    for request in assets:
        if request.identity in seen:
            continue
        seen.add(request.identity)
        asset = WorkProjectAsset(
            project_id=project_id,
            origin=WorkProjectAssetOrigin.SCOPE,
            created_at=now,
            updated_at=now,
        )
        apply_asset_request(asset, request, now)
        session.add(asset)


async def _upsert_project_assets(session, project_id: int, assets: list[WorkProjectAssetRequest]) -> None:
    rows = (await session.exec(
        select(WorkProjectAsset).where(WorkProjectAsset.project_id == project_id)
    )).all()
    existing = {(asset.type, asset.identifier): asset for asset in rows}
    seen: set[tuple[WorkProjectAssetType, str]] = set()
    now = datetime.now()
    for request in assets:
        if request.identity in seen:
            continue
        seen.add(request.identity)
        asset = existing.get(request.identity)
        if asset is None:
            asset = WorkProjectAsset(project_id=project_id, created_at=now, updated_at=now)
            existing[request.identity] = asset
            session.add(asset)
            apply_asset_request(asset, request, now)
        else:
            previous_extra = asset.extra
            apply_asset_request(asset, request, now)
            if "extra" not in request.model_fields_set:
                asset.extra = previous_extra
        # A metadata-declared asset is authoritative project scope, even if an agent discovered it first.
        asset.origin = WorkProjectAssetOrigin.SCOPE
        asset.created_by_agent_code = ""
        asset.created_from_session_id = ""
    for asset in rows:
        if asset.origin != WorkProjectAssetOrigin.SCOPE or (asset.type, asset.identifier) in seen:
            continue
        await session.execute(
            update(WorkProjectFinding)
            .where(WorkProjectFinding.asset_id == asset.id)
            .values(asset_id=None)
        )
        await purge_edges_touching_asset(session, project_id, asset.id or 0)
        await session.delete(asset)


def _duplicate_asset_identity(assets: list[WorkProjectAssetRequest]) -> str:
    seen: set[tuple[WorkProjectAssetType, str]] = set()
    for asset in assets:
        if asset.identity in seen:
            return f"{asset.type.value}:{asset.identifier}"
        seen.add(asset.identity)
    return ""


async def can_access_work_project(
    project_id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    async with get_async_session() as session:
        return await _can_access_work_project_in_tx(session, project_id, user_id, user_role)


async def _can_access_work_project_in_tx(
    session,
    project_id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    if await session.get(WorkProject, project_id) is None:
        return False
    if user_role == SystemUserRole.ADMIN:
        return True
    return await session.get(WorkProjectOwner, (project_id, user_id)) is not None
