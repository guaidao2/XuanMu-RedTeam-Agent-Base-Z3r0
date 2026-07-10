from datetime import datetime
from uuid import uuid4

from sqlmodel import select, update

from database import get_async_session
from logger import get_logger
from model.agent.subordinates import AgentSubordinateTask
from schema.agent.notifications import AgentNotificationKind
from schema.agent.subordinates import (
    AgentSubordinateStatus,
    AgentSubordinateTaskSnapshot,
)
from schema.system_user.users import SystemUserRole
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)


TERMINAL_SUBAGENT_STATUSES = {
    AgentSubordinateStatus.COMPLETED,
    AgentSubordinateStatus.FAILED,
    AgentSubordinateStatus.CANCELED,
}

# Statuses whose result the parent must integrate (wakes the parent driver).
# CANCELED is resolved silently so an aborted child never wakes the parent.
_PARENT_WAKING_STATUSES = {
    AgentSubordinateStatus.COMPLETED,
    AgentSubordinateStatus.FAILED,
}


async def create_subagent_task(
    *,
    session_id: str,
    parent_agent_code: str,
    parent_agent_instance_id: str,
    agent_code: str,
    agent_name: str,
    brief: str,
    nested_call_id: str,
    owner_id: int,
    sandbox_container_id: int | None = None,
    sandbox_container_generation: int = 0,
    sandbox_skill_metadata: tuple[str, ...] = (),
) -> AgentSubordinateTaskSnapshot:
    now = datetime.now()
    run_id = str(uuid4())
    task = AgentSubordinateTask(
        run_id=run_id,
        session_id=session_id,
        parent_agent_code=parent_agent_code,
        parent_agent_instance_id=parent_agent_instance_id,
        agent_code=agent_code,
        agent_name=agent_name,
        status=AgentSubordinateStatus.RUNNING.value,
        brief=brief,
        nested_call_id=nested_call_id,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    async with get_async_session() as session:
        session.add(task)
        # Register the parent wake-up obligation in the same transaction so the
        # parent driver can never see the child as neither running nor pending.
        if parent_agent_code:
            agent_notifications.add_obligation_in_session(
                session,
                kind=AgentNotificationKind.SUBAGENT_FINISHED,
                session_id=session_id,
                target_agent_code=parent_agent_code,
                target_agent_instance_id=parent_agent_instance_id,
                run_id=run_id,
                payload={
                    "run_id": run_id,
                    "agent_code": agent_code,
                    "agent_name": agent_name,
                },
                sandbox_container_id=sandbox_container_id,
                sandbox_container_generation=sandbox_container_generation,
                sandbox_skill_metadata=sandbox_skill_metadata,
            )
        await session.commit()
        await session.refresh(task)
    logger.debug("subagent task created: %s", task.run_id)
    return snapshot_from_task(task)


async def get_subagent_task(
    *,
    run_id: str,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> AgentSubordinateTaskSnapshot | None:
    async with get_async_session() as session:
        task = await session.get(AgentSubordinateTask, run_id)
        if task is None or not _can_access_task(task, session_id, user_id, user_role):
            return None
        return snapshot_from_task(task)


async def list_subagent_tasks(
    *,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
    limit: int = 20,
) -> list[AgentSubordinateTaskSnapshot]:
    async with get_async_session() as session:
        statement = (
            select(AgentSubordinateTask)
            .where(AgentSubordinateTask.session_id == session_id)
            .order_by(AgentSubordinateTask.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        rows = (await session.exec(statement)).all()
        return [snapshot_from_task(task) for task in rows if _can_access_task(task, session_id, user_id, user_role)]


async def get_subagent_task_internal(run_id: str) -> AgentSubordinateTaskSnapshot | None:
    async with get_async_session() as session:
        task = await session.get(AgentSubordinateTask, run_id)
        return snapshot_from_task(task) if task is not None else None


async def update_subagent_progress(run_id: str, progress: str) -> AgentSubordinateTaskSnapshot | None:
    async with get_async_session() as session:
        task = await session.get(AgentSubordinateTask, run_id)
        if task is None or _coerce_subagent_status(task.status) in TERMINAL_SUBAGENT_STATUSES:
            return None
        task.progress = progress
        task.updated_at = datetime.now()
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return snapshot_from_task(task)


async def complete_subagent_task(run_id: str, result: str) -> AgentSubordinateTaskSnapshot | None:
    return await _finish_subagent_task(run_id, AgentSubordinateStatus.COMPLETED, result=result)


async def fail_subagent_task(run_id: str, error: str) -> AgentSubordinateTaskSnapshot | None:
    return await _finish_subagent_task(run_id, AgentSubordinateStatus.FAILED, error=error)


async def cancel_subagent_task_record(run_id: str, error: str = "") -> AgentSubordinateTaskSnapshot | None:
    return await _finish_subagent_task(run_id, AgentSubordinateStatus.CANCELED, error=error)


async def cancel_running_subagent_tasks_for_session(
    session_id: str,
    error: str = "",
) -> list[AgentSubordinateTaskSnapshot]:
    return await _cancel_running_subagent_tasks(error=error, session_id=session_id)


async def cancel_running_child_subagent_tasks(
    *,
    session_id: str,
    parent_agent_instance_id: str,
    error: str = "",
) -> list[AgentSubordinateTaskSnapshot]:
    return await _cancel_running_subagent_tasks(
        error=error,
        session_id=session_id,
        parent_agent_instance_id=parent_agent_instance_id,
    )


async def cancel_running_subagent_tasks(error: str = "") -> list[AgentSubordinateTaskSnapshot]:
    return await _cancel_running_subagent_tasks(error=error)


async def _cancel_running_subagent_tasks(
    *,
    error: str = "",
    session_id: str | None = None,
    parent_agent_instance_id: str | None = None,
) -> list[AgentSubordinateTaskSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        statement = select(AgentSubordinateTask).where(
            AgentSubordinateTask.status == AgentSubordinateStatus.RUNNING.value,
        )
        if session_id is not None:
            statement = statement.where(AgentSubordinateTask.session_id == session_id)
        if parent_agent_instance_id is not None:
            statement = statement.where(AgentSubordinateTask.parent_agent_instance_id == parent_agent_instance_id)
        rows = (await session.exec(statement)).all()
        for task in rows:
            task.status = AgentSubordinateStatus.CANCELED.value
            task.error = error
            task.progress = ""
            task.updated_at = now
            task.finished_at = now
            session.add(task)
            await agent_notifications.resolve_obligation_in_session(
                session,
                kind=AgentNotificationKind.SUBAGENT_FINISHED,
                run_id=task.run_id,
                ready=False,
                error=error,
            )
        if not rows:
            return []
        await session.commit()
        for task in rows:
            await session.refresh(task)
        return [snapshot_from_task(task) for task in rows]


async def mark_stale_running_subagent_tasks_failed() -> list[AgentSubordinateTaskSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        rows = (await session.exec(
            select(AgentSubordinateTask).where(AgentSubordinateTask.status == AgentSubordinateStatus.RUNNING.value)
        )).all()
        restart_error = "Subagent task was interrupted by backend restart."
        for task in rows:
            task.status = AgentSubordinateStatus.FAILED.value
            task.error = restart_error
            task.updated_at = now
            task.finished_at = now
            session.add(task)
            # Surface the restart failure to the recovered parent so it can
            # finish its turn instead of waiting forever on a dead child.
            await agent_notifications.resolve_obligation_in_session(
                session,
                kind=AgentNotificationKind.SUBAGENT_FINISHED,
                run_id=task.run_id,
                ready=True,
                payload=_subagent_obligation_payload(task),
                error=restart_error,
            )
        if rows:
            await session.commit()
            for task in rows:
                await session.refresh(task)
    if rows:
        logger.info("stale subagent tasks marked failed: %d", len(rows))
    return [snapshot_from_task(task) for task in rows]


async def _finish_subagent_task(
    run_id: str,
    status: AgentSubordinateStatus,
    *,
    result: str = "",
    error: str = "",
) -> AgentSubordinateTaskSnapshot | None:
    now = datetime.now()
    async with get_async_session() as session:
        task = await session.get(AgentSubordinateTask, run_id)
        if task is None:
            return None
        if _coerce_subagent_status(task.status) in TERMINAL_SUBAGENT_STATUSES:
            return snapshot_from_task(task)
        updated = await session.exec(
            update(AgentSubordinateTask)
            .where(
                AgentSubordinateTask.run_id == run_id,
                AgentSubordinateTask.status == AgentSubordinateStatus.RUNNING.value,
            )
            .values(
                status=status.value,
                result=result,
                error=error,
                progress="",
                updated_at=now,
                finished_at=now,
            )
        )
        if updated.rowcount != 1:
            await session.rollback()
            current = await session.get(AgentSubordinateTask, run_id)
            return snapshot_from_task(current) if current is not None else None
        # Flip the parent obligation in the same transaction: task-terminal and
        # parent-wakeup commit atomically, so there is no check-then-act window.
        refreshed = await session.get(AgentSubordinateTask, run_id)
        await agent_notifications.resolve_obligation_in_session(
            session,
            kind=AgentNotificationKind.SUBAGENT_FINISHED,
            run_id=run_id,
            ready=status in _PARENT_WAKING_STATUSES,
            payload=_subagent_obligation_payload(refreshed) if refreshed is not None else None,
            error=error,
        )
        await session.commit()
        current = await session.get(AgentSubordinateTask, run_id)
        return snapshot_from_task(current) if current is not None else None


def _subagent_obligation_payload(task: AgentSubordinateTask) -> dict[str, object]:
    # Metadata only: the body lives in the DB and is paged through read_subagent_task,
    # so the notification stays small and the parent agent has a single source of truth.
    return {
        "run_id": task.run_id,
        "agent_code": task.agent_code,
        "agent_name": task.agent_name,
        "status": _coerce_subagent_status(task.status).value,
    }


def snapshot_from_task(task: AgentSubordinateTask) -> AgentSubordinateTaskSnapshot:
    return AgentSubordinateTaskSnapshot(
        run_id=task.run_id,
        session_id=task.session_id,
        parent_agent_code=task.parent_agent_code,
        parent_agent_instance_id=task.parent_agent_instance_id,
        agent_code=task.agent_code,
        agent_name=task.agent_name,
        status=_coerce_subagent_status(task.status),
        brief=task.brief,
        result=task.result,
        error=task.error,
        progress=task.progress,
        nested_call_id=task.nested_call_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _coerce_subagent_status(status: AgentSubordinateStatus | str) -> AgentSubordinateStatus:
    if isinstance(status, AgentSubordinateStatus):
        return status
    return AgentSubordinateStatus(status.lower())


def _can_access_task(
    task: AgentSubordinateTask,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    if task.session_id != session_id:
        return False
    return user_role == SystemUserRole.ADMIN or task.owner_id == user_id
