"""Task-resumption prompts for completed background work.

Converts system-generated ``AgentNotificationSnapshot`` instances into
natural-language prompts consumable by the agent.  User-message
notifications are handled separately by the executor and should never
reach ``notification_prompt``.
"""

from schema.agent.events import MAX_AGENT_TEXT_INPUT_CHARS
from schema.agent.notifications import AgentNotificationKind, AgentNotificationSnapshot


# Sandbox error payloads are short, but cap the inline preview defensively
# so a long stderr never blows up the resumption prompt.
_SANDBOX_ERROR_PREVIEW_CHARS = 1000


def notification_prompt(notification: AgentNotificationSnapshot) -> str:
    """Return a resumption prompt for a *system* notification.

    Raises ``ValueError`` if called with a ``USER_MESSAGE`` notification,
    which must be routed through the executor's content-reconstruction
    path instead.
    """
    if notification.is_user_message:
        raise ValueError(
            f"notification_prompt must not be called for USER_MESSAGE "
            f"notifications (id={notification.id})"
        )
    if notification.kind == AgentNotificationKind.SANDBOX_ASYNC_JOB_FINISHED:
        return _fit_text_input(_sandbox_async_job_prompt(notification))
    return _fit_text_input(_subagent_finished_prompt(notification))


_RESUMPTION_HEADER = (
    "# Task Resumption Context\n\n"
    "This is task context, not a new user request. "
    "Continue from the completed background work without mentioning how this context was delivered."
)


def _subagent_finished_prompt(notification: AgentNotificationSnapshot) -> str:
    # The notification carries metadata only; the body lives in the DB and is
    # paged through read_subagent_task. This keeps the resumption prompt small
    # and prevents overlap with the first slice the agent will fetch.
    payload = notification.payload
    status = str(payload.get("status") or "unknown")
    agent_code = str(payload.get("agent_code") or "")
    agent_name = str(payload.get("agent_name") or agent_code or "subagent")
    run_id = str(payload.get("run_id") or notification.run_id)

    event_lines = [
        "- kind: delegated_task_completed",
        f"- run_id: {run_id}",
        f"- agent_code: {agent_code or 'unknown'}",
        f"- subagent: {agent_name}",
        f"- status: {status}",
    ]

    sections = [
        _RESUMPTION_HEADER,
        "## Event\n\n" + "\n".join(event_lines),
        "## Next Step\n\n"
        "Call `read_subagent_task(run_id, offset=0)` and repeat with `offset=next_offset` "
        "until the response omits `next_offset` to read the full result/error. "
        "Report to the user only when there is a useful conclusion, coordination update, or next action.",
    ]
    return "\n\n".join(sections)


def _sandbox_async_job_prompt(notification: AgentNotificationSnapshot) -> str:
    payload = notification.payload
    status = str(payload.get("status") or "unknown")
    run_id = notification.run_id
    output_file = str(payload.get("output_file") or "")
    output_lines = int(payload.get("output_lines") or 0)
    output_bytes = int(payload.get("output_bytes") or 0)
    exit_code = payload.get("exit_code")
    # Sandbox errors are short free-form strings without a paginated reader,
    # so inlining a capped preview is the only way to expose them here.
    error_preview = _truncate_inline(payload.get("error"), _SANDBOX_ERROR_PREVIEW_CHARS)

    event_lines = [
        "- kind: async_command_completed",
        f"- run_id: {run_id}",
        f"- status: {status}",
    ]
    if exit_code is not None:
        event_lines.append(f"- exit_code: {exit_code}")
    if output_file:
        event_lines.append(f"- output_file: {output_file}")
        event_lines.append(f"- output_lines: {output_lines}")
        event_lines.append(f"- output_bytes: {output_bytes}")
    sections = [
        _RESUMPTION_HEADER,
        "## Event\n\n" + "\n".join(event_lines),
    ]
    if error_preview:
        sections.append(f"## Error Preview\n\n{error_preview}")

    sections.append(
        "## Next Step\n\n"
        "The async command has reached a terminal state. "
        "If `output_lines` is greater than 0 and the result matters, read the output with "
        "`read_sandbox_command_output` using `output_file` and `start_line: 1`. "
        "Then continue the task or report the final result.",
    )
    return "\n\n".join(sections)


def _truncate_inline(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _truncate_with_marker(text, limit, "[Preview truncated.]")


def _fit_text_input(text: str) -> str:
    return _truncate_with_marker(
        text.strip() or "Task context is available.",
        MAX_AGENT_TEXT_INPUT_CHARS,
        "[Task resumption context truncated to fit input limits.]",
    )


def _truncate_with_marker(text: str, limit: int, marker: str) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n" + marker
    body_limit = max(1, limit - len(suffix))
    return text[:body_limit].rstrip() + suffix
