import asyncio
import re
import shlex
from dataclasses import replace

from agents import RunContextWrapper, function_tool

from core.runtime.context import AgentRuntimeContext
from core.sandbox import command_output
from core.sandbox.command_jobs import cancel_async_sandbox_command, start_async_sandbox_command
from core.sandbox.command_output import COMMAND_TIMEOUT_ERROR
from schema.sandbox.async_jobs import SandboxAsyncJobStatus
from schema.common.tool_results import ToolResultSchema, ToolResultStatusSchema, ToolResultTypeSchema
from service.sandbox import async_jobs as sandbox_async_jobs
from service.sandbox.commands import SandboxContainerCommandTimeoutError, execute_sandbox_container_command
from utils.markdown import markdown_body_without_front_matter


_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SANDBOX_SKILLS_DIR = ".agents/skills"
_SKILL_RESOURCE_FILES_MARKER = "__Z3R0_SKILL_RESOURCE_FILES__"
_SKILL_RESOURCE_FILES_TRUNCATED_MARKER = "__Z3R0_SKILL_RESOURCE_FILES_TRUNCATED__"
_MAX_SKILL_RESOURCE_FILES = 200
_SYNC_COMMAND_TIMEOUT_SECONDS = 30
_ASYNC_COMMAND_TIMEOUT_SECONDS = 300
_ASYNC_COMMAND_CONCURRENCY_LIMIT = 3


def _command_result(
    *,
    status: SandboxAsyncJobStatus,
    output_file: str | None = None,
    output_bytes: int = 0,
    output_lines: int = 0,
    exit_code: int | None = None,
    run_id: str | None = None,
    error: str | None = None,
) -> str:
    return command_output.result_metadata(
        status=status,
        output_file=output_file,
        output_bytes=output_bytes,
        output_lines=output_lines,
        exit_code=exit_code,
        run_id=run_id,
        error=error,
    ).model_dump_json(exclude_none=True, exclude_defaults=True)


def _error_result(error: str) -> str:
    return _command_result(status=SandboxAsyncJobStatus.FAILED, error=error)


def _clamp_timeout(timeout_seconds: int | None, maximum: int) -> int:
    if timeout_seconds is None:
        return maximum
    try:
        timeout_seconds = int(timeout_seconds)
    except (TypeError, ValueError):
        return maximum
    return min(max(timeout_seconds, 1), maximum)


@function_tool
async def execute_sync_command(
    ctx: RunContextWrapper[AgentRuntimeContext],
    command: str,
    timeout_seconds: int = _SYNC_COMMAND_TIMEOUT_SECONDS,
) -> str:
    """Execute a short sandbox command and return result metadata.

    Args:
        command: str shell command to execute in the selected sandbox container.
        timeout_seconds: int command timeout in seconds, clamped to 1-30.

    Returns:
        JSON metadata with status, output_file, output_bytes, output_lines, exit_code, and optional error.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _error_result("No sandbox container selected.")
    if not command.strip():
        return _error_result("sandbox container command is required")
    timeout = _clamp_timeout(timeout_seconds, _SYNC_COMMAND_TIMEOUT_SECONDS)
    output_path = command_output.new_output_path()

    try:
        result = await execute_sandbox_container_command(
            id=container_id,
            command=command_output.capture_command(command, output_path),
            timeout_seconds=timeout,
        )
    except asyncio.CancelledError:
        raise
    except SandboxContainerCommandTimeoutError:
        return _error_result(COMMAND_TIMEOUT_ERROR)
    except Exception as exc:
        return _error_result(str(exc) or "Command execution failed.")

    output_bytes, output_lines = command_output.parse_capture_stats(result.output)
    return _command_result(
        status=SandboxAsyncJobStatus.COMPLETED if result.exit_code == 0 else SandboxAsyncJobStatus.FAILED,
        output_file=output_path,
        output_bytes=output_bytes,
        output_lines=output_lines,
        exit_code=result.exit_code,
    )


@function_tool
async def execute_async_command(
    ctx: RunContextWrapper[AgentRuntimeContext],
    command: str,
    timeout_seconds: int = _ASYNC_COMMAND_TIMEOUT_SECONDS,
) -> str:
    """Start a long-running sandbox command; this ends the current turn.

    Dispatching is turn-terminal: control returns to the runtime and the agent
    is resumed automatically when the command finishes, with its result and
    output file delivered as fresh context. Never poll or read a running job.

    Args:
        command: str shell command to execute in the selected sandbox container.
        timeout_seconds: int command timeout in seconds, clamped to 1-300.

    Returns:
        JSON metadata with status and run_id.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _error_result("No sandbox container selected.")
    if not command.strip():
        return _error_result("sandbox container command is required")
    if not ctx.context.agent_instance_id:
        return _error_result("agent instance id is required for async command execution")

    running_jobs = await sandbox_async_jobs.count_running_async_jobs_for_agent(
        session_id=ctx.context.session_id,
        agent_instance_id=ctx.context.agent_instance_id,
    )
    if running_jobs >= _ASYNC_COMMAND_CONCURRENCY_LIMIT:
        return _error_result(
            f"sandbox async command limit reached; at most {_ASYNC_COMMAND_CONCURRENCY_LIMIT} commands may run concurrently",
        )

    timeout = _clamp_timeout(timeout_seconds, _ASYNC_COMMAND_TIMEOUT_SECONDS)
    run_id = command_output.new_run_id()
    output_path = command_output.output_path_for_run(run_id)
    command_text = command.strip()

    await start_async_sandbox_command(
        run_id=run_id,
        context=replace(ctx.context),
        command=command_text,
        output_file=output_path,
        wrapped_command=command_output.async_command(command_text, output_path),
        stat_command=command_output.stat_command(output_path),
        timeout_seconds=timeout,
    )
    return _command_result(
        status=SandboxAsyncJobStatus.RUNNING,
        run_id=run_id,
    )


