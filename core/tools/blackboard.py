"""Blackboard tools — shared reasoning graph for multi-agent coordination.

These tools give every agent read/write access to the project's blackboard,
enabling Cairn-style Stigmergy coordination through a shared Fact-Intent-Hint graph.
"""

from agents import RunContextWrapper, function_tool

from core.runtime.context import AgentRuntimeContext
from core.tools.work_project_results import work_project_error, work_project_success
from schema.blackboard.nodes import (
    BlackboardCreateNodeRequest,
    BlackboardNodeType,
    BlackboardNodeStatus,
    BlackboardUpdateNodeRequest,
)
from service.blackboard.nodes import (
    create_blackboard_node,
    get_blackboard_snapshot,
    get_path_to_node,
    update_blackboard_node,
)

_MAX_DESC_LENGTH = 2000


def _project_id(ctx: RunContextWrapper[AgentRuntimeContext]) -> int | None:
    return ctx.context.work_project_id


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@function_tool
async def create_fact(
    ctx: RunContextWrapper[AgentRuntimeContext],
    description: str,
    parent_intent_ids: list[int] | None = None,
    confidence: float = 1.0,
    extra_json: str = "{}",
) -> str:
    """Record a confirmed finding on the blackboard as a Fact.

    Facts are objective, confirmed observations discovered through exploration.
    A Fact should always cite the Intent(s) that led to it via parent_intent_ids.
    Once written, other agents can see this Fact and use it to derive new Intents.

    Args:
        description: What was confirmed. Be specific and evidence-backed. Max 2000 chars.
        parent_intent_ids: Optional list of intent node IDs that led to this discovery.
        confidence: How certain you are (0.0 = guess, 1.0 = certain). Default 1.0.
        extra_json: Optional JSON string with additional context (tool output refs, etc).

    Returns:
        JSON with the created fact node id and status.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    description = description.strip()[: _MAX_DESC_LENGTH]
    if not description:
        return work_project_error("description must not be empty")

    request = BlackboardCreateNodeRequest(
        node_type=BlackboardNodeType.FACT,
        description=description,
        parent_ids=parent_intent_ids or [],
        creator_agent_code=ctx.context.agent_code or "",
        session_id=ctx.context.session_id or "",
        confidence=confidence,
        extra=extra_json,
    )
    node, error = await create_blackboard_node(project_id, request)
    if error:
        return work_project_error(error)
    return work_project_success({"node_id": node.id, "status": node.status, "description": node.description})


@function_tool
async def create_intent(
    ctx: RunContextWrapper[AgentRuntimeContext],
    description: str,
    parent_fact_ids: list[int] | None = None,
    extra_json: str = "{}",
) -> str:
    """Declare an exploration direction on the blackboard as an Intent.

    Intents are declared directions of exploration — what you plan to do and why.
    Always cite the Fact(s) that justify this intent via parent_fact_ids.
    After completing the exploration, conclude the intent by creating a Fact
    that references this intent's ID.

    Args:
        description: What you intend to explore and why. Max 2000 chars.
        parent_fact_ids: Optional list of fact node IDs that motivate this intent.
        extra_json: Optional JSON with additional planning context.

    Returns:
        JSON with the created intent node id and status.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    description = description.strip()[: _MAX_DESC_LENGTH]
    if not description:
        return work_project_error("description must not be empty")

    request = BlackboardCreateNodeRequest(
        node_type=BlackboardNodeType.INTENT,
        description=description,
        parent_ids=parent_fact_ids or [],
        creator_agent_code=ctx.context.agent_code or "",
        session_id=ctx.context.session_id or "",
        extra=extra_json,
    )
    node, error = await create_blackboard_node(project_id, request)
    if error:
        return work_project_error(error)
    return work_project_success({"node_id": node.id, "status": node.status, "description": node.description})


