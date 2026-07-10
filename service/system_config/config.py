import asyncio
from dataclasses import dataclass
from http import HTTPStatus

from fastapi import HTTPException

from config import (
    AgentConfig,
    AgentPoolConfig,
    AgentRuntimeConfig,
    GlobalConfig,
    get_config,
    read_config_file,
    write_config_file,
)
from core.delegation.subagents import start_subagent_runtime, stop_subagent_runtime
from core.runtime.session import AgentSessionPool, get_agent_pool, replace_agent_pool
from logger import get_logger
from schema.system_config.config import InstanceConfigSchema, UpdateInstanceConfigRequest


logger = get_logger(__name__)

_config_lock = asyncio.Lock()


@dataclass(frozen=True)
class InstanceConfigApplyResult:
    config: InstanceConfigSchema
    restarted: bool


async def get_instance_config() -> InstanceConfigApplyResult:
    async with _config_lock:
        file_cfg = read_config_file()
        return await _apply_instance_config_from_file(file_cfg)


async def update_instance_config(request: UpdateInstanceConfigRequest) -> InstanceConfigApplyResult:
    async with _config_lock:
        current = read_config_file()
        if set(request.agents) != set(current.agents):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST.value,
                detail="agent set cannot be changed",
            )

        agents = {}
        for code, agent in current.agents.items():
            patch = request.agents[code]
            agents[code] = agent.model_copy(update={
                "name": patch.name,
                "description": patch.description,
                "base_url": patch.base_url,
                "api_key": patch.api_key,
                "model": patch.model,
                "use_responses": patch.use_responses,
                "context_window": patch.context_window,
            })

        next_cfg = current.model_copy(update={
            "agents": agents,
            "agent_pool": request.agent_pool,
            "agent_runtime": request.agent_runtime,
        })
        write_config_file(next_cfg)
        return await _apply_instance_config_from_file(next_cfg)


async def _apply_instance_config_from_file(file_cfg: GlobalConfig) -> InstanceConfigApplyResult:
    previous = _snapshot_instance_config(get_config())
    runtime_changed = _apply_instance_config(file_cfg)
    if runtime_changed:
        try:
            await rebuild_agent_instances()
        except Exception:
            _restore_instance_config(previous)
            raise
        logger.info("instance config applied and agent instances rebuilt")
    return InstanceConfigApplyResult(
        config=_instance_config_from_global(get_config()),
        restarted=runtime_changed,
    )


def _apply_instance_config(file_cfg: GlobalConfig) -> bool:
    current = get_config()
    if not _instance_config_changed(current, file_cfg):
        return False

    current.agents = _copy_agents(file_cfg.agents)
    current.agent_pool = _copy_agent_pool(file_cfg.agent_pool)
    current.agent_runtime = _copy_agent_runtime(file_cfg.agent_runtime)
    return True


def _instance_config_changed(current: GlobalConfig, next_cfg: GlobalConfig) -> bool:
    return (
        current.agents != next_cfg.agents
        or current.agent_pool != next_cfg.agent_pool
        or current.agent_runtime != next_cfg.agent_runtime
    )


def _copy_agents(agents: dict[str, AgentConfig]) -> dict[str, AgentConfig]:
    return {code: agent.model_copy(deep=True) for code, agent in agents.items()}


def _copy_agent_pool(agent_pool: AgentPoolConfig) -> AgentPoolConfig:
    return agent_pool.model_copy(deep=True)


def _copy_agent_runtime(agent_runtime: AgentRuntimeConfig) -> AgentRuntimeConfig:
    return agent_runtime.model_copy(deep=True)


def _snapshot_instance_config(cfg: GlobalConfig) -> InstanceConfigSchema:
    return _instance_config_from_global(cfg).model_copy(deep=True)


def _restore_instance_config(snapshot: InstanceConfigSchema) -> None:
    current = get_config()
    current.agents = _copy_agents(snapshot.agents)
    current.agent_pool = _copy_agent_pool(snapshot.agent_pool)
    current.agent_runtime = _copy_agent_runtime(snapshot.agent_runtime)


async def rebuild_agent_instances() -> None:
    old_pool = get_agent_pool()
    new_pool = replace_agent_pool(AgentSessionPool())
    try:
        try:
            await stop_subagent_runtime()
        finally:
            await old_pool.stop()
        await start_subagent_runtime()
        await new_pool.start()
    except Exception:
        logger.exception("agent instance rebuild failed")
        await new_pool.stop()
        fallback_pool = replace_agent_pool(AgentSessionPool())
        await fallback_pool.start()
        raise


def _instance_config_from_global(cfg: GlobalConfig) -> InstanceConfigSchema:
    return InstanceConfigSchema(
        agents=cfg.agents,
        agent_pool=cfg.agent_pool,
        agent_runtime=cfg.agent_runtime,
    )
