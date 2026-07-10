"""Provider-boundary normalization for Agents SDK model input items."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents import TResponseInputItem

from core import extract_message_text as _extract_message_text, tool_call_id as _tool_call_id


class ModelInputAdapter:
    """Normalize SDK history into provider-safe item order."""

    def adapt(self, input: str | list[TResponseInputItem]) -> str | list[TResponseInputItem]:
        if isinstance(input, str):
            return input
        return ToolTransactionNormalizer(input).normalize()


@dataclass(slots=True)
class _ToolTransaction:
    calls: list[TResponseInputItem] = field(default_factory=list)
    call_ids: list[str] = field(default_factory=list)
    outputs_by_call_id: dict[str, TResponseInputItem] = field(default_factory=dict)
    deferred_items: list[TResponseInputItem] = field(default_factory=list)

    def add_call(self, item: TResponseInputItem, call_id: str) -> bool:
        if not call_id or call_id in self.outputs_by_call_id or call_id in self.call_ids:
            return False
        self.calls.append(item)
        self.call_ids.append(call_id)
        return True

    def add_output(self, item: TResponseInputItem, call_id: str) -> bool:
        if call_id not in self.call_ids or call_id in self.outputs_by_call_id:
            return False
        self.outputs_by_call_id[call_id] = item
        return True

    @property
    def complete(self) -> bool:
        return bool(self.call_ids) and all(call_id in self.outputs_by_call_id for call_id in self.call_ids)

    def ordered_items(self) -> list[TResponseInputItem]:
        return [
            *self.calls,
            *(self.outputs_by_call_id[call_id] for call_id in self.call_ids),
            *self.deferred_items,
        ]


class ToolTransactionNormalizer:
    """Group tool calls with their outputs even when SDK history has reasoning between them."""

    def __init__(self, items: list[TResponseInputItem]) -> None:
        self._items = items
        self._normalized: list[TResponseInputItem] = []
        self._transaction = _ToolTransaction()

    def normalize(self) -> list[TResponseInputItem]:
        for entry in self._items:
            item = _dict_item(entry)
            item_type = item.get("type") if item is not None else ""

            if item_type == "function_call":
                self._handle_call(entry, item)
            elif item_type == "function_call_output":
                self._handle_output(entry, item)
            else:
                self._handle_regular_item(entry, item)

        self._flush_if_complete()
        self._discard_incomplete_transaction()
        return self._normalized

    def _handle_call(self, entry: TResponseInputItem, item: dict[str, Any]) -> None:
        self._flush_if_complete()
        if not self._transaction.add_call(entry, _tool_call_id(item)):
            self._discard_incomplete_transaction()
            if not self._transaction.add_call(entry, _tool_call_id(item)):
                return

    def _handle_output(self, entry: TResponseInputItem, item: dict[str, Any]) -> None:
        if not self._transaction.add_output(entry, _tool_call_id(item)):
            return
        self._flush_if_complete()

    def _handle_regular_item(self, entry: TResponseInputItem, item: dict[str, Any] | None) -> None:
        if item is not None and _is_empty_assistant_message(item):
            return
        if self._transaction.calls:
            self._transaction.deferred_items.append(entry)
            return
        self._normalized.append(entry)

    def _flush_if_complete(self) -> None:
        if not self._transaction.complete:
            return
        self._normalized.extend(self._transaction.ordered_items())
        self._drop_transaction()

    def _discard_incomplete_transaction(self) -> None:
        if not self._transaction.calls:
            return
        self._normalized.extend(self._transaction.deferred_items)
        self._drop_transaction()

    def _drop_transaction(self) -> None:
        self._transaction = _ToolTransaction()


def _dict_item(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        return entry
    dump = getattr(entry, "model_dump", None)
    if not callable(dump):
        return None
    dumped = dump(mode="json", exclude_none=True)
    return dumped if isinstance(dumped, dict) else None


def _is_empty_assistant_message(item: dict[str, Any]) -> bool:
    if item.get("type") != "message" or item.get("role") != "assistant":
        return False
    return not _extract_message_text(item.get("content")).strip()
