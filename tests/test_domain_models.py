from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.models import BudgetPlan, SavingsGoal, Transaction, TransactionKind


def test_transaction_to_from_dict() -> None:
    tx = Transaction(
        id="tx-1",
        user_id="u1",
        amount=Decimal("1500.50"),
        currency="RUB",
        description="Продукты",
        category="food",
        kind=TransactionKind.EXPENSE,
        occurred_on=date(2026, 1, 1),
    )

    restored = Transaction.from_dict(tx.to_dict())

    assert restored.id == "tx-1"
    assert restored.amount == Decimal("1500.50")
    assert restored.kind == TransactionKind.EXPENSE


def test_budget_plan_to_from_dict() -> None:
    plan = BudgetPlan(monthly_income=Decimal("100000"), category_limits={"food": Decimal("20000")})

    restored = BudgetPlan.from_dict(plan.to_dict())

    assert restored.monthly_income == Decimal("100000")
    assert restored.category_limits["food"] == Decimal("20000")


def test_goal_to_from_dict() -> None:
    goal = SavingsGoal(name="Подушка", target_amount=Decimal("300000"), horizon_months=12)

    restored = SavingsGoal.from_dict(goal.to_dict())

    assert restored.name == "Подушка"
    assert restored.saved_amount == Decimal("0")
