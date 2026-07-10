import asyncio
import shlex
import threading
from uuid import uuid4

import docker

from database import get_async_session
from logger import get_logger
from model.sandbox.containers import SandboxContainer
from model.host.hosts import ManagedHost
from schema.sandbox.containers import SandboxContainerStatus
from service.sandbox.docker_ops import (
    docker_status_to_sandbox_status,
    inspect_container_state_sync,
)
from service.sandbox import close_docker_response_sync as _close_response_sync
from service.sandbox.control_proxy import resolve_container_egress_environment
from service.sandbox.status import save_sandbox_container_status
from service.sandbox.types import SandboxContainerCommandResult


logger = get_logger(__name__)

_COMMAND_CANCEL_JOIN_TIMEOUT_SECONDS = 3
_COMMAND_TERMINATE_TIMEOUT_SECONDS = 5
_COMMAND_WORKDIR = "/root"


class _SandboxCommandCancelled(RuntimeError):
    pass


class SandboxContainerCommandTimeoutError(TimeoutError):
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"sandbox container command timed out after {_format_timeout_seconds(timeout_seconds)} seconds")


class _RunningContainerCommand:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream: object | None = None
        self._closed = False

    def set_stream(self, stream: object) -> None:
        with self._lock:
            if self._closed:
                close_now = True
            else:
                self._stream = stream
                close_now = False
        if close_now:
            _close_command_stream(stream)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            stream, self._stream = self._stream, None
        if stream is not None:
            _close_command_stream(stream)


