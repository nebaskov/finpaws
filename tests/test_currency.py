from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from app.api.models import CurrencyRateRow
from app.db import Base
from app.integrations import currency as currency_mod
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _factory():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)


def test_same_currency_no_call(monkeypatch) -> None:
    factory = _factory()
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("must not call remote")

    monkeypatch.setattr(currency_mod, "_fetch_rate_remote", boom)
    with factory() as session:
        result = currency_mod.convert(session, Decimal("100"), "RUB", "RUB")
    assert result.converted == Decimal("100.00")
    assert result.rate == Decimal("1")
    assert called["n"] == 0


def test_remote_then_cache(monkeypatch) -> None:
    factory = _factory()
    monkeypatch.setattr(currency_mod, "_fetch_rate_remote", lambda *a, **k: Decimal("90.5"))
    with factory() as session:
        first = currency_mod.convert(session, Decimal("10"), "USD", "RUB")
    assert first.converted == Decimal("905.00")
    assert not first.stale

    def boom(*a, **k):
        raise AssertionError("cache should be hit")

    monkeypatch.setattr(currency_mod, "_fetch_rate_remote", boom)
    with factory() as session:
        second = currency_mod.convert(session, Decimal("10"), "USD", "RUB")
    assert second.converted == Decimal("905.00")
    assert not second.stale


def test_stale_fallback_when_remote_fails(monkeypatch) -> None:
    factory = _factory()
    with factory() as session:
        session.add(
            CurrencyRateRow(
                pair="EUR/RUB",
                rate=Decimal("100"),
                fetched_at=datetime.now(tz=UTC) - timedelta(days=10),
            )
        )
        session.commit()

    def fail(*a, **k):
        raise currency_mod.CurrencyError("down")

    monkeypatch.setattr(currency_mod, "_fetch_rate_remote", fail)
    with factory() as session:
        result = currency_mod.convert(session, Decimal("5"), "EUR", "RUB")
    assert result.stale
    assert result.converted == Decimal("500.00")


def test_remote_parses_exchangerate_host(monkeypatch) -> None:
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, json={"result": 91.25})

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None, **kwargs):
            return fake_get(url, params=params)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    rate = currency_mod._fetch_rate_remote("USD", "RUB")
    assert rate == Decimal("91.25")
    assert captured["params"]["from"] == "USD"
