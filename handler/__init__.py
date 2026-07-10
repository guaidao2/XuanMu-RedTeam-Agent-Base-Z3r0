"""Shared handler utilities."""

import asyncio
from typing import Any

from fastapi import WebSocket, status as ws_status

from logger import get_logger
from middleware.auth import AuthUser, decode_access_token


logger = get_logger(__name__)


async def cancel_ws_task(task: asyncio.Task | None) -> None:
    """Cancel an asyncio task spawned by a WebSocket handler, draining any result."""
    if task is None:
        return
    if task.done():
        try:
            task.result()
        except (asyncio.CancelledError, Exception):
            pass
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def close_ws_silently(websocket: WebSocket, code: int = ws_status.WS_1011_INTERNAL_ERROR) -> None:
    """Best-effort WebSocket close that never raises."""
    try:
        await websocket.close(code=code)
    except Exception:
        pass


async def finish_ws_reader_task(task: asyncio.Task | None) -> None:
    """Wait briefly for a shell reader task to finish, then cancel if still running."""
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=1)
    except asyncio.TimeoutError:
        await cancel_ws_task(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("shell reader stopped with error", exc_info=True)


def authenticate_ws_token(token: str) -> AuthUser | None:
    """Decode a JWT access token for WebSocket authentication."""
    try:
        return decode_access_token(token)
    except Exception:
        return None


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Clamp a value to [minimum, maximum], returning default on parse failure."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))
