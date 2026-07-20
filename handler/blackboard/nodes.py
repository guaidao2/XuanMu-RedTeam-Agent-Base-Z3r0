from http import HTTPStatus

from middleware.auth import AuthUser
from schema.blackboard.nodes import (
    BlackboardCreateNodeRequest,
    BlackboardSnapshotSchema,
    BlackboardUpdateNodeRequest,
)
from schema.common.responses import CommonResponse
from service.blackboard.nodes import (
    create_blackboard_node,
    delete_blackboard_node,
    get_blackboard_snapshot,
    update_blackboard_node,
)


async def get_blackboard_handler(project_id: int) -> CommonResponse:
    snapshot = await get_blackboard_snapshot(project_id)
    return CommonResponse(data=snapshot)


async def create_blackboard_node_handler(
    project_id: int,
    request: BlackboardCreateNodeRequest,
) -> CommonResponse:
    node, error = await create_blackboard_node(project_id, request)
    if error:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=error)
    return CommonResponse(data=node, message="blackboard node created")


async def update_blackboard_node_handler(
    project_id: int,
    node_id: int,
    request: BlackboardUpdateNodeRequest,
) -> CommonResponse:
    node, error = await update_blackboard_node(project_id, node_id, request)
    if error:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=error)
    return CommonResponse(data=node, message="blackboard node updated")


async def delete_blackboard_node_handler(project_id: int, node_id: int) -> CommonResponse:
    error = await delete_blackboard_node(project_id, node_id)
    if error:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=error)
    return CommonResponse(message="blackboard node deleted")
