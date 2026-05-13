from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ExpenseIn(BaseModel):
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=2)
    currency: str = "RUB"
    occurred_on: date | None = None


class IncomeIn(BaseModel):
    amount: Decimal = Field(gt=0)
    description: str = "Доход"
    currency: str = "RUB"
    occurred_on: date | None = None


class TransactionOut(BaseModel):
    id: str
    user_id: str
    amount: Decimal
    currency: str
    description: str
    category: str
    kind: str
    occurred_on: date


class BudgetPlanIn(BaseModel):
    monthly_income: Decimal = Field(gt=0)


class BudgetPlanOut(BaseModel):
    user_id: str
    monthly_income: Decimal
    category_limits: dict[str, Decimal]


class GoalCreateIn(BaseModel):
    name: str = Field(min_length=2)
    target_amount: Decimal = Field(gt=0)
    horizon_months: int = Field(gt=0)


class GoalProgressIn(BaseModel):
    name: str
    amount: Decimal = Field(gt=0)


class GoalOut(BaseModel):
    user_id: str
    name: str
    target_amount: Decimal
    horizon_months: int
    saved_amount: Decimal


class ReportOut(BaseModel):
    user_id: str
    days: int
    income: Decimal
    spent: Decimal
    balance: Decimal
    by_category: dict[str, Decimal]
    goals: list[GoalOut]


class AgentEventOut(BaseModel):
    id: int
    kind: str
    thread_id: str
    payload: dict[str, Any]
    latency_ms: int
    created_at: datetime
