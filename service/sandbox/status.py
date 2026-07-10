import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.sandbox.containers import SandboxContainer
from model.host.hosts import ManagedHost
from schema.sandbox.containers import SandboxContainerStatus
from schema.system_user.users import SystemUserRole
from service.sandbox.docker_ops import (
    DockerContainerState,
    docker_status_to_sandbox_status,
    inspect_container_state_sync,
)
from service.sandbox.records import load_sandbox_container_record
from service.sandbox.types import SandboxContainerRecord, SandboxContainerToolBinding


logger = get_logger(__name__)

_STATUS_MONITOR_INTERVAL_SECONDS = 5
_TOOL_BINDING_INSPECT_TTL_SECONDS = 3
_status_monitor_task: asyncio.Task[None] | None = None
_tool_invalidation_tasks: set[asyncio.Task[None]] = set()
_tool_binding_state_cache: dict[int, "DockerStateCacheEntry"] = {}


@dataclass(frozen=True)
class ContainerStatusSnapshot:
    id: int
    host_id: int
    container_hash: str
    status: SandboxContainerStatus


@dataclass(frozen=True)
class DockerStateCacheEntry:
    host_id: int
    container_hash: str
    generation: int
    state: DockerContainerState
    expires_at: float


async def save_sandbox_container_status(
    id: int,
    status: SandboxContainerStatus,
) -> SandboxContainerRecord | None:
    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            return None

        sandbox_container.status = status
        sandbox_container.updated_at = datetime.now()
        session.add(sandbox_container)
        await session.commit()

    _schedule_agent_tool_invalidation(id)
    return await load_sandbox_container_record(id)


def status_generation(sandbox_container: SandboxContainer) -> int:
    return int(sandbox_container.updated_at.timestamp() * 1_000_000)


def _clear_tool_binding_state_cache(container_id: int | None = None) -> None:
    if container_id is None:
        _tool_binding_state_cache.clear()
        return
    _tool_binding_state_cache.pop(container_id, None)


async def inspect_container_state_cached(
    *,
    id: int,
    host_id: int,
    container_hash: str,
    generation: int,
) -> DockerContainerState:
    now = time.monotonic()
    cached = _tool_binding_state_cache.get(id)
    if (
        cached is not None
        and cached.host_id == host_id
        and cached.container_hash == container_hash
        and cached.generation == generation
        and cached.expires_at > now
    ):
        return cached.state

    host = await _load_host(host_id)
    if host is None:
        return DockerContainerState(exists=False)
    state = await asyncio.to_thread(inspect_container_state_sync, host, container_hash)
    _tool_binding_state_cache[id] = DockerStateCacheEntry(
        host_id=host_id,
        container_hash=container_hash,
        generation=generation,
        state=state,
        expires_at=now + _TOOL_BINDING_INSPECT_TTL_SECONDS,
    )
    return state


def _schedule_agent_tool_invalidation(container_id: int) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("no running loop for agent tool invalidation: %s", container_id)
        return

    task = loop.create_task(
        invalidate_agent_tool_bindings(container_id),
        name=f"agent-tool-invalidate-{container_id}",
    )
    _tool_invalidation_tasks.add(task)
    task.add_done_callback(_tool_invalidation_tasks.discard)


async def invalidate_agent_tool_bindings(container_id: int) -> None:
    _clear_tool_binding_state_cache(container_id)
    try:
        from core.runtime.session import get_agent_pool

        await get_agent_pool().invalidate_tool_bindings(container_id)
    except Exception:
        logger.exception("agent tool binding invalidation failed: %s", container_id)


async def _invalidate_all_agent_tool_bindings() -> None:
    _clear_tool_binding_state_cache()
    if _tool_invalidation_tasks:
        await asyncio.gather(*tuple(_tool_invalidation_tasks), return_exceptions=True)
    try:
        from core.runtime.session import get_agent_pool

        await get_agent_pool().invalidate_tool_bindings()
    except Exception:
        logger.exception("agent tool binding invalidation failed")


