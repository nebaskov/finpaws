from __future__ import annotations

from app.agent import tracing
from app.config import SETTINGS


def test_langfuse_callbacks_empty_when_unconfigured() -> None:
    assert tracing.langfuse_callbacks() == []


def test_langfuse_callbacks_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(SETTINGS, "langfuse_public_key", "pk-lf-test")
    monkeypatch.setattr(SETTINGS, "langfuse_secret_key", "sk-lf-test")
    monkeypatch.setattr(SETTINGS, "langfuse_host", "http://localhost:3000")
    assert SETTINGS.langfuse_enabled
    callbacks = tracing.langfuse_callbacks()
    assert len(callbacks) == 1
