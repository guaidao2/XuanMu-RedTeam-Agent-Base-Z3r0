"""Local shell execution tools — replaces Docker sandbox with local subprocess.

Provides agent tools that run shell commands directly on the host machine
(Kali Linux) via subprocess, instead of inside Docker containers.
"""
import asyncio
import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import RunContextWrapper, function_tool

from core.runtime.context import AgentRuntimeContext
from schema.common.tool_results import ToolResultSchema, ToolResultStatusSchema, ToolResultTypeSchema
from schema.sandbox.async_jobs import SandboxAsyncJobStatus
from utils.markdown import markdown_body_without_front_matter


# ── constants ──────────────────────────────────────────────────────────────

_SYNC_TIMEOUT = 60  # seconds
_ASYNC_TIMEOUT = 600
_OUTPUT_DIR = ".xuanmu/outputs"
_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_LOCAL_SKILLS_DIR = ".agents/skills"
_MAX_OUTPUT_BYTES = 100_000
_MAX_OUTPUT_LINES = 5_000
_ASYNC_CONCURRENCY_LIMIT = 5

_SKILL_RESOURCE_FILES_MARKER = "__Z3R0_SKILL_RESOURCE_FILES__"
_SKILL_RESOURCE_FILES_TRUNCATED_MARKER = "__Z3R0_SKILL_RESOURCE_FILES_TRUNCATED__"
_MAX_SKILL_RESOURCE_FILES = 200


# ── in-memory async job registry ──────────────────────────────────────────

@dataclass
class _AsyncJob:
    run_id: str
    command: str
    process: asyncio.subprocess.Process
    output_path: str
    start_time: float
    status: str = "running"


_async_jobs: dict[str, _AsyncJob] = {}
_next_run_id: int = 0


def _new_run_id() -> str:
    global _next_run_id
    _next_run_id += 1
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"local-{ts}-{_next_run_id:04d}"


def _ensure_output_dir() -> Path:
    p = Path(_OUTPUT_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _output_path(run_id: str) -> str:
    return str(_ensure_output_dir() / f"{run_id}.out")


def _read_output(path: str, start_line: int = 1, line_count: int = 500) -> str:
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    total = len(lines)
    end = min(start_line + line_count - 1, total)
    selected = lines[start_line - 1 : end]
    return "\n".join(selected)


# ── result helpers ─────────────────────────────────────────────────────────

def _result(
    status: str,
    output_file: str = "",
    output_bytes: int = 0,
    output_lines: int = 0,
    exit_code: int | None = None,
    run_id: str | None = None,
    error: str | None = None,
) -> str:
    d: dict[str, Any] = {"status": status}
    if output_file:
        d["output_file"] = output_file
    if output_bytes:
        d["output_bytes"] = output_bytes
    if output_lines:
        d["output_lines"] = output_lines
    if exit_code is not None:
        d["exit_code"] = exit_code
    if run_id:
        d["run_id"] = run_id
    if error:
        d["error"] = error
    import json
    return json.dumps(d, ensure_ascii=False)


def _error(error: str) -> str:
    return _result(SandboxAsyncJobStatus.FAILED, error=error)


# ── tools ──────────────────────────────────────────────────────────────────

@function_tool
async def execute_command(
    ctx: RunContextWrapper[AgentRuntimeContext],
    command: str,
    timeout_seconds: int = _SYNC_TIMEOUT,
) -> str:
    """Execute a shell command on the local machine and return its result.

    The command runs directly on the host (Kali Linux) with the same
    environment and tooling available. Use this for reconnaissance, scanning,
    file operations, and any security tool execution.

    Args:
        command: Shell command to execute.
        timeout_seconds: Max execution time in seconds (1-60).

    Returns:
        JSON metadata with status, output_file, output_bytes, output_lines,
        exit_code, and optional error.
    """
    if not command.strip():
        return _error("command is required")
    timeout = max(1, min(timeout_seconds, _SYNC_TIMEOUT))

    run_id = _new_run_id()
    out_path = _output_path(run_id)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return _result(
                SandboxAsyncJobStatus.TIMED_OUT,
                error=f"Command timed out after {timeout}s",
            )

        output = stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]
        lines = output.splitlines()
        Path(out_path).write_text(output, encoding="utf-8")
        exit_code = proc.returncode or 0

        return _result(
            SandboxAsyncJobStatus.COMPLETED if exit_code == 0 else SandboxAsyncJobStatus.FAILED,
            output_file=out_path,
            output_bytes=len(output.encode("utf-8")),
            output_lines=len(lines),
            exit_code=exit_code,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _error(str(exc) or "Command execution failed.")


@function_tool
async def read_command_output(
    ctx: RunContextWrapper[AgentRuntimeContext],
    output_file: str,
    start_line: int = 1,
    line_count: int = 500,
) -> str:
    """Read a range of lines from a previous command's output file.

    Args:
        output_file: Path returned by execute_command's output_file field.
        start_line: 1-based starting line number.
        line_count: Number of lines to read (max 500).

    Returns:
        JSON with output_file, start_line, end_line, and content.
    """
    content = _read_output(output_file, start_line, line_count)
    lines = content.splitlines() if content else []
    import json
    return json.dumps({
        "output_file": output_file,
        "start_line": start_line,
        "end_line": start_line + len(lines) - 1 if lines else start_line - 1,
        "content": content,
    }, ensure_ascii=False)


@function_tool
async def run_background_command(
    ctx: RunContextWrapper[AgentRuntimeContext],
    command: str,
    timeout_seconds: int = _ASYNC_TIMEOUT,
) -> str:
    """Start a long-running command in the background and return immediately.

    The agent will be notified when the command finishes. Use this for
    long-running tasks like scans or brute-force attacks.

    Args:
        command: Shell command to execute in background.
        timeout_seconds: Max execution time in seconds (1-600).

    Returns:
        JSON with status and run_id. Use read_command_output later with
        the output path to see results.
    """
    if not command.strip():
        return _error("command is required")
    timeout = max(1, min(timeout_seconds, _ASYNC_TIMEOUT))

    run_id = _new_run_id()
    out_path = _output_path(run_id)

    # Check concurrency
    running = sum(1 for j in _async_jobs.values() if j.status == "running")
    if running >= _ASYNC_CONCURRENCY_LIMIT:
        return _error(f"Background command limit reached ({_ASYNC_CONCURRENCY_LIMIT})")

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            shell=True,
            executable="/bin/bash",
        )

        job = _AsyncJob(
            run_id=run_id,
            command=command,
            process=proc,
            output_path=out_path,
            start_time=time.time(),
        )
        _async_jobs[run_id] = job

        # Read output in background
        async def _collect(j: _AsyncJob, t: int) -> None:
            try:
                stdout, _ = await asyncio.wait_for(j.process.communicate(), timeout=t)
                output = stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT_BYTES]
                Path(j.output_path).write_text(output, encoding="utf-8")
                j.status = "completed"
            except asyncio.TimeoutError:
                j.process.kill()
                await j.process.wait()
                j.status = "timed_out"
            except Exception:
                j.status = "failed"
                import traceback
                Path(j.output_path).write_text(traceback.format_exc(), encoding="utf-8")

        asyncio.create_task(_collect(job, timeout))

        return _result(SandboxAsyncJobStatus.RUNNING, run_id=run_id)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return _error(str(exc) or "Failed to start background command.")


