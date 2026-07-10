from fastapi import APIRouter, Cookie, Depends, File, Form, Query, UploadFile, WebSocket
from starlette.responses import StreamingResponse

from handler.sandbox.containers import (
    create_sandbox_container_handler,
    delete_sandbox_container_handler,
    handle_container_shell_stream,
    handle_copy_files,
    handle_delete_files,
    handle_download_files,
    handle_list_files,
    handle_mkdir,
    handle_move_files,
    handle_novnc_http_proxy,
    handle_novnc_ws_proxy,
    handle_read_file,
    handle_upload_files,
    handle_write_file,
    query_available_sandbox_containers_handler,
    query_sandbox_containers_handler,
    start_sandbox_container_handler,
    stop_sandbox_container_handler,
    update_sandbox_container_egress_handler,
)
from middleware.auth import AuthUser, require_admin, require_user
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, CONFLICT_RESPONSE, INTERNAL_ERROR_RESPONSE, not_found_response
from schema.common.responses import CommonResponse
from schema.sandbox.containers import (
    ContainerFileCopyRequest,
    ContainerFileDeleteRequest,
    ContainerFileMkdirRequest,
    ContainerFileMoveRequest,
    ContainerFileReadResponse,
    ContainerFileUploadResponse,
    ContainerFileWriteRequest,
    CreateSandboxContainerRequest,
    DeleteSandboxContainerResponse,
    ListContainerFilesResponse,
    QuerySandboxContainersResponse,
    SandboxContainerSchema,
    UpdateSandboxContainerEgressRequest,
)


NOT_FOUND_RESPONSE = not_found_response("Sandbox container")
CREATE_NOT_FOUND_RESPONSE = not_found_response("Sandbox image")
FILE_OPERATION_ERROR_RESPONSES = {
    **COMMON_ERROR_RESPONSES,
    **NOT_FOUND_RESPONSE,
    **BAD_REQUEST_RESPONSE,
    **INTERNAL_ERROR_RESPONSE,
}
FILE_UPLOAD_ERROR_RESPONSES = {
    **FILE_OPERATION_ERROR_RESPONSES,
    **CONFLICT_RESPONSE,
}

router = APIRouter(
    prefix="/sandbox-containers",
    tags=["sandbox-containers"],
)

ADMIN_ONLY = [Depends(require_admin)]


async def create_sandbox_container_route(
    request: CreateSandboxContainerRequest,
    user: AuthUser = Depends(require_admin),
) -> CommonResponse[SandboxContainerSchema]:
    effective_owner_id = request.owner_id if request.owner_id is not None else user.id
    return await create_sandbox_container_handler(request=request, owner_id=effective_owner_id)


async def query_sandbox_containers_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QuerySandboxContainersResponse]:
    return await query_sandbox_containers_handler(page=page, size=size, keyword=keyword)


async def query_available_sandbox_containers_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[QuerySandboxContainersResponse]:
    return await query_available_sandbox_containers_handler(
        page=page,
        size=size,
        keyword=keyword,
        user_id=user.id,
        user_role=user.role,
    )


router.add_api_route(
    "",
    create_sandbox_container_route,
    methods=["POST"],
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **CREATE_NOT_FOUND_RESPONSE},
)


