from fastapi import APIRouter, Depends, Query

from handler.work_project.projects import (
    cancel_work_project_handler,
    create_work_project_handler,
    create_work_project_session_handler,
    delete_work_project_handler,
    delete_work_project_session_handler,
    get_work_project_record_snapshot_handler,
    list_work_project_sessions_handler,
    query_work_projects_handler,
    retry_work_project_handler,
    update_work_project_metadata_handler,
)
from middleware.auth import AuthUser, require_admin, require_user
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.work_project.projects import (
    CreateWorkProjectRequest,
    CreateWorkProjectSessionResponse,
    DeleteWorkProjectResponse,
    ListWorkProjectSessionsResponse,
    QueryWorkProjectsResponse,
    UpdateWorkProjectMetadataRequest,
    WorkProjectSchema,
)
from schema.work_project.records import WorkProjectRecordSnapshotSchema


NOT_FOUND_RESPONSE = not_found_response("Work project")

router = APIRouter(
    prefix="/work-projects",
    tags=["work-projects"],
    dependencies=[Depends(require_user)],
)


async def query_work_projects_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[QueryWorkProjectsResponse]:
    return await query_work_projects_handler(page=page, size=size, keyword=keyword, user=user)


async def create_work_project_route(
    request: CreateWorkProjectRequest,
    _: AuthUser = Depends(require_admin),
) -> CommonResponse[WorkProjectSchema]:
    return await create_work_project_handler(request=request)


async def get_work_project_record_snapshot_route(
    id: int,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[WorkProjectRecordSnapshotSchema]:
    return await get_work_project_record_snapshot_handler(id=id, user=user)


async def update_work_project_metadata_route(
    id: int,
    request: UpdateWorkProjectMetadataRequest,
    _: AuthUser = Depends(require_admin),
) -> CommonResponse[WorkProjectSchema]:
    return await update_work_project_metadata_handler(id=id, request=request)


async def create_work_project_session_route(
    id: int,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[CreateWorkProjectSessionResponse]:
    return await create_work_project_session_handler(id=id, user=user)


async def list_work_project_sessions_route(
    id: int,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[ListWorkProjectSessionsResponse]:
    return await list_work_project_sessions_handler(id=id, user=user)


async def delete_work_project_session_route(
    id: int,
    session_id: str,
    user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await delete_work_project_session_handler(id=id, session_id=session_id, user=user)


router.add_api_route(
    "",
    create_work_project_route,
    methods=["POST"],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "",
    query_work_projects_route,
    methods=["GET"],
    response_model=CommonResponse[QueryWorkProjectsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/record-snapshot",
    get_work_project_record_snapshot_route,
    methods=["GET"],
    response_model=CommonResponse[WorkProjectRecordSnapshotSchema],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/metadata",
    update_work_project_metadata_route,
    methods=["PATCH"],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/sessions",
    list_work_project_sessions_route,
    methods=["GET"],
    response_model=CommonResponse[ListWorkProjectSessionsResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/sessions",
    create_work_project_session_route,
    methods=["POST"],
    response_model=CommonResponse[CreateWorkProjectSessionResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/sessions/{session_id}",
    delete_work_project_session_route,
    methods=["DELETE"],
    response_model=CommonResponse,
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}",
    delete_work_project_handler,
    methods=["DELETE"],
    dependencies=[Depends(require_admin)],
    response_model=CommonResponse[DeleteWorkProjectResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/cancel",
    cancel_work_project_handler,
    methods=["POST"],
    dependencies=[Depends(require_admin)],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/retry",
    retry_work_project_handler,
    methods=["POST"],
    dependencies=[Depends(require_admin)],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
