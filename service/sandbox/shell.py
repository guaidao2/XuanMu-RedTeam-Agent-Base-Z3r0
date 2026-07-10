from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import websockets

from database import get_async_session
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerStatus
from service.sandbox.control_proxy import resolve_sandbox_control_proxy_target, sandbox_control_proxy_token_headers


_DEFAULT_SHELL_ROWS = 24
_DEFAULT_SHELL_COLS = 80


@dataclass
class ContainerShellSession:
    websocket: Any
    closed: bool = False

    def shutdown(self) -> None:
        return None

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.websocket.close()


async def resolve_shell_container(id: int) -> SandboxContainer | None:
    async with get_async_session() as session:
        container = await session.get(SandboxContainer, id)
        if container is None or container.status != SandboxContainerStatus.RUNNING:
            return None
        return container


async def open_container_shell(
    id: int,
    rows: int = _DEFAULT_SHELL_ROWS,
    cols: int = _DEFAULT_SHELL_COLS,
) -> ContainerShellSession:
    target = await resolve_sandbox_control_proxy_target(id, require_running=True)
    if target is None:
        raise ValueError("sandbox container not found")
    url = f"{target.ws_base_url}/shell?token={target.token}"
    websocket = await websockets.connect(
        url,
        additional_headers=sandbox_control_proxy_token_headers(target),
        proxy=None,
        open_timeout=10,
        close_timeout=5,
        max_size=2**20,
    )
    await websocket.send(_resize_message(rows, cols))
    return ContainerShellSession(websocket=websocket)


async def resize_container_shell(session: ContainerShellSession, rows: int, cols: int) -> None:
    rows = max(1, min(rows, 300))
    cols = max(1, min(cols, 500))
    await session.websocket.send(_resize_message(rows, cols))


async def read_container_shell(session: ContainerShellSession) -> bytes:
    try:
        data = await session.websocket.recv()
    except (websockets.exceptions.ConnectionClosed, OSError, ValueError, asyncio.CancelledError):
        return b""
    if isinstance(data, str):
        return data.encode()
    return data or b""


async def write_container_shell(session: ContainerShellSession, data: str) -> None:
    if not data:
        return
    await session.websocket.send(data)


def _resize_message(rows: int, cols: int) -> str:
    return f"\x00resize:{rows}:{cols}"