router.add_api_route(
    "/available",
    query_available_sandbox_containers_route,
    methods=["GET"],
    response_model=CommonResponse[QuerySandboxContainersResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    delete_sandbox_container_handler,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteSandboxContainerResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/start",
    start_sandbox_container_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/stop",
    stop_sandbox_container_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/egress",
    update_sandbox_container_egress_handler,
    methods=["PATCH"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_sandbox_containers_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QuerySandboxContainersResponse],
    responses=COMMON_ERROR_RESPONSES,
)


# ── container file manager routes ──────────────────────────────────────────────


async def list_container_files_route(
    id: int,
    path: str = Query(default="/"),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListContainerFilesResponse]:
    return await handle_list_files(id=id, path=path, user=user)


async def read_container_file_route(
    id: int,
    path: str = Query(default=""),
    base64: bool = Query(default=False),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ContainerFileReadResponse]:
    return await handle_read_file(id=id, path=path, base64_mode=base64, user=user)


async def write_container_file_route(
    id: int,
    body: ContainerFileWriteRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await handle_write_file(id=id, body=body, user=user)


async def upload_container_files_route(
    id: int,
    path: str = Form(default="/"),
    overwrite: bool = Form(default=True),
    files: list[UploadFile] = File(),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ContainerFileUploadResponse]:
    return await handle_upload_files(id=id, path=path, files=files, overwrite=overwrite, user=user)


async def download_container_files_route(
    id: int,
    path: list[str] = Query(min_length=1),
    user: AuthUser = Depends(require_user),
) -> StreamingResponse | CommonResponse:
    return await handle_download_files(id=id, paths=path, user=user)


async def copy_container_files_route(
    id: int,
    body: ContainerFileCopyRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await handle_copy_files(id=id, body=body, user=user)


async def move_container_files_route(
    id: int,
    body: ContainerFileMoveRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await handle_move_files(id=id, body=body, user=user)


async def delete_container_files_route(
    id: int,
    body: ContainerFileDeleteRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await handle_delete_files(id=id, body=body, user=user)


async def mkdir_container_files_route(
    id: int,
    body: ContainerFileMkdirRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await handle_mkdir(id=id, body=body, user=user)


router.add_api_route(
    "/{id}/files",
    list_container_files_route,
    methods=["GET"],
    response_model=CommonResponse[ListContainerFilesResponse],
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/read",
    read_container_file_route,
    methods=["GET"],
    response_model=CommonResponse[ContainerFileReadResponse],
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/write",
    write_container_file_route,
    methods=["POST"],
    response_model=CommonResponse,
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/upload",
    upload_container_files_route,
    methods=["POST"],
    response_model=CommonResponse[ContainerFileUploadResponse],
    responses=FILE_UPLOAD_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/download",
    download_container_files_route,
    methods=["GET"],
    response_model=None,
    response_class=StreamingResponse,
    responses={
        **FILE_OPERATION_ERROR_RESPONSES,
        200: {
            "description": "File stream or tar archive",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
                "application/x-tar": {"schema": {"type": "string", "format": "binary"}},
            },
        },
    },
)

router.add_api_route(
    "/{id}/files/copy",
    copy_container_files_route,
    methods=["POST"],
    response_model=CommonResponse,
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/move",
    move_container_files_route,
    methods=["POST"],
    response_model=CommonResponse,
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/delete",
    delete_container_files_route,
    methods=["POST"],
    response_model=CommonResponse,
    responses=FILE_OPERATION_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/files/mkdir",
    mkdir_container_files_route,
    methods=["POST"],
    response_model=CommonResponse,
    responses=FILE_OPERATION_ERROR_RESPONSES,
)


@router.websocket("/{id}/shell")
async def container_shell_stream(
    websocket: WebSocket,
    id: int,
    token: str = Query(default=""),
) -> None:
    await handle_container_shell_stream(
        websocket=websocket,
        id=id,
        token=token,
    )


@router.websocket("/{id}/novnc-ws")
async def container_novnc_ws(
    websocket: WebSocket,
    id: int,
    token: str = Query(default=""),
) -> None:
    await handle_novnc_ws_proxy(
        websocket=websocket,
        id=id,
        token=token,
    )


@router.api_route("/{id}/novnc/{path:path}", methods=["GET"], include_in_schema=False)
async def container_novnc_http(
    id: int,
    path: str,
    token: str = Query(default=""),
    sandbox_novnc_access: str = Cookie(default=""),
):
    return await handle_novnc_http_proxy(
        id=id,
        path=path,
        token=token,
        cookie_token=sandbox_novnc_access,
    )
