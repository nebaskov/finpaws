from __future__ import annotations

from app.agent import checkpoint
from app.config import SETTINGS


def test_to_psycopg_url_strips_sqlalchemy_driver():
    assert checkpoint._to_psycopg_url("postgresql+psycopg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert checkpoint._to_psycopg_url("sqlite:///:memory:") == "sqlite:///:memory:"


def test_open_checkpointer_in_memory_for_non_postgres(monkeypatch):
    monkeypatch.setattr(SETTINGS, "database_url", "sqlite:///:memory:")
    with checkpoint.open_checkpointer() as saver:
        assert saver is not None


def test_open_checkpointer_falls_back_when_postgres_unavailable(monkeypatch):
    # Port 1 is reserved/closed → connection refused → graceful fallback to in-memory.
    monkeypatch.setattr(SETTINGS, "database_url", "postgresql+psycopg://u:p@127.0.0.1:1/nope")
    with checkpoint.open_checkpointer() as saver:
        assert saver is not None