@function_tool
async def read_sandbox_command_output(
    ctx: RunContextWrapper[AgentRuntimeContext],
    output_file: str,
    start_line: int = 1,
    line_count: int = command_output.OUTPUT_CHUNK_LINE_COUNT,
) -> str:
    """Read a bounded line range from a sandbox command output file.

    Args:
        output_file: str output path returned by execute_sync_command or an async completion notification.
        start_line: int one-based starting line number.
        line_count: int number of lines to read, clamped by the output reader to a bounded chunk size.

    Returns:
        JSON chunk with output_file, start_line, end_line, and content.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _error_result("No sandbox container selected.")
    try:
        read_cmd, start, count, end = command_output.read_command(output_file, start_line, line_count)
        result = await execute_sandbox_container_command(
            id=container_id,
            command=read_cmd,
            timeout_seconds=_SYNC_COMMAND_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except ValueError as exc:
        return _error_result(str(exc))
    except SandboxContainerCommandTimeoutError:
        return _error_result(COMMAND_TIMEOUT_ERROR)
    except Exception as exc:
        return _error_result(str(exc) or "Command output read failed.")
    if result.exit_code != 0:
        return _error_result(result.output or "Command output read failed.")

    return command_output.output_chunk(
        output_file=output_file,
        start_line=start,
        line_count=count,
        content=result.output,
    ).model_dump_json(exclude_none=True)


@function_tool
async def cancel_sandbox_async_job(ctx: RunContextWrapper[AgentRuntimeContext], run_id: str) -> str:
    """Cancel a sandbox async command owned by the current session.

    Args:
        run_id: str async command run id returned by execute_async_command.

    Returns:
        JSON metadata for the latest known async command state after cancellation is requested.
    """
    snapshot = await sandbox_async_jobs.get_async_job(run_id.strip(), session_id=ctx.context.session_id)
    if snapshot is None or snapshot.agent_instance_id != ctx.context.agent_instance_id:
        return _error_result("sandbox async job not found")
    await cancel_async_sandbox_command(snapshot.run_id)
    latest = await sandbox_async_jobs.get_async_job(snapshot.run_id, session_id=ctx.context.session_id)
    return command_output.result_metadata_from_snapshot(
        latest or snapshot,
    ).model_dump_json(exclude_none=True, exclude_defaults=True)


def _skill_result(status: ToolResultStatusSchema, output: str) -> str:
    return ToolResultSchema(
        status=status, type=ToolResultTypeSchema.SKILL_DETAIL, output=output,
    ).model_dump_json()


def _skill_root(skill_name: str) -> str:
    return f"{SANDBOX_SKILLS_DIR}/{skill_name}"


def _load_skill_command(skill_name: str) -> str:
    skill_root = _skill_root(skill_name)
    return f"""
