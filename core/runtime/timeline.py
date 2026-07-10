"""Timeline identity + durable writer for the per-session UI event log.

Every wire event that belongs on the rendered transcript is addressed by a
stable ``item_key`` so streaming updates upsert in place and the client can
merge history with live frames idempotently. Deltas and control frames carry a
``seq`` for ordering but are never persisted (the in-memory live projection
covers the in-flight tail; completed segments are what reach the log).
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from logger import get_logger
from schema.agent.events import AgentEventSchema


logger = get_logger(__name__)

# event types that never enter the persisted timeline
_CONTROL_TYPES = frozenset({"run_state", "done"})
_DELTA_TYPES = frozenset({"text_delta", "thinking_delta"})


def timeline_item_key(event: AgentEventSchema) -> str | None:
    """Stable identity for events that carry their own id; None for keyless ones."""
    event_type = str(event.type)
    nested_call_id = getattr(event, "nested_call_id", "")
    if event_type in ("text_delta", "text_complete"):
        return f"text:{nested_call_id}:{event.segment_id}"
    if event_type in ("thinking_delta", "thinking_complete"):
        return f"thinking:{nested_call_id}:{event.segment_id}"
    if event_type == "tool_call":
        return f"tc:{nested_call_id}:{event.call_id}"
    if event_type == "tool_result":
        return f"tr:{nested_call_id}:{event.call_id}"
    if event_type == "subagent_task":
        return f"sa:{event.run_id}"
    return None


def is_persistable(event: AgentEventSchema) -> bool:
    event_type = str(event.type)
    return event_type not in _CONTROL_TYPES and event_type not in _DELTA_TYPES


def carries_seq(event: AgentEventSchema) -> bool:
    return str(event.type) not in _CONTROL_TYPES


@dataclass(frozen=True, slots=True)
class _TimelineRow:
    item_key: str
    seq: int
    payload: str
    created_at: datetime


_FlushBarrier: TypeAlias = asyncio.Future[None]
_TimelineQueueItem: TypeAlias = _TimelineRow | _FlushBarrier | None


class TimelineLogWriter:
    """Single-consumer async writer that batches timeline upserts for a session."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._queue: asyncio.Queue[_TimelineQueueItem] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._control_lock = asyncio.Lock()
        self._stopping = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._run(), name=f"timeline-writer-{self._session_id}")

    def enqueue(self, item_key: str, seq: int, payload: str, created_at: datetime) -> bool:
        if self._stopping:
            return False
        self._queue.put_nowait(_TimelineRow(item_key, seq, payload, created_at))
        return True

    async def flush(self) -> None:
        async with self._control_lock:
            task = self._task
            if self._stopping and task is not None and not task.done():
                wait_for_stop = task
                barrier = None
            elif task is None or task.done():
                wait_for_stop = None
                barrier = None
            else:
                wait_for_stop = None
                loop = asyncio.get_running_loop()
                barrier = loop.create_future()
                self._queue.put_nowait(barrier)

        if wait_for_stop is not None:
            await wait_for_stop
            return
        if barrier is not None:
            await barrier
            return

        async with self._control_lock:
            rows, barriers = self._drain_remaining()
        await self._flush(rows)
        self._resolve_barriers(barriers)

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            if await self._process_batch(first):
                return

    async def _process_batch(self, first: _TimelineQueueItem) -> bool:
        rows: list[_TimelineRow] = []
        stop = await self._process_item(first, rows)
        if stop:
            return True
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                await self._flush(rows)
                return False
            stop = await self._process_item(item, rows)
            if stop:
                return True

    async def _process_item(self, item: _TimelineQueueItem, rows: list[_TimelineRow]) -> bool:
        if isinstance(item, _TimelineRow):
            rows.append(item)
            return False
        if isinstance(item, asyncio.Future):
            await self._flush(rows)
            rows.clear()
            if not item.done():
                item.set_result(None)
            return False
        await self._flush(rows)
        drained_rows, barriers = self._drain_remaining()
        await self._flush(drained_rows)
        self._resolve_barriers(barriers)
        return True

    def _drain_remaining(self) -> tuple[list[_TimelineRow], list[_FlushBarrier]]:
        rows: list[_TimelineRow] = []
        barriers: list[_FlushBarrier] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(item, _TimelineRow):
                rows.append(item)
            elif isinstance(item, asyncio.Future):
                barriers.append(item)
        return rows, barriers

    @staticmethod
    def _resolve_barriers(barriers: list[_FlushBarrier]) -> None:
        for barrier in barriers:
            if not barrier.done():
                barrier.set_result(None)

    async def _flush(self, batch: list[_TimelineRow]) -> None:
        from service.agent.event_log import upsert_timeline_events

        if not batch:
            return
        # collapse repeated keys within the window, keeping the latest payload
        collapsed: dict[str, _TimelineRow] = {}
        for row in batch:
            collapsed[row.item_key] = row
        try:
            await upsert_timeline_events(
                self._session_id,
                [(row.item_key, row.seq, row.payload, row.created_at) for row in collapsed.values()],
            )
        except Exception:
            logger.exception("timeline writer upsert failed session=%s", self._session_id)

    async def stop(self) -> None:
        async with self._control_lock:
            self._stopping = True
            task = self._task
            if task is not None and not task.done():
                self._queue.put_nowait(None)

        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._control_lock:
            if self._task is task:
                self._task = None
            rows, barriers = self._drain_remaining()
        # final drain so the last completed segments are not lost on eviction
        await self._flush(rows)
        self._resolve_barriers(barriers)