async def _load_container_status_snapshots() -> list[ContainerStatusSnapshot]:
    statement = select(SandboxContainer.id, SandboxContainer.host_id, SandboxContainer.container_hash, SandboxContainer.status).where(
        SandboxContainer.container_hash != ""
    )
    async with get_async_session() as session:
        result = await session.exec(statement)
        return [
            ContainerStatusSnapshot(id=row[0], host_id=row[1], container_hash=row[2], status=row[3])
            for row in result.all()
        ]


async def sync_container_status(snapshot: ContainerStatusSnapshot) -> None:
    host = await _load_host(snapshot.host_id)
    if host is None:
        await save_sandbox_container_status(snapshot.id, SandboxContainerStatus.ERROR)
        return
    state = await asyncio.to_thread(inspect_container_state_sync, host, snapshot.container_hash)
    next_status = SandboxContainerStatus.ERROR if not state.exists else docker_status_to_sandbox_status(state.status)
    if next_status == snapshot.status:
        return

    await save_sandbox_container_status(snapshot.id, next_status)
    logger.debug(
        "sandbox container status synced: %s %s -> %s",
        snapshot.id,
        snapshot.status,
        next_status,
    )


async def sync_sandbox_container_statuses() -> None:
    snapshots = await _load_container_status_snapshots()
    for snapshot in snapshots:
        try:
            await sync_container_status(snapshot)
        except Exception:
            logger.exception("sandbox container status sync failed: %s", snapshot.id)


async def _status_monitor_loop() -> None:
    while True:
        try:
            await sync_sandbox_container_statuses()
            await asyncio.sleep(_STATUS_MONITOR_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sandbox container status monitor iteration failed")
            await asyncio.sleep(_STATUS_MONITOR_INTERVAL_SECONDS)


async def start_sandbox_container_status_monitor() -> None:
    global _status_monitor_task
    if _status_monitor_task is not None and not _status_monitor_task.done():
        return
    _status_monitor_task = asyncio.create_task(
        _status_monitor_loop(),
        name="sandbox-container-status-monitor",
    )
    logger.info("sandbox container status monitor started")


async def stop_sandbox_container_status_monitor() -> None:
    global _status_monitor_task
    task, _status_monitor_task = _status_monitor_task, None
    if task is None or task.done():
        await _drain_tool_invalidation_tasks()
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await _drain_tool_invalidation_tasks()
    logger.info("sandbox container status monitor stopped")


async def invalidate_all_agent_tool_bindings() -> None:
    await _invalidate_all_agent_tool_bindings()


async def _drain_tool_invalidation_tasks() -> None:
    tasks = tuple(_tool_invalidation_tasks)
    if not tasks:
        return
    await asyncio.gather(*tasks, return_exceptions=True)


async def resolve_sandbox_container_tool_binding(
    id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> SandboxContainerToolBinding | None:
    return await _resolve_sandbox_container_tool_binding(
        id=id,
        can_use=lambda container: (
            user_role == SystemUserRole.ADMIN
            or container.owner_id == user_id
        ),
    )


async def resolve_project_sandbox_container_tool_binding(
    id: int,
) -> SandboxContainerToolBinding | None:
    return await _resolve_sandbox_container_tool_binding(id=id, can_use=lambda _: True)


async def _resolve_sandbox_container_tool_binding(
    id: int,
    can_use: Callable[[SandboxContainer], bool],
) -> SandboxContainerToolBinding | None:
    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            return None
        if sandbox_container.status != SandboxContainerStatus.RUNNING:
            return None
        if not can_use(sandbox_container):
            return None
        container_hash = sandbox_container.container_hash
        host_id = sandbox_container.host_id
        generation = status_generation(sandbox_container)

    try:
        state = await inspect_container_state_cached(
            id=id,
            host_id=host_id,
            container_hash=container_hash,
            generation=generation,
        )
    except Exception:
        logger.exception("sandbox container inspect failed before tool binding: %s", id)
        return None

    status = SandboxContainerStatus.ERROR if not state.exists else docker_status_to_sandbox_status(state.status)
    if status != SandboxContainerStatus.RUNNING:
        await save_sandbox_container_status(id, status)
        return None

    return SandboxContainerToolBinding(id=id, generation=generation)


async def _load_host(host_id: int) -> ManagedHost | None:
    async with get_async_session() as session:
        return await session.get(ManagedHost, host_id)
