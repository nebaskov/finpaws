from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import col

from app.agent import memory as prefs
from app.agent.kb import KnowledgeBase
from app.api.models import (
    BudgetPlanRow,
    CategorizationFeedbackRow,
    SavingsGoalRow,
    TransactionRow,
)
from app.domain import planning
from app.domain.models import TransactionKind
from app.integrations import currency as currency_mod
from app.integrations import hledger as hledger_mod
from app.services.categorizer import categorize

# --- LLM-facing argument schemas (validation + tool-call schema for the model) ----------


class _AmountIn(BaseModel):
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=2, max_length=256)
    currency: str = Field(default="RUB", min_length=3, max_length=8)
    occurred_on: date | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return Decimal(value.replace(",", "."))
            except InvalidOperation as exc:
                raise ValueError("amount must be numeric") from exc
        return value


class AddExpenseIn(_AmountIn):
    pass


class AddIncomeIn(_AmountIn):
    pass


class GetReportIn(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)


class BuildBudgetIn(BaseModel):
    monthly_income: Decimal = Field(gt=0)


class AddGoalIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    target_amount: Decimal = Field(gt=0)
    horizon_months: int = Field(gt=0, le=600)


class GoalProgressIn(BaseModel):
    name: str
    amount: Decimal = Field(gt=0)


class ConvertCurrencyIn(BaseModel):
    amount: Decimal = Field(gt=0)
    from_currency: str = Field(min_length=3, max_length=8)
    to_currency: str = Field(min_length=3, max_length=8)


class SearchAdviceIn(BaseModel):
    query: str = Field(min_length=2, max_length=256)
    k: int = Field(default=3, ge=1, le=10)


class SetPreferenceIn(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=512)


class GetPreferenceIn(BaseModel):
    key: str = Field(min_length=1, max_length=128)


class ListPreferencesIn(BaseModel):
    pass


class ListGoalsIn(BaseModel):
    pass


class HledgerQueryIn(BaseModel):
    command: str = Field(default="balance", pattern=r"^(balance|register)$")
    account: str | None = None
    period: str | None = None


# --- tool factory ----------------------------------------------------------------------


def _today() -> date:
    return date.today()


def _expense_category(session: Session, user_id: str, description: str) -> str:
    lowered = description.lower()
    try:
        overrides = (
            session.execute(
                select(CategorizationFeedbackRow).where(col(CategorizationFeedbackRow.user_id) == user_id)
            )
            .scalars()
            .all()
        )
        for row in overrides:
            if row.keyword.lower() in lowered:
                return row.category
    except SQLAlchemyError:
        logger.exception("category override lookup failed")
        session.rollback()
    return categorize(description).value


