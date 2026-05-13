from __future__ import annotations

import shutil
import uuid

from app.agent.kb import KnowledgeBase
from app.agent.tools import build_tools
from app.api.models import UserRow
from app.db import Base
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


def _user(factory) -> str:
    uid = str(uuid.uuid4())
    with factory() as s:
        s.add(UserRow(id=uid, email=f"{uid}@x.io", password_hash="!"))
        s.commit()
    return uid


def _by_name(tools, name):
    return next(t for t in tools if t.name == name)


def test_tools_full_lifecycle() -> None:
    factory = _factory()
    user_id = _user(factory)
    tools = build_tools(factory, user_id, KnowledgeBase(None))

    income = _by_name(tools, "add_income").invoke(
        {"amount": "100000", "description": "Зарплата", "currency": "RUB"}
    )
    assert income["currency"] == "RUB"

    expense = _by_name(tools, "add_expense").invoke(
        {"amount": "850", "description": "Яндекс Такси", "currency": "RUB"}
    )
    assert expense["category"] == "transport"

    report = _by_name(tools, "get_report").invoke({"days": 30})
    assert report["income"] == "100000.00"
    assert report["spent"] == "850.00"

    plan = _by_name(tools, "build_budget").invoke({"monthly_income": "120000"})
    assert "category_limits" in plan

    goal = _by_name(tools, "add_goal").invoke(
        {"name": "Подушка", "target_amount": "300000", "horizon_months": 12}
    )
    assert goal["per_month"] == "25000.00"

    progress = _by_name(tools, "update_goal_progress").invoke({"name": "Подушка", "amount": "10000"})
    assert progress["progress_percent"].startswith("3.")

    goals = _by_name(tools, "list_goals").invoke({})
    assert [g["name"] for g in goals["goals"]] == ["Подушка"]
    assert goals["goals"][0]["horizon_months"] == 12

    dup = _by_name(tools, "add_goal").invoke({"name": "Подушка", "target_amount": "1", "horizon_months": 1})
    assert "error" in dup

    missing = _by_name(tools, "update_goal_progress").invoke({"name": "Нет такой", "amount": "1"})
    assert "error" in missing

    pref_set = _by_name(tools, "set_preference").invoke({"key": "tz", "value": "Europe/Moscow"})
    assert pref_set["saved"] is True
    pref_get = _by_name(tools, "get_preference").invoke({"key": "tz"})
    assert pref_get["value"] == "Europe/Moscow"
    pref_list = _by_name(tools, "list_preferences").invoke({})
    assert pref_list["preferences"]["tz"] == "Europe/Moscow"


def test_search_advice_uses_kb() -> None:
    class FakeKB(KnowledgeBase):
        def __init__(self) -> None:
            super().__init__(None)

        def search(self, query, k=3):
            from app.agent.kb import KBHit

            return [KBHit(doc_id="x", title="X", snippet="snip", score=1.0)]

    factory = _factory()
    user_id = _user(factory)
    tools = build_tools(factory, user_id, FakeKB())
    out = _by_name(tools, "search_advice").invoke({"query": "fund"})
    assert out["hits"][0]["doc_id"] == "x"


def test_currency_tool_handles_error(monkeypatch) -> None:
    factory = _factory()
    user_id = _user(factory)
    tools = build_tools(factory, user_id, KnowledgeBase(None))

    from app.integrations import currency as currency_mod

    def fail(*a, **k):
        raise currency_mod.CurrencyError("api down")

    monkeypatch.setattr(currency_mod, "_fetch_rate_remote", fail)
    out = _by_name(tools, "convert_currency").invoke(
        {"amount": "10", "from_currency": "USD", "to_currency": "RUB"}
    )
    assert "error" in out


def test_hledger_query_missing_binary(monkeypatch) -> None:
    factory = _factory()
    user_id = _user(factory)
    tools = build_tools(factory, user_id, KnowledgeBase(None))

    monkeypatch.setattr(shutil, "which", lambda _: None)
    out = _by_name(tools, "hledger_query").invoke({"command": "balance"})
    assert "error" in out
