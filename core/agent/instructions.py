from core.tools.knowledge import load_knowledge_metadata


MARKDOWN_OUTPUT_INSTRUCTIONS = """## Response Formatting

Always write user-facing responses as valid GitHub-Flavored Markdown.

- Put block elements on their own lines: headings, lists, blockquotes, tables, horizontal rules, and fenced code blocks must not be appended to the end of a paragraph.
- Insert a blank line before and after headings, lists, blockquotes, tables, horizontal rules, and fenced code blocks unless the element is at the start or end of the response.
- Use ATX headings with a space after the marker, for example `## Findings`; never write `##Findings`.
- Use fenced code blocks with a language tag when practical, and close every fence.
- Do not concatenate prose directly with Markdown control markers such as `#`, `-`, `>`, `|`, or ```.
"""

DIAGRAM_INSTRUCTIONS = """## Diagram Policy

- Use Mermaid, and only Mermaid, for user-facing diagrams such as structures, flows, sequences, dependencies, state transitions, call chains, hierarchies, timelines, and data flow.
- Never draw diagrams with ASCII or Unicode line art, including manually aligned boxes, trees, connector grids, arrows, or repeated punctuation.
- If a diagram is useful but Mermaid is not appropriate, use prose, a Markdown list, or a real Markdown table instead; never fall back to ASCII art.
- Source code, terminal output, file paths, and protocol examples may contain ASCII characters only when quoted as literal evidence, not as invented diagrams.
"""


SANDBOX_COMMAND_INSTRUCTIONS = """## Sandbox Command Execution

- Use `execute_sync_command` for short commands expected to finish within 30 seconds. It returns metadata with `status`, `output_file`, `output_bytes`, `output_lines`, and optional `exit_code`. Raw output is captured to `output_file`.
- Use `execute_async_command` for long-running commands. Dispatching it ends the current turn immediately: it returns only `status` and `run_id`, then control returns to the runtime. After dispatching, do not continue working, run follow-up steps, or take any further action; your turn is over.
- The runtime resumes you automatically when the command finishes, delivering its terminal `status`, `exit_code`, and `output_file` as fresh context. Never poll, list, or read a running job; there is nothing to check and no waiting loop to run.
- On that resumption, if `output_lines > 0` and the result matters, read it with `read_sandbox_command_output` using the delivered `output_file` and `start_line: 1`, at most 200 lines per call.
- Do not use `cat` on command output files; always use `read_sandbox_command_output`.
"""


KNOWLEDGE_TOOL_INSTRUCTIONS = """## Knowledge Tools

- Use knowledge tools only for reusable professional methodology that should benefit future work by the same agent.
- Do not store conversation logs, raw tool output, project records, secrets, credentials, user preferences, or one-off task details as knowledge.
- The Knowledge Index contains metadata only. Use `find_knowledge` to locate relevant entries and `load_knowledge` with line ranges before relying on details.
"""


DELEGATION_TOOL_INSTRUCTIONS = """## Delegation Tools

- When starting a subagent, make the brief self-contained: objective, scope, language, relevant prior results, expected output, and any WorkProject task context.
- After `start_subagent_task` returns a started task, end the turn silently. Do not produce status text, call other tools, or read task state.
- The runtime resumes the owning agent when the subagent finishes. Use `read_subagent_task`, `list_subagent_tasks`, or `cancel_subagent_task` only when the user asks for progress, history, or cancellation.
"""


