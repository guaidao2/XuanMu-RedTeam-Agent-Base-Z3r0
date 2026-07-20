import json
from datetime import datetime

from sqlalchemy import Text, cast, delete as sa_delete
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.blackboard.nodes import BlackboardNode
from schema.blackboard.nodes import (
    BlackboardCreateNodeRequest,
    BlackboardNodeSchema,
    BlackboardSnapshotSchema,
    BlackboardUpdateNodeRequest,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Snapshot — full blackboard graph for a project
# ---------------------------------------------------------------------------
async def get_blackboard_snapshot(project_id: int) -> BlackboardSnapshotSchema:
    """Return every node for the project, newest first."""
    async with get_async_session() as session:
        nodes = (
            await session.exec(
                select(BlackboardNode)
                .where(BlackboardNode.project_id == project_id)
                .order_by(BlackboardNode.id.asc())
            )
        ).all()
    return BlackboardSnapshotSchema(
        project_id=project_id,
        nodes=[BlackboardNodeSchema.model_validate(n) for n in nodes],
        total_count=len(nodes),
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
async def create_blackboard_node(
    project_id: int,
    request: BlackboardCreateNodeRequest,
) -> tuple[BlackboardNodeSchema | None, str]:
    now = datetime.now()
    node = BlackboardNode(
        project_id=project_id,
        node_type=request.node_type.value,
        status="proposed",
        description=request.description,
        parent_ids=json.dumps(request.parent_ids, ensure_ascii=False),
        creator_agent_code=request.creator_agent_code.strip(),
        session_id=request.session_id.strip(),
        confidence=request.confidence,
        extra=request.extra,
        created_at=now,
        updated_at=now,
    )
    async with get_async_session() as session:
        session.add(node)
        await session.commit()
        await session.refresh(node)
    return BlackboardNodeSchema.model_validate(node), ""


async def update_blackboard_node(
    project_id: int,
    node_id: int,
    request: BlackboardUpdateNodeRequest,
) -> tuple[BlackboardNodeSchema | None, str]:
    async with get_async_session() as session:
        node = await session.get(BlackboardNode, node_id)
        if node is None or node.project_id != project_id:
            return None, "blackboard node not found"

        dirty = False
        if request.status is not None:
            node.status = request.status.value
            dirty = True
        if request.description is not None:
            node.description = request.description.strip()
            dirty = True
        if request.parent_ids is not None:
            node.parent_ids = json.dumps(request.parent_ids, ensure_ascii=False)
            dirty = True
        if request.confidence is not None:
            node.confidence = request.confidence
            dirty = True
        if request.extra is not None:
            node.extra = request.extra
            dirty = True

        if dirty:
            node.updated_at = datetime.now()
            session.add(node)
            await session.commit()
            await session.refresh(node)
        return BlackboardNodeSchema.model_validate(node), ""


async def delete_blackboard_node(project_id: int, node_id: int) -> str:
    async with get_async_session() as session:
        node = await session.get(BlackboardNode, node_id)
        if node is None or node.project_id != project_id:
            return "blackboard node not found"
        await session.delete(node)
        await session.commit()
    return ""


async def delete_blackboard_for_project(project_id: int) -> None:
    """Remove all blackboard nodes for a project (cascade cleanup)."""
    async with get_async_session() as session:
        await session.exec(
            sa_delete(BlackboardNode).where(BlackboardNode.project_id == project_id)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Graph traversal helpers
# ---------------------------------------------------------------------------
async def get_path_to_node(
    project_id: int,
    node_id: int,
) -> list[BlackboardNodeSchema]:
    """Trace the parent chain from a given node back to the root(s).

    Returns an ordered list from oldest ancestor to the requested node.
    """
    async with get_async_session() as session:
        node = await session.get(BlackboardNode, node_id)
        if node is None or node.project_id != project_id:
            return []

        all_nodes = {
            n.id: n
            for n in (
                await session.exec(
                    select(BlackboardNode).where(BlackboardNode.project_id == project_id)
                )
            ).all()
        }

    # walk parent chain
    path: list[BlackboardNode] = []
    seen: set[int] = set()
    current = node
    while current is not None and current.id not in seen:
        path.append(current)
        seen.add(current.id)
        pids = json.loads(current.parent_ids or "[]")
        if not pids:
            break
        # take the first parent; for full DAG traversal, this returns one linear path
        current = all_nodes.get(pids[0])
        if current is None:
            break

    path.reverse()
    return [BlackboardNodeSchema.model_validate(n) for n in path]
