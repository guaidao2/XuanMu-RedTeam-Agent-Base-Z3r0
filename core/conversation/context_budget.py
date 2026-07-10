"""Model-call context budgeting for SDK-backed sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents import TResponseInputItem
from agents.run import CallModelData, ModelInputData, RunConfig

from config import AgentConfig, get_config
from core import extract_message_text, tool_call_id
from core.conversation.compaction import estimate_items_tokens, resolve_context_window
from logger import get_logger


logger = get_logger(__name__)

_NOTICE_ID = "context_budget_notice"
_NOTICE_TEXT = (
    "# Context Budget Notice\n\n"
    "Older conversation items were omitted from this model call because the active input exceeded "
    "the configured context window. Use the retained context summary and recent messages. Reload "
    "specific files, command outputs, or knowledge entries if exact omitted details are needed."
)
_MIN_COMPLETION_SLACK_TOKENS = 2048


@dataclass(frozen=True, slots=True)
class ContextBudget:
    model: str
    context_window: int
    input_budget_tokens: int


@dataclass(frozen=True, slots=True)
class _InputChunk:
    items: list[TResponseInputItem]
    token_estimate: int


def build_context_run_config(agent_config: AgentConfig) -> RunConfig:
    """Build SDK run config that enforces context budget before every model call."""
    return RunConfig(call_model_input_filter=ContextBudgetFilter(agent_config))


@dataclass(frozen=True, slots=True)
class ContextBudgetFilter:
    agent_config: AgentConfig

    def __call__(self, data: CallModelData[Any]) -> ModelInputData:
        budget = resolve_context_budget(self.agent_config)
        if budget is None:
            return data.model_data
        input_items = data.model_data.input
        instructions = data.model_data.instructions
        constrained = constrain_model_input(
            input_items,
            instructions=instructions,
            budget=budget,
        )
        if constrained is input_items:
            return data.model_data
        return ModelInputData(input=constrained, instructions=instructions)


def resolve_context_budget(agent_config: AgentConfig) -> ContextBudget | None:
    context_window = resolve_context_window(agent_config)
    if context_window <= 0:
        return None
    cfg = get_config().agent_runtime
    ratio_budget = int(context_window * cfg.context_budget_model_call_ratio)
    completion_slack = min(_MIN_COMPLETION_SLACK_TOKENS, max(1, context_window // 10))
    hard_budget = max(1, context_window - completion_slack)
    input_budget = max(1, min(ratio_budget, hard_budget))
    return ContextBudget(
        model=agent_config.model,
        context_window=context_window,
        input_budget_tokens=input_budget,
    )


def constrain_model_input(
    input_items: list[TResponseInputItem],
    *,
    instructions: str | None,
    budget: ContextBudget,
) -> list[TResponseInputItem]:
    current_tokens = _estimate_model_call_tokens(input_items, instructions, budget.model)
    if current_tokens <= budget.input_budget_tokens:
        return input_items

    instruction_tokens = _estimate_instruction_tokens(instructions, budget.model)
    item_budget = budget.input_budget_tokens - instruction_tokens
    if item_budget <= 0:
        raise RuntimeError(
            "agent instructions exceed configured model context budget "
            f"tokens={instruction_tokens} budget={budget.input_budget_tokens}",
        )

    constrained = _prune_items_to_budget(input_items, item_budget, budget.model)
    constrained_tokens = _estimate_model_call_tokens(constrained, instructions, budget.model)
    if constrained_tokens > budget.input_budget_tokens:
        raise RuntimeError(
            "model input exceeds configured context budget after pruning "
            f"tokens={constrained_tokens} budget={budget.input_budget_tokens} "
            f"window={budget.context_window}",
        )

    logger.warning(
        "agent model input pruned to context budget: model=%s tokens=%d original_tokens=%d budget=%d window=%d original_items=%d items=%d",
        budget.model,
        constrained_tokens,
        current_tokens,
        budget.input_budget_tokens,
        budget.context_window,
        len(input_items),
        len(constrained),
    )
    return constrained


def _estimate_model_call_tokens(
    input_items: list[TResponseInputItem],
    instructions: str | None,
    model: str,
) -> int:
    return estimate_items_tokens(input_items, model) + _estimate_instruction_tokens(instructions, model)


def _estimate_instruction_tokens(instructions: str | None, model: str) -> int:
    if not instructions:
        return 0
    return estimate_items_tokens([{
        "type": "message",
        "role": "system",
        "content": instructions,
    }], model)


def _prune_items_to_budget(
    items: list[TResponseInputItem],
    item_budget_tokens: int,
    model: str,
) -> list[TResponseInputItem]:
    anchor, tail_items = _split_context_anchor(items)
    anchor_tokens = estimate_items_tokens(anchor, model) if anchor else 0
    notice = [_budget_notice_item()]
    notice_tokens = estimate_items_tokens(notice, model)
    suffix_budget = item_budget_tokens - anchor_tokens - notice_tokens

    if suffix_budget <= 0 and anchor:
        anchor = []
        anchor_tokens = 0
        suffix_budget = item_budget_tokens - anchor_tokens - notice_tokens

    chunks = _build_chunks(tail_items, model)
    suffix, omitted_chunks = _select_recent_chunks(chunks, max(0, suffix_budget))

    if not suffix and chunks:
        raise RuntimeError(
            "latest model input item exceeds configured context budget; reduce the request or tool output size"
        )

    if omitted_chunks <= 0:
        candidate = [*anchor, *suffix]
    else:
        candidate = [*anchor, *notice, *suffix]

    candidate = _drop_orphan_tool_items(candidate)
    if estimate_items_tokens(candidate, model) <= item_budget_tokens:
        return candidate

    if anchor:
        candidate = [*notice, *suffix] if omitted_chunks > 0 else suffix
        candidate = _drop_orphan_tool_items(candidate)
        if estimate_items_tokens(candidate, model) <= item_budget_tokens:
            return candidate

    raise RuntimeError(
        "model input exceeds configured context budget after context pruning"
    )


def _split_context_anchor(items: list[TResponseInputItem]) -> tuple[list[TResponseInputItem], list[TResponseInputItem]]:
    if not items:
        return [], []
    first = items[0]
    if _is_context_summary(first):
        return [first], items[1:]
    return [], items


def _is_context_summary(item: TResponseInputItem) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("type") != "message" or item.get("role") != "user":
        return False
    text = extract_message_text(item.get("content"))
    return text.lstrip().startswith("# Context Summary")


def _build_chunks(items: list[TResponseInputItem], model: str) -> list[_InputChunk]:
    chunks: list[_InputChunk] = []
    pending: list[TResponseInputItem] = []
    open_calls: set[str] = set()

    def flush_pending() -> None:
        nonlocal pending, open_calls
        if not pending:
            return
        chunks.append(_InputChunk(
            items=pending,
            token_estimate=estimate_items_tokens(pending, model),
        ))
        pending = []
        open_calls = set()

    for item in items:
        item_type = item.get("type") if isinstance(item, dict) else ""
        call_id = tool_call_id(item) if isinstance(item, dict) else ""

        if item_type == "function_call":
            if not pending:
                pending = [item]
                open_calls = {call_id} if call_id else set()
                continue
            pending.append(item)
            if call_id:
                open_calls.add(call_id)
            continue

        if pending:
            pending.append(item)
            if item_type == "function_call_output" and call_id in open_calls:
                open_calls.remove(call_id)
            if not open_calls:
                flush_pending()
            continue

        chunks.append(_InputChunk(
            items=[item],
            token_estimate=estimate_items_tokens([item], model),
        ))

    flush_pending()
    return chunks


def _select_recent_chunks(chunks: list[_InputChunk], budget_tokens: int) -> tuple[list[TResponseInputItem], int]:
    selected: list[_InputChunk] = []
    total = 0
    omitted = 0
    for chunk in reversed(chunks):
        if total + chunk.token_estimate > budget_tokens:
            omitted = len(chunks) - len(selected)
            break
        selected.append(chunk)
        total += chunk.token_estimate
    selected.reverse()
    return [item for chunk in selected for item in chunk.items], omitted


def _budget_notice_item() -> TResponseInputItem:
    return {
        "id": _NOTICE_ID,
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": _NOTICE_TEXT}],
    }


def _drop_orphan_tool_items(items: list[TResponseInputItem]) -> list[TResponseInputItem]:
    call_ids = {
        call_id
        for item in items
        if isinstance(item, dict)
        and item.get("type") == "function_call"
        and (call_id := tool_call_id(item))
    }
    output_ids = {
        call_id
        for item in items
        if isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and (call_id := tool_call_id(item))
    }
    paired = call_ids & output_ids
    cleaned: list[TResponseInputItem] = []
    for item in items:
        if not isinstance(item, dict):
            cleaned.append(item)
            continue
        item_type = item.get("type")
        if item_type in {"function_call", "function_call_output"} and tool_call_id(item) not in paired:
            continue
        cleaned.append(item)
    return cleaned
