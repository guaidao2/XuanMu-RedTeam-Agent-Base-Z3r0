"""Agent declarations and session-bound SDK Agent construction."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agents import (
    Agent,
    FunctionToolResult,
    Model,
    ModelSettings,
    RunContextWrapper,
    Tool,
    ToolsToFinalOutputResult,
)

from config import AgentConfig, WORKSPACE, get_config
from core.agent.instructions import build_instructions
from core.agent.models import build_openai_model
from core.agent.specs import AGENT_SPECS, AgentSpec, ToolMount
from core.delegation.subagents import build_subagent_tools
from core.runtime.context import AgentRuntimeContext
from core.tools.knowledge import find_knowledge, load_knowledge
from core.tools.sandbox import (
    execute_async_command,
    execute_sync_command,
    load_skill,
)
from schema.sandbox.async_jobs import SandboxAsyncJobStatus


async def _end_turn_after_async_dispatch(
    _ctx: RunContextWrapper[AgentRuntimeContext],
    results: list[FunctionToolResult],
) -> ToolsToFinalOutputResult:
    """End the turn the moment an async command is successfully dispatched.

    Dispatching background work is turn-terminal: the agent stops here and is
    woken by the completion notification, so it can never poll for the result.
    A failed dispatch is not terminal, letting the agent react in the same turn.
    """
    for result in results:
        if getattr(result.tool, "name", None) != execute_async_command.name:
            continue
        try:
            status = json.loads(result.output).get("status")
        except (TypeError, ValueError):
            status = None
        if status == SandboxAsyncJobStatus.RUNNING.value:
            return ToolsToFinalOutputResult(is_final_output=True, final_output=result.output)
    return ToolsToFinalOutputResult(is_final_output=False)


@dataclass(frozen=True, slots=True)
class AgentToolSnapshot:
    knowledge_generation: int = 0
    sandbox_container_id: int | None = None
    sandbox_container_generation: int = 0
    sandbox_skill_metadata: tuple[str, ...] = ()
    work_project_id: int | None = None

    @classmethod
    def from_context(cls, context: AgentRuntimeContext) -> "AgentToolSnapshot":
        return cls(
            knowledge_generation=context.knowledge_generation,
            sandbox_container_id=context.sandbox_container_id,
            sandbox_container_generation=context.sandbox_container_generation,
            sandbox_skill_metadata=context.sandbox_skill_metadata,
            work_project_id=context.work_project_id,
        )


class AgentRegistry:
    def __init__(self, specs: tuple[AgentSpec, ...] = AGENT_SPECS) -> None:
        self._specs: dict[str, AgentSpec] = {spec.code: spec for spec in specs}
        self._codes_cache: tuple[str, ...] | None = None
        self._code_to_name_cache: dict[str, str] | None = None
        # Reject self-mounts and circular subagent chains at boot.
        self._validate_subagent_graph()

    def codes(self) -> list[str]:
        if self._codes_cache is None:
            configured = set(get_config().agents.keys())
            self._codes_cache = tuple(code for code in self._specs if code in configured)
        return list(self._codes_cache)

    def code_to_name(self) -> dict[str, str]:
        if self._code_to_name_cache is None:
            cfg = get_config()
            self._code_to_name_cache = {code: cfg.agents[code].name for code in self.codes()}
        return self._code_to_name_cache

    def has(self, agent_code: str) -> bool:
        return agent_code in self.codes()

    def bind(self, tool_snapshot: AgentToolSnapshot) -> SessionAgentGraph:
        return SessionAgentGraph(self, tool_snapshot)

    def _spec(self, agent_code: str) -> AgentSpec:
        spec = self._specs.get(agent_code)
        if spec is None:
            raise ValueError(f"agent spec not declared for code: {agent_code}")
        return spec

    def _validate_subagent_graph(self) -> None:
        for code in self._specs:
            self._check_subagent_chain(code, [code])

    def _check_subagent_chain(self, code: str, path: list[str]) -> None:
        spec = self._specs.get(code)
        if spec is None:
            return
        for mount in spec.subagents:
            if mount.code == code:
                raise ValueError(f"agent {code} cannot mount itself as a subagent")
            if mount.code in path:
                chain = " -> ".join([*path, mount.code])
                raise ValueError(f"circular subagent mount detected: {chain}")
            self._check_subagent_chain(mount.code, [*path, mount.code])

    def _build(self, spec: AgentSpec, cfg: AgentConfig, graph: SessionAgentGraph) -> Agent:
        agent_path = WORKSPACE / "agents" / spec.code
        soul = (agent_path / "SOUL.md").read_text(encoding="utf-8").strip()
        rules = (agent_path / "AGENTS.md").read_text(encoding="utf-8").strip()
        instructions = build_instructions(
            soul,
            rules,
            spec.code,
            graph.tool_snapshot.sandbox_skill_metadata,
            has_sandbox_container=graph.tool_snapshot.sandbox_container_id is not None,
            include_sandbox_commands=_has_tool(spec, execute_sync_command) or _has_tool(spec, execute_async_command),
            include_sandbox_skills=_has_tool(spec, load_skill),
            include_agent_knowledges=_has_any_tool(spec, (find_knowledge, load_knowledge)),
            include_work_project_tools=(
                graph.tool_snapshot.work_project_id is not None
                and _has_work_project_tool(spec)
            ),
            include_delegation_tools=bool(spec.subagents),
        )

        tools: list[Tool] = [
            mount.tool for mount in spec.tools
            if _tool_mount_available(mount, graph.tool_snapshot)
        ]
        if spec.subagents:
            tools.extend(_build_subagent_tools(spec, self))

        return Agent(
            name=cfg.name,
            model=build_openai_model(cfg),
            model_settings=ModelSettings(parallel_tool_calls=False),
            instructions=instructions,
            tools=tools,
            tool_use_behavior=_end_turn_after_async_dispatch,
        )


class SessionAgentGraph:
    """Single-owner container for an Agent and its httpx client.

    Each driver (main session or one sub-agent) binds its own graph, so
    disposing one graph never tears down a sibling's in-flight HTTP stream.
    """

    def __init__(self, registry: AgentRegistry, tool_snapshot: AgentToolSnapshot) -> None:
        self._registry = registry
        self.tool_snapshot = tool_snapshot
        self._agents: dict[str, Agent] = {}
        self._models: list[Model] = []

    def code_to_name(self) -> dict[str, str]:
        return self._registry.code_to_name()

    def get(self, agent_code: str) -> Agent:
        cached = self._agents.get(agent_code)
        if cached is not None:
            return cached

        spec = self._registry._spec(agent_code)
        cfg = get_config().agents.get(agent_code)
        if cfg is None:
            raise ValueError(f"agent config missing for code: {agent_code}")

        agent = self._registry._build(spec, cfg, self)
        self._agents[agent_code] = agent
        self._models.append(agent.model)
        return agent

    async def close(self) -> None:
        for model in self._models:
            await model.close()
        self._agents.clear()
        self._models.clear()


def _has_tool(spec: AgentSpec, tool: Tool) -> bool:
    return any(mount.tool is tool for mount in spec.tools)


def _has_any_tool(spec: AgentSpec, tools: tuple[Tool, ...]) -> bool:
    return any(_has_tool(spec, tool) for tool in tools)


def _has_work_project_tool(spec: AgentSpec) -> bool:
    return any(mount.requires_work_project for mount in spec.tools)


def _tool_mount_available(mount: ToolMount, snapshot: AgentToolSnapshot) -> bool:
    if mount.requires_sandbox_container and snapshot.sandbox_container_id is None:
        return False
    if mount.requires_work_project and snapshot.work_project_id is None:
        return False
    return True


def _build_subagent_tools(spec: AgentSpec, registry: AgentRegistry) -> list[Tool]:
    return build_subagent_tools(
        spec.code,
        (mount.code for mount in spec.subagents),
        registry=registry,
    )
