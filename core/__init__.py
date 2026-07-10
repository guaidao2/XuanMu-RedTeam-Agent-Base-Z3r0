"""Core agent runtime packages."""

from typing import Any

TEXT_CONTENT_TYPES = frozenset({"input_text", "output_text", "text"})


def extract_message_text(content: Any) -> str:
    """Extract concatenated text from a message content field (str or list of typed parts)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for piece in content:
        if not isinstance(piece, dict):
            continue
        if piece.get("type") in TEXT_CONTENT_TYPES:
            text = piece.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


INTERNAL_USER_MESSAGE_PREFIXES = ("# Task Resumption Context", "# Context Summary")


def is_internal_user_text(text: str) -> bool:
    """Return True if the text starts with a known internal-message prefix."""
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in INTERNAL_USER_MESSAGE_PREFIXES)


def tool_call_id(item: dict[str, Any]) -> str:
    """Extract the tool call ID from an SDK item dict (``call_id`` or ``id``)."""
    value = item.get("call_id") or item.get("id")
    return value if isinstance(value, str) else ""
