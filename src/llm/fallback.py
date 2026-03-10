"""Fallback chain configuration and helpers."""

from __future__ import annotations

from src.config.settings import settings

# Ordered list — first model is tried first, then fallback(s).
DEFAULT_FALLBACK_CHAIN: list[str] = [
    settings.default_model,
    settings.fallback_model,
]


def build_chain(*models: str) -> list[str]:
    """Build a de-duplicated fallback chain from the given models."""
    seen: set[str] = set()
    chain: list[str] = []
    for m in models:
        if m and m not in seen:
            seen.add(m)
            chain.append(m)
    return chain