async def _execute_container_command(
    host: ManagedHost,
    container_hash: str,
    command: str,
    environment: dict[str, str],
    timeout_seconds: float,
) -> SandboxContainerCommandResult:
    marker_path = f"/tmp/sandbox-command-{uuid4().hex}.pid"
    cancel_requested = threading.Event()
    running_command = _RunningContainerCommand()
    command_task = asyncio.create_task(
        asyncio.to_thread(
            _execute_container_command_sync,
            host,
            container_hash,
            command,
            environment,
            marker_path,
            cancel_requested,
            running_command,
        ),
        name="sandbox-container-command",
    )
    try:
        return await asyncio.wait_for(asyncio.shield(command_task), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        cancel_requested.set()
        running_command.close()
        await _terminate_container_command(host, container_hash, marker_path)
        await _drain_cancelled_command_task(command_task, container_hash)
        raise SandboxContainerCommandTimeoutError(timeout_seconds) from exc
    except asyncio.CancelledError:
        cancel_requested.set()
        running_command.close()
        await _terminate_container_command(host, container_hash, marker_path)
        await _drain_cancelled_command_task(command_task, container_hash)
        raise


async def _terminate_container_command(host: ManagedHost, container_hash: str, marker_path: str) -> None:
    terminate_task = asyncio.create_task(
        asyncio.to_thread(_terminate_container_command_sync, host, container_hash, marker_path),
        name="sandbox-container-command-terminate",
    )
    try:
        await asyncio.wait_for(asyncio.shield(terminate_task), timeout=_COMMAND_TERMINATE_TIMEOUT_SECONDS + 1)
    except asyncio.TimeoutError:
        logger.warning("sandbox container command termination timed out: %s", container_hash)
        _consume_background_task(terminate_task)
    except docker.errors.NotFound:
        logger.debug("sandbox container absent while cancelling command: %s", container_hash)
    except asyncio.CancelledError:
        _consume_background_task(terminate_task)
        raise
    except Exception:
        logger.warning("sandbox container command termination failed: %s", container_hash, exc_info=True)


async def _drain_cancelled_command_task(task: asyncio.Task, container_hash: str) -> None:
    if task.done():
        _consume_background_task(task)
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=_COMMAND_CANCEL_JOIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("sandbox container command did not exit after cancellation: %s", container_hash)
        _consume_background_task(task)
    except asyncio.CancelledError:
        _consume_background_task(task)
        raise
    except _SandboxCommandCancelled:
        pass
    except Exception:
        logger.debug("sandbox container command exited after cancellation with an error", exc_info=True)


def _consume_background_task(task: asyncio.Task) -> None:
    if task.done():
        _discard_background_task_result(task)
        return
    task.add_done_callback(_discard_background_task_result)


def _discard_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except _SandboxCommandCancelled:
        pass
    except Exception:
        logger.debug("background sandbox command task failed", exc_info=True)


def _execute_container_command_sync(
    host: ManagedHost,
    container_hash: str,
    command: str,
    environment: dict[str, str],
    marker_path: str,
    cancel_requested: threading.Event,
    running_command: _RunningContainerCommand,
) -> SandboxContainerCommandResult:
    from service.host.docker import docker_client_for_host

    client = docker_client_for_host(host)
    stream: object | None = None
    try:
        if cancel_requested.is_set():
            raise _SandboxCommandCancelled()
        container = client.containers.get(container_hash)
        exec_response = client.api.exec_create(
            container=container.id,
            cmd=["/bin/sh", "-lc", _wrap_cancellable_command(command, marker_path)],
            environment=environment or None,
            workdir=_COMMAND_WORKDIR,
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
        )
        exec_id = str(exec_response["Id"])
        if cancel_requested.is_set():
            raise _SandboxCommandCancelled()
        stream = client.api.exec_start(exec_id, stream=True, demux=True)
        running_command.set_stream(stream)

        stdout_parts: list[bytes | str] = []
        stderr_parts: list[bytes | str] = []
        try:
            for chunk in stream:
                if cancel_requested.is_set():
                    raise _SandboxCommandCancelled()
                stdout, stderr = _split_command_output_chunk(chunk)
                if stdout:
                    stdout_parts.append(stdout)
                if stderr:
                    stderr_parts.append(stderr)
        except Exception:
            if cancel_requested.is_set():
                raise _SandboxCommandCancelled()
            raise
        if cancel_requested.is_set():
            raise _SandboxCommandCancelled()

        inspect_result = client.api.exec_inspect(exec_id)
        exit_code = inspect_result.get("ExitCode")
        return SandboxContainerCommandResult(
            output=_decode_command_output_parts(stdout_parts) + _decode_command_output_parts(stderr_parts),
            exit_code=exit_code if isinstance(exit_code, int) else 1,
        )
    finally:
        running_command.close()
        client.close()


def _terminate_container_command_sync(host: ManagedHost, container_hash: str, marker_path: str) -> None:
    from service.host.docker import docker_client_for_host

    client = docker_client_for_host(host, timeout=_COMMAND_TERMINATE_TIMEOUT_SECONDS)
    try:
        container = client.containers.get(container_hash)
        container.exec_run(
            cmd=["/bin/sh", "-lc", _build_command_termination_script(marker_path)],
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
            demux=True,
        )
    finally:
        client.close()


def _close_command_stream(stream: object) -> None:
    response = getattr(stream, "_response", None)
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.debug("failed to close sandbox command stream", exc_info=True)
    _close_response_sync(stream, response)
    try:
        setattr(stream, "_response", None)
    except Exception:
        pass


def _split_command_output_chunk(chunk: object) -> tuple[bytes | str | None, bytes | str | None]:
    if isinstance(chunk, tuple):
        stdout = chunk[0] if len(chunk) > 0 else None
        stderr = chunk[1] if len(chunk) > 1 else None
        return stdout, stderr
    if isinstance(chunk, (bytes, str)):
        return chunk, None
    return None, None


def _decode_command_output_parts(parts: list[bytes | str]) -> str:
    return "".join(_decode_command_output(part) for part in parts)


def _wrap_cancellable_command(command: str, marker_path: str) -> str:
    marker = shlex.quote(marker_path)
    shell_command = _bash_command(command)
    group_inner = (
        f"rm -f {marker}; "
        f"printf '%s' \"$$\" > {marker}; "
        f"{shell_command} & "
        "pid=$!; wait \"$pid\"; code=$?; "
        f"rm -f {marker}; "
        "exit \"$code\""
    )
    child_inner = (
        f"rm -f {marker}; "
        f"{shell_command} & "
        "pid=$!; "
        f"printf '%s' \"$pid\" > {marker}; "
        "wait \"$pid\"; code=$?; "
        f"rm -f {marker}; "
        "exit \"$code\""
    )
    return (
        "if command -v setsid >/dev/null 2>&1 "
        "&& setsid -w /bin/sh -lc 'exit 0' >/dev/null 2>&1; then "
        f"exec setsid -w /bin/sh -lc {shlex.quote(group_inner)}; "
        "else "
        f"exec /bin/sh -lc {shlex.quote(child_inner)}; "
        "fi"
    )


def _bash_command(command: str) -> str:
    return f"/bin/bash -lc {shlex.quote(command)}"


def _build_command_termination_script(marker_path: str) -> str:
    marker = shlex.quote(marker_path)
    return (
        "pid=''; "
        "for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do "
        f"pid=$(cat {marker} 2>/dev/null || true); "
        "[ -n \"$pid\" ] && break; "
        "sleep 0.1; "
        "done; "
        f"rm -f {marker}; "
        "if [ -n \"$pid\" ]; then "
        "kill -TERM -\"$pid\" 2>/dev/null || kill -TERM \"$pid\" 2>/dev/null || true; "
        "sleep 0.5; "
        "kill -KILL -\"$pid\" 2>/dev/null || kill -KILL \"$pid\" 2>/dev/null || true; "
        "fi"
    )


def _decode_command_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output


def _normalize_command_timeout(timeout_seconds: float) -> float:
    try:
        normalized_timeout_seconds = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("sandbox container command timeout must be a number") from exc
    if normalized_timeout_seconds <= 0:
        raise ValueError("sandbox container command timeout must be greater than 0 seconds")
    return normalized_timeout_seconds


def _format_timeout_seconds(timeout_seconds: float) -> str:
    value = float(timeout_seconds)
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


async def execute_sandbox_container_command(
    id: int,
    command: str,
    timeout_seconds: float,
) -> SandboxContainerCommandResult:
    command = command.strip()
    if not command:
        raise ValueError("sandbox container command is required")
    normalized_timeout_seconds = _normalize_command_timeout(timeout_seconds)

    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            raise ValueError("sandbox container not found")
        if sandbox_container.status != SandboxContainerStatus.RUNNING:
            raise ValueError("only running sandbox containers can execute commands")

        container_hash = sandbox_container.container_hash
        host_id = sandbox_container.host_id

        host = await session.get(ManagedHost, host_id)
        if host is None:
            raise ValueError("managed host not found")

    environment = await resolve_container_egress_environment(id)

    try:
        state = await asyncio.to_thread(inspect_container_state_sync, host, container_hash)
    except Exception:
        logger.exception("sandbox container inspect failed before command execution: %s", id)
        raise RuntimeError("failed to inspect sandbox container")

    status = SandboxContainerStatus.ERROR if not state.exists else docker_status_to_sandbox_status(state.status)
    if status != SandboxContainerStatus.RUNNING:
        await save_sandbox_container_status(id, status)
        raise RuntimeError("sandbox container is not running")

    try:
        return await _execute_container_command(host, container_hash, command, environment, normalized_timeout_seconds)
    except asyncio.CancelledError:
        raise
    except SandboxContainerCommandTimeoutError:
        raise
    except docker.errors.NotFound:
        logger.debug("sandbox container instance not found while executing command: %s", id)
        await save_sandbox_container_status(id, SandboxContainerStatus.ERROR)
        raise RuntimeError("sandbox container instance not found")
    except Exception:
        logger.exception("sandbox container command execution failed: %s", id)
        raise RuntimeError("failed to execute sandbox container command")
