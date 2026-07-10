from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from model.egress_proxy.proxies import EgressProxy
from model.sandbox.containers import SandboxContainer
from model.sandbox.images import SandboxImage
from model.host.hosts import ManagedHost
from model.system_user.users import SystemUser
from schema.sandbox.containers import SandboxContainerSchema, SandboxContainerStatus
from schema.system_user.users import SystemUserRole
from service.common.pagination import Page, paginate_statement
from service.sandbox.egress import sandbox_egress_label
from service.sandbox.types import SandboxContainerRecord


def _base_container_record_statement():
    return (
        select(
            SandboxContainer,
            SandboxImage.image_name,
            SandboxImage.supports_tor,
            SandboxImage.control_proxy_port,
            SystemUser.username,
            ManagedHost.ip_address,
            EgressProxy,
        )
        .join(SandboxImage, SandboxContainer.image_id == SandboxImage.id)
        .join(SystemUser, SandboxContainer.owner_id == SystemUser.id)
        .join(ManagedHost, SandboxContainer.host_id == ManagedHost.id)
        .outerjoin(EgressProxy, SandboxContainer.egress_proxy_id == EgressProxy.id)
    )


def _apply_keyword_filter(statement, keyword: str):
    keyword = keyword.strip()
    if not keyword:
        return statement
    pattern = f"%{keyword}%"
    return statement.where(
        or_(
            SandboxContainer.container_name.ilike(pattern),
            SandboxContainer.container_hash.ilike(pattern),
            SandboxImage.image_name.ilike(pattern),
            ManagedHost.ip_address.ilike(pattern),
            SystemUser.username.ilike(pattern),
            EgressProxy.proxy_host.ilike(pattern),
            EgressProxy.proxy_account.ilike(pattern),
            cast(SandboxContainer.status, String).ilike(pattern),
            cast(SandboxContainer.port_mappings, String).ilike(pattern),
            cast(SandboxContainer.control_proxy_host_port, String).ilike(pattern),
            cast(SandboxImage.control_proxy_port, String).ilike(pattern),
        )
    )


def _to_record(row) -> SandboxContainerRecord:
    return SandboxContainerRecord(
        container=row[0],
        image_name=row[1],
        supports_tor=row[2],
        control_proxy_port=row[3],
        owner_username=row[4],
        host_ip_address=row[5],
        egress_label=sandbox_egress_label(row[0], row[6]),
    )


async def _paginate_container_records(statement, page: int, size: int) -> Page[SandboxContainerRecord]:
    page_result = await paginate_statement(statement, page=page, size=size)
    return Page(
        page=page_result.page,
        size=page_result.size,
        total=page_result.total,
        items=[_to_record(row) for row in page_result.items],
    )


async def load_sandbox_container_record(id: int) -> SandboxContainerRecord | None:
    statement = _base_container_record_statement().where(SandboxContainer.id == id)
    async with get_async_session() as session:
        result = await session.exec(statement)
        row = result.first()
        return _to_record(row) if row is not None else None


def sandbox_container_schema(record: SandboxContainerRecord) -> SandboxContainerSchema:
    container = record.container
    return SandboxContainerSchema(
        id=container.id or 0,
        host_id=container.host_id,
        host_ip_address=record.host_ip_address,
        container_name=container.container_name,
        container_hash=container.container_hash,
        image_id=container.image_id,
        image_name=record.image_name,
        supports_tor=record.supports_tor,
        control_proxy_port=record.control_proxy_port,
        egress_mode=container.egress_mode,
        egress_proxy_id=container.egress_proxy_id,
        egress_label=record.egress_label,
        control_proxy_host_port=container.control_proxy_host_port,
        port_mappings=container.port_mappings,
        status=container.status,
        owner_id=container.owner_id,
        owner_username=record.owner_username,
        created_at=container.created_at,
        updated_at=container.updated_at,
    )


async def query_sandbox_containers(
    page: int = 1,
    size: int = 100,
    keyword: str = "",
) -> Page[SandboxContainerRecord]:
    statement = _base_container_record_statement().order_by(SandboxContainer.id)
    statement = _apply_keyword_filter(statement, keyword)
    return await _paginate_container_records(statement, page, size)


async def query_available_sandbox_containers(
    user_id: int,
    user_role: SystemUserRole,
    page: int = 1,
    size: int = 100,
    keyword: str = "",
) -> Page[SandboxContainerRecord]:
    statement = _base_container_record_statement().order_by(SandboxContainer.id)
    if user_role != SystemUserRole.ADMIN:
        statement = statement.where(SandboxContainer.owner_id == user_id)
    statement = statement.where(SandboxContainer.status == SandboxContainerStatus.RUNNING)
    statement = _apply_keyword_filter(statement, keyword)
    return await _paginate_container_records(statement, page, size)
