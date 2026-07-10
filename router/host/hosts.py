from fastapi import APIRouter, Depends, Query, WebSocket

from handler.host.hosts import (
    create_managed_host_handler,
    delete_managed_host_handler,
    delete_managed_host_image_handler,
    handle_host_shell_stream,
    list_managed_host_images_handler,
    pull_managed_host_images_handler,
    query_managed_hosts_handler,
    update_managed_host_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.host.hosts import (
    DeleteManagedHostResponse,
    ListManagedHostImagesResponse,
    ManagedHostSchema,
    PullManagedHostImagesResponse,
    QueryManagedHostsResponse,
)


NOT_FOUND_RESPONSE = not_found_response("Managed host")
ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/hosts", tags=["hosts"])


async def query_managed_hosts_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QueryManagedHostsResponse]:
    return await query_managed_hosts_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    create_managed_host_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[ManagedHostSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "/{id}",
    update_managed_host_handler,
    methods=["PATCH"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[ManagedHostSchema],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}",
    delete_managed_host_handler,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteManagedHostResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_managed_hosts_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QueryManagedHostsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/images",
    list_managed_host_images_handler,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[ListManagedHostImagesResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/images/pull",
    pull_managed_host_images_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[PullManagedHostImagesResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/images/remove",
    delete_managed_host_image_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse,
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **BAD_REQUEST_RESPONSE},
)


@router.websocket("/{id}/shell")
async def host_shell_stream(
    websocket: WebSocket,
    id: int,
    token: str = Query(default=""),
) -> None:
    await handle_host_shell_stream(websocket=websocket, id=id, token=token)
