"""Automatic context compaction for SDK-backed agent sessions."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any

import tiktoken
from agents import Agent, ModelSettings, Runner, TResponseInputItem
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import AgentConfig, get_config
from core.agent.models import build_openai_model
from core.conversation.projection import ContextProjection, ProjectedItem, ProjectionCompaction
from logger import get_logger
from model.agent.context_compactions import AgentContextCompaction


logger = get_logger(__name__)

_SUMMARY_PREFIX = "# Context Summary\n\n"
_SUMMARY_AGENT_INSTRUCTIONS = """# Runtime Guidance

## Context Compression

Compress earlier agent conversation items for future continuation.

Write a concise but information-dense Markdown summary using exactly these sections:

## User Goals
## Active Constraints
## Decisions
## Relevant Files And Code
## Tool Results
## Open Tasks
## Current State

Write "None" for empty sections. Preserve durable facts, user requests, constraints, decisions,
code/file references, tool results, errors, pending tasks, and current state. Discard greetings,
repetitive reasoning, obsolete plans, and low-value narration. Do not invent facts. The summary will
replace the source messages in the next model context, so include anything required to continue the
work safely."""


@dataclass(frozen=True, slots=True)
class CompactionScope:
    session_id: str
    viewer_agent_code: str
    nested_for: str = ""
    nested_call_id: str = ""


@dataclass(frozen=True, slots=True)
class CompactionDecision:
    should_compact: bool
    projected_tokens: int
    context_window: int
    trigger_tokens: int
    target_tokens: int


def estimate_items_tokens(items: list[TResponseInputItem], model: str) -> int:
    encoding = _encoding_for_model(model)
    total = 0
    for item in items:
        total += 4
        total += len(encoding.encode(json.dumps(_summary_safe_value(item), ensure_ascii=False, separators=(",", ":"))))
    return total


def estimate_projection_tokens(projection: ContextProjection, model: str) -> ContextProjection:
    return ContextProjection(projected_items=[
        ProjectedItem(
            item=item.item,
            source_message_ids=item.source_message_ids,
            token_estimate=item.token_estimate or estimate_items_tokens([item.item], model),
            atomic_group=item.atomic_group,
        )
        for item in projection.projected_items
    ])


async def get_latest_compaction(sess: AsyncSession, scope: CompactionScope) -> ProjectionCompaction | None:
    row = (await sess.execute(
        select(AgentContextCompaction)
        .where(
            AgentContextCompaction.session_id == scope.session_id,
            AgentContextCompaction.viewer_agent_code == scope.viewer_agent_code,
            AgentContextCompaction.nested_for == scope.nested_for,
            AgentContextCompaction.nested_call_id == scope.nested_call_id,
        )
        .order_by(AgentContextCompaction.end_message_id.desc(), AgentContextCompaction.id.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None or row.id is None:
        return None
    return ProjectionCompaction(
        id=row.id,
        start_message_id=row.start_message_id,
        end_message_id=row.end_message_id,
        summary_item=row.summary_item,
    )


async def compact_if_needed(
    *,
    session_factory: Any,
    scope: CompactionScope,
    agent_config: AgentConfig,
    projection: ContextProjection,
    incoming_items: list[TResponseInputItem],
) -> CompactionDecision:
    cfg = get_config().agent_runtime
    context_window = resolve_context_window(agent_config)
    if not cfg.context_compression_enabled or context_window <= 0:
        return CompactionDecision(False, 0, context_window, 0, 0)

    projection = estimate_projection_tokens(projection, agent_config.model)
    projected_tokens = sum(item.token_estimate for item in projection.projected_items)
    projected_tokens += estimate_items_tokens(incoming_items, agent_config.model)
    trigger_tokens = int(context_window * cfg.context_compression_trigger_ratio)
    hard_stop_tokens = int(context_window * cfg.context_compression_hard_stop_ratio)
    target_tokens = int(context_window * cfg.context_compression_target_ratio)
    if projected_tokens < trigger_tokens:
        return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)
    candidate_items = _select_compaction_candidates(
        projection.projected_items,
        target_tokens=target_tokens,
        projected_tokens=projected_tokens,
        incoming_tokens=estimate_items_tokens(incoming_items, agent_config.model),
        summary_max_tokens=cfg.context_compression_summary_max_tokens,
    )
    compact_start_message_id = _candidate_start_message_id(candidate_items)
    compact_until_message_id = _candidate_end_message_id(candidate_items)
    if compact_start_message_id is None or compact_until_message_id is None:
        return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)
    if len(candidate_items) < cfg.context_compression_min_items:
        logger.debug(
            "agent context compaction skipped: too few candidate items session=%s viewer=%s candidates=%d min=%d tokens=%d trigger=%d window=%d",
            scope.session_id,
            scope.viewer_agent_code,
            len(candidate_items),
            cfg.context_compression_min_items,
            projected_tokens,
            trigger_tokens,
            context_window,
        )
        return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)

    candidate_tokens = sum(item.token_estimate for item in candidate_items)
    logger.debug(
        "agent context compaction starting session=%s viewer=%s nested_for=%s nested_call=%s model=%s items=%d candidate_items=%d tokens=%d trigger=%d target=%d window=%d end_message_id=%s",
        scope.session_id,
        scope.viewer_agent_code,
        scope.nested_for,
        scope.nested_call_id,
        agent_config.model,
        len(projection.items),
        len(candidate_items),
        projected_tokens,
        trigger_tokens,
        target_tokens,
        context_window,
        compact_until_message_id,
    )

    logger.debug(
        "agent context compaction summarizing session=%s viewer=%s candidate_items=%d candidate_tokens=%d",
        scope.session_id,
        scope.viewer_agent_code,
        len(candidate_items),
        candidate_tokens,
    )
    # Summarize WITHOUT holding a pooled connection: the LLM call can run for
    # seconds up to the stream idle timeout, and pinning a connection across it
    # starves the pool under sub-agent fan-out (the original deadlock that left
    # parents waiting forever). The advisory lock only needs to guard the fast
    # store, and compaction scope is per-agent-instance with serialized turns,
    # so same-scope concurrency is effectively impossible anyway.
    try:
        summary_text = await _summarize_items([item.item for item in candidate_items], agent_config)
    except Exception as exc:
        logger.warning(
            "agent context compaction failed session=%s viewer=%s reason=%s",
            scope.session_id,
            scope.viewer_agent_code,
            _one_line_error(exc),
        )
        _raise_if_hard_stop(projected_tokens, hard_stop_tokens, "context compaction failed near model context limit")
        return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)
    if not summary_text.strip():
        logger.warning(
            "agent context compaction produced empty summary session=%s viewer=%s candidate_items=%d",
            scope.session_id,
            scope.viewer_agent_code,
            len(candidate_items),
        )
        _raise_if_hard_stop(projected_tokens, hard_stop_tokens, "context compaction produced an empty summary")
        return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)

    summary_item = _summary_item(summary_text)
    source_tokens = candidate_tokens
    summary_tokens = estimate_items_tokens([summary_item], agent_config.model)
    async with session_factory() as sess:
        if not await _try_lock_compaction(sess, scope):
            logger.debug(
                "agent context compaction skipped: lock busy session=%s viewer=%s nested_for=%s nested_call=%s",
                scope.session_id,
                scope.viewer_agent_code,
                scope.nested_for,
                scope.nested_call_id,
            )
            return CompactionDecision(False, projected_tokens, context_window, trigger_tokens, target_tokens)
        try:
            await _store_compaction(
                sess=sess,
                scope=scope,
                start_message_id=compact_start_message_id,
                end_message_id=compact_until_message_id,
                summary_item=summary_item,
                source_item_count=len(candidate_items),
                source_token_estimate=source_tokens,
                summary_token_estimate=summary_tokens,
                model=agent_config.model,
            )
        finally:
            await _unlock_compaction(sess, scope)
    logger.info(
        "agent context compacted session=%s viewer=%s nested_for=%s nested_call=%s items=%d tokens=%d summary_tokens=%d window=%d end_message_id=%s",
        scope.session_id,
        scope.viewer_agent_code,
        scope.nested_for,
        scope.nested_call_id,
        len(candidate_items),
        source_tokens,
        summary_tokens,
        context_window,
        compact_until_message_id,
    )
    return CompactionDecision(True, projected_tokens, context_window, trigger_tokens, target_tokens)


def _select_compaction_candidates(
    projected_items: list[ProjectedItem],
    *,
    target_tokens: int,
    projected_tokens: int,
    incoming_tokens: int,
    summary_max_tokens: int,
) -> list[ProjectedItem]:
    cfg = get_config().agent_runtime
    preserve_tokens = int(target_tokens * cfg.context_compression_preserve_recent_ratio)
    preserved: list[ProjectedItem] = []
    preserved_tokens = 0
    for item in reversed(projected_items):
        if len(preserved) >= cfg.context_compression_preserve_recent_items and preserved_tokens >= preserve_tokens:
            break
        preserved.append(item)
        preserved_tokens += item.token_estimate
    compact_count = max(0, len(projected_items) - len(preserved))
    if compact_count <= 0:
        return []

    candidates: list[ProjectedItem] = []
    removed_tokens = 0
    open_atomic_groups: set[str] = set()
    last_complete_index = -1
    for item in projected_items[:compact_count]:
        if not item.source_message_ids:
            continue
        candidates.append(item)
        if item.atomic_group:
            if item.atomic_group in open_atomic_groups:
                open_atomic_groups.remove(item.atomic_group)
            else:
                open_atomic_groups.add(item.atomic_group)
        removed_tokens += item.token_estimate
        if not open_atomic_groups and len(candidates) >= cfg.context_compression_min_items:
            last_complete_index = len(candidates) - 1
        estimated_after_compaction = projected_tokens - removed_tokens + summary_max_tokens
        if (
            estimated_after_compaction <= target_tokens
            and len(candidates) >= cfg.context_compression_min_items
            and not open_atomic_groups
        ):
            return candidates

    # If the target cannot be reached because the recent tail or incoming prompt is too large,
    # compact all eligible prefix items and let the next turn decide whether another pass is needed.
    if incoming_tokens >= target_tokens:
        logger.debug("incoming prompt tokens exceed compression target: incoming=%d target=%d", incoming_tokens, target_tokens)
    if open_atomic_groups:
        return candidates[:last_complete_index + 1]
    return candidates


def _raise_if_hard_stop(projected_tokens: int, hard_stop_tokens: int, message: str) -> None:
    if hard_stop_tokens > 0 and projected_tokens >= hard_stop_tokens:
        raise RuntimeError(message)


def _candidate_end_message_id(candidate_items: list[ProjectedItem]) -> int | None:
    ids = [mid for item in candidate_items for mid in item.source_message_ids]
    return max(ids) if ids else None


def _candidate_start_message_id(candidate_items: list[ProjectedItem]) -> int | None:
    ids = [mid for item in candidate_items for mid in item.source_message_ids]
    return min(ids) if ids else None


async def _try_lock_compaction(sess: AsyncSession, scope: CompactionScope) -> bool:
    lock_key = _advisory_lock_key(scope)
    return bool((await sess.execute(select(func.pg_try_advisory_lock(lock_key)))).scalar_one())


async def _unlock_compaction(sess: AsyncSession, scope: CompactionScope) -> None:
    lock_key = _advisory_lock_key(scope)
    await sess.execute(select(func.pg_advisory_unlock(lock_key)))


async def _store_compaction(
    *,
    sess: AsyncSession,
    scope: CompactionScope,
    start_message_id: int,
    end_message_id: int,
    summary_item: TResponseInputItem,
    source_item_count: int,
    source_token_estimate: int,
    summary_token_estimate: int,
    model: str,
) -> None:
    try:
        await sess.execute(delete(AgentContextCompaction).where(
            AgentContextCompaction.session_id == scope.session_id,
            AgentContextCompaction.viewer_agent_code == scope.viewer_agent_code,
            AgentContextCompaction.nested_for == scope.nested_for,
            AgentContextCompaction.nested_call_id == scope.nested_call_id,
        ))
        sess.add(AgentContextCompaction(
            session_id=scope.session_id,
            viewer_agent_code=scope.viewer_agent_code,
            nested_for=scope.nested_for,
            nested_call_id=scope.nested_call_id,
            start_message_id=start_message_id,
            end_message_id=end_message_id,
            summary_item=summary_item,
            source_item_count=source_item_count,
            source_token_estimate=source_token_estimate,
            summary_token_estimate=summary_token_estimate,
            model=model,
        ))
        await sess.commit()
    except Exception:
        await sess.rollback()
        raise


async def _summarize_items(items: list[TResponseInputItem], agent_config: AgentConfig) -> str:
    cfg = get_config().agent_runtime
    agent = Agent(
        name="Context Compressor",
        model=build_openai_model(agent_config),
        model_settings=ModelSettings(max_tokens=cfg.context_compression_summary_max_tokens),
        instructions=_SUMMARY_AGENT_INSTRUCTIONS,
    )
    try:
        payload = json.dumps(_summary_safe_value(items), ensure_ascii=False, indent=2)
        result = await Runner.run(
            starting_agent=agent,
            input=(
                "# Context Compression Input\n\n"
                "Compress the following earlier conversation items into a replacement summary. "
                "Return only the summary body with the required sections.\n\n"
                "## Items\n\n"
                f"```json\n{payload}\n```"
            ),
            max_turns=1,
        )
        output = getattr(result, "final_output", "")
        return output if isinstance(output, str) else str(output or "")
    finally:
        await agent.model.close()


def _summary_item(summary_text: str) -> TResponseInputItem:
    return {
        "id": "context_summary",
        "type": "message",
        "role": "user",
        "content": [{
            "type": "input_text",
            "text": _SUMMARY_PREFIX + "This is context, not a new user request. Continue from the summary below.\n\n" + summary_text.strip(),
        }],
    }


def _summary_safe_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_summary_safe_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("type") == "input_image":
        media_type = _image_media_type(value.get("image_url"))
        return {
            "type": "input_image",
            "image_url": f"data:{media_type};base64,[omitted]",
            "detail": value.get("detail") or "auto",
            "note": "image bytes omitted from context compaction prompt",
        }
    return {key: _summary_safe_value(item) for key, item in value.items()}


def _image_media_type(image_url: Any) -> str:
    if not isinstance(image_url, str) or not image_url.startswith("data:"):
        return "image/*"
    header = image_url.split(",", 1)[0]
    media_type = header.removeprefix("data:").split(";", 1)[0]
    return media_type or "image/*"


def resolve_context_window(agent_config: AgentConfig) -> int:
    return agent_config.context_window


def _one_line_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:500]


def _encoding_for_model(model: str):
    try:
        return tiktoken.encoding_for_model(model.split("/", 1)[-1])
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _advisory_lock_key(scope: CompactionScope) -> int:
    raw = "\x1f".join((scope.session_id, scope.viewer_agent_code, scope.nested_for, scope.nested_call_id))
    value = int.from_bytes(hashlib.blake2b(raw.encode("utf-8"), digest_size=8).digest(), "big", signed=False)
    return value - (1 << 63)
