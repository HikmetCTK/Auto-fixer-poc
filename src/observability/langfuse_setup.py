"""Langfuse observability setup — integrates with LiteLLM callbacks."""

from __future__ import annotations

import logging
import litellm
from src.config.settings import settings

logger = logging.getLogger(__name__)


def setup_langfuse():
    """Configures LiteLLM to use Langfuse for tracing."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse keys not configured, skipping observability setup.")
        return

    # LiteLLM native Langfuse integration (v3+ uses langfuse_otel)
    litellm.callbacks = ["langfuse_otel"]

    # These environment variables are read by LiteLLM's langfuse callback
    import os
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host
    os.environ["LANGFUSE_OTEL_HOST"] = settings.langfuse_host # OTEL expects this optionally

    logger.info("Langfuse OTEL observability enabled (HOST: %s)", settings.langfuse_host)
