from dataclasses import dataclass

from schema.system_user.users import SystemUserRole


MAIN_AGENT_INSTANCE_PREFIX = "main:"
SUBAGENT_INSTANCE_PREFIX = "subagent:"


@dataclass(frozen=True)
class AgentUserContext:
    id: int
    username: str
    email: str
    role: SystemUserRole


@dataclass
class AgentRuntimeContext:
    session_id: str
    user: AgentUserContext
    agent_code: str = ""
    agent_instance_id: str = ""
    nested_for_agent_code: str = ""
    nested_call_id: str = ""
    knowledge_generation: int = 0
    sandbox_container_id: int | None = None
    sandbox_container_generation: int = 0
    sandbox_skill_metadata: tuple[str, ...] = ()
    work_project_id: int | None = None


def main_agent_instance_id(session_id: str, user_id: int, agent_code: str) -> str:
    return f"{MAIN_AGENT_INSTANCE_PREFIX}{session_id}:{user_id}:{agent_code}"


def subagent_instance_id(run_id: str) -> str:
    return f"{SUBAGENT_INSTANCE_PREFIX}{run_id}"
