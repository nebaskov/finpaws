from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from prometheus_client import CollectorRegistry
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import col

from app.agent.kb import KnowledgeBase, build_kb
from app.agent.memory import list_preferences, set_preference
from app.agent.orchestrator import recent_events, run_agent
from app.api.models import BudgetPlanRow, SavingsGoalRow, TransactionRow
from app.api.schemas import (
    AgentEventOut,
    BudgetPlanIn,
    BudgetPlanOut,
    ExpenseIn,
    GoalCreateIn,
    GoalOut,
    GoalProgressIn,
    IncomeIn,
    ReportOut,
    TransactionOut,
)
from app.auth.routes import MeOut, make_current_user_dep, make_router
from app.config import SETTINGS
from app.db import Base, SessionLocal, engine
from app.domain import planning
from app.domain.models import TransactionKind
from app.observability.logging import configure_logging
from app.services.categorizer import categorize


class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None


class ChatOut(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]]
    pii_redacted: bool
    injection_suspected: bool
    toxic: bool
    toxicity_score: float
    latency_ms: int


class PreferenceIn(BaseModel):
    key: str
    value: str


def _install_rate_limiter(app: FastAPI) -> None:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[SETTINGS.api_rate_limit] if SETTINGS.api_rate_limit_enabled else [],
        enabled=SETTINGS.api_rate_limit_enabled,
        headers_enabled=True,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


