from datetime import datetime

from agents import RunContextWrapper, function_tool
from sqlalchemy import Text, cast, func, literal, update
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, array
from sqlmodel import select

from core.agent.constants import DEFAULT_AGENT_CODE
from core.runtime.context import AgentRuntimeContext
from core.tools.work_project_results import work_project_error, work_project_success
from database import get_async_session
from model.work_project.projects import WorkProject
from model.work_project.projects import WorkProjectSandboxContainer
from schema.work_project.projects import (
    WorkProjectAgentSummaryContentSchema,
    WorkProjectAgentSummarySchema,
    WorkProjectTaskSchema,
)
from service.work_project.progress import calculate_work_project_progress, derive_work_project_status


@function_tool
async def load_work_project_metadata(ctx: RunContextWrapper[AgentRuntimeContext]) -> str:
    """Load metadata for the WorkProject bound to the current session.

    Args:
        None.

    Returns:
        JSON status with project id, name, description, sandbox container ids, status, and type.
    """
    project = await _current_project(ctx.context)
    if project is None:
        return work_project_error("No WorkProject is bound to this session.")
    return work_project_success(await _metadata_payload(project))


@function_tool
async def load_work_project_tasks(ctx: RunContextWrapper[AgentRuntimeContext]) -> str:
    """Load the shared task list for the WorkProject bound to the current session.

    Args:
        None.

    Returns:
        JSON status with project_id, code-calculated overall progress, and shared task records.
    """
    project = await _current_project(ctx.context)
    if project is None:
        return work_project_error("No WorkProject is bound to this session.")
    return work_project_success(_tasks_payload(project))


@function_tool
async def load_work_project_agent_summaries(ctx: RunContextWrapper[AgentRuntimeContext]) -> str:
    """Load all agent summary slots for the WorkProject bound to the current session.

    Args:
        None.

    Returns:
        JSON status with project_id and structured summaries written by participating agents.
    """
    project = await _current_project(ctx.context)
    if project is None:
        return work_project_error("No WorkProject is bound to this session.")
    return work_project_success(_agent_summaries_payload(project))


@function_tool
async def update_work_project_agent_summary(
    ctx: RunContextWrapper[AgentRuntimeContext],
    summary: WorkProjectAgentSummaryContentSchema,
) -> str:
    """Replace this agent's live structured task summary for the current WorkProject.

    Each agent can only write its own summary slot, keyed by agent_code.
    Call after meaningful discoveries, useful negative results, blockers,
    decisions, handoffs, or progress changes, before the next command, delegated task, handoff, or user reply when practical.
    Keep the summary current throughout the task.
    Use task_id/task_title and progress (0-100, at most two decimals) to report this agent's current subtask progress.

    Args:
        summary: WorkProjectAgentSummaryContentSchema full replacement for this agent's current summary.
            Include task_id/task_title,
            progress, status, findings, decisions, blockers, next_steps, and notes as applicable.
            When task_id or exact task_title matches a shared task, that task's progress is synchronized.
            Overall project progress is recalculated by code and is not an input.

    Returns:
        JSON status with project_id and all current structured agent summaries.
    """
    agent_code = ctx.context.agent_code.strip()
    if not agent_code:
        return work_project_error("Agent code is required.")
    project_id = ctx.context.work_project_id
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    now = datetime.now()
    payload = {
        "agent_code": agent_code,
        "summary": summary.model_dump(mode="json"),
        "updated_at": now.isoformat(),
    }
    async with get_async_session() as session:
        result = await session.execute(
            update(WorkProject)
            .where(WorkProject.id == project_id)
            .values(
                agent_summaries=func.jsonb_set(
                    func.coalesce(WorkProject.agent_summaries, literal({}, type_=JSONB)),
                    cast(array([agent_code]), ARRAY(Text)),
                    literal(payload, type_=JSONB),
                    True,
                ),
                updated_at=now,
            )
            .returning(WorkProject.id)
        )
        updated_project_id = result.scalar_one_or_none()
        if updated_project_id is None:
            await session.rollback()
            return work_project_error("WorkProject not found.")
        project = (await session.exec(
            select(WorkProject)
            .where(WorkProject.id == project_id)
            .with_for_update()
        )).first()
        if project is None:
            await session.rollback()
            return work_project_error("WorkProject not found.")
        _sync_summary_progress_to_task(project, summary)
        session.add(project)
        await session.commit()
        await session.refresh(project)

    return work_project_success(_agent_summaries_payload(project))


