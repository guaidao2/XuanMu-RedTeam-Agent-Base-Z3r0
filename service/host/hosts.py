from dataclasses import dataclass
from datetime import datetime
import asyncio
import getpass

from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from model.host.hosts import ManagedHost
from model.sandbox.containers import SandboxContainer
from schema.host.hosts import ManagedHostImageSchema, PullManagedHostImageResultSchema
from service.common.pagination import Page, paginate_statement
from service.host.docker import list_host_images_sync, pull_host_images_sync, remove_host_image_sync


DEFAULT_LOCAL_HOST_ID = 1


@dataclass(frozen=True)
class DeleteManagedHostResult:
    deleted: bool
    not_found: bool = False
    message: str = ""


@dataclass(frozen=True)
class UpdateManagedHostResult:
    host: ManagedHost | None
    not_found: bool = False
    message: str = ""


async def create_managed_host(
    ip_address: str,
    ssh_port: int,
    host_account: str,
    host_password: str,
    docker_management_port: int,
    docker_tls_enabled: bool,
    docker_client_ca_cert: str,
    docker_client_cert: str,
    docker_client_key: str,
) -> ManagedHost:
    now = datetime.now()
    host = ManagedHost(
        ip_address=ip_address,
        ssh_port=ssh_port,
        host_account=host_account,
        host_password=host_password,
        docker_management_port=docker_management_port,
        docker_tls_enabled=docker_tls_enabled,
        docker_client_ca_cert=docker_client_ca_cert,
        docker_client_cert=docker_client_cert,
        docker_client_key=docker_client_key,
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(host)
        await session.commit()
        await session.refresh(host)

    return host


async def update_managed_host(
    id: int,
    ip_address: str | None = None,
    ssh_port: int | None = None,
    host_account: str | None = None,
    host_password: str | None = None,
    docker_management_port: int | None = None,
    docker_tls_enabled: bool | None = None,
    docker_client_ca_cert: str | None = None,
    docker_client_cert: str | None = None,
    docker_client_key: str | None = None,
) -> UpdateManagedHostResult:
    async with get_async_session() as session:
        host = await session.get(ManagedHost, id)
        if host is None:
            return UpdateManagedHostResult(host=None, not_found=True, message="managed host not found")

        next_docker_tls_enabled = (
            docker_tls_enabled if docker_tls_enabled is not None else host.docker_tls_enabled
        )
        next_docker_client_ca_cert = (
            docker_client_ca_cert
            if docker_client_ca_cert is not None
            else host.docker_client_ca_cert
        )
        next_docker_client_cert = (
            docker_client_cert
            if docker_client_cert is not None
            else host.docker_client_cert
        )
        next_docker_client_key = (
            docker_client_key
            if docker_client_key is not None
            else host.docker_client_key
        )
        if not next_docker_tls_enabled:
            next_docker_client_ca_cert = ""
            next_docker_client_cert = ""
            next_docker_client_key = ""
        elif not all((next_docker_client_ca_cert, next_docker_client_cert, next_docker_client_key)):
            return UpdateManagedHostResult(
                host=host,
                message="docker TLS CA certificate, client certificate, and client key are required",
            )

        docker_connection_changed = _docker_connection_changed(
            host=host,
            ip_address=ip_address,
            docker_management_port=docker_management_port,
            docker_tls_enabled=next_docker_tls_enabled,
            docker_client_ca_cert=next_docker_client_ca_cert,
            docker_client_cert=next_docker_client_cert,
            docker_client_key=next_docker_client_key,
        )
        if docker_connection_changed and await _host_has_sandbox_containers(session, id):
            return UpdateManagedHostResult(
                host=host,
                message="host docker connection is used by sandbox containers",
            )

        if ip_address is not None:
            host.ip_address = ip_address
        if ssh_port is not None:
            host.ssh_port = ssh_port
        if host_account is not None:
            host.host_account = host_account
        if host_password is not None:
            host.host_password = host_password
        if docker_management_port is not None:
            host.docker_management_port = docker_management_port
        host.docker_tls_enabled = next_docker_tls_enabled
        host.docker_client_ca_cert = next_docker_client_ca_cert
        host.docker_client_cert = next_docker_client_cert
        host.docker_client_key = next_docker_client_key

        host.updated_at = datetime.now()
        session.add(host)
        await session.commit()
        await session.refresh(host)

    return UpdateManagedHostResult(host=host)


async def delete_managed_host(id: int) -> DeleteManagedHostResult:
    if id == DEFAULT_LOCAL_HOST_ID:
        return DeleteManagedHostResult(deleted=False, message="default local host cannot be deleted")
    async with get_async_session() as session:
        host = await session.get(ManagedHost, id)
        if host is None:
            return DeleteManagedHostResult(deleted=False, not_found=True, message="managed host not found")
        if await _host_has_sandbox_containers(session, id):
            return DeleteManagedHostResult(
                deleted=False,
                message="managed host is used by sandbox containers",
            )

        await session.delete(host)
        await session.commit()

    return DeleteManagedHostResult(deleted=True)


async def query_managed_hosts(page: int = 1, size: int = 100, keyword: str = "") -> Page[ManagedHost]:
    statement = select(ManagedHost).order_by(ManagedHost.id)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                ManagedHost.ip_address.ilike(pattern),
                ManagedHost.host_account.ilike(pattern),
                cast(ManagedHost.ssh_port, String).ilike(pattern),
                cast(ManagedHost.docker_management_port, String).ilike(pattern),
            )
        )

    return await paginate_statement(statement, page=page, size=size)


