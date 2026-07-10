from http import HTTPStatus

from schema.common.responses import CommonResponse
from schema.system_user.users import (
    CreateSystemUserRequest,
    DeleteSystemUserResponse,
    QuerySystemUsersResponse,
    SystemUserLoginRequest,
    SystemUserLoginResponse,
    SystemUserSchema,
    UpdateSystemUserRequest,
)
from service.system_user.users import (
    create_system_user,
    delete_system_user,
    query_system_users,
    system_user_login,
    update_system_user,
)
from service.common.pagination import paginated_payload


async def create_system_user_handler(request: CreateSystemUserRequest) -> CommonResponse:
    system_user = await create_system_user(
        username=request.username,
        password=request.password,
        email=request.email,
        role=request.role,
    )
    return CommonResponse(data=SystemUserSchema.model_validate(system_user))


async def delete_system_user_handler(id: int) -> CommonResponse:
    result = await delete_system_user(id)
    if result.not_found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="system user not found")
    if not result.deleted:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=DeleteSystemUserResponse(id=id))


async def update_system_user_handler(id: int, request: UpdateSystemUserRequest) -> CommonResponse:
    system_user = await update_system_user(
        id=id,
        username=request.username,
        password=request.password,
        email=request.email,
        role=request.role,
    )
    if system_user is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="system user not found")
    return CommonResponse(data=SystemUserSchema.model_validate(system_user))


async def query_system_users_handler(page: int, size: int, keyword: str) -> CommonResponse:
    system_users = await query_system_users(page=page, size=size, keyword=keyword)
    return CommonResponse(data=QuerySystemUsersResponse(
        **paginated_payload(
            system_users,
            [SystemUserSchema.model_validate(user) for user in system_users.items],
        ),
    ))


async def system_user_login_handler(request: SystemUserLoginRequest) -> CommonResponse:
    token = await system_user_login(email=request.email, password=request.password)
    if token is None:
        return CommonResponse(code=HTTPStatus.UNAUTHORIZED.value, message="invalid email or password")
    return CommonResponse(data=SystemUserLoginResponse(token=token))
