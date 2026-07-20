from fastapi import APIRouter, Depends

from handler.blackboard.nodes import (
    create_blackboard_node_handler,
    delete_blackboard_node_handler,
    get_blackboard_handler,
    update_blackboard_node_handler,
)
from middleware.auth import AuthUser, require_user
from router.common.responses import not_found_response
from schema.blackboard.nodes import (
    BlackboardCreateNodeRequest,
    BlackboardSnapshotSchema,
    BlackboardUpdateNodeRequest,
)
from schema.common.responses import CommonResponse

NOT_FOUND_RESPONSE = not_found_response("Blackboard")

router = APIRouter(
    prefix="/blackboard",
    tags=["blackboard"],
    dependencies=[Depends(require_user)],
)


async def get_blackboard_route(
    project_id: int,
    _user: AuthUser = Depends(require_user),
) -> CommonResponse[BlackboardSnapshotSchema]:
    return await get_blackboard_handler(project_id=project_id)


async def create_blackboard_node_route(
    project_id: int,
    request: BlackboardCreateNodeRequest,
    _user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await create_blackboard_node_handler(project_id=project_id, request=request)


async def update_blackboard_node_route(
    project_id: int,
    node_id: int,
    request: BlackboardUpdateNodeRequest,
    _user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await update_blackboard_node_handler(
        project_id=project_id, node_id=node_id, request=request
    )


async def delete_blackboard_node_route(
    project_id: int,
    node_id: int,
    _user: AuthUser = Depends(require_user),
) -> CommonResponse:
    return await delete_blackboard_node_handler(project_id=project_id, node_id=node_id)


router.add_api_route(
    "/{project_id}",
    get_blackboard_route,
    methods=["GET"],
    response_model=CommonResponse[BlackboardSnapshotSchema],
    summary="Read full blackboard graph for a project",
)
router.add_api_route(
    "/{project_id}/nodes",
    create_blackboard_node_route,
    methods=["POST"],
    response_model=CommonResponse,
    summary="Create a new blackboard node (fact / intent / hint)",
)
router.add_api_route(
    "/{project_id}/nodes/{node_id}",
    update_blackboard_node_route,
    methods=["PUT"],
    response_model=CommonResponse,
    summary="Update a blackboard node (status / description / etc)",
)
router.add_api_route(
    "/{project_id}/nodes/{node_id}",
    delete_blackboard_node_route,
    methods=["DELETE"],
    response_model=CommonResponse,
    summary="Delete a blackboard node",
)
