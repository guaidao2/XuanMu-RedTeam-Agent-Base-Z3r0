from fastapi import APIRouter, Depends

from handler.agent.agents import list_agents_handler
from middleware.auth import require_user
from router.common.responses import COMMON_ERROR_RESPONSES
from schema.agent.sessions import ListAgentsResponse
from schema.common.responses import CommonResponse


router = APIRouter(prefix="/agents", tags=["agents"])

USER_ONLY = [Depends(require_user)]


router.add_api_route(
    "",
    list_agents_handler,
    methods=["GET"],
    dependencies=USER_ONLY,
    response_model=CommonResponse[ListAgentsResponse],
    responses=COMMON_ERROR_RESPONSES,
)
