"""Native OpenAI model construction for configured agents.

Supports DeepSeek context caching optimization:
when a DeepSeek model is detected, cache hit/miss metrics
are automatically tracked and logged.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import (
    AgentOutputSchemaBase,
    Handoff,
    Model,
    ModelResponse,
    ModelRetryAdvice,
    ModelRetryAdviceRequest,
    ModelSettings,
    ModelTracing,
    TResponseInputItem,
    Tool,
)
from agents.models.openai_provider import OpenAIProvider
from agents.stream_events import TResponseStreamEvent
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai import AsyncOpenAI

from config import AgentConfig
from core.agent.deepseek import (
    extract_cache_tokens,
    get_global_stats,
    is_deepseek_model,
)
from core.agent.model_input import ModelInputAdapter
from logger import get_logger

logger = get_logger(__name__)


def _make_deepseek_client(cfg: AgentConfig) -> AsyncOpenAI:
    """Create an AsyncOpenAI client with cache metrics interception."""
    import httpx

    cache_stats = get_global_stats()

    async def _log_cache_response(response: httpx.Response) -> None:
        """Intercept response to extract DeepSeek cache metrics."""
        if response.status_code != 200:
            return
        # Only parse chat completions responses
        url = str(response.url)
        if "/chat/completions" not in url and "/responses" not in url:
            return

        try:
            body = response.json()
            usage = body.get("usage") or {}
            hit, miss = extract_cache_tokens(usage)
            if hit or miss:
                cache_stats.record(hit, miss)
                if cache_stats.total_requests % 10 == 1:
                    cache_stats.log_summary(cfg.model)
        except Exception:
            pass

    # Use httpx event hooks for response interception
    transport = httpx.AsyncHTTPTransport(retries=2)
    http_client = httpx.AsyncClient(
        transport=transport,
        event_hooks={"response": [_log_cache_response]},
    )

    return AsyncOpenAI(
        api_key=cfg.api_key or ("unused" if cfg.base_url else None),
        base_url=cfg.base_url or None,
        http_client=http_client,
        max_retries=10,
    )


class XuanMuModel(Model):
    def __init__(self, cfg: AgentConfig) -> None:
        self.model = cfg.model
        self._is_deepseek = is_deepseek_model(cfg)
        self._input_adapter = ModelInputAdapter()

        if self._is_deepseek:
            logger.info(
                "DeepSeek model detected: %s | cache optimization enabled",
                cfg.model,
            )
            self._client = _make_deepseek_client(cfg)
        else:
            self._client = AsyncOpenAI(
                api_key=cfg.api_key or ("unused" if cfg.base_url else None),
                base_url=cfg.base_url or None,
                max_retries=10,
            )

        self._provider = OpenAIProvider(
            openai_client=self._client,
            use_responses=cfg.use_responses,
        )
        self._model = self._provider.get_model(cfg.model)

    def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
        return self._model.get_retry_advice(request)

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        return await self._model.get_response(
            system_instructions,
            self._input_adapter.adapt(input),
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        async for event in self._model.stream_response(
            system_instructions,
            self._input_adapter.adapt(input),
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        ):
            yield event

    async def close(self) -> None:
        await self._model.close()
        await self._provider.aclose()
        await self._client.close()


def build_openai_model(cfg: AgentConfig) -> XuanMuModel:
    return XuanMuModel(cfg)