@function_tool
async def create_hint(
    ctx: RunContextWrapper[AgentRuntimeContext],
    content: str,
    parent_node_ids: list[int] | None = None,
) -> str:
    """Write a hint to the blackboard.

    Hints are human or agent judgments injected to guide exploration.
    Unlike Facts (confirmed) and Intents (planned), Hints are advisory.
    They can steer direction, flag dead ends, or suggest approaches.

    Args:
        content: The hint text. Max 2000 chars.
        parent_node_ids: Optional list of node IDs this hint responds to.

    Returns:
        JSON with the created hint node id.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    content = content.strip()[: _MAX_DESC_LENGTH]
    if not content:
        return work_project_error("content must not be empty")

    request = BlackboardCreateNodeRequest(
        node_type=BlackboardNodeType.HINT,
        description=content,
        parent_ids=parent_node_ids or [],
        creator_agent_code=ctx.context.agent_code or "",
        session_id=ctx.context.session_id or "",
    )
    node, error = await create_blackboard_node(project_id, request)
    if error:
        return work_project_error(error)
    return work_project_success({"node_id": node.id, "description": node.description})


@function_tool
async def read_blackboard(
    ctx: RunContextWrapper[AgentRuntimeContext],
) -> str:
    """Read the full blackboard graph for the current WorkProject.

    Returns every Fact, Intent, and Hint node with their relationships.
    Use this to understand what other agents have discovered, what
    exploration directions are open, and what hints have been injected.

    Args:
        None.

    Returns:
        JSON with the full blackboard snapshot: nodes array, each with
        id, node_type, status, description, parent_ids, creator, confidence.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    snapshot = await get_blackboard_snapshot(project_id)
    return work_project_success({
        "project_id": snapshot.project_id,
        "total_nodes": snapshot.total_count,
        "nodes": [
            {
                "id": n.id,
                "node_type": n.node_type,
                "status": n.status,
                "description": n.description,
                "parent_ids": n.parent_ids,
                "creator": n.creator_agent_code,
                "confidence": n.confidence,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in snapshot.nodes
        ],
    })


@function_tool
async def update_node_status(
    ctx: RunContextWrapper[AgentRuntimeContext],
    node_id: int,
    new_status: str,
    confidence: float | None = None,
) -> str:
    """Update the status of a blackboard node.

    Lifecycle: proposed → in_progress → confirmed | rejected | superseded

    Use this when you start working on an intent (→ in_progress),
    confirm a fact (→ confirmed), hit a dead end (→ rejected),
    or find a better direction that supersedes an older node (→ superseded).

    Args:
        node_id: The ID of the node to update.
        new_status: One of: proposed, in_progress, confirmed, rejected, superseded.
        confidence: Optional new confidence value (0.0 to 1.0).

    Returns:
        JSON with the updated node id and new status.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    new_status = new_status.strip().lower()
    valid_statuses = {"proposed", "in_progress", "confirmed", "rejected", "superseded"}
    if new_status not in valid_statuses:
        return work_project_error(f"invalid status: {new_status}. Must be one of: {', '.join(sorted(valid_statuses))}")

    request = BlackboardUpdateNodeRequest(
        status=BlackboardNodeStatus(new_status),
        confidence=confidence,
    )
    node, error = await update_blackboard_node(project_id, node_id, request)
    if error:
        return work_project_error(error)
    return work_project_success({"node_id": node.id, "status": node.status})


@function_tool
async def trace_reasoning_path(
    ctx: RunContextWrapper[AgentRuntimeContext],
    node_id: int,
) -> str:
    """Trace the reasoning path from a node back to its roots.

    Given a node ID, walks the parent chain to show how the current
    understanding evolved — from initial facts through intents to
    the current node.

    Args:
        node_id: The node to trace from.

    Returns:
        JSON array of nodes from root ancestor to the requested node.
    """
    project_id = _project_id(ctx)
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    path = await get_path_to_node(project_id, node_id)
    if not path:
        return work_project_error("node not found or no path to root")

    return work_project_success({
        "path": [
            {
                "id": n.id,
                "node_type": n.node_type,
                "status": n.status,
                "description": n.description,
            }
            for n in path
        ],
    })
