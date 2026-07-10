from fastapi import APIRouter, Depends, Query

from handler.system_user.users import (
    create_system_user_handler,
    delete_system_user_handler,
    query_system_users_handler,
    system_user_login_handler,
    update_system_user_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.system_user.users import (
    DeleteSystemUserResponse,
    QuerySystemUsersResponse,
    SystemUserLoginResponse,
    SystemUserSchema,
)


NOT_FOUND_RESPONSE = not_found_response("System user")
LOGIN_ERROR_RESPONSES = {
    401: {"description": "Invalid email or password", "model": CommonResponse},
    422: {"description": "Validation Error", "model": CommonResponse},
}

ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/system-users", tags=["system-users"])


async def query_system_users_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QuerySystemUsersResponse]:
    return await query_system_users_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    create_system_user_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SystemUserSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/login",
    system_user_login_handler,
    methods=["POST"],
    response_model=CommonResponse[SystemUserLoginResponse],
    responses=LOGIN_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    delete_system_user_handler,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteSystemUserResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}",
    update_system_user_handler,
    methods=["PATCH"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SystemUserSchema],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_system_users_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QuerySystemUsersResponse],
    responses=COMMON_ERROR_RESPONSES,
)
