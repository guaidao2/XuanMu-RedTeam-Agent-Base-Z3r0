---
name: sandbox-shell
description: Use when a task requires shell-level work inside the sandbox, including environment setup, script writing, code execution, running programs, downloads, package installs, scanning, or browser/tool CLIs.
---

# Sandbox Shell

Use sandbox command tools for authorized task work inside the selected sandbox container.

## Tool Contract

Command tools return compact JSON metadata; raw output is captured to `output_file`:

- `execute_sync_command` returns `status`, `output_file`, `output_bytes`, `output_lines`, and optional `exit_code`.
- `execute_async_command` returns only `status` and `run_id`; its terminal `status`, `exit_code`, and `output_file` are delivered later when the runtime resumes you.
- Status values: `running`, `completed`, `failed`, `canceled`.
- Read output with `read_sandbox_command_output` using `output_file` and `start_line: 1`, at most 200 lines per call. Do not use `cat`.

## Choosing Execution

Use `execute_sync_command` for short, local, bounded commands expected to finish within 30 seconds:

- file inspection, small scripts, local parsing, `which`, `test`, `sed -n`, `head`, `tail`, `wc`, bounded `grep`
- one sync command per assistant response unless the previous result requires an immediate bounded read

Use `execute_async_command` for anything slow, remote, stateful, or externally dependent:

- HTTP requests, downloads, scans, probes, brute-force checks, browser automation, package installs, builds, servers, watchers, REPLs
- loops around network, browser, install, build, scan, or other external resources
- consolidated scripts that run several slow checks and write structured output

Always pass timing arguments explicitly via `timeout_seconds`.

## Async Jobs

Dispatching `execute_async_command` ends the current turn immediately.

- After dispatching, do not continue working, run follow-up steps, or take any further action — your turn is over.
- The runtime resumes you automatically when the job finishes, delivering its `status`, `exit_code`, and `output_file` as fresh context.
- Never poll, read, or check a running job, and never use `sleep`, shell wait loops, or filler progress messages — there is nothing to do but wait to be resumed.
- Use `cancel_sandbox_async_job` only when cancellation is requested or the job is no longer useful.

## Output Handling

- When metadata has terminal `status` and `output_lines > 0`, read needed chunks with `read_sandbox_command_output`.
- Continue with the next `start_line` only when the next chunk is needed.
- Do not re-run a command just to inspect an existing `output_file`.
- Use a new bounded command only when file-side filtering/counting is more efficient than reading chunks.
- Keep generated files and installed packages scoped to the task.

## Python Packages

- Prefer `uv` for Python environments, package installs, and temporary tool execution.
- Use `uv run`, `uvx`, or `uv pip` inside a task-scoped virtual environment.
- Do not use global `pip install` or assume `pip3` is available in the sandbox.

## Available Tools

- Archives: `7z`, `unzip`
- Shell/runtime: `python3`, `uv`, `node`, `npm`, `nc`, `jq`, `rg`, `git`
- Network: `curl`, `wget`, `dig`, `nslookup`, `whois`, `openssl`, `httpx`, `nmap`, `sqlmap`
- Fingerprinting: `observer_ward`
- Android/reversing: `jadx`, `apktool`, `analyzeHeadless`
- File/firmware: `file`, `binwalk`
- Browser: `agent-browser-cli`

## Skill Resource Paths

Use `.agents/skills/<skill-name>/...` paths in sandbox commands for skill-shipped files:

- Ghidra wrapper: `.agents/skills/ghidra/scripts/ghidra-analyze.sh`

Report only meaningful results: changed files, commands run, relevant output, and failures that affect completion.