WORK_PROJECT_INSTRUCTIONS = """## WorkProject

Project state is live shared memory for users and future agents. Keep it current. Summaries are checkpoints, not final reports or durable security records.

- Read only needed state: structured Asset records before scope work; tasks/summaries before planning, resuming, delegation, handoff, or reporting. Asset records are authoritative scope; do not invent targets.
- The durable model has two first-class records, Asset and Finding, plus a relationship graph built on them:
  - Asset records are the graph nodes. `type` is one of `service`, `domain`, `network`, or `binary`; `service`/`domain`/`network` use the `host` field (port optional for `service`, identifying a specific host endpoint), `binary` uses `path`. Each asset is keyed by a normalized `(type, identifier)` identity. `origin` (`scope` for declared targets, `discovered` for newly found ones) is system-managed. Store only a short recon `banner` in the small `extra` object; never dump large output there.
  - Finding records are weaknesses or proven issues. Set `asset_id` to the affected asset. When a finding substantiates a relationship or an attack step, set `edge_id` to the graph edge it backs. The finding's `description` and `impact` carry the proof; mark `status` `validated` only once it is actually confirmed.
  - Graph edges are directed relationships between two assets (`source_asset_id` -> `target_asset_id`). The `type` is either structural (`related`, `resolves_to`, `hosts`, `connects_to`, `trusts`) describing the target architecture, or offensive (`exploits`, `pivots_to`, `leads_to`) describing attack progression. Findings attached to an edge are its supporting proof.
  - Attack paths are ordered chains; each step traverses one relationship edge, in `sequence` order, to explain how access or impact progressed.
- Keep record content concise and reviewable. Do not copy large raw command output into records; reference output files, events, async runs, tool calls, or artifacts in the finding text instead.
- Do not assert graph edges or attack paths as fact until the relationship is known; keep uncertain paths `suspected` and update status when confirmation changes.
- Use `delete_work_project_record` only to remove records created in error or superseded noise; deleting an asset removes the edges touching it and detaches its findings, and deleting an edge removes the steps that traverse it.
- After any material event, update your summary before the next investigation or action tool call when practical. Material events include confirmed findings, useful negative results, blockers, failed attempts worth preserving, decisions, scope changes, handoffs, progress changes, and completion.
- Use `update_work_project_agent_summary` for your own live state only. Replace stale content with concise current fields: `task_id`, `task_title`, `progress`, `status`, `findings`, `decisions`, `blockers`, `next_steps`, `notes`.
- If nothing material changed, do not rewrite the summary. If material state changed and your next step is another command, delegated task, handoff, or user reply, checkpoint first.
- Summary `progress` is your subtask progress, `0..100` with at most two decimals. Match an existing `task_id` when possible; otherwise use the closest `task_title`.
- If `update_work_project_tasks` is available, you own the shared task list only: create/replan tasks, set active work `in_progress`, blockers `blocked`, completed work `done`, and update per-task progress after your work or subagent results change task state. After subagent results, update tasks before reporting or delegating more work.
- If `update_work_project_tasks` is unavailable, do not edit shared tasks; maintain task status/progress through your own summary so `cso` can aggregate it.
- Task status values: `todo`, `in_progress`, `blocked`, `done`. Overall project progress is read-only for agents: query it with `load_work_project_tasks`; it is code-calculated from task progress and must never be estimated or written by an agent.
"""


def build_instructions(
    soul: str,
    rules: str,
    agent_code: str,
    sandbox_skill_metadata: tuple[str, ...],
    *,
    has_sandbox_container: bool,
    include_sandbox_commands: bool,
    include_sandbox_skills: bool,
    include_agent_knowledges: bool,
    include_work_project_tools: bool,
    include_delegation_tools: bool,
) -> str:
    runtime_guidance = [MARKDOWN_OUTPUT_INSTRUCTIONS, DIAGRAM_INSTRUCTIONS]
    if include_agent_knowledges:
        runtime_guidance.append(KNOWLEDGE_TOOL_INSTRUCTIONS)
    if include_delegation_tools:
        runtime_guidance.append(DELEGATION_TOOL_INSTRUCTIONS)
    if include_sandbox_commands and has_sandbox_container:
        runtime_guidance.append(SANDBOX_COMMAND_INSTRUCTIONS)
    if include_work_project_tools:
        runtime_guidance.append(WORK_PROJECT_INSTRUCTIONS)
    parts = [
        soul,
        rules,
        "# Runtime Guidance\n\n" + "\n\n".join(part.strip() for part in runtime_guidance if part.strip()),
    ]
    if include_agent_knowledges:
        parts.append(_build_agent_knowledge_instructions(load_knowledge_metadata(agent_code)))
    if include_sandbox_skills and has_sandbox_container:
        parts.append(_build_sandbox_skill_instructions(sandbox_skill_metadata))
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _build_agent_knowledge_instructions(knowledge_metadata: tuple[str, ...]) -> str:
    if not knowledge_metadata:
        return (
            "# Knowledge Index\n\n"
            "## Available Items\n\n"
            "None."
        )

    return (
        "# Knowledge Index\n\n"
        "## Available Items\n\n"
        + "\n\n".join(knowledge_metadata)
    )


def _build_sandbox_skill_instructions(skill_metadata: tuple[str, ...]) -> str:
    if not skill_metadata:
        return (
            "# Sandbox Skill Index\n\n"
            "## Available Items\n\n"
            "None."
        )

    usage = (
        "## Usage\n\n"
        "Use matching sandbox skills to complete tasks. This index contains metadata only; "
        "load the full skill body before applying any skill.\n\n"
        "- Before executing any command, first call `load_skill` for `sandbox-shell` if it is listed.\n"
        "- Do not run skill workflows from metadata alone; the loaded skill body is authoritative.\n"
        "- After loading a skill, follow its workflow and constraints exactly.\n"
        "- Loaded skills include a `Skill Resource Root` and `Skill Resource Files`; "
        "use sandbox command tools for any resource file reads, inspection, or execution.\n"
    )
    return (
        "# Sandbox Skill Index\n\n"
        + usage
        + "\n## Available Items\n\n"
        + "\n\n".join(skill_metadata)
    )
