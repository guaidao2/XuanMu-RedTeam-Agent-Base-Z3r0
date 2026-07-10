"""Background sandbox command execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from core.runtime.context import AgentRuntimeContext
from core.sandbox.command_output import COMMAND_TIMEOUT_ERROR
from logger import get_logger
from schema.sandbox.async_jobs import SandboxAsyncJobSnapshot
from service.sandbox import async_jobs as sandbox_async_jobs
from service.sandbox.commands import SandboxContainerCommandTimeoutError, execute_sandbox_container_command


logger = get_logger(__name__)
_OUTPUT_STAT_TIMEOUT_SECONDS = 30


@dataclass
class _AsyncCommandJob:
    task: asyncio.Task[None]
    session_id: str
    agent_instance_id: str
    sandbox_container_id: int | None
    sandbox_container_generation: int


_jobs: dict[str, _AsyncCommandJob] = {}
_jobs_lock = asyncio.Lock()
_AsyncCommandJobPredicate = Callable[[str, _AsyncCommandJob], bool]


async def start_async_sandbox_runtime() -> None:
    snapshots = await sandbox_async_jobs.mark_stale_running_async_jobs_failed()
    for snapshot in snapshots:
        await _queue_completion_notification(snapshot)


async def start_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    command: str,
    output_file: str,
    wrapped_command: str,
    stat_command: str,
    timeout_seconds: int,
) -> None:
    await _create_job_record(
        run_id=run_id,
        context=context,
        command=command,
        output_file=output_file,
    )
    async with _jobs_lock:
        task = asyncio.create_task(
            _run_async_sandbox_command(
                run_id=run_id,
                context=context,
                wrapped_command=wrapped_command,
                stat_command=stat_command,
                timeout_seconds=timeout_seconds,
            ),
            name=f"sandbox-async-command-{run_id}",
        )
        _jobs[run_id] = _AsyncCommandJob(
            task=task,
            session_id=context.session_id,
            agent_instance_id=context.agent_instance_id,
            sandbox_container_id=context.sandbox_container_id,
            sandbox_container_generation=context.sandbox_container_generation,
        )
    task.add_done_callback(lambda completed: _finish_async_sandbox_command(run_id, completed))


async def cancel_agent_async_sandbox_commands(
    *,
    session_id: str,
    agent_instance_id: str,
) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(
        lambda _, job: job.session_id == session_id and job.agent_instance_id == agent_instance_id
    )
    if runtime_canceled:
        return True
    snapshots = await sandbox_async_jobs.cancel_running_async_jobs_for_agent(
        session_id=session_id,
        agent_instance_id=agent_instance_id,
        error="Sandbox async job canceled.",
    )
    await _queue_completion_notifications(snapshots)
    return runtime_canceled or bool(snapshots)


async def cancel_async_sandbox_command(run_id: str) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda candidate, _: candidate == run_id)
    if runtime_canceled:
        return True
    snapshot = await sandbox_async_jobs.cancel_async_job(run_id, "Sandbox async job cancel requested.")
    await _queue_completion_notification(snapshot)
    return runtime_canceled or snapshot is not None


async def cancel_sandbox_async_commands(container_id: int) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda _, job: job.sandbox_container_id == container_id)
    if runtime_canceled:
        return True
    snapshots = await sandbox_async_jobs.cancel_running_async_jobs_for_container(
        container_id,
        "Sandbox async job canceled.",
    )
    await _queue_completion_notifications(snapshots)
    return runtime_canceled or bool(snapshots)


async def cancel_session_async_sandbox_commands(session_id: str) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda _, job: job.session_id == session_id)
    if runtime_canceled:
        return True
    snapshots = await sandbox_async_jobs.cancel_running_async_jobs_for_session(
        session_id,
        "Sandbox async job canceled.",
    )
    await _queue_completion_notifications(snapshots)
    return runtime_canceled or bool(snapshots)


async def stop_async_sandbox_commands() -> None:
    await _cancel_runtime_jobs(lambda _, __: True)
    snapshots = await sandbox_async_jobs.cancel_running_async_jobs("Sandbox async job canceled by runtime shutdown.")
    await _queue_completion_notifications(snapshots)


async def _cancel_runtime_jobs(predicate: _AsyncCommandJobPredicate) -> bool:
    async with _jobs_lock:
        tasks: list[asyncio.Task[None]] = []
        for run_id, job in list(_jobs.items()):
            if not predicate(run_id, job):
                continue
            _jobs.pop(run_id, None)
            if not job.task.done():
                job.task.cancel()
            tasks.append(job.task)
    if not tasks:
        return False
    await asyncio.gather(*tasks, return_exceptions=True)
    return True


async def _run_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    wrapped_command: str,
    stat_command: str,
    timeout_seconds: int,
) -> None:
    if context.sandbox_container_id is None:
        await sandbox_async_jobs.fail_async_job(run_id, "No sandbox container selected.")
        return

    try:
        result = await execute_sandbox_container_command(
            id=context.sandbox_container_id,
            command=wrapped_command,
            timeout_seconds=timeout_seconds,
        )
        output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
        snapshot = await sandbox_async_jobs.complete_async_job(
            run_id,
            exit_code=result.exit_code,
            output_bytes=output_bytes,
            output_lines=output_lines,
        )
        await _queue_completion_notification(snapshot)
    except asyncio.CancelledError:
        output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
        snapshot = await sandbox_async_jobs.cancel_async_job(
            run_id,
            "Sandbox async job canceled.",
            output_bytes=output_bytes,
            output_lines=output_lines,
        )
        await _queue_completion_notification(snapshot)
        raise
    except SandboxContainerCommandTimeoutError:
        output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
        snapshot = await sandbox_async_jobs.fail_async_job(
            run_id,
            COMMAND_TIMEOUT_ERROR,
            output_bytes=output_bytes,
            output_lines=output_lines,
        )
        await _queue_completion_notification(snapshot)
    except Exception as exc:
        logger.exception("async sandbox command execution failed: %s", run_id)
        output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
        snapshot = await sandbox_async_jobs.fail_async_job(
            run_id,
            str(exc) or "Sandbox async job failed.",
            output_bytes=output_bytes,
            output_lines=output_lines,
        )
        await _queue_completion_notification(snapshot)
    finally:
        async with _jobs_lock:
            current = _jobs.get(run_id)
            if current is not None and current.task is asyncio.current_task():
                _jobs.pop(run_id, None)


async def _stat_output_file(container_id: int, stat_command: str) -> tuple[int, int]:
    try:
        result = await execute_sandbox_container_command(
            id=container_id,
            command=stat_command,
            timeout_seconds=_OUTPUT_STAT_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.debug("failed to stat async sandbox command output", exc_info=True)
        return 0, 0
    parts = result.output.strip().split()
    if len(parts) < 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _finish_async_sandbox_command(run_id: str, task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("async sandbox command task failed: %s", run_id)


async def _create_job_record(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    command: str,
    output_file: str,
) -> None:
    await sandbox_async_jobs.create_async_job(
        run_id=run_id,
        session_id=context.session_id,
        agent_code=context.agent_code,
        agent_instance_id=context.agent_instance_id,
        command=command,
        output_file=output_file,
        nested_for_agent_code=context.nested_for_agent_code,
        nested_call_id=context.nested_call_id,
        sandbox_container_id=context.sandbox_container_id,
        sandbox_container_generation=context.sandbox_container_generation,
        sandbox_skill_metadata=context.sandbox_skill_metadata,
    )


async def _queue_completion_notification(snapshot: SandboxAsyncJobSnapshot | None) -> None:
    # The terminal write already flipped the obligation atomically (PENDING for
    # completed/failed, silent for canceled); kick the owner so it integrates a
    # result or re-evaluates when dormant. The kick is a no-op when nothing pends.
    if snapshot is None:
        return
    try:
        from core.delegation.subagents import resume_target_instance

        await resume_target_instance(snapshot.session_id, snapshot.agent_instance_id)
    except Exception:
        logger.exception("failed to resume owner after async job completion: %s", snapshot.run_id)


async def _queue_completion_notifications(snapshots: list[SandboxAsyncJobSnapshot]) -> None:
    for snapshot in snapshots:
        await _queue_completion_notification(snapshot)
