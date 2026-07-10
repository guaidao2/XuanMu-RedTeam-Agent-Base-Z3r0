from __future__ import annotations

from datetime import datetime
from sqlmodel import select, update

from database import get_async_session
from logger import get_logger
from model.sandbox.async_jobs import SandboxAsyncJob
from schema.agent.notifications import AgentNotificationKind
from schema.sandbox.async_jobs import SandboxAsyncJobSnapshot, SandboxAsyncJobStatus
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)

TERMINAL_ASYNC_JOB_STATUSES = {
    SandboxAsyncJobStatus.COMPLETED,
    SandboxAsyncJobStatus.FAILED,
    SandboxAsyncJobStatus.CANCELED,
}

# Statuses whose result the owning agent must integrate (wakes its driver).
_OWNER_WAKING_STATUSES = {
    SandboxAsyncJobStatus.COMPLETED,
    SandboxAsyncJobStatus.FAILED,
}


async def create_async_job(
    *,
    run_id: str,
    session_id: str,
    agent_code: str,
    agent_instance_id: str,
    command: str,
    output_file: str,
    nested_for_agent_code: str,
    nested_call_id: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
    sandbox_skill_metadata: tuple[str, ...],
) -> SandboxAsyncJobSnapshot:
    now = datetime.now()
    job = SandboxAsyncJob(
        run_id=run_id,
        session_id=session_id,
        agent_code=agent_code,
        agent_instance_id=agent_instance_id,
        command=command,
        output_file=output_file,
        status=SandboxAsyncJobStatus.RUNNING.value,
        nested_for_agent_code=nested_for_agent_code,
        nested_call_id=nested_call_id,
        sandbox_container_id=sandbox_container_id,
        sandbox_container_generation=sandbox_container_generation,
        sandbox_skill_metadata=list(sandbox_skill_metadata),
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    async with get_async_session() as session:
        session.add(job)
        # Register the owner wake-up obligation in the same transaction (single
        # source of truth for liveness; no window between job and notification).
        agent_notifications.add_obligation_in_session(
            session,
            kind=AgentNotificationKind.SANDBOX_ASYNC_JOB_FINISHED,
            session_id=session_id,
            target_agent_code=agent_code,
            target_agent_instance_id=agent_instance_id,
            run_id=run_id,
            nested_for_agent_code=nested_for_agent_code,
            nested_call_id=nested_call_id,
            sandbox_container_id=sandbox_container_id,
            sandbox_container_generation=sandbox_container_generation,
            sandbox_skill_metadata=sandbox_skill_metadata,
        )
        await session.commit()
        await session.refresh(job)
    logger.debug("sandbox async job created: %s", job.run_id)
    return snapshot_from_job(job)


async def get_async_job(run_id: str, *, session_id: str) -> SandboxAsyncJobSnapshot | None:
    async with get_async_session() as session:
        job = await session.get(SandboxAsyncJob, run_id)
        if job is None or job.session_id != session_id:
            return None
        return snapshot_from_job(job)


async def count_running_async_jobs_for_agent(*, session_id: str, agent_instance_id: str) -> int:
    async with get_async_session() as session:
        return len((await session.exec(
            select(SandboxAsyncJob.run_id).where(
                SandboxAsyncJob.session_id == session_id,
                SandboxAsyncJob.agent_instance_id == agent_instance_id,
                SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value,
            )
        )).all())


async def complete_async_job(
    run_id: str,
    *,
    exit_code: int,
    output_bytes: int,
    output_lines: int,
) -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(
        run_id,
        SandboxAsyncJobStatus.COMPLETED,
        exit_code=exit_code,
        output_bytes=output_bytes,
        output_lines=output_lines,
    )


async def fail_async_job(
    run_id: str,
    error: str,
    *,
    output_bytes: int = 0,
    output_lines: int = 0,
) -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(
        run_id,
        SandboxAsyncJobStatus.FAILED,
        output_bytes=output_bytes,
        output_lines=output_lines,
        error=error,
    )


async def cancel_async_job(
    run_id: str,
    error: str = "",
    *,
    output_bytes: int = 0,
    output_lines: int = 0,
) -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(
        run_id,
        SandboxAsyncJobStatus.CANCELED,
        output_bytes=output_bytes,
        output_lines=output_lines,
        error=error,
    )


async def cancel_running_async_jobs_for_session(session_id: str, error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(session_id=session_id, error=error)


async def cancel_running_async_jobs_for_agent(
    *,
    session_id: str,
    agent_instance_id: str,
    error: str = "",
) -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(
        session_id=session_id,
        agent_instance_id=agent_instance_id,
        error=error,
    )


async def cancel_running_async_jobs_for_container(container_id: int, error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(sandbox_container_id=container_id, error=error)


async def cancel_running_async_jobs(error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(error=error)


async def mark_stale_running_async_jobs_failed() -> list[SandboxAsyncJobSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        rows = (await session.exec(
            select(SandboxAsyncJob).where(SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value)
        )).all()
        restart_error = "Sandbox async job was interrupted by backend restart."
        for job in rows:
            job.status = SandboxAsyncJobStatus.FAILED.value
            job.error = restart_error
            job.updated_at = now
            job.finished_at = now
            session.add(job)
            await agent_notifications.resolve_obligation_in_session(
                session,
                kind=AgentNotificationKind.SANDBOX_ASYNC_JOB_FINISHED,
                run_id=job.run_id,
                ready=True,
                payload=_async_job_obligation_payload(job),
                error=restart_error,
            )
        if rows:
            await session.commit()
            for job in rows:
                await session.refresh(job)
            logger.info("stale sandbox async jobs marked failed: %d", len(rows))
        snapshots = [snapshot_from_job(job) for job in rows]
    return snapshots


def snapshot_from_job(job: SandboxAsyncJob) -> SandboxAsyncJobSnapshot:
    return SandboxAsyncJobSnapshot(
        run_id=job.run_id,
        session_id=job.session_id,
        agent_code=job.agent_code,
        agent_instance_id=job.agent_instance_id,
        command=job.command,
        output_file=job.output_file,
        status=_coerce_status(job.status),
        exit_code=job.exit_code,
        output_bytes=job.output_bytes,
        output_lines=job.output_lines,
        error=job.error,
        nested_for_agent_code=job.nested_for_agent_code,
        nested_call_id=job.nested_call_id,
        sandbox_container_id=job.sandbox_container_id,
        sandbox_container_generation=job.sandbox_container_generation,
        sandbox_skill_metadata=_coerce_string_tuple(job.sandbox_skill_metadata),
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _finish_async_job(
    run_id: str,
    status: SandboxAsyncJobStatus,
    *,
    exit_code: int | None = None,
    output_bytes: int = 0,
    output_lines: int = 0,
    error: str = "",
) -> SandboxAsyncJobSnapshot | None:
    now = datetime.now()
    async with get_async_session() as session:
        job = await session.get(SandboxAsyncJob, run_id)
        if job is None:
            return None
        if _coerce_status(job.status) in TERMINAL_ASYNC_JOB_STATUSES:
            return snapshot_from_job(job)
        updated = await session.exec(
            update(SandboxAsyncJob)
            .where(
                SandboxAsyncJob.run_id == run_id,
                SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value,
            )
            .values(
                status=status.value,
                exit_code=exit_code,
                output_bytes=output_bytes,
                output_lines=output_lines,
                error=error,
                updated_at=now,
                finished_at=now,
            )
        )
        if updated.rowcount != 1:
            await session.rollback()
            current = await session.get(SandboxAsyncJob, run_id)
            return snapshot_from_job(current) if current is not None else None
        # Flip the owner obligation atomically with the job-terminal write.
        refreshed = await session.get(SandboxAsyncJob, run_id)
        await agent_notifications.resolve_obligation_in_session(
            session,
            kind=AgentNotificationKind.SANDBOX_ASYNC_JOB_FINISHED,
            run_id=run_id,
            ready=status in _OWNER_WAKING_STATUSES,
            payload=_async_job_obligation_payload(refreshed) if refreshed is not None else None,
            error=error,
        )
        await session.commit()
        current = await session.get(SandboxAsyncJob, run_id)
        return snapshot_from_job(current) if current is not None else None


def _async_job_obligation_payload(job: SandboxAsyncJob) -> dict[str, object]:
    return {
        "status": _coerce_status(job.status).value,
        "output_file": job.output_file,
        "output_bytes": job.output_bytes,
        "output_lines": job.output_lines,
        "exit_code": job.exit_code,
        "error": job.error,
    }


async def _cancel_running_async_jobs(
    *,
    session_id: str | None = None,
    agent_instance_id: str | None = None,
    sandbox_container_id: int | None = None,
    error: str = "",
) -> list[SandboxAsyncJobSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        statement = select(SandboxAsyncJob).where(SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value)
        if session_id is not None:
            statement = statement.where(SandboxAsyncJob.session_id == session_id)
        if agent_instance_id is not None:
            statement = statement.where(SandboxAsyncJob.agent_instance_id == agent_instance_id)
        if sandbox_container_id is not None:
            statement = statement.where(SandboxAsyncJob.sandbox_container_id == sandbox_container_id)
        rows = (await session.exec(statement)).all()
        for job in rows:
            job.status = SandboxAsyncJobStatus.CANCELED.value
            job.error = error
            job.updated_at = now
            job.finished_at = now
            session.add(job)
            await agent_notifications.resolve_obligation_in_session(
                session,
                kind=AgentNotificationKind.SANDBOX_ASYNC_JOB_FINISHED,
                run_id=job.run_id,
                ready=False,
                error=error,
            )
        if not rows:
            return []
        await session.commit()
        for job in rows:
            await session.refresh(job)
        snapshots = [snapshot_from_job(job) for job in rows]
    return snapshots


def _coerce_status(status: SandboxAsyncJobStatus | str) -> SandboxAsyncJobStatus:
    if isinstance(status, SandboxAsyncJobStatus):
        return status
    return SandboxAsyncJobStatus(str(status).lower())


def _coerce_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))
