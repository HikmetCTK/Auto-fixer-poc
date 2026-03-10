"""Application settings — loaded from environment variables via Pydantic."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Bug Detective application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"
    use_native_tool_calling: bool = False

    # ── LLM Providers ───────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    tavily_api_key: str = ""
    cerebras_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    groq_api_key: str = ""
    aws_access_key_id: str = ""  # New: AWS Bedrock
    aws_secret_access_key: str = ""  # New: AWS Bedrock
    aws_region_name: str = ""  # New: AWS Bedrock
    # ── Default Models ──────────────────────────────────
    # Groq: openai/gpt-oss-120b → 120B, primary workhorse (override via .env)
    # Groq: compound            → multi-model compound AI, fallback
    default_model: str = ""
    fallback_model: str = ""

    # ── Redis ───────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── PostgreSQL ──────────────────────────────────────
    database_url: str = "postgresql+asyncpg://app:changeme@localhost:5432/bugdetective"

    # ── Temporal ────────────────────────────────────────
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "bug-detective-queue"

    # ── Langfuse (Phase 2) ──────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# Singleton — import this everywhere
settings = Settings()
