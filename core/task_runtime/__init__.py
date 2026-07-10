"""Interrupt-driven task execution runtime for agent turns."""

from core.task_runtime.executor import run_until_idle
from core.task_runtime.interrupt import InterruptSignal, iter_interruptible_events
from core.task_runtime.trigger import TurnTrigger, replace as replace_trigger

__all__ = [
    "InterruptSignal",
    "TurnTrigger",
    "iter_interruptible_events",
    "replace_trigger",
    "run_until_idle",
]
