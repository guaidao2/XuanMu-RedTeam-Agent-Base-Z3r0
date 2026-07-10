from fastapi import APIRouter, Depends, Query

from handler.sandbox.images import (
    create_sandbox_image_handler,
    delete_sandbox_image_handler,
    query_sandbox_images_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.sandbox.images import (
    DeleteSandboxImageResponse,
    QuerySandboxImagesResponse,
    SandboxImageSchema,
)


NOT_FOUND_RESPONSE = not_found_response("Sandbox image")

router = APIRouter(
    prefix="/sandbox-images",
    tags=["sandbox-images"],
    dependencies=[Depends(require_admin)],
)


async def query_sandbox_images_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QuerySandboxImagesResponse]:
    return await query_sandbox_images_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    create_sandbox_image_handler,
    methods=["POST"],
    response_model=CommonResponse[SandboxImageSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    delete_sandbox_image_handler,
    methods=["DELETE"],
    response_model=CommonResponse[DeleteSandboxImageResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_sandbox_images_route,
    methods=["GET"],
    response_model=CommonResponse[QuerySandboxImagesResponse],
    responses=COMMON_ERROR_RESPONSES,
)
