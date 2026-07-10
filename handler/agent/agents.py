from config import get_config
from core.agent.constants import DEFAULT_AGENT_CODE
from core.runtime.session import get_agent_registry
from schema.agent.sessions import AgentInfoSchema, ListAgentsResponse
from schema.common.responses import CommonResponse


async def list_agents_handler() -> CommonResponse:
    cfg = get_config()
    items = [
        AgentInfoSchema(
            code=code,
            name=cfg.agents[code].name,
            description=cfg.agents[code].description,
        )
        for code in get_agent_registry().codes()
    ]
    return CommonResponse(data=ListAgentsResponse(
        items=items,
        default_code=DEFAULT_AGENT_CODE,
    ))
