from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/finpaws",
        validation_alias="DATABASE_URL",
    )

    jwt_secret: str = Field(default="dev-secret-change-me", validation_alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_ttl_seconds: int = Field(default=86400, validation_alias="JWT_TTL")

    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_max_tool_steps: int = Field(default=8, validation_alias="AGENT_MAX_STEPS")
    llm_timeout_seconds: int = Field(default=30, validation_alias="LLM_TIMEOUT")
    llm_max_retries: int = Field(default=2, validation_alias="LLM_RETRIES")
    # Client-side LLM rate limit (0 = disabled). Throttles requests to the model provider.
    llm_requests_per_second: float = Field(default=0.0, validation_alias="LLM_RPS")
    llm_rate_limit_burst: float = Field(default=1.0, validation_alias="LLM_RATE_LIMIT_BURST")

    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="EMBEDDING_MODEL")
    embedding_base_url: str | None = Field(default=None, validation_alias="EMBEDDING_BASE_URL")
    embedding_api_key: str | None = Field(default=None, validation_alias="EMBEDDING_API_KEY")

    # LLM-as-a-judge for deepeval (OpenAI-compatible endpoint; defaults to DeepSeek).
    judge_model: str = Field(default="deepseek-chat", validation_alias="JUDGE_MODEL")
    judge_base_url: str = Field(default="https://api.deepseek.com/v1", validation_alias="JUDGE_BASE_URL")
    judge_api_key: str | None = Field(default=None, validation_alias="JUDGE_API_KEY")
    judge_temperature: float = Field(default=0.0, validation_alias="JUDGE_TEMPERATURE")

    kb_backend: str = Field(default="chroma", validation_alias="KB_BACKEND")
    kb_path: str = Field(default="data/kb", validation_alias="KB_PATH")
    kb_collection: str = Field(default="finpaws-advice", validation_alias="KB_COLLECTION")
    kb_seed_path: str = Field(default="data/kb_seed", validation_alias="KB_SEED_PATH")
    qdrant_url: str = Field(default="http://localhost:6333", validation_alias="QDRANT_URL")

    currency_api_url: str = Field(
        default="https://api.exchangerate.host/convert",
        validation_alias="CURRENCY_API_URL",
    )
    currency_cache_ttl_seconds: int = Field(default=3600, validation_alias="CURRENCY_TTL")

    pii_redaction_enabled: bool = Field(default=True, validation_alias="PII_REDACT")
    safe_mode: bool = Field(default=True, validation_alias="SAFE_MODE")
    # Rule-based toxicity score in [0, 1] — `toxic=True` when score ≥ this threshold.
    toxicity_threshold: float = Field(default=0.5, validation_alias="TOXICITY_THRESHOLD")

    # Prometheus metrics endpoint (/metrics) for API monitoring.
    metrics_enabled: bool = Field(default=True, validation_alias="METRICS_ENABLED")

    # API rate limit: a slowapi limit string ("120/minute", "10/second", ...), per client IP.
    api_rate_limit_enabled: bool = Field(default=True, validation_alias="API_RATE_LIMIT_ENABLED")
    api_rate_limit: str = Field(default="120/minute", validation_alias="API_RATE_LIMIT")

    # Langfuse LLM tracing — enabled when both keys are set.
    langfuse_public_key: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", validation_alias="LANGFUSE_HOST")

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_serialize: bool = Field(default=True, validation_alias="LOG_JSON")
    log_backtrace: bool = Field(default=False, validation_alias="LOG_BACKTRACE")
    log_diagnose: bool = Field(default=False, validation_alias="LOG_DIAGNOSE")

    hledger_bin: str = Field(default="hledger", validation_alias="HLEDGER_BIN")
    hledger_journal: str = Field(default="data/finpaws.journal", validation_alias="HLEDGER_JOURNAL")
    hledger_mirror_enabled: bool = Field(default=True, validation_alias="HLEDGER_MIRROR")
    hledger_timeout_seconds: int = Field(default=10, validation_alias="HLEDGER_TIMEOUT")


SETTINGS = Settings()
