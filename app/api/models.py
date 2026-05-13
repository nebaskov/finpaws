"""Database tables, defined with SQLModel so the ORM rows are also Pydantic models."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


_TOUCH_ON_UPDATE: dict[str, Any] = {"onupdate": _utcnow}


class UserRow(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    email: str = Field(index=True, unique=True, max_length=255)
    password_hash: str = Field(max_length=255)
    display_name: str = Field(default="", max_length=128)
    created_at: datetime = Field(default_factory=_utcnow)


class TransactionRow(SQLModel, table=True):
    __tablename__ = "transactions"

    id: str = Field(default_factory=_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", index=True, max_length=64)
    amount: Decimal = Field(max_digits=14, decimal_places=2)
    currency: str = Field(default="RUB", max_length=10)
    description: str
    category: str = Field(max_length=64)
    kind: str = Field(index=True, max_length=16)
    occurred_on: date = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class SavingsGoalRow(SQLModel, table=True):
    __tablename__ = "savings_goals"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", index=True, max_length=64)
    name: str = Field(index=True, max_length=128)
    target_amount: Decimal = Field(max_digits=14, decimal_places=2)
    horizon_months: int
    saved_amount: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=2)


class BudgetPlanRow(SQLModel, table=True):
    __tablename__ = "budget_plans"

    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", primary_key=True, max_length=64)
    monthly_income: Decimal = Field(max_digits=14, decimal_places=2)
    category_limits: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column_kwargs=_TOUCH_ON_UPDATE)


class UserPreferenceRow(SQLModel, table=True):
    __tablename__ = "user_preferences"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", index=True, max_length=64)
    key: str = Field(index=True, max_length=128)
    value: str
    updated_at: datetime = Field(default_factory=_utcnow, sa_column_kwargs=_TOUCH_ON_UPDATE)


class AgentEventRow(SQLModel, table=True):
    __tablename__ = "agent_events"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, max_length=64)
    thread_id: str = Field(index=True, max_length=128)
    kind: str = Field(index=True, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    latency_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow)


class CurrencyRateRow(SQLModel, table=True):
    __tablename__ = "currency_rates"

    pair: str = Field(primary_key=True, max_length=16)
    rate: Decimal = Field(max_digits=20, decimal_places=8)
    fetched_at: datetime = Field(default_factory=_utcnow)


class CategorizationFeedbackRow(SQLModel, table=True):
    __tablename__ = "categorization_feedback"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="users.id", ondelete="CASCADE", index=True, max_length=64)
    keyword: str = Field(index=True, max_length=128)
    category: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
