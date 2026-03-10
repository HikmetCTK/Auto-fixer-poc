"""LLM Router — unified interface to all models via LiteLLM.

Sets provider API keys from settings and exposes `completion()` / `acompletion()`
wrappers that automatically apply the fallback chain.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import litellm
from litellm import acompletion, ModelResponse

from src.config.settings import settings

logger = logging.getLogger(__name__)

# ── Inject API keys into environment (LiteLLM reads them from env) ─────
_KEY_MAP: dict[str, str] = {
    "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    "OPENAI_API_KEY": settings.openai_api_key,
    "OPENROUTER_API_KEY": settings.openrouter_api_key,
    "CEREBRAS_API_KEY": settings.cerebras_api_key,
    "GEMINI_API_KEY": settings.gemini_api_key,
    "GROQ_API_KEY": settings.groq_api_key,
    "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
    "AWS_SECRET_ACCESS_KEY": settings.aws_secret_access_key,
    "AWS_REGION_NAME": settings.aws_region_name,
}

for env_var, value in _KEY_MAP.items():
    if value:
        os.environ[env_var] = value

# ── LiteLLM global config ──────────────────────────────────────────────
litellm.drop_params = True  # silently ignore unsupported params per model
#litellm.set_verbose = settings.log_level == "DEBUG"


# ── Fallback chain ─────────────────────────────────────────────────────
FALLBACK_CHAIN: list[str] = [
    settings.default_model,
    settings.fallback_model,
]


async def llm_completion(
    *,
    model: str | None = None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> ModelResponse | Any:
    """Call an LLM with automatic fallback.

    Tries ``model`` first (defaults to ``settings.default_model``), then walks
    the fallback chain on failure.
    """
    models_to_try = [model or settings.default_model] + [
        m for m in FALLBACK_CHAIN if m != (model or settings.default_model)
    ]

    last_error: Exception | None = None

    for candidate in models_to_try:
        try:
            logger.info("LLM call → %s", candidate)
            response = await acompletion(
                model=candidate,
                messages=messages,
                tools=tools,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                num_retries=3,  # 3 kez otomatik tekrar dene (Rate limit vb. hatalar için)
                **kwargs,
            )
            # Safe getattr in case response is a Stream object (which doesn't have .usage immediately)
            usage_obj = getattr(response, "usage", None)
            total_tokens = getattr(usage_obj, "total_tokens", "?") if usage_obj else "?"
            logger.info("LLM response ← %s (tokens: %s)", candidate, total_tokens)
            return response

        except Exception as exc:
            logger.warning("Model %s failed: %s — trying next fallback", candidate, exc)
            last_error = exc

    raise RuntimeError(f"All models failed. Last error: {last_error}") from last_error
