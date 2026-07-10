from http import HTTPStatus

from middleware.auth import AuthUser
from schema.common.responses import CommonResponse
from schema.work_project.projects import (
    CreateWorkProjectRequest,
    CreateWorkProjectSessionResponse,
    DeleteWorkProjectResponse,
    ListWorkProjectSessionsResponse,
    QueryWorkProjectsResponse,
    UpdateWorkProjectMetadataRequest,
)
from service.work_project.projects import (
    cancel_work_project,
    create_work_project,
    create_work_project_session,
    delete_work_project,
    delete_work_project_session,
    get_work_project_record_snapshot_for_user,
    list_work_project_sessions,
    query_work_projects_for_user,
    retry_work_project,
    update_work_project_metadata,
    validate_work_project_metadata,
    work_project_exists,
)
from service.common.pagination import paginated_payload


async def create_work_project_handler(request: CreateWorkProjectRequest) -> CommonResponse:
    validation_error = await validate_work_project_metadata(request)
    if validation_error:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=validation_error)
    project = await create_work_project(request)
    return CommonResponse(data=project)


async def get_work_project_record_snapshot_handler(id: int, user: AuthUser) -> CommonResponse:
    snapshot = await get_work_project_record_snapshot_for_user(id, user_id=user.id, user_role=user.role)
    if snapshot is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    return CommonResponse(data=snapshot)


async def update_work_project_metadata_handler(
    id: int,
    request: UpdateWorkProjectMetadataRequest,
) -> CommonResponse:
    if not await work_project_exists(id):
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    validation_error = await validate_work_project_metadata(request, project_id=id)
    if validation_error:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=validation_error)
    project = await update_work_project_metadata(id, request)
    if project is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    return CommonResponse(message="work project updated", data=project)


async def delete_work_project_handler(id: int) -> CommonResponse:
    if not await delete_work_project(id):
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    return CommonResponse(data=DeleteWorkProjectResponse(id=id))


async def cancel_work_project_handler(id: int) -> CommonResponse:
    project, canceled = await cancel_work_project(id)
    if project is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if not canceled:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="canceled projects cannot be canceled again",
            data=project,
        )
    return CommonResponse(message="work project canceled", data=project)


async def retry_work_project_handler(id: int) -> CommonResponse:
    project, retried = await retry_work_project(id)
    if project is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if not retried:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only canceled projects can be retried",
            data=project,
        )
    return CommonResponse(message="work project restarted", data=project)


async def query_work_projects_handler(page: int, size: int, keyword: str, user: AuthUser) -> CommonResponse:
    projects = await query_work_projects_for_user(
        page=page,
        size=size,
        keyword=keyword,
        user_id=user.id,
        user_role=user.role,
    )
    return CommonResponse(data=QueryWorkProjectsResponse(**paginated_payload(projects, projects.items)))


async def create_work_project_session_handler(
    id: int,
    user: AuthUser,
) -> CommonResponse:
    result = await create_work_project_session(
        id,
        owner_id=user.id,
        user_role=user.role,
    )
    if result.not_found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if result.inactive:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message="canceled projects cannot create sessions")
    return CommonResponse(data=CreateWorkProjectSessionResponse(session_id=result.session_id))


async def list_work_project_sessions_handler(id: int, user: AuthUser) -> CommonResponse:
    sessions = await list_work_project_sessions(id, user_id=user.id, user_role=user.role)
    if sessions is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    return CommonResponse(data=ListWorkProjectSessionsResponse(items=sessions))


async def delete_work_project_session_handler(id: int, session_id: str, user: AuthUser) -> CommonResponse:
    deleted = await delete_work_project_session(
        project_id=id,
        session_id=session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if deleted is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if not deleted:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project session not found")
    return CommonResponse(message="work project session deleted")
