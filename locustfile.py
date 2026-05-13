"""Locust load test for the FinPaws API.

    make load                                  # web UI on http://localhost:8089
    uv run locust --host http://localhost:8000 # same, explicit host
    uv run locust --host http://localhost:8000 --headless -u 20 -r 2 -t 60s   # CI-style
    uv run locust --host http://localhost:8000 --exclude-tags llm             # skip the real /chat calls

Each simulated user registers once, then hammers a weighted mix of endpoints. `/chat` is the heavy
one (a real LLM round-trip — tokens + a few seconds each) so it has the lowest weight and the `llm`
tag; exclude it for raw-throughput runs. Note the API rate limiter (default 120/min per client IP)
will return 429s under load — that's expected; raise `API_RATE_LIMIT` or set `API_RATE_LIMIT_ENABLED=false`
to measure unthrottled throughput.
"""

from __future__ import annotations

import random
import uuid

from locust import HttpUser, between, tag, task

_CHAT_MESSAGES = (
    "потратил 850 на яндекс такси",
    "покажи отчёт за месяц",
    "построй бюджет на доход 150000",
    "объясни правило 50 30 20",
    "хочу накопить 300000 за 12 месяцев",
)


class FinPawsUser(HttpUser):
    wait_time = between(0.5, 2.0)
    headers: dict[str, str] = {}

    def on_start(self) -> None:
        email = f"loadtest-{uuid.uuid4().hex[:12]}@example.com"
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "password": "Password123!"},
            name="POST /auth/register",
        )
        if resp.status_code == 201:
            self.headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    @task(10)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(4)
    def metrics(self) -> None:
        self.client.get("/metrics", name="GET /metrics")

    @task(6)
    def add_expense(self) -> None:
        self.client.post(
            "/transactions/expense",
            json={"amount": "850", "description": "яндекс такси"},
            headers=self.headers,
            name="POST /transactions/expense",
        )

    @task(2)
    def add_income(self) -> None:
        self.client.post(
            "/transactions/income",
            json={"amount": "100000", "description": "Зарплата"},
            headers=self.headers,
            name="POST /transactions/income",
        )

    @task(6)
    def report(self) -> None:
        self.client.get("/report?days=30", headers=self.headers, name="GET /report")

    @task(3)
    def budget(self) -> None:
        self.client.post(
            "/budget/plan",
            json={"monthly_income": "150000"},
            headers=self.headers,
            name="POST /budget/plan",
        )

    @tag("llm")
    @task(1)
    def chat(self) -> None:
        self.client.post(
            "/chat",
            json={"message": random.choice(_CHAT_MESSAGES)},
            headers=self.headers,
            name="POST /chat",
        )
