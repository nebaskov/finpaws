from __future__ import annotations

from app.agent import llm
from app.config import SETTINGS


def test_rate_limiter_disabled_by_default() -> None:
    assert llm._build_rate_limiter() is None


def test_rate_limiter_enabled(monkeypatch) -> None:
    monkeypatch.setattr(SETTINGS, "llm_requests_per_second", 5.0)
    assert llm._build_rate_limiter() is not None


def test_build_chat_model_constructs(monkeypatch) -> None:
    monkeypatch.setattr(SETTINGS, "llm_requests_per_second", 3.0)
    model = llm.build_chat_model(model="gpt-test", api_key="k")
    assert model is not None
