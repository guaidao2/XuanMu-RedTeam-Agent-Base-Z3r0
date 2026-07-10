"""Helpers for constructing SDK input items consistently."""

from agents import TResponseInputItem
from openai.types.responses import (
    EasyInputMessageParam,
    ResponseInputImageParam,
    ResponseInputMessageContentListParam,
    ResponseInputTextParam,
)

from schema.agent.events import AgentImageInputPart, AgentInputPart, AgentTextInputPart


def text_input_content(text: str) -> list[AgentInputPart]:
    return [AgentTextInputPart(text=text)]


def display_text_from_content(content: list[AgentInputPart]) -> str:
    text = "\n\n".join(part.text for part in content if isinstance(part, AgentTextInputPart)).strip()
    if text:
        return text
    image_count = sum(1 for part in content if isinstance(part, AgentImageInputPart))
    return "[Image]" if image_count == 1 else f"[{image_count} images]"


def build_user_message_item(content_parts: list[AgentInputPart]) -> TResponseInputItem:
    content: ResponseInputMessageContentListParam = []
    for part in content_parts:
        if isinstance(part, AgentTextInputPart):
            text_item: ResponseInputTextParam = {"type": "input_text", "text": part.text}
            content.append(text_item)
        elif isinstance(part, AgentImageInputPart):
            image_item: ResponseInputImageParam = {
                "type": "input_image",
                "image_url": f"data:{str(part.media_type)};base64,{part.data}",
                "detail": str(part.detail),
            }
            content.append(image_item)
    message: EasyInputMessageParam = {"type": "message", "role": "user", "content": content}
    return message