@function_tool
async def cancel_background_command(ctx: RunContextWrapper[AgentRuntimeContext], run_id: str) -> str:
    """Cancel a running background command.

    Args:
        run_id: The run_id returned by run_background_command.

    Returns:
        JSON with final status of the cancelled command.
    """
    job = _async_jobs.get(run_id.strip())
    if job is None:
        return _error("Background job not found")

    try:
        job.process.send_signal(signal.SIGTERM)
        await asyncio.sleep(0.5)
        if job.process.returncode is None:
            job.process.kill()
        job.status = "cancelled"
    except Exception as exc:
        return _error(f"Failed to cancel: {exc}")

    return _result(SandboxAsyncJobStatus.CANCELLED, run_id=run_id)


@function_tool
async def list_skills(ctx: RunContextWrapper[AgentRuntimeContext]) -> str:
    """List available skill directories under .agents/skills/.

    Returns:
        JSON with a list of available skill names.
    """
    skills_dir = Path(_LOCAL_SKILLS_DIR)
    if not skills_dir.is_dir():
        import json
        return json.dumps({"skills": [], "root": str(skills_dir)}, ensure_ascii=False)

    names = sorted(
        d.name for d in skills_dir.iterdir()
        if d.is_dir() and _SKILL_NAME_PATTERN.fullmatch(d.name)
    )
    import json
    return json.dumps({"skills": names, "root": str(skills_dir)}, ensure_ascii=False)


@function_tool
async def load_skill(ctx: RunContextWrapper[AgentRuntimeContext], name: str) -> str:
    """Load a skill definition from the local .agents/skills/ directory.

    Args:
        name: Skill directory name under .agents/skills/.

    Returns:
        JSON status with skill body and resource file list.
    """
    skill_name = name.strip()
    if not _SKILL_NAME_PATTERN.fullmatch(skill_name):
        import json
        return json.dumps({
            "status": ToolResultStatusSchema.ERROR,
            "output": "Skill name must contain only letters, numbers, dot, underscore, or dash.",
        }, ensure_ascii=False)

    skill_root = Path(f"{_LOCAL_SKILLS_DIR}/{skill_name}")
    skill_file = skill_root / "SKILL.md"

    if not skill_file.is_file():
        import json
        return json.dumps({
            "status": ToolResultStatusSchema.ERROR,
            "output": f"Skill not found: {skill_name}",
        }, ensure_ascii=False)

    try:
        markdown = skill_file.read_text(encoding="utf-8")

        # List resource files
        resource_files: list[str] = []
        truncated = False
        for fpath in sorted(skill_root.rglob("*")):
            if not fpath.is_file() or fpath.name == "SKILL.md":
                continue
            rel = str(fpath.relative_to(skill_root))
            if len(resource_files) < _MAX_SKILL_RESOURCE_FILES:
                resource_files.append(rel)
            else:
                truncated = True
                break

        body = markdown_body_without_front_matter(markdown).strip()
        parts = [
            f"## Skill Resource Root\n\n`{skill_root}`\n\nUse command tools for reads, inspection, and execution under this root."
        ]

        # Resource files section
        if not resource_files:
            parts.append("## Skill Resource Files\n\nNone.")
        else:
            lines = [f"- `{p}`" for p in resource_files]
            if truncated:
                lines.append(f"- ... truncated after {_MAX_SKILL_RESOURCE_FILES} files")
            parts.append("## Skill Resource Files\n\nPaths are relative to `Skill Resource Root`:\n\n" + "\n".join(lines))

        if body:
            parts.append(body)

        import json
        return json.dumps({
            "status": ToolResultStatusSchema.SUCCESS,
            "output": "\n\n".join(parts),
        }, ensure_ascii=False)
    except Exception as exc:
        import json
        return json.dumps({
            "status": ToolResultStatusSchema.ERROR,
            "output": str(exc) or "Skill loading failed.",
        }, ensure_ascii=False)


# ── exported tool list for specs ──────────────────────────────────────────

LOCAL_SHELL_TOOLS = (
    execute_command,
    read_command_output,
    run_background_command,
    cancel_background_command,
    list_skills,
    load_skill,
)