async def query_managed_host_by_id(id: int) -> ManagedHost | None:
    async with get_async_session() as session:
        return await session.get(ManagedHost, id)


async def ensure_local_managed_host() -> ManagedHost:
    username = _detect_local_username()

    async with get_async_session() as session:
        host = await session.get(ManagedHost, DEFAULT_LOCAL_HOST_ID)
        if host is None:
            now = datetime.now()
            host = ManagedHost(
                id=DEFAULT_LOCAL_HOST_ID,
                ip_address="127.0.0.1",
                ssh_port=22,
                host_account=username,
                host_password="",
                docker_management_port=2375,
                docker_tls_enabled=False,
                docker_client_ca_cert="",
                docker_client_cert="",
                docker_client_key="",
                created_at=now,
                updated_at=now,
            )
            session.add(host)
            await session.commit()
            await session.refresh(host)
        else:
            updated = False
            if not host.host_account and username:
                host.host_account = username
                updated = True
            if host.host_password:
                host.host_password = ""
                updated = True
            if updated:
                host.updated_at = datetime.now()
                session.add(host)
                await session.commit()
                await session.refresh(host)

        from sqlalchemy import text
        await session.execute(text(
            "SELECT setval(pg_get_serial_sequence('managed_hosts', 'id'), (SELECT MAX(id) FROM managed_hosts))"
        ))
        await session.commit()
        await session.refresh(host)
        return host


def _detect_local_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


async def list_managed_host_images(id: int) -> list[ManagedHostImageSchema] | None:
    host = await query_managed_host_by_id(id)
    if host is None:
        return None
    return await asyncio.to_thread(list_host_images_sync, host)


async def pull_managed_host_images(id: int, image_names: list[str]) -> list[PullManagedHostImageResultSchema] | None:
    host = await query_managed_host_by_id(id)
    if host is None:
        return None
    return await asyncio.to_thread(pull_host_images_sync, host, image_names)


async def delete_managed_host_image(id: int, image_id: str, force: bool = False) -> str | None:
    host = await query_managed_host_by_id(id)
    if host is None:
        return "managed host not found"
    try:
        await asyncio.to_thread(remove_host_image_sync, host, image_id, force)
    except Exception as exc:
        return str(exc).strip() or "failed to remove image"
    return None


async def _host_has_sandbox_containers(session, host_id: int) -> bool:
    result = await session.exec(select(SandboxContainer.id).where(SandboxContainer.host_id == host_id).limit(1))
    return result.first() is not None


def _docker_connection_changed(
    *,
    host: ManagedHost,
    ip_address: str | None,
    docker_management_port: int | None,
    docker_tls_enabled: bool,
    docker_client_ca_cert: str,
    docker_client_cert: str,
    docker_client_key: str,
) -> bool:
    return (
        (ip_address is not None and ip_address != host.ip_address)
        or (
            docker_management_port is not None
            and docker_management_port != host.docker_management_port
        )
        or docker_tls_enabled != host.docker_tls_enabled
        or docker_client_ca_cert != host.docker_client_ca_cert
        or docker_client_cert != host.docker_client_cert
        or docker_client_key != host.docker_client_key
    )
