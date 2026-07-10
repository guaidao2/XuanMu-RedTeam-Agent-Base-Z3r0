import asyncio
from dataclasses import dataclass

import httpx
import websockets
from logger import get_logger
from service.sandbox.control_proxy import SandboxControlProxyTarget, resolve_sandbox_control_proxy_target, sandbox_control_proxy_token_headers


logger = get_logger(__name__)

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            trust_env=False,
        )
    return _http_client


async def close_novnc_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


@dataclass(frozen=True)
class NoVNCTarget:
    control_proxy: SandboxControlProxyTarget


async def resolve_novnc_target(container_id: int) -> NoVNCTarget | None:
    target = await resolve_sandbox_control_proxy_target(container_id, require_running=True)
    if target is None:
        return None
    return NoVNCTarget(control_proxy=target)


async def proxy_novnc_http(target: NoVNCTarget, path: str) -> httpx.Response | None:
    url = f"{target.control_proxy.base_url}/novnc/{path}"
    try:
        return await _get_http_client().get(url, headers=sandbox_control_proxy_token_headers(target.control_proxy))
    except (httpx.HTTPError, OSError):
        logger.debug("novnc http proxy failed: %s -> %s", target.control_proxy.container_id, url, exc_info=True)
        return None


async def proxy_novnc_websocket(
    target: NoVNCTarget,
    receive_from_client,
    send_to_client,
    client_connected,
    subprotocols: list[str] | None = None,
) -> None:
    url = f"{target.control_proxy.ws_base_url}/websockify?token={target.control_proxy.token}"
    try:
        async with websockets.connect(
            url,
            additional_headers=sandbox_control_proxy_token_headers(target.control_proxy),
            subprotocols=subprotocols or [],
            proxy=None,
            max_size=2**20,
            open_timeout=10,
            close_timeout=5,
        ) as upstream:
            await _bidirectional_ws_forward(upstream, receive_from_client, send_to_client, client_connected)
    except (websockets.exceptions.WebSocketException, OSError, asyncio.CancelledError):
        logger.debug("novnc ws proxy ended: %s", target.control_proxy.container_id, exc_info=True)


async def _bidirectional_ws_forward(upstream, receive_from_client, send_to_client, client_connected):
    async def forward_upstream_to_client():
        try:
            async for message in upstream:
                if not client_connected():
                    return
                await send_to_client(message)
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    async def forward_client_to_upstream():
        try:
            while client_connected():
                data = await receive_from_client()
                if data is None:
                    return
                await upstream.send(data)
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    upstream_task = asyncio.create_task(forward_upstream_to_client())
    client_task = asyncio.create_task(forward_client_to_upstream())
    try:
        await asyncio.wait({upstream_task, client_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (upstream_task, client_task):
            if not task.done():
                task.cancel()
        for task in (upstream_task, client_task):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
