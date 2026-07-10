"""In-memory signal primitives for low-latency agent turn preemption.

Notification consumption is handled by ``core.task_runtime.executor`` and
driver resumption by ``resume_target_instance``. This module provides only the
signal/wait/version mechanism that lets ``iter_interruptible_events`` preempt an
in-flight turn promptly when a higher-priority notification (e.g. a new user
message) becomes pending, instead of waiting for its poll interval.
"""

from __future__ import annotations

import asyncio

from core.runtime.context import MAIN_AGENT_INSTANCE_PREFIX


_target_signal_lock = asyncio.Lock()
_target_signals: dict[str, asyncio.Event] = {}
_target_signal_versions: dict[str, int] = {}


def is_main_agent_instance(agent_instance_id: str) -> bool:
    return agent_instance_id.startswith(MAIN_AGENT_INSTANCE_PREFIX)


async def signal_target_notifications(target_agent_instance_id: str) -> None:
    """Bump the version counter and wake any waiter for *target_agent_instance_id*."""
    async with _target_signal_lock:
        _target_signal_versions[target_agent_instance_id] = _target_signal_versions.get(target_agent_instance_id, 0) + 1
        signal = _target_signals.get(target_agent_instance_id)
        if signal is not None:
            signal.set()


async def target_notification_version(target_agent_instance_id: str) -> int:
    """Return the current signal version for *target_agent_instance_id*."""
    async with _target_signal_lock:
        return _target_signal_versions.get(target_agent_instance_id, 0)


async def wait_for_target_notifications(
    target_agent_instance_id: str,
    *,
    after_version: int | None = None,
    timeout_seconds: float | None = None,
) -> bool:
    """Block until the signal version changes or *timeout_seconds* elapses.

    Returns ``True`` if a new version was observed, ``False`` on timeout.
    """
    async with _target_signal_lock:
        version = _target_signal_versions.get(target_agent_instance_id, 0) if after_version is None else after_version
        signal = _target_signals.setdefault(target_agent_instance_id, asyncio.Event())

    while True:
        async with _target_signal_lock:
            if _target_signal_versions.get(target_agent_instance_id, 0) != version:
                return True
            signal = _target_signals[target_agent_instance_id]
            signal.clear()
        try:
            await asyncio.wait_for(signal.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return False


async def forget_target_notifications(target_agent_instance_id: str) -> None:
    """Remove all in-memory signal state for *target_agent_instance_id*."""
    async with _target_signal_lock:
        _target_signals.pop(target_agent_instance_id, None)
        _target_signal_versions.pop(target_agent_instance_id, None)
