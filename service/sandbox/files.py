import json as json_module
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from typing import BinaryIO

import httpx

from schema.sandbox.containers import ContainerFileInfo, ContainerFileUploadItem, SandboxContainerStatus
from service.sandbox.control_proxy import SandboxControlProxyTarget, resolve_sandbox_control_proxy_target, sandbox_control_proxy_token_headers


_http_client: httpx.AsyncClient | None = None


@dataclass(frozen=True)
class ContainerUploadSource:
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class ContainerDownloadStream:
    filename: str
    media_type: str
    chunks: AsyncIterator[bytes]


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=False)
    return _http_client


async def close_file_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def resolve_file_container_status(id: int) -> SandboxContainerStatus | None:
    target = await resolve_sandbox_control_proxy_target(id)
    if target is None:
        return None
    return target.status


async def list_container_files(container_id: int, path: str) -> list[ContainerFileInfo]:
    payload = await _request_json(container_id, "GET", "/files", params={"path": path})
    files = payload.get("files", [])
    return [ContainerFileInfo.model_validate(file) for file in files if isinstance(file, dict)]


async def get_container_file_info(container_id: int, path: str) -> ContainerFileInfo | None:
    payload = await _request_json(container_id, "GET", "/files/info", params={"path": path})
    info = payload.get("file")
    return ContainerFileInfo.model_validate(info) if isinstance(info, dict) else None


async def read_container_file(container_id: int, path: str, max_bytes: int = 1_048_576, *, base64_mode: bool = False) -> str:
    payload = await _request_json(
        container_id,
        "GET",
        "/files/read",
        params={"path": path, "max_bytes": str(max_bytes), "base64": str(base64_mode).lower()},
    )
    content = payload.get("content", "")
    return str(content)


async def upload_container_files(
    container_id: int,
    path: str,
    sources: list[ContainerUploadSource],
    overwrite: bool,
) -> list[ContainerFileUploadItem]:
    files = []
    try:
        for source in sources:
            files.append(("files", (source.filename, source.stream, "application/octet-stream")))
        payload = await _request_json(
            container_id,
            "POST",
            "/files/upload",
            data={"path": path, "overwrite": str(overwrite).lower()},
            files=files,
        )
    finally:
        for source in sources:
            source.stream.close()
    uploaded = payload.get("files", [])
    return [ContainerFileUploadItem.model_validate(item) for item in uploaded if isinstance(item, dict)]


async def download_container_paths(container_id: int, paths: list[str]) -> ContainerDownloadStream:
    target = await _resolve_running_target(container_id)
    if target is None:
        raise FileNotFoundError("sandbox container not found")
    params = [("path", path) for path in paths]
    stream = _get_http_client().stream(
        "GET",
        f"{target.base_url}/files/download",
        params=params,
        headers=sandbox_control_proxy_token_headers(target),
    )
    response = await stream.__aenter__()
    try:
        await _raise_for_control_proxy_stream_response(response)
    except Exception:
        await stream.__aexit__(None, None, None)
        raise
    filename = _download_filename(response.headers.get("content-disposition", ""))
    return ContainerDownloadStream(
        filename=filename,
        media_type=response.headers.get("content-type", "application/octet-stream"),
        chunks=_stream_response_bytes(response, stream),
    )


async def write_container_file(container_id: int, path: str, content: str) -> bool:
    await _request_json(container_id, "POST", "/files/write", json={"path": path, "content": content})
    return True


async def copy_container_files(container_id: int, sources: list[str], destination: str) -> bool:
    await _request_json(container_id, "POST", "/files/copy", json={"sources": sources, "destination": destination})
    return True


async def move_container_files(container_id: int, sources: list[str], destination: str) -> bool:
    await _request_json(container_id, "POST", "/files/move", json={"sources": sources, "destination": destination})
    return True


async def delete_container_files(container_id: int, paths: list[str]) -> bool:
    await _request_json(container_id, "POST", "/files/delete", json={"paths": paths})
    return True


async def create_container_directory(container_id: int, path: str) -> bool:
    await _request_json(container_id, "POST", "/files/mkdir", json={"path": path})
    return True


async def _request_json(
    container_id: int,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json: dict | None = None,
    data: dict | None = None,
    files: list | None = None,
) -> dict:
    target = await _resolve_running_target(container_id)
    if target is None:
        raise FileNotFoundError("sandbox container not found")
    response = await _get_http_client().request(
        method,
        f"{target.base_url}{path}",
        params=params,
        json=json,
        data=data,
        files=files,
        headers=sandbox_control_proxy_token_headers(target),
    )
    _raise_for_control_proxy_response(response)
    try:
        payload = response.json()
    except json_module.JSONDecodeError as exc:
        raise RuntimeError("invalid sandbox control proxy response") from exc
    return payload if isinstance(payload, dict) else {}


async def _resolve_running_target(container_id: int) -> SandboxControlProxyTarget | None:
    return await resolve_sandbox_control_proxy_target(container_id, require_running=True)


def _raise_for_control_proxy_response(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise FileNotFoundError("path not found")
    if response.status_code == 409:
        raise FileExistsError(response.text)
    if response.status_code >= 400:
        raise RuntimeError(response.text or "sandbox control proxy request failed")


async def _raise_for_control_proxy_stream_response(response: httpx.Response) -> None:
    if response.status_code == 404:
        raise FileNotFoundError("path not found")
    if response.status_code < 400:
        return
    content = await response.aread()
    message = content.decode(errors="replace") if content else "sandbox control proxy request failed"
    if response.status_code == 409:
        raise FileExistsError(message)
    raise RuntimeError(message)


async def _stream_response_bytes(response: httpx.Response, stream) -> AsyncIterator[bytes]:
    async with aclosing(response.aiter_bytes()) as chunks:
        try:
            async for chunk in chunks:
                yield chunk
        finally:
            await stream.__aexit__(None, None, None)


def _download_filename(content_disposition: str) -> str:
    marker = "filename="
    if marker not in content_disposition:
        return "download"
    raw = content_disposition.split(marker, 1)[1].split(";", 1)[0].strip().strip('"')
    return raw or "download"