def _install_metrics(app: FastAPI) -> None:
    if not SETTINGS.metrics_enabled:
        return
    # A per-app registry keeps create_app() reusable (tests build many apps) and avoids
    # polluting prometheus_client's global REGISTRY.
    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/health"],
        registry=CollectorRegistry(),
    ).instrument(app).expose(app, include_in_schema=False)


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    db_engine: Engine | None = None,
    kb: KnowledgeBase | None = None,
) -> FastAPI:
    configure_logging()
    active_factory = session_factory or SessionLocal
    active_engine = db_engine or engine
    active_kb = kb or build_kb()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(bind=active_engine)
        yield

    app = FastAPI(title="FinPaws API", version="0.2.0", lifespan=lifespan)

    def get_session() -> Iterator[Session]:
        session = active_factory()
        try:
            yield session
        finally:
            session.close()

    current_user = make_current_user_dep(get_session)
    app.include_router(make_router(get_session))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me", response_model=MeOut)
    def me(user: MeOut = Depends(current_user)) -> MeOut:
        return user

    @app.post("/transactions/expense", response_model=TransactionOut, status_code=201)
    def add_expense(
        payload: ExpenseIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> TransactionOut:
        row = TransactionRow(
            user_id=user.user_id,
            amount=payload.amount,
            currency=payload.currency,
            description=payload.description,
            category=categorize(payload.description).value,
            kind=TransactionKind.EXPENSE.value,
            occurred_on=payload.occurred_on or date.today(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return TransactionOut.model_validate(row, from_attributes=True)

    @app.post("/transactions/income", response_model=TransactionOut, status_code=201)
    def add_income(
        payload: IncomeIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> TransactionOut:
        row = TransactionRow(
            user_id=user.user_id,
            amount=payload.amount,
            currency=payload.currency,
            description=payload.description,
            category="income",
            kind=TransactionKind.INCOME.value,
            occurred_on=payload.occurred_on or date.today(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return TransactionOut.model_validate(row, from_attributes=True)

    @app.post("/budget/plan", response_model=BudgetPlanOut)
    def build_plan(
        payload: BudgetPlanIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> BudgetPlanOut:
        horizon = date.today() - timedelta(days=90)
        rows = (
            session.execute(
                select(TransactionRow).where(
                    col(TransactionRow.user_id) == user.user_id,
                    col(TransactionRow.kind) == TransactionKind.EXPENSE.value,
                    col(TransactionRow.occurred_on) >= horizon,
                )
            )
            .scalars()
            .all()
        )
        history = planning.totals_by_category((row.category, row.amount) for row in rows)
        limits = planning.budget_limits(payload.monthly_income, history)
        stored_limits = {category: str(limit) for category, limit in limits.items()}

        plan = session.get(BudgetPlanRow, user.user_id)
        if plan is None:
            session.add(
                BudgetPlanRow(
                    user_id=user.user_id,
                    monthly_income=payload.monthly_income,
                    category_limits=stored_limits,
                )
            )
        else:
            plan.monthly_income = payload.monthly_income
            plan.category_limits = stored_limits
        session.commit()

        return BudgetPlanOut(
            user_id=user.user_id,
            monthly_income=payload.monthly_income,
            category_limits=limits,
        )

    @app.post("/goals", response_model=GoalOut, status_code=201)
    def add_goal(
        payload: GoalCreateIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> GoalOut:
        goal = SavingsGoalRow(
            user_id=user.user_id,
            name=payload.name,
            target_amount=payload.target_amount,
            horizon_months=payload.horizon_months,
        )
        session.add(goal)
        session.commit()
        session.refresh(goal)
        return GoalOut.model_validate(goal, from_attributes=True)

    @app.post("/goals/progress", response_model=GoalOut)
    def add_goal_progress(
        payload: GoalProgressIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> GoalOut:
        goal = session.execute(
            select(SavingsGoalRow).where(
                col(SavingsGoalRow.user_id) == user.user_id,
                col(SavingsGoalRow.name) == payload.name,
            )
        ).scalar_one_or_none()
        if goal is None:
            raise HTTPException(status_code=404, detail="Goal not found")

        goal.saved_amount += payload.amount
        session.commit()
        session.refresh(goal)
        return GoalOut.model_validate(goal, from_attributes=True)

    @app.get("/report", response_model=ReportOut)
    def report(
        days: int = Query(default=30, ge=1, le=3650),
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> ReportOut:
        start_date = date.today() - timedelta(days=days)
        rows = (
            session.execute(
                select(TransactionRow).where(
                    col(TransactionRow.user_id) == user.user_id,
                    col(TransactionRow.occurred_on) >= start_date,
                )
            )
            .scalars()
            .all()
        )
        totals = planning.summarize((row.kind, row.category, row.amount) for row in rows).rounded()

        goal_rows = (
            session.execute(select(SavingsGoalRow).where(col(SavingsGoalRow.user_id) == user.user_id))
            .scalars()
            .all()
        )
        goals = [GoalOut.model_validate(goal, from_attributes=True) for goal in goal_rows]

        return ReportOut(
            user_id=user.user_id,
            days=days,
            income=totals.income,
            spent=totals.spent,
            balance=totals.balance,
            by_category=totals.by_category,
            goals=goals,
        )

    @app.post("/chat", response_model=ChatOut)
    def chat(payload: ChatIn, user: MeOut = Depends(current_user)) -> ChatOut:
        result = run_agent(
            session_factory=active_factory,
            kb=active_kb,
            user_id=user.user_id,
            message=payload.message,
            thread_id=payload.thread_id,
        )
        return ChatOut.model_validate(result, from_attributes=True)

    @app.get("/preferences")
    def get_prefs(
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> dict[str, str]:
        return list_preferences(session, user.user_id)

    @app.put("/preferences")
    def put_pref(
        payload: PreferenceIn,
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> dict[str, bool]:
        return {"saved": set_preference(session, user.user_id, payload.key, payload.value)}

    @app.get("/agent/events", response_model=list[AgentEventOut])
    def agent_events(
        limit: int = Query(default=20, ge=1, le=200),
        session: Session = Depends(get_session),
        user: MeOut = Depends(current_user),
    ) -> list[AgentEventOut]:
        return recent_events(session, user.user_id, limit=limit)

    _install_rate_limiter(app)
    _install_metrics(app)
    return app


app = create_app()


def run() -> None:
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)
