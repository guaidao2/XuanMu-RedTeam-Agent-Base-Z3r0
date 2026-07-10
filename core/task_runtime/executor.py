"""Unified, non-blocking drain loop for main and sub-agent turn execution.

Lifecycle: optional initial turn -> drain every ready notification -> return.
It never waits on background work; later turns arrive via a fresh driver launch
(``resume_target_instance``). Per-turn execution is delegated to the caller's
``run_turn`` callback, keeping the executor agent-agnostic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from core.delegation.notifications import notification_prompt
from core.runtime.input_items import text_input_content
from core.task_runtime.interrupt import InterruptSignal
from core.task_runtime.trigger import TurnTrigger
from logger import get_logger
from schema.agent.events import AgentImageInputPart, AgentInputPart, AgentTextInputPart
from schema.agent.notifications import AgentNotificationSnapshot
from service.agent import notifications as agent_notifications

logger = get_logger(__name__)

RunTurnFn = Callable[[TurnTrigger], Awaitable[Any]]


def _content_for_notification(notification: AgentNotificationSnapshot) -> list[AgentInputPart]:
    # User messages reconstitute their original parts; system notifications wrap
    # the resumption prompt as text input.
    if notification.is_user_message:
        parts: list[AgentInputPart] = []
        for raw in notification.user_content or []:
            part_type = raw.get("type", "")
            if part_type == "text":
                text = (raw.get("text") or "").strip()
                if text:
                    parts.append(AgentTextInputPart(text=text))
            elif part_type == "image":
                media_type = raw.get("media_type")
                data = raw.get("data")
                if media_type and data:
                    parts.append(AgentImageInputPart(
                        media_type=media_type,
                        data=data,
                        detail=raw.get("detail", "auto"),
                    ))
        return parts or text_input_content(notification.user_display_text or "…")

    return text_input_content(notification_prompt(notification))


def _trigger_for_notification(notification: AgentNotificationSnapshot) -> TurnTrigger:
    return TurnTrigger(
        content=_content_for_notification(notification),
        notification=notification,
    )


async def run_until_idle(
    *,
    session_id: str,
    agent_instance_id: str,
    initial_content: list[AgentInputPart] | None = None,
    run_turn: RunTurnFn,
) -> Any:
    # Non-blocking: run the optional initial turn, drain every claimable PENDING
    # notification for this instance, then return without waiting on background
    # work. ``initial_content`` is None for resume/recovery; ``run_turn`` must let
    # InterruptSignal propagate. Returns the last completed turn's result or None.
    result: Any = None

    if initial_content is not None:
        try:
            result = await run_turn(TurnTrigger(content=initial_content))
        except InterruptSignal:
            pass

    while True:
        notification = await agent_notifications.claim_next_pending_notification(
            session_id=session_id,
            target_agent_instance_id=agent_instance_id,
        )
        if notification is None:
            return result

        try:
            trigger = _trigger_for_notification(notification)
            result = await run_turn(trigger)
            await agent_notifications.complete_notification(notification.id)
        except InterruptSignal:
            await agent_notifications.complete_notification(notification.id)
        except asyncio.CancelledError:
            await agent_notifications.release_notification(notification.id)
            raise
        except Exception as exc:
            # Fail just this notification and keep draining: re-raising would
            # strand sibling PENDING notifications and leave the session stuck
            # "running" with no task to interrupt.
            logger.exception(
                "notification turn failed session=%s notification=%s",
                session_id,
                notification.id,
            )
            await agent_notifications.fail_notification(
                notification.id,
                str(exc) or "notification handling failed",
            )
            continue
