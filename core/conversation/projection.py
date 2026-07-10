"""Viewer-specific projection of stored SDK items into model context."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from agents.items import TResponseInputItem

from core import extract_message_text, is_internal_user_text as _is_internal_user_text_check, tool_call_id as _tool_call_id


_OWNER_PRIVATE_TYPES = frozenset({"reasoning", "function_call", "function_call_output"})
_FOREIGN_PREFIX = "[other agent: {name}]\n"


@dataclass(frozen=True, slots=True)
class ProjectionCompaction:
    id: int
    start_message_id: int
    end_message_id: int
    summary_item: TResponseInputItem


@dataclass(frozen=True, slots=True)
class ProjectedItem:
    item: TResponseInputItem
    source_message_ids: tuple[int, ...] = ()
    token_estimate: int = 0
    atomic_group: str = ""


@dataclass(frozen=True, slots=True)
class ContextProjection:
    projected_items: list[ProjectedItem]

    @property
    def items(self) -> list[TResponseInputItem]:
        return [projected.item for projected in self.projected_items]


class StoredContextItem(Protocol):
    message_id: int
    owner_code: str
    item: dict[str, Any]
    nested_for: str
    nested_call_id: str


def project_context(
    stored_items: Iterable[StoredContextItem],
    *,
    viewing_agent_code: str,
    agent_code_to_name: dict[str, str],
    nested_for: str = "",
    nested_call_id: str = "",
    compaction: ProjectionCompaction | None = None,
) -> ContextProjection:
    visible_stored = _filter_compacted(list(stored_items), compaction.end_message_id if compaction else None)
    projected = list(_project_visible(
        visible_stored,
        viewing_agent_code=viewing_agent_code,
        agent_code_to_name=agent_code_to_name,
        nested_for=nested_for,
        nested_call_id=nested_call_id,
    ))
    if compaction is not None:
        projected.insert(0, ProjectedItem(
            item=compaction.summary_item,
            source_message_ids=(compaction.start_message_id, compaction.end_message_id),
        ))
    return ContextProjection(projected_items=projected)


def _project_visible(
    stored_items: Iterable[StoredContextItem],
    *,
    viewing_agent_code: str,
    agent_code_to_name: dict[str, str],
    nested_for: str,
    nested_call_id: str,
) -> Iterable[ProjectedItem]:
    pending_owner: str = ""
    pending_texts: list[str] = []
    pending_ids: list[int] = []
    owner_tool_groups: dict[tuple[str, str], str] = {}

    if nested_for:
        for stored in stored_items:
            if (
                stored.owner_code == viewing_agent_code
                and stored.nested_for == nested_for
                and stored.nested_call_id == nested_call_id
            ):
                yield _projected(stored.item, (stored.message_id,), _tool_group(stored, owner_tool_groups))
        return

    def flush() -> ProjectedItem | None:
        nonlocal pending_owner, pending_texts, pending_ids
        if not pending_texts:
            return None
        source_ids = tuple(pending_ids)
        merged = _build_foreign_block(
            source_code=pending_owner,
            source_name=agent_code_to_name.get(pending_owner, pending_owner),
            message_ids=pending_ids,
            texts=pending_texts,
        )
        pending_owner = ""
        pending_texts = []
        pending_ids = []
        return _projected(merged, source_ids)

    for stored in stored_items:
        owner, item = stored.owner_code, stored.item
        role = item.get("role")
        item_type = item.get("type")

        # Nested subagent items are scoped to their parent tool call and are replayed in the UI.
        # Parent model context receives only the subagent task result, not the full nested trace.
        if stored.nested_for:
            continue

        if role == "user":
            if _is_internal_user_message(item) and owner != viewing_agent_code:
                continue
            if (m := flush()) is not None:
                yield m
            yield _projected(item, (stored.message_id,), _tool_group(stored, owner_tool_groups))
            continue

        if owner == viewing_agent_code:
            if (m := flush()) is not None:
                yield m
            yield _projected(item, (stored.message_id,), _tool_group(stored, owner_tool_groups))
            continue

        if item_type in _OWNER_PRIVATE_TYPES:
            continue
        if role != "assistant" or item_type != "message":
            continue
        text = extract_message_text(item.get("content"))
        if not text:
            continue
        if pending_owner and pending_owner != owner:
            if (m := flush()) is not None:
                yield m
        pending_owner = owner
        pending_ids.append(stored.message_id)
        pending_texts.append(text)

    if (m := flush()) is not None:
        yield m


def _filter_compacted(stored_items: list[StoredContextItem], end_message_id: int | None) -> list[StoredContextItem]:
    if end_message_id is None:
        return stored_items
    return [stored for stored in stored_items if stored.message_id > end_message_id]


def _projected(
    item: TResponseInputItem,
    source_message_ids: tuple[int, ...],
    atomic_group: str = "",
) -> ProjectedItem:
    return ProjectedItem(item=item, source_message_ids=source_message_ids, atomic_group=atomic_group)


def _tool_group(stored: StoredContextItem, owner_tool_groups: dict[tuple[str, str], str]) -> str:
    item_type = stored.item.get("type")
    if item_type not in {"function_call", "function_call_output"}:
        return ""
    call_id = _tool_call_id(stored.item)
    if not call_id:
        return ""
    key = (stored.owner_code, call_id)
    group = owner_tool_groups.get(key)
    if group is None:
        group = f"tool:{stored.owner_code}:{call_id}"
        owner_tool_groups[key] = group
    return group


def _build_foreign_block(*, source_code: str, source_name: str, message_ids: list[int], texts: list[str]) -> dict[str, Any]:
    body = "\n\n".join(texts)
    first_id = message_ids[0] if message_ids else ""
    last_id = message_ids[-1] if message_ids else ""
    return {
        "id": f"foreign_{source_code}_{first_id}_{last_id}",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "output_text",
            "text": _FOREIGN_PREFIX.format(name=source_name) + body,
            "annotations": [],
        }],
        "status": "completed",
    }


def _is_internal_user_message(item: dict[str, Any]) -> bool:
    return _is_internal_user_text_check(extract_message_text(item.get("content")))
