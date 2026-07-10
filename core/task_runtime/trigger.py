"""Turn trigger: the single object describing what initiated an agent turn."""

from __future__ import annotations

from dataclasses import dataclass, replace as _replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schema.agent.events import AgentInputPart
    from schema.agent.notifications import AgentNotificationSnapshot


@dataclass(frozen=True, slots=True)
class TurnTrigger:
    """Immutable descriptor for one agent turn.

    Encapsulates the input content, the optional notification that caused
    the turn, and whether a ``UserMessageEvent`` should be published.
    Created by the executor loop and optionally augmented by session-layer
    callbacks before being passed to ``_execute_turn``.

    Use ``replace()`` to derive a modified copy (the dataclass is frozen).
    """

    content: list[AgentInputPart]
    """Input parts to feed the agent SDK."""

    notification: AgentNotificationSnapshot | None = None
    """The notification that produced this turn, or ``None`` for an
    initial user-input turn."""

    emit_user_event: bool = False
    """Whether ``_execute_turn`` should publish a ``UserMessageEvent``
    to the WebSocket subscriber stream."""

    @property
    def has_notification(self) -> bool:
        return self.notification is not None

    @property
    def notification_id(self) -> str:
        """Shorthand for lifecycle management (complete / release / fail)."""
        return self.notification.id if self.notification is not None else ""


def replace(trigger: TurnTrigger, **changes: object) -> TurnTrigger:
    """Derive a new ``TurnTrigger`` with selected fields replaced.

    Thin wrapper around ``dataclasses.replace`` exported for convenience
    so callers don't need a separate import.
    """
    return _replace(trigger, **changes)
