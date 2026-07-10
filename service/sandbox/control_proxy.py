import asyncio
from dataclasses import dataclass

import httpx
from sqlmodel import select

from database import get_async_session
from model.egress_proxy.proxies import EgressProxy
from model.host.hosts import ManagedHost
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerEgressMode, SandboxContainerStatus
from service.sandbox.egress import (
    SandboxEgressSelection,
    sandbox_egress_container_environment,
)


_http_client: httpx.AsyncClient | None = None
_EGRESS_APPLY_ATTEMPTS = 3
_EGRESS_APPLY_RETRY_SECONDS = 0.5


@dataclass(frozen=True)
class SandboxControlProxyTarget:
    container_id: int
    base_url: str
    ws_base_url: str
    token: str
    status: SandboxContainerStatus


async def resolve_sandbox_control_proxy_target(
    container_id: int,
    *,
    require_running: bool = False,
) -> SandboxControlProxyTarget | None:
    async with get_async_session() as session:
        row = (await session.exec(
            select(SandboxContainer, ManagedHost)
            .join(ManagedHost, SandboxContainer.host_id == ManagedHost.id)
            .where(SandboxContainer.id == container_id)
        )).first()
        if row is None:
            return None
        container, host = row

    if container.control_proxy_host_port <= 0 or not container.control_proxy_token:
        return None
    if require_running and container.status != SandboxContainerStatus.RUNNING:
        return None

    base = f"http://{host.ip_address}:{container.control_proxy_host_port}"
    return SandboxControlProxyTarget(
        container_id=container.id or container_id,
        base_url=base,
        ws_base_url=f"ws://{host.ip_address}:{container.control_proxy_host_port}",
        token=container.control_proxy_token,
        status=container.status,
    )


def sandbox_control_proxy_token_headers(target: SandboxControlProxyTarget) -> dict[str, str]:
    return {"X-Sandbox-Token": target.token}


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), trust_env=False)
    return _http_client


async def close_control_proxy_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def resolve_container_egress_environment(container_id: int) -> dict[str, str]:
    async with get_async_session() as session:
        row = (await session.exec(
            select(SandboxContainer, EgressProxy)
            .outerjoin(EgressProxy, SandboxContainer.egress_proxy_id == EgressProxy.id)
            .where(SandboxContainer.id == container_id)
        )).first()
    if row is None:
        raise ValueError("sandbox container not found")
    container, proxy = row
    return sandbox_egress_container_environment(SandboxEgressSelection(
        mode=container.egress_mode,
        proxy=proxy,
    ))


async def apply_container_egress(container_id: int) -> None:
    target = await resolve_sandbox_control_proxy_target(container_id, require_running=True)
    if target is None:
        raise ValueError("sandbox container is not running")
    environment = await resolve_container_egress_environment(container_id)
    await apply_egress_environment(target, environment)


async def apply_managed_proxy_egress_to_running_containers(egress_proxy_id: int) -> list[int]:
    async with get_async_session() as session:
        container_ids = list((await session.exec(
            select(SandboxContainer.id)
            .where(SandboxContainer.egress_mode == SandboxContainerEgressMode.PROXY)
            .where(SandboxContainer.egress_proxy_id == egress_proxy_id)
            .where(SandboxContainer.status == SandboxContainerStatus.RUNNING)
        )).all())

    failed: list[int] = []
    for container_id in container_ids:
        if container_id is None:
            continue
        try:
            await apply_container_egress(container_id)
        except Exception:
            failed.append(container_id)
    return failed


async def apply_egress_environment(target: SandboxControlProxyTarget, environment: dict[str, str]) -> None:
    payload = {"environment": environment}
    last_error: Exception | None = None
    for attempt in range(_EGRESS_APPLY_ATTEMPTS):
        try:
            response = await _get_http_client().post(
                f"{target.base_url}/egress",
                json=payload,
                headers=sandbox_control_proxy_token_headers(target),
            )
            response.raise_for_status()
            return
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt < _EGRESS_APPLY_ATTEMPTS - 1:
                await asyncio.sleep(_EGRESS_APPLY_RETRY_SECONDS)
    if last_error is not None:
        raise last_error
