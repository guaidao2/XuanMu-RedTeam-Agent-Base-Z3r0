import asyncio
import json
from http import HTTPStatus

from fastapi import WebSocket, WebSocketDisconnect, status as ws_status
from fastapi.websockets import WebSocketState

from handler import (
    authenticate_ws_token,
    bounded_int,
    cancel_ws_task as _cancel_task,
    close_ws_silently as _close_silently,
    finish_ws_reader_task,
)
from logger import get_logger
from schema.common.responses import CommonResponse
from schema.host.hosts import (
    CreateManagedHostRequest,
    DeleteManagedHostImageRequest,
    DeleteManagedHostResponse,
    ListManagedHostImagesResponse,
    ManagedHostSchema,
    PullManagedHostImagesRequest,
    PullManagedHostImagesResponse,
    QueryManagedHostsResponse,
    UpdateManagedHostRequest,
)
from schema.system_user.users import SystemUserRole
from service.common.pagination import paginated_payload
from service.host.hosts import (
    create_managed_host,
    delete_managed_host,
    delete_managed_host_image,
    list_managed_host_images,
    pull_managed_host_images,
    query_managed_hosts,
    update_managed_host,
)
from service.host.shell import (
    ShellSession,
    open_host_shell,
    read_host_shell,
    resize_host_shell,
    resolve_shell_host,
    write_host_shell,
)


logger = get_logger(__name__)


async def create_managed_host_handler(request: CreateManagedHostRequest) -> CommonResponse:
    host = await create_managed_host(
        ip_address=request.ip_address,
        ssh_port=request.ssh_port,
        host_account=request.host_account,
        host_password=request.host_password,
        docker_management_port=request.docker_management_port,
        docker_tls_enabled=request.docker_tls_enabled,
        docker_client_ca_cert=request.docker_client_ca_cert,
        docker_client_cert=request.docker_client_cert,
        docker_client_key=request.docker_client_key,
    )
    return CommonResponse(data=ManagedHostSchema.model_validate(host))


async def update_managed_host_handler(id: int, request: UpdateManagedHostRequest) -> CommonResponse:
    result = await update_managed_host(
        id=id,
        ip_address=request.ip_address,
        ssh_port=request.ssh_port,
        host_account=request.host_account,
        host_password=request.host_password,
        docker_management_port=request.docker_management_port,
        docker_tls_enabled=request.docker_tls_enabled,
        docker_client_ca_cert=request.docker_client_ca_cert,
        docker_client_cert=request.docker_client_cert,
        docker_client_key=request.docker_client_key,
    )
    if result.not_found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="managed host not found")
    if result.host is None or result.message:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=ManagedHostSchema.model_validate(result.host))


async def delete_managed_host_handler(id: int) -> CommonResponse:
    result = await delete_managed_host(id)
    if result.not_found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="managed host not found")
    if not result.deleted:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=DeleteManagedHostResponse(id=id))


async def query_managed_hosts_handler(page: int, size: int, keyword: str) -> CommonResponse:
    hosts = await query_managed_hosts(page=page, size=size, keyword=keyword)
    return CommonResponse(data=QueryManagedHostsResponse(
        **paginated_payload(
            hosts,
            [ManagedHostSchema.model_validate(host) for host in hosts.items],
        ),
    ))


async def list_managed_host_images_handler(id: int) -> CommonResponse:
    try:
        images = await list_managed_host_images(id)
    except Exception as exc:
        logger.warning("list host images failed: id=%s error=%s", id, exc)
        return CommonResponse(code=HTTPStatus.BAD_GATEWAY.value, message="failed to connect to docker host")
    if images is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="managed host not found")
    return CommonResponse(data=ListManagedHostImagesResponse(items=images))


async def pull_managed_host_images_handler(id: int, request: PullManagedHostImagesRequest) -> CommonResponse:
    try:
        results = await pull_managed_host_images(id, request.image_names)
    except Exception as exc:
        logger.warning("pull host images failed: id=%s error=%s", id, exc)
        return CommonResponse(code=HTTPStatus.BAD_GATEWAY.value, message="failed to connect to docker host")
    if results is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="managed host not found")
    return CommonResponse(data=PullManagedHostImagesResponse(items=results))


async def delete_managed_host_image_handler(id: int, request: DeleteManagedHostImageRequest) -> CommonResponse:
    error = await delete_managed_host_image(id, request.image_id, force=request.force)
    if error:
        code = HTTPStatus.NOT_FOUND.value if "not found" in error.lower() else HTTPStatus.BAD_REQUEST.value
        return CommonResponse(code=code, message=error)
    return CommonResponse(message="image removed")


async def handle_host_shell_stream(websocket: WebSocket, id: int, token: str) -> None:
    user = authenticate_ws_token(token)
    if user is None or user.role != SystemUserRole.ADMIN:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    host = await resolve_shell_host(id)
    if host is None:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    shell: ShellSession | None = None
    reader: asyncio.Task | None = None
    receiver: asyncio.Task | None = None

    try:
        try:
            shell = await open_host_shell(host)
        except Exception as exc:
            logger.warning(
                "host shell connection failed: id=%s host=%s error=%s",
                id,
                host.ip_address,
                str(exc).strip() or exc.__class__.__name__,
            )
            await _send_shell_error(websocket, exc)
            await _close_silently(websocket, ws_status.WS_1011_INTERNAL_ERROR)
            return

        reader = asyncio.create_task(_forward_shell_output(websocket, shell))

        while True:
            receiver = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait(
                {receiver, reader},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reader in done:
                await reader
                await _close_silently(websocket, ws_status.WS_1000_NORMAL_CLOSURE)
                return

            message = receiver.result()
            receiver = None
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await write_host_shell(shell, message)
                continue

            if not isinstance(payload, dict):
                continue
            message_type = payload.get("type")
            if message_type == "input":
                await write_host_shell(shell, str(payload.get("data", "")))
            elif message_type == "resize":
                rows = bounded_int(payload.get("rows"), default=24, minimum=1, maximum=300)
                cols = bounded_int(payload.get("cols"), default=80, minimum=1, maximum=500)
                await resize_host_shell(shell, rows=rows, cols=cols)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("host shell stream failed: %s", id)
        await _close_silently(websocket)
    finally:
        try:
            if shell is not None:
                shell.shutdown()
            await _cancel_task(receiver)
            await finish_ws_reader_task(reader)
        finally:
            if shell is not None:
                await shell.close()


async def _forward_shell_output(websocket: WebSocket, shell: ShellSession) -> None:
    while True:
        data = await read_host_shell(shell)
        if not data:
            return
        if websocket.client_state != WebSocketState.CONNECTED or websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_bytes(data)


async def _send_shell_error(websocket: WebSocket, error: Exception) -> None:
    if websocket.client_state != WebSocketState.CONNECTED or websocket.application_state != WebSocketState.CONNECTED:
        return
    message = str(error).strip() or error.__class__.__name__
    await websocket.send_bytes(f"\r\nShell connection failed: {message}\r\n".encode())