@function_tool
async def update_work_project_tasks(
    ctx: RunContextWrapper[AgentRuntimeContext],
    tasks: list[WorkProjectTaskSchema],
) -> str:
    """Update the shared WorkProject task list.

    Only the chief security officer agent (`cso`) can update the shared project task list.
    Call when global task state changes, including after your own progress or subagent results,
    before reporting or delegating more work when practical.
    Each task status must be one of: todo, in_progress, blocked, done.
    Each task progress value must be 0-100 with at most two decimal places.
    Do not provide or estimate overall project progress; it is recalculated by code from task progress.

    Args:
        tasks: list[WorkProjectTaskSchema] complete desired task list after applying your changes.
            Preserve existing tasks that still matter,
            update status/progress/summary, and add or remove tasks only when the project plan changes.

    Returns:
        JSON status with project_id, recalculated overall progress, and the saved shared task list.
    """
    # The default agent code is the chief security officer (cso), the sole owner of the shared task list.
    if ctx.context.agent_code != DEFAULT_AGENT_CODE:
        return work_project_error("Only the cso agent can update the shared WorkProject task list.")
    project_id = ctx.context.work_project_id
    if project_id is None:
        return work_project_error("No WorkProject is bound to this session.")

    async with get_async_session() as session:
        project = await session.get(WorkProject, project_id)
        if project is None:
            return work_project_error("WorkProject not found.")
        project.tasks = [task.model_dump(mode="json") for task in tasks]
        _recalculate_project_progress(project)
        project.updated_at = datetime.now()
        session.add(project)
        await session.commit()
        await session.refresh(project)

    return work_project_success(_tasks_payload(project))


async def _current_project(context: AgentRuntimeContext) -> WorkProject | None:
    if context.work_project_id is None:
        return None
    async with get_async_session() as session:
        return await session.get(WorkProject, context.work_project_id)


async def _metadata_payload(project: WorkProject) -> dict:
    async with get_async_session() as session:
        container_ids = list((await session.exec(
            select(WorkProjectSandboxContainer.sandbox_container_id)
            .where(WorkProjectSandboxContainer.project_id == project.id)
            .order_by(WorkProjectSandboxContainer.position)
        )).all())
    return {
        "project_id": project.id,
        "name": project.name,
        "description": project.description,
        "sandbox_container_ids": container_ids,
        "status": project.status,
        "type": project.type,
    }


def _tasks_payload(project: WorkProject) -> dict:
    return {
        "project_id": project.id,
        "progress": project.progress,
        "tasks": [
            WorkProjectTaskSchema.model_validate(task).model_dump(mode="json")
            for task in project.tasks
        ],
    }


def _agent_summaries_payload(project: WorkProject) -> dict:
    summaries = [
        WorkProjectAgentSummarySchema.model_validate(summary).model_dump(mode="json")
        for summary in (project.agent_summaries or {}).values()
        if isinstance(summary, dict)
    ]
    return {
        "project_id": project.id,
        "agent_summaries": summaries,
    }


def _sync_summary_progress_to_task(
    project: WorkProject,
    summary: WorkProjectAgentSummaryContentSchema,
) -> None:
    task_id = summary.task_id.strip()
    task_title = summary.task_title.strip()
    if not task_id and not task_title:
        return

    tasks: list[dict] = []
    changed = False
    for raw_task in project.tasks:
        task = WorkProjectTaskSchema.model_validate(raw_task)
        if task.id == task_id or (not task_id and task.title == task_title):
            task.progress = summary.progress
            changed = True
        tasks.append(task.model_dump(mode="json"))

    if not changed:
        return
    project.tasks = tasks
    _recalculate_project_progress(project)


def _recalculate_project_progress(project: WorkProject) -> None:
    project.progress = calculate_work_project_progress(project.tasks)
    project.status = derive_work_project_status(project.tasks, project.status)
