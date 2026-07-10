from datetime import datetime

from sqlalchemy import String, cast, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from database import get_async_session
from model.work_project.assets import WorkProjectAsset
from model.work_project.findings import WorkProjectFinding
from schema.work_project.assets import (
    WorkProjectAssetOrigin,
    WorkProjectAssetRequest,
    WorkProjectAssetSchema,
    WorkProjectAssetType,
)
from service.common.pagination import Page, paginate_statement
from service.work_project.graph import purge_edges_touching_asset


_ASSET_ALREADY_EXISTS = "asset already exists"
_SCOPE_ASSET_IDENTITY_LOCKED = "scope asset identity is managed by project metadata"
_SCOPE_ASSET_DELETE_LOCKED = "scope assets are managed by project metadata"


async def query_work_project_assets(
    project_id: int,
    *,
    page: int,
    size: int,
    keyword: str,
) -> Page[WorkProjectAssetSchema]:
    statement = (
        select(WorkProjectAsset)
        .where(WorkProjectAsset.project_id == project_id)
        .order_by(WorkProjectAsset.id)
    )
    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(or_(
            WorkProjectAsset.identifier.ilike(pattern),
            WorkProjectAsset.host.ilike(pattern),
            WorkProjectAsset.path.ilike(pattern),
            cast(WorkProjectAsset.type, String).ilike(pattern),
        ))
    page_result = await paginate_statement(statement, page=page, size=size)
    return Page(
        page=page_result.page,
        size=page_result.size,
        total=page_result.total,
        items=[WorkProjectAssetSchema.model_validate(item) for item in page_result.items],
    )


async def create_work_project_asset(
    project_id: int,
    request: WorkProjectAssetRequest,
    *,
    origin: WorkProjectAssetOrigin = WorkProjectAssetOrigin.DISCOVERED,
    created_by_agent_code: str = "",
    created_from_session_id: str = "",
) -> tuple[WorkProjectAssetSchema | None, str]:
    now = datetime.now()
    async with get_async_session() as session:
        if await _get_asset_by_identity(session, project_id, request.type, request.identifier) is not None:
            return None, _ASSET_ALREADY_EXISTS
        asset = WorkProjectAsset(
            project_id=project_id,
            origin=origin,
            created_by_agent_code=created_by_agent_code.strip(),
            created_from_session_id=created_from_session_id.strip(),
            created_at=now,
            updated_at=now,
        )
        apply_asset_request(asset, request, now)
        session.add(asset)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None, _ASSET_ALREADY_EXISTS
        await session.refresh(asset)
    return WorkProjectAssetSchema.model_validate(asset), ""


async def update_work_project_asset(
    project_id: int,
    asset_id: int,
    request: WorkProjectAssetRequest,
) -> tuple[WorkProjectAssetSchema | None, str]:
    now = datetime.now()
    async with get_async_session() as session:
        asset = await session.get(WorkProjectAsset, asset_id)
        if asset is None or asset.project_id != project_id:
            return None, "asset not found"
        if (
            asset.origin == WorkProjectAssetOrigin.SCOPE
            and (asset.type, asset.identifier) != request.identity
        ):
            return None, _SCOPE_ASSET_IDENTITY_LOCKED
        conflict = await _get_asset_by_identity(session, project_id, request.type, request.identifier)
        if conflict is not None and conflict.id != asset_id:
            return None, _ASSET_ALREADY_EXISTS
        previous_extra = asset.extra
        apply_asset_request(asset, request, now)
        if "extra" not in request.model_fields_set:
            asset.extra = previous_extra
        session.add(asset)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None, _ASSET_ALREADY_EXISTS
        await session.refresh(asset)
    return WorkProjectAssetSchema.model_validate(asset), ""


async def upsert_work_project_asset(
    project_id: int,
    request: WorkProjectAssetRequest,
    *,
    created_by_agent_code: str = "",
    created_from_session_id: str = "",
) -> tuple[WorkProjectAssetSchema | None, str]:
    async with get_async_session() as session:
        existing = await _get_asset_by_identity(session, project_id, request.type, request.identifier)
        existing_asset_id = existing.id if existing is not None else None
    if existing_asset_id is not None:
        return await update_work_project_asset(project_id, existing_asset_id, request)
    saved, error = await create_work_project_asset(
        project_id,
        request,
        created_by_agent_code=created_by_agent_code,
        created_from_session_id=created_from_session_id,
    )
    if error != _ASSET_ALREADY_EXISTS:
        return saved, error
    # Lost a concurrent create race: the row another agent inserted now wins, so update it.
    async with get_async_session() as session:
        winner = await _get_asset_by_identity(session, project_id, request.type, request.identifier)
        winner_id = winner.id if winner is not None else None
    if winner_id is None:
        return None, _ASSET_ALREADY_EXISTS
    return await update_work_project_asset(project_id, winner_id, request)


async def delete_work_project_asset(project_id: int, asset_id: int) -> str:
    async with get_async_session() as session:
        asset = await session.get(WorkProjectAsset, asset_id)
        if asset is None or asset.project_id != project_id:
            return "asset not found"
        if asset.origin == WorkProjectAssetOrigin.SCOPE:
            return _SCOPE_ASSET_DELETE_LOCKED
        await session.execute(
            update(WorkProjectFinding)
            .where(WorkProjectFinding.asset_id == asset_id)
            .values(asset_id=None)
        )
        await purge_edges_touching_asset(session, project_id, asset_id)
        await session.delete(asset)
        await session.commit()
    return ""


def apply_asset_request(asset: WorkProjectAsset, request: WorkProjectAssetRequest, now: datetime) -> None:
    """Copy a validated asset request onto a model row, including its identifier."""
    asset.type = request.type
    asset.host = request.host
    asset.port = request.port
    asset.path = request.path
    asset.identifier = request.identifier
    asset.extra = request.extra
    asset.updated_at = now


async def _get_asset_by_identity(
    session,
    project_id: int,
    asset_type: WorkProjectAssetType,
    identifier: str,
) -> WorkProjectAsset | None:
    return (await session.exec(
        select(WorkProjectAsset).where(
            WorkProjectAsset.project_id == project_id,
            WorkProjectAsset.type == asset_type,
            WorkProjectAsset.identifier == identifier,
        )
    )).first()
