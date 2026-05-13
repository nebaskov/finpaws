"""Langfuse tracing for the LLM/agent path.

When ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set, :func:`langfuse_callbacks`
returns a LangChain callback handler that ships traces/spans of every agent run to Langfuse.
Otherwise it returns an empty list and the agent runs untraced — tracing never breaks a request.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.config import SETTINGS


def langfuse_callbacks() -> list[Any]:
    if not SETTINGS.langfuse_enabled:
        return []
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        Langfuse(
            public_key=SETTINGS.langfuse_public_key,
            secret_key=SETTINGS.langfuse_secret_key,
            host=SETTINGS.langfuse_host,
        )
        return [CallbackHandler()]
    except Exception:  # noqa: BLE001 - tracing is best-effort; never fail a chat over it
        logger.exception("langfuse callback init failed")
        return []