def build_tools(
    session_factory: sessionmaker[Session],
    user_id: str,
    kb: KnowledgeBase,
) -> list[StructuredTool]:
    """Build the agent's tool belt, bound to a specific user and DB session factory."""
    bound = logger.bind(user_id=user_id)

    def add_expense(
        amount: Decimal,
        description: str,
        currency: str = "RUB",
        occurred_on: date | None = None,
    ) -> dict[str, Any]:
        when = occurred_on or _today()
        with session_factory() as session:
            category = _expense_category(session, user_id, description)
            row = TransactionRow(
                user_id=user_id,
                amount=amount,
                currency=currency.upper(),
                description=description,
                category=category,
                kind=TransactionKind.EXPENSE.value,
                occurred_on=when,
            )
            try:
                session.add(row)
                session.commit()
                session.refresh(row)
            except SQLAlchemyError as exc:
                bound.exception("add_expense failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            hledger_mod.append_expense(amount, currency.upper(), description, category, when)
            return {
                "id": row.id,
                "amount": str(row.amount),
                "currency": row.currency,
                "category": row.category,
                "description": row.description,
                "occurred_on": row.occurred_on.isoformat(),
            }

    def add_income(
        amount: Decimal,
        description: str,
        currency: str = "RUB",
        occurred_on: date | None = None,
    ) -> dict[str, Any]:
        when = occurred_on or _today()
        with session_factory() as session:
            row = TransactionRow(
                user_id=user_id,
                amount=amount,
                currency=currency.upper(),
                description=description,
                category="income",
                kind=TransactionKind.INCOME.value,
                occurred_on=when,
            )
            try:
                session.add(row)
                session.commit()
                session.refresh(row)
            except SQLAlchemyError as exc:
                bound.exception("add_income failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            hledger_mod.append_income(amount, currency.upper(), description, when)
            return {
                "id": row.id,
                "amount": str(row.amount),
                "currency": row.currency,
                "description": row.description,
                "occurred_on": row.occurred_on.isoformat(),
            }

    def get_report(days: int = 30) -> dict[str, Any]:
        start = _today() - timedelta(days=days)
        with session_factory() as session:
            try:
                rows = (
                    session.execute(
                        select(TransactionRow).where(
                            col(TransactionRow.user_id) == user_id,
                            col(TransactionRow.occurred_on) >= start,
                        )
                    )
                    .scalars()
                    .all()
                )
            except SQLAlchemyError as exc:
                bound.exception("get_report failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            totals = planning.summarize((row.kind, row.category, row.amount) for row in rows).rounded()
        return {
            "days": days,
            "income": str(totals.income),
            "spent": str(totals.spent),
            "balance": str(totals.balance),
            "by_category": {category: str(amount) for category, amount in totals.by_category.items()},
            "transactions_count": totals.transactions_count,
        }

    def build_budget(monthly_income: Decimal) -> dict[str, Any]:
        horizon = _today() - timedelta(days=90)
        with session_factory() as session:
            try:
                rows = (
                    session.execute(
                        select(TransactionRow).where(
                            col(TransactionRow.user_id) == user_id,
                            col(TransactionRow.kind) == TransactionKind.EXPENSE.value,
                            col(TransactionRow.occurred_on) >= horizon,
                        )
                    )
                    .scalars()
                    .all()
                )
            except SQLAlchemyError as exc:
                bound.exception("build_budget read failed")
                session.rollback()
                return {"error": f"db error: {exc}"}

            history = planning.totals_by_category((row.category, row.amount) for row in rows)
            limits = planning.budget_limits(monthly_income, history)
            stored_limits = {category: str(limit) for category, limit in limits.items()}

            try:
                plan = session.get(BudgetPlanRow, user_id)
                if plan is None:
                    session.add(
                        BudgetPlanRow(
                            user_id=user_id,
                            monthly_income=monthly_income,
                            category_limits=stored_limits,
                        )
                    )
                else:
                    plan.monthly_income = monthly_income
                    plan.category_limits = stored_limits
                session.commit()
            except SQLAlchemyError as exc:
                bound.exception("build_budget write failed")
                session.rollback()
                return {"error": f"db error: {exc}"}

        return {"monthly_income": str(monthly_income), "category_limits": stored_limits}

    def add_goal(name: str, target_amount: Decimal, horizon_months: int) -> dict[str, Any]:
        with session_factory() as session:
            try:
                existing = session.execute(
                    select(SavingsGoalRow).where(
                        col(SavingsGoalRow.user_id) == user_id,
                        col(SavingsGoalRow.name) == name,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return {"error": f"goal '{name}' already exists"}
                row = SavingsGoalRow(
                    user_id=user_id,
                    name=name,
                    target_amount=target_amount,
                    horizon_months=horizon_months,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            except SQLAlchemyError as exc:
                bound.exception("add_goal failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            per_month = (target_amount / Decimal(horizon_months)).quantize(planning.CENTS)
            return {
                "name": row.name,
                "target_amount": str(row.target_amount),
                "horizon_months": row.horizon_months,
                "per_month": str(per_month),
            }

    def update_goal_progress(name: str, amount: Decimal) -> dict[str, Any]:
        with session_factory() as session:
            try:
                row = session.execute(
                    select(SavingsGoalRow).where(
                        col(SavingsGoalRow.user_id) == user_id,
                        col(SavingsGoalRow.name) == name,
                    )
                ).scalar_one_or_none()
                if row is None:
                    return {"error": f"goal '{name}' not found"}
                row.saved_amount += amount
                session.commit()
                session.refresh(row)
            except SQLAlchemyError as exc:
                bound.exception("update_goal_progress failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            progress = (row.saved_amount / row.target_amount * Decimal("100")).quantize(planning.CENTS)
            return {
                "name": row.name,
                "saved_amount": str(row.saved_amount),
                "target_amount": str(row.target_amount),
                "progress_percent": str(progress),
            }

    def list_goals() -> dict[str, Any]:
        with session_factory() as session:
            try:
                rows = (
                    session.execute(select(SavingsGoalRow).where(col(SavingsGoalRow.user_id) == user_id))
                    .scalars()
                    .all()
                )
            except SQLAlchemyError as exc:
                bound.exception("list_goals failed")
                session.rollback()
                return {"error": f"db error: {exc}"}
            return {
                "goals": [
                    {
                        "name": row.name,
                        "target_amount": str(row.target_amount),
                        "saved_amount": str(row.saved_amount),
                        "horizon_months": row.horizon_months,
                    }
                    for row in rows
                ]
            }

    def convert_currency(amount: Decimal, from_currency: str, to_currency: str) -> dict[str, Any]:
        with session_factory() as session:
            try:
                result = currency_mod.convert(session, amount, from_currency, to_currency)
            except currency_mod.CurrencyError as exc:
                return {"error": f"currency unavailable: {exc}"}
            return result.model_dump(mode="json")

    def search_advice(query: str, k: int = 3) -> dict[str, Any]:
        return {"hits": [hit.model_dump() for hit in kb.search(query, k=k)]}

    def get_preference(key: str) -> dict[str, Any]:
        with session_factory() as session:
            return {"key": key, "value": prefs.get_preference(session, user_id, key)}

    def set_preference(key: str, value: str) -> dict[str, Any]:
        with session_factory() as session:
            return {"key": key, "saved": prefs.set_preference(session, user_id, key, value)}

    def list_preferences() -> dict[str, Any]:
        with session_factory() as session:
            return {"preferences": prefs.list_preferences(session, user_id)}

    def hledger_query(
        command: str = "balance",
        account: str | None = None,
        period: str | None = None,
    ) -> dict[str, Any]:
        try:
            output = (
                hledger_mod.balance(account)
                if command == "balance"
                else hledger_mod.register(account, period)
            )
        except hledger_mod.HledgerError as exc:
            return {"error": str(exc)}
        return {"command": command, "output": output}

    return [
        StructuredTool.from_function(
            func=add_expense,
            name="add_expense",
            description="Записать расход. amount > 0, описание свободным текстом, категория определяется автоматически.",
            args_schema=AddExpenseIn,
        ),
        StructuredTool.from_function(
            func=add_income,
            name="add_income",
            description="Записать доход (зарплата, перевод и т.п.).",
            args_schema=AddIncomeIn,
        ),
        StructuredTool.from_function(
            func=get_report,
            name="get_report",
            description="Сводка по тратам и доходам за N дней с разбивкой по категориям.",
            args_schema=GetReportIn,
        ),
        StructuredTool.from_function(
            func=build_budget,
            name="build_budget",
            description="Построить месячный бюджетный план для заданного дохода. Использует историю трат, если есть.",
            args_schema=BuildBudgetIn,
        ),
        StructuredTool.from_function(
            func=add_goal,
            name="add_goal",
            description="Создать цель накоплений (имя, целевая сумма, горизонт в месяцах).",
            args_schema=AddGoalIn,
        ),
        StructuredTool.from_function(
            func=update_goal_progress,
            name="update_goal_progress",
            description="Зафиксировать прогресс по цели накоплений (нужно точное имя цели — см. list_goals).",
            args_schema=GoalProgressIn,
        ),
        StructuredTool.from_function(
            func=list_goals,
            name="list_goals",
            description="Список всех целей накоплений пользователя (имя, целевая и накопленная сумма, горизонт).",
            args_schema=ListGoalsIn,
        ),
        StructuredTool.from_function(
            func=convert_currency,
            name="convert_currency",
            description=(
                "Конвертировать сумму между валютами по актуальному курсу. "
                "При недоступности API использует кэш и помечает stale=True."
            ),
            args_schema=ConvertCurrencyIn,
        ),
        StructuredTool.from_function(
            func=search_advice,
            name="search_advice",
            description="Поиск в базе финансовых советов (RAG). Возвращает релевантные сниппеты.",
            args_schema=SearchAdviceIn,
        ),
        StructuredTool.from_function(
            func=get_preference,
            name="get_preference",
            description="Получить пользовательскую настройку (предпочтение) по ключу.",
            args_schema=GetPreferenceIn,
        ),
        StructuredTool.from_function(
            func=set_preference,
            name="set_preference",
            description="Сохранить пользовательскую настройку (предпочтение).",
            args_schema=SetPreferenceIn,
        ),
        StructuredTool.from_function(
            func=list_preferences,
            name="list_preferences",
            description="Вернуть все сохранённые предпочтения пользователя.",
            args_schema=ListPreferencesIn,
        ),
        StructuredTool.from_function(
            func=hledger_query,
            name="hledger_query",
            description="Запустить hledger CLI (balance/register) против журнала пользователя.",
            args_schema=HledgerQueryIn,
        ),
    ]
