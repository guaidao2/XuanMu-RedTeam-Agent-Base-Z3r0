"""Command output capture and read protocol for sandbox tools."""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from uuid import uuid4

from schema.sandbox.async_jobs import SandboxAsyncJobSnapshot, SandboxAsyncJobStatus
from schema.sandbox.command_outputs import (
    SandboxCommandOutputChunk,
    SandboxCommandResultMetadata,
)


OUTPUT_CHUNK_LINE_COUNT = 200
OUTPUT_DIR = "/tmp/shell-command-output"
COMMAND_TIMEOUT_ERROR = "Command execution timed out."
_OUTPUT_PREFIX = f"{OUTPUT_DIR}/"
_META_PREFIX = "__sandbox_command_meta__"
_OUTPUT_FILE_RE = re.compile(
    r"^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.log$",
    re.IGNORECASE,
)


def new_output_path() -> str:
    return output_path_for_run(new_run_id())


def new_run_id() -> str:
    return uuid4().hex


def output_path_for_run(run_id: str) -> str:
    return f"{OUTPUT_DIR}/{run_id}.log"


def result_metadata(
    *,
    status: SandboxAsyncJobStatus,
    output_file: str | None = None,
    output_bytes: int = 0,
    output_lines: int = 0,
    exit_code: int | None = None,
    run_id: str | None = None,
    error: str | None = None,
) -> SandboxCommandResultMetadata:
    return SandboxCommandResultMetadata(
        status=status,
        exit_code=exit_code,
        output_file=validate_output_path(output_file) if output_file else None,
        output_bytes=max(output_bytes, 0),
        output_lines=max(output_lines, 0),
        run_id=run_id,
        error=error or None,
    )


def result_metadata_from_snapshot(snapshot: SandboxAsyncJobSnapshot) -> SandboxCommandResultMetadata:
    return result_metadata(
        status=snapshot.status,
        output_file=snapshot.output_file or None,
        output_bytes=snapshot.output_bytes,
        output_lines=snapshot.output_lines,
        exit_code=snapshot.exit_code,
        run_id=snapshot.run_id,
        error=snapshot.error,
    )


def capture_command(command: str, output_path: str) -> str:
    lines = _base_command_script(command, output_path)
    lines.extend(_stat_output_lines('"$output_path"'))
    lines.append(f"printf '{_META_PREFIX} %s %s\\n' \"$output_bytes\" \"$output_lines\"")
    lines.append('exit "$command_exit_code"')
    return "\n".join(lines)


def async_command(command: str, output_path: str) -> str:
    lines = _base_command_script(command, output_path)
    lines.append('exit "$command_exit_code"')
    return "\n".join(lines)


def stat_command(output_path: str) -> str:
    quoted_output_path = shlex.quote(output_path)
    return "; ".join(
        (
            f"test -f {quoted_output_path} || exit 0",
            *_stat_output_lines(quoted_output_path),
            'printf "%s %s\\n" "$output_bytes" "$output_lines"',
        )
    )


def parse_capture_stats(raw: str) -> tuple[int, int]:
    meta_match = re.search(rf"^{re.escape(_META_PREFIX)}\s+(\d+)\s+(\d+)\s*$", raw, re.MULTILINE)
    output_bytes = int(meta_match.group(1)) if meta_match else 0
    output_lines = int(meta_match.group(2)) if meta_match else 0
    return output_bytes, output_lines


def read_command(output_file: str, start_line: int, line_count: int) -> tuple[str, int, int, int]:
    start, count, end = normalize_read_range(start_line, line_count)
    quoted_output_file = shlex.quote(validate_output_path(output_file))
    command = (
        f"test -f {quoted_output_file} "
        f"&& sed -n '{start},{end}p' {quoted_output_file} "
        "|| { printf 'command output file not found\\n' >&2; exit 1; }"
    )
    return command, start, count, end


def output_chunk(*, output_file: str, start_line: int, line_count: int, content: str) -> SandboxCommandOutputChunk:
    start, count, end = normalize_read_range(start_line, line_count)
    return SandboxCommandOutputChunk(
        output_file=validate_output_path(output_file),
        start_line=start,
        end_line=end,
        content=content,
    )


def normalize_read_range(start_line: int, line_count: int) -> tuple[int, int, int]:
    start = max(1, int(start_line))
    count = min(max(1, int(line_count)), OUTPUT_CHUNK_LINE_COUNT)
    end = start + count - 1
    return start, count, end


def validate_output_path(output_file: str) -> str:
    stripped = output_file.strip()
    normalized = str(PurePosixPath(stripped))
    parts = PurePosixPath(normalized).parts
    filename = parts[-1] if parts else ""
    if (
        not normalized.startswith(_OUTPUT_PREFIX)
        or normalized != stripped
        or parts != ("/", "tmp", "shell-command-output", filename)
        or not _OUTPUT_FILE_RE.fullmatch(filename)
    ):
        raise ValueError("output_file must be a command result path returned by sandbox command tools")
    return normalized


def _base_command_script(command: str, output_path: str) -> list[str]:
    quoted_output_dir = shlex.quote(OUTPUT_DIR)
    quoted_output_path = shlex.quote(output_path)
    return [
        "set +e",
        f"output_dir={quoted_output_dir}",
        f"output_path={quoted_output_path}",
        'mkdir -p "$output_dir" || exit 125',
        'rm -f "$output_path"',
        ': > "$output_path" || exit 125',
        f"{_bash_command(command)} > \"$output_path\" 2>&1 &",
        "command_pid=$!",
        'trap \'kill -TERM "$command_pid" 2>/dev/null\' TERM INT HUP',
        'wait "$command_pid"',
        "command_exit_code=$?",
        "trap - TERM INT HUP",
    ]


def _bash_command(command: str) -> str:
    return f"/bin/bash -lc {shlex.quote(command)}"


def _stat_output_lines(quoted_output_path: str) -> tuple[str, ...]:
    return (
        f'output_bytes=$(wc -c < {quoted_output_path} 2>/dev/null | tr -d "[:space:]")',
        f"output_lines=$(sed -n '$=' {quoted_output_path} 2>/dev/null | tr -d '[:space:]')",
        'case "$output_bytes" in ""|*[!0-9]*) output_bytes=0 ;; esac',
        'case "$output_lines" in ""|*[!0-9]*) output_lines=0 ;; esac',
    )
