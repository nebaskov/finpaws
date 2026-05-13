from __future__ import annotations

from decimal import Decimal

from app.services.finance import FinanceService
from app.services.storage import JsonStorage


def test_add_expense_persists_and_categorizes(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)

    tx = service.add_expense(Decimal("1500"), "Продукты в магазине")

    assert tx.category == "food"
    snapshot = service.dashboard(days=1)
    assert snapshot.spent == Decimal("1500")


def test_build_budget_plan_from_history(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)
    # Three distinct categories — enough history to scale, not fall back to defaults.
    service.add_expense(Decimal("1000"), "taxi")
    service.add_expense(Decimal("3000"), "groceries")
    service.add_expense(Decimal("4000"), "rent")

    plan = service.build_budget_plan(Decimal("10000"))

    total_limits = sum(plan.category_limits.values(), start=Decimal("0"))
    assert total_limits == Decimal("8000.00")
    assert {"transport", "food", "housing"} <= set(plan.category_limits)


def test_build_budget_plan_sparse_history_uses_defaults(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)
    service.add_expense(Decimal("1000"), "taxi")  # only one category

    plan = service.build_budget_plan(Decimal("100000"))

    # Sparse history → fall back to the standard 30/20/10/... split, not 100% transport.
    assert plan.category_limits["housing"] == Decimal("30000.00")
    assert plan.category_limits["food"] == Decimal("20000.00")
    assert plan.category_limits["transport"] == Decimal("10000.00")


def test_build_goal_duplicate_name_raises(tmp_path) -> None:
    import pytest

    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)
    service.add_goal("Подушка", Decimal("100000"), 12)
    with pytest.raises(ValueError, match="already exists"):
        service.add_goal("Подушка", Decimal("200000"), 6)


def test_goal_progress(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)
    service.add_goal("Vacation", Decimal("120000"), 12)

    goal = service.add_goal_progress("Vacation", Decimal("10000"))

    assert goal.saved_amount == Decimal("10000")


def test_yandex_taxi_is_transport(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)

    tx = service.add_expense(Decimal("650"), "Яндекс Такси до офиса")

    assert tx.category == "transport"


def test_ozon_is_shopping(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    service = FinanceService(storage=storage)

    tx = service.add_expense(Decimal("2300"), "Покупка на Ozon")

    assert tx.category == "shopping"
