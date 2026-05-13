from __future__ import annotations

from app.agent.kb import KnowledgeBase
from app.api.main import create_app, run
from app.db import Base
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _create_client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=SessionLocal, db_engine=engine, kb=KnowledgeBase(None))
    return TestClient(app)


def _register(client: TestClient, email: str = "u@example.com", password: str = "Password123!") -> str:
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health() -> None:
    client = _create_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_and_me() -> None:
    client = _create_client()
    token = _register(client)
    me = client.get("/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["email"] == "u@example.com"


def test_login_wrong_password() -> None:
    client = _create_client()
    _register(client, "x@example.com", "Password123!")
    bad = client.post("/auth/login", json={"email": "x@example.com", "password": "WrongPass1!"})
    assert bad.status_code == 401


def test_protected_endpoint_requires_token() -> None:
    client = _create_client()
    resp = client.get("/report")
    assert resp.status_code == 401


def test_transactions_and_report() -> None:
    client = _create_client()
    token = _register(client, "tx@example.com")
    h = _auth(token)

    income = client.post(
        "/transactions/income",
        json={"amount": "100000", "description": "Зарплата", "currency": "RUB"},
        headers=h,
    )
    expense = client.post(
        "/transactions/expense",
        json={"amount": "700", "description": "Яндекс Такси до дома", "currency": "RUB"},
        headers=h,
    )
    report = client.get("/report?days=30", headers=h)

    assert income.status_code == 201
    assert expense.status_code == 201
    assert expense.json()["category"] == "transport"
    assert report.status_code == 200
    body = report.json()
    assert body["income"] == "100000.00"
    assert body["spent"] == "700.00"
    assert body["balance"] == "99300.00"
    assert body["by_category"]["transport"] == "700.00"


def test_budget_default_and_history() -> None:
    client = _create_client()
    token = _register(client, "budget@example.com")
    h = _auth(token)

    first = client.post("/budget/plan", json={"monthly_income": "120000"}, headers=h)
    assert first.status_code == 200
    assert first.json()["category_limits"]["housing"] == "36000.00"

    # Three distinct categories — otherwise the planner falls back to defaults (see the sparse test).
    for amount, desc in (("6000", "Продукты"), ("2000", "Яндекс Такси"), ("4000", "Аренда")):
        r = client.post(
            "/transactions/expense",
            json={"amount": amount, "description": desc, "currency": "RUB"},
            headers=h,
        )
        assert r.status_code == 201

    second = client.post("/budget/plan", json={"monthly_income": "100000"}, headers=h)
    limits = second.json()["category_limits"]
    # food share = 6000/12000 → 0.5 * 100000 * 0.8 = 40000
    assert limits["food"] == "40000.00"
    assert limits["transport"] == "13333.33"
    assert limits["housing"] == "26666.67"


def test_budget_sparse_history_falls_back_to_defaults() -> None:
    client = _create_client()
    token = _register(client, "sparse@example.com")
    h = _auth(token)
    client.post(
        "/transactions/expense",
        json={"amount": "6000", "description": "Продукты", "currency": "RUB"},
        headers=h,
    )
    plan = client.post("/budget/plan", json={"monthly_income": "100000"}, headers=h).json()
    # One category alone isn't a budget — should be the standard split, not 100% food.
    assert plan["category_limits"]["housing"] == "30000.00"
    assert plan["category_limits"]["food"] == "20000.00"


def test_goals_progress_and_not_found() -> None:
    client = _create_client()
    token = _register(client, "goal@example.com")
    h = _auth(token)

    created = client.post(
        "/goals",
        json={"name": "Подушка", "target_amount": "300000", "horizon_months": 12},
        headers=h,
    )
    updated = client.post(
        "/goals/progress",
        json={"name": "Подушка", "amount": "25000"},
        headers=h,
    )
    missing = client.post(
        "/goals/progress",
        json={"name": "Нет", "amount": "1000"},
        headers=h,
    )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["saved_amount"] == "25000.00"
    assert missing.status_code == 404


def test_preferences_roundtrip() -> None:
    client = _create_client()
    token = _register(client, "pref@example.com")
    h = _auth(token)

    put = client.put("/preferences", json={"key": "base_currency", "value": "RUB"}, headers=h)
    assert put.status_code == 200
    assert put.json() == {"saved": True}

    got = client.get("/preferences", headers=h)
    assert got.status_code == 200
    assert got.json()["base_currency"] == "RUB"


def test_run_invokes_uvicorn(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_run(app_path: str, host: str, port: int, reload: bool) -> None:
        called["app_path"] = app_path
        called["host"] = host
        called["port"] = port
        called["reload"] = reload

    monkeypatch.setattr("app.api.main.uvicorn.run", _fake_run)

    run()

    assert called == {
        "app_path": "app.api.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": True,
    }


def test_metrics_endpoint_exposes_prometheus() -> None:
    client = _create_client()
    client.get("/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "http_requests_total" in resp.text or "http_request_duration_seconds" in resp.text


def test_api_rate_limit_returns_429(monkeypatch) -> None:
    from app.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "api_rate_limit", "2/minute")
    client = _create_client()

    assert client.get("/health").status_code == 200
    assert client.get("/health").status_code == 200
    third = client.get("/health")
    assert third.status_code == 429
    assert "retry-after" in {k.lower() for k in third.headers}
