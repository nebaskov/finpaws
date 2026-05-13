from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.domain import planning
from app.domain.models import BudgetPlan, SavingsGoal, Transaction, TransactionKind
from app.services.categorizer import categorize
from app.services.storage import JsonStorage


@dataclass(slots=True)
class Dashboard:
    spent: Decimal
    income: Decimal
    by_category: dict[str, Decimal]
    goals: list[SavingsGoal]


@dataclass(slots=True)
class _State:
    """In-memory view of the JSON file, with proper domain types."""

    transactions: list[Transaction] = field(default_factory=list)
    budget_plan: BudgetPlan | None = None
    goals: list[SavingsGoal] = field(default_factory=list)

    @classmethod
    def from_storage(cls, raw: dict[str, Any]) -> _State:
        budget_plan = raw.get("budget_plan")
        return cls(
            transactions=[Transaction.from_dict(item) for item in raw.get("transactions", [])],
            budget_plan=BudgetPlan.from_dict(budget_plan) if budget_plan is not None else None,
            goals=[SavingsGoal.from_dict(item) for item in raw.get("goals", [])],
        )

    def to_storage(self) -> dict[str, Any]:
        return {
            "transactions": [tx.to_dict() for tx in self.transactions],
            "budget_plan": self.budget_plan.to_dict() if self.budget_plan is not None else None,
            "goals": [goal.to_dict() for goal in self.goals],
        }


class FinanceService:
    def __init__(self, storage: JsonStorage, user_id: str = "demo") -> None:
        self._storage = storage
        self._user_id = user_id

    def add_expense(self, amount: Decimal, description: str, currency: str = "RUB") -> Transaction:
        state = self._load_state()
        tx = Transaction(
            id=str(uuid4()),
            user_id=self._user_id,
            amount=amount,
            currency=currency,
            description=description,
            category=categorize(description).value,
            kind=TransactionKind.EXPENSE,
            occurred_on=date.today(),
        )
        state.transactions.append(tx)
        self._save_state(state)
        return tx

    def add_income(self, amount: Decimal, description: str = "income", currency: str = "RUB") -> Transaction:
        state = self._load_state()
        tx = Transaction(
            id=str(uuid4()),
            user_id=self._user_id,
            amount=amount,
            currency=currency,
            description=description,
            category="income",
            kind=TransactionKind.INCOME,
            occurred_on=date.today(),
        )
        state.transactions.append(tx)
        self._save_state(state)
        return tx

    def build_budget_plan(self, monthly_income: Decimal) -> BudgetPlan:
        state = self._load_state()
        horizon = date.today() - timedelta(days=90)
        history = planning.totals_by_category(
            (tx.category, tx.amount)
            for tx in state.transactions
            if tx.kind == TransactionKind.EXPENSE and tx.occurred_on >= horizon
        )
        plan = BudgetPlan(
            monthly_income=monthly_income,
            category_limits=planning.budget_limits(monthly_income, history),
        )
        state.budget_plan = plan
        self._save_state(state)
        return plan

    def add_goal(self, name: str, target_amount: Decimal, horizon_months: int) -> SavingsGoal:
        state = self._load_state()
        if any(g.name == name for g in state.goals):
            raise ValueError(f"Goal '{name}' already exists")
        goal = SavingsGoal(name=name, target_amount=target_amount, horizon_months=horizon_months)
        state.goals.append(goal)
        self._save_state(state)
        return goal

    def add_goal_progress(self, name: str, amount: Decimal) -> SavingsGoal:
        state = self._load_state()
        for goal in state.goals:
            if goal.name == name:
                goal.saved_amount += amount
                self._save_state(state)
                return goal
        raise ValueError(f"Goal '{name}' not found")

    def dashboard(self, days: int = 30) -> Dashboard:
        state = self._load_state()
        start_date = date.today() - timedelta(days=days)
        totals = planning.summarize(
            (tx.kind, tx.category, tx.amount) for tx in state.transactions if tx.occurred_on >= start_date
        )
        return Dashboard(
            spent=totals.spent,
            income=totals.income,
            by_category=totals.by_category,
            goals=state.goals,
        )

    def _load_state(self) -> _State:
        return _State.from_storage(self._storage.load())

    def _save_state(self, state: _State) -> None:
        self._storage.save(state.to_storage())
