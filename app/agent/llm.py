from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI

from app.config import SETTINGS


def _build_rate_limiter() -> Any | None:
    rps = SETTINGS.llm_requests_per_second
    if rps <= 0:
        return None
    return InMemoryRateLimiter(
        requests_per_second=rps,
        check_every_n_seconds=0.1,
        max_bucket_size=max(1.0, SETTINGS.llm_rate_limit_burst),
    )


def build_chat_model(
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.2,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> BaseChatModel:
    return ChatOpenAI(
        model=model or SETTINGS.llm_model,
        api_key=api_key or SETTINGS.llm_api_key or "missing-key",
        base_url=base_url or SETTINGS.llm_base_url,
        temperature=temperature,
        timeout=timeout if timeout is not None else SETTINGS.llm_timeout_seconds,
        max_retries=max_retries if max_retries is not None else SETTINGS.llm_max_retries,
        rate_limiter=_build_rate_limiter(),
    )
