"""Core finance domain types shared by the CLI service, the API, and the agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class TransactionKind(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class ExpenseCategory(StrEnum):
    FOOD = "food"
    TRANSPORT = "transport"
    HOUSING = "housing"
    UTILITIES = "utilities"
    HEALTH = "health"
    EDUCATION = "education"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


@dataclass(slots=True)
class Transaction:
    id: str
    user_id: str
    amount: Decimal
    currency: str
    description: str
    category: str
    kind: TransactionKind
    occurred_on: date

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "description": self.description,
            "category": self.category,
            "kind": self.kind.value,
            "occurred_on": self.occurred_on.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> Transaction:
        return cls(
            id=payload["id"],
            user_id=payload["user_id"],
            amount=Decimal(payload["amount"]),
            currency=payload["currency"],
            description=payload["description"],
            category=payload["category"],
            kind=TransactionKind(payload["kind"]),
            occurred_on=date.fromisoformat(payload["occurred_on"]),
        )


@dataclass(slots=True)
class BudgetPlan:
    monthly_income: Decimal
    category_limits: dict[str, Decimal]

    def to_dict(self) -> dict[str, Any]:
        return {
            "monthly_income": str(self.monthly_income),
            "category_limits": {key: str(value) for key, value in self.category_limits.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BudgetPlan:
        raw_limits: Any = payload.get("category_limits") or {}
        limits = {str(key): Decimal(str(value)) for key, value in dict(raw_limits).items()}
        return cls(monthly_income=Decimal(str(payload["monthly_income"])), category_limits=limits)


@dataclass(slots=True)
class SavingsGoal:
    name: str
    target_amount: Decimal
    horizon_months: int
    saved_amount: Decimal = Decimal("0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target_amount": str(self.target_amount),
            "horizon_months": self.horizon_months,
            "saved_amount": str(self.saved_amount),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SavingsGoal:
        return cls(
            name=str(payload["name"]),
            target_amount=Decimal(str(payload["target_amount"])),
            horizon_months=int(payload["horizon_months"]),
            saved_amount=Decimal(str(payload.get("saved_amount", "0"))),
        )
