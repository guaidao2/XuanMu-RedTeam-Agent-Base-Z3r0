"""DeepSeek model detection and context cache optimization.

DeepSeek API provides automatic hard-disk context caching (KV Cache).
When a request prefix matches a previously cached prefix, input tokens
are billed at ~1/50 the normal price.

This module provides:
- Model detection (is_deepseek)
- Cache metrics tracking (accumulates hit/miss tokens)
- Logging helpers for monitoring cache efficiency
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import AgentConfig
from logger import get_logger

logger = get_logger(__name__)

# DeepSeek Cache Pricing (per 1M tokens)
# Cache HIT:  $0.0028 (deepseek-v4-flash) / $0.003625 (deepseek-v4-pro)
# Cache MISS: $0.14   (deepseek-v4-flash) / $0.435   (deepseek-v4-pro)
_DS_MODEL_PREFIXES = ("deepseek",)
_DS_URL_PREFIXES = ("https://api.deepseek.com",)


def is_deepseek_model(cfg: AgentConfig) -> bool:
    """Detect if the configured model is a DeepSeek model."""
    model = (cfg.model or "").lower().strip()
    url = (cfg.base_url or "").lower().strip()
    if any(model.startswith(p) for p in _DS_MODEL_PREFIXES):
        return True
    if any(url.startswith(p) for p in _DS_URL_PREFIXES):
        return True
    return False


@dataclass
class DeepSeekCacheStats:
    """Accumulated cache hit/miss statistics for a session."""
    total_requests: int = 0
    total_hit_tokens: int = 0
    total_miss_tokens: int = 0
    sessions: dict[str, "SessionCacheStats"] = field(default_factory=dict)

    @property
    def hit_ratio(self) -> float:
        total = self.total_hit_tokens + self.total_miss_tokens
        if total == 0:
            return 0.0
        return self.total_hit_tokens / total

    @property
    def estimated_savings_multiplier(self) -> float:
        """How many times cheaper due to cache (approximate)."""
        ratio = self.hit_ratio
        if ratio <= 0:
            return 1.0
        # Cache hit = 1/50 cost, miss = 1x cost
        blended_cost = (1 - ratio) * 1.0 + ratio * (1.0 / 50)
        return 1.0 / blended_cost if blended_cost > 0 else 1.0

    def record(self, hit: int, miss: int, session_id: str = "") -> None:
        self.total_requests += 1
        self.total_hit_tokens += hit
        self.total_miss_tokens += miss
        if session_id:
            s = self.sessions.setdefault(session_id, SessionCacheStats())
            s.record(hit, miss)

    def log_summary(self, tag: str = "") -> None:
        tag_str = f" [{tag}]" if tag else ""
        if self.total_requests == 0:
            logger.info("DeepSeek cache%s: no requests yet", tag_str)
            return
        hit_mb = self.total_hit_tokens / 1_000_000
        miss_mb = self.total_miss_tokens / 1_000_000
        logger.info(
            "DeepSeek cache%s: %d req | hit=%.1fM tokens miss=%.1fM tokens "
            "hit_ratio=%.1f%% est_savings=%.1fx",
            tag_str,
            self.total_requests,
            hit_mb,
            miss_mb,
            self.hit_ratio * 100,
            self.estimated_savings_multiplier,
        )


@dataclass
class SessionCacheStats:
    """Per-session cache stats."""
    hit_tokens: int = 0
    miss_tokens: int = 0
    request_count: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hit_tokens + self.miss_tokens
        return self.hit_tokens / total if total > 0 else 0.0

    def record(self, hit: int, miss: int) -> None:
        self.hit_tokens += hit
        self.miss_tokens += miss
        self.request_count += 1


# Global stats accumulator
_global_stats = DeepSeekCacheStats()


def get_global_stats() -> DeepSeekCacheStats:
    return _global_stats


def extract_cache_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    """Extract prompt_cache_hit_tokens and prompt_cache_miss_tokens from usage.

    Returns:
        Tuple of (hit_tokens, miss_tokens). Returns (0, total_input_tokens)
        if cache fields are not present (non-DeepSeek or older API version).
    """
    if not usage:
        return 0, 0
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", 0) or 0
    if hit or miss:
        return int(hit), int(miss)
    # No cache fields present — this is fine for non-DeepSeek models
    return 0, 0