skill_root={shlex.quote(skill_root)}
skill_file="$skill_root/SKILL.md"
test -f "$skill_file" || exit 1
cat "$skill_file"
printf '\\n%s\\n' {shlex.quote(_SKILL_RESOURCE_FILES_MARKER)}
find "$skill_root" -mindepth 1 -type f | sort | awk -v prefix="$skill_root/" -v max={_MAX_SKILL_RESOURCE_FILES} -v truncated={shlex.quote(_SKILL_RESOURCE_FILES_TRUNCATED_MARKER)} '
  index($0, prefix) == 1 {{
    rel = substr($0, length(prefix) + 1)
    if (rel == "SKILL.md") next
    count += 1
    if (count <= max) print rel
    else {{ print truncated; exit }}
  }}
'
""".strip()


def _parse_loaded_skill_output(output: str) -> tuple[str, tuple[str, ...], bool]:
    markdown, separator, resources = output.rpartition(f"\n{_SKILL_RESOURCE_FILES_MARKER}\n")
    if not separator:
        return output, (), False

    files: list[str] = []
    truncated = False
    for line in resources.splitlines():
        entry = line.strip()
        if not entry:
            continue
        if entry == _SKILL_RESOURCE_FILES_TRUNCATED_MARKER:
            truncated = True
            continue
        files.append(entry)
    return markdown, tuple(files), truncated


def _loaded_skill_body(
    skill_name: str,
    markdown: str,
    resource_files: tuple[str, ...] = (),
    resource_files_truncated: bool = False,
) -> str:
    skill_root = _skill_root(skill_name)
    body = markdown_body_without_front_matter(markdown).strip()
    parts = [
        (
            "## Skill Resource Root\n\n"
            f"`{skill_root}`\n\n"
            "Use sandbox command tools for reads, inspection, execution, and other file operations under this root."
        ),
        _skill_resource_files_section(resource_files, resource_files_truncated),
    ]
    if body:
        parts.append(body)
    return "\n\n".join(parts)


def _skill_resource_files_section(files: tuple[str, ...], truncated: bool) -> str:
    if not files:
        return "## Skill Resource Files\n\nNone."
    lines = [f"- `{path}`" for path in files]
    if truncated:
        lines.append(f"- ... truncated after {_MAX_SKILL_RESOURCE_FILES} files")
    return "## Skill Resource Files\n\nPaths are relative to `Skill Resource Root`:\n\n" + "\n".join(lines)


@function_tool
async def load_skill(ctx: RunContextWrapper[AgentRuntimeContext], name: str) -> str:
    """Load the body of a named skill from the selected sandbox container.

    Args:
        name: str skill directory name under .agents/skills.

    Returns:
        JSON status with the skill body, sandbox-relative skill root, and resource file list.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _skill_result(ToolResultStatusSchema.ERROR, "No sandbox container selected.")

    skill_name = name.strip()
    if not _SKILL_NAME_PATTERN.fullmatch(skill_name):
        return _skill_result(
            ToolResultStatusSchema.ERROR,
            "Skill name must contain only letters, numbers, dot, underscore, or dash.",
        )

    try:
        result = await execute_sandbox_container_command(
            id=container_id,
            command=_load_skill_command(skill_name),
            timeout_seconds=_SYNC_COMMAND_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except SandboxContainerCommandTimeoutError:
        return _skill_result(ToolResultStatusSchema.ERROR, COMMAND_TIMEOUT_ERROR)
    except Exception as exc:
        return _skill_result(ToolResultStatusSchema.ERROR, str(exc) or "Skill loading failed.")

    if result.exit_code != 0:
        return _skill_result(ToolResultStatusSchema.ERROR, f"Skill not found: {skill_name}")

    markdown, resource_files, resource_files_truncated = _parse_loaded_skill_output(result.output)
    return _skill_result(
        ToolResultStatusSchema.SUCCESS,
        _loaded_skill_body(skill_name, markdown, resource_files, resource_files_truncated),
    )
