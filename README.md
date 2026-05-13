<div align="center">

<img src="https://cataas.com/cat/cute/says/FinPaws?fontColor=white&fontSize=50&type=square" width="300" alt="FinPaws cat" />

# FinPaws

[![CI](https://github.com/nebaskov/finpaws/actions/workflows/ci.yml/badge.svg)](https://github.com/nebaskov/finpaws/actions/workflows/ci.yml)
[![Coverage](./coverage.svg)](https://github.com/nebaskov/finpaws/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-2a6db2)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-PoC-orange)]()

Агентный AI-ассистент для планирования личного бюджета.
Маскот — чёрный кот **Баксик**: следит за финансами так же внимательно, как за птицами за окном.

</div>

## Задача

**Для кого.** Люди, которые хотят регулярно вести личный бюджет, но не готовы переключаться
между таблицей, калькулятором и трекером трат и заново вспоминать, что и куда они вписывали.

**Боль сейчас.** Существующие приложения дают учёт, но не диалог: пользователь сам гонит
данные, сам категоризирует, сам строит планы и сам же ищет, какое правило накопления ему
подходит. Учёт превращается в рутину и забрасывается.

**Что предлагаем.** FinPaws — агентная система, которая ведёт бюджет в чате: распознаёт
свободные формулировки расходов и доходов, категоризирует, строит бюджет по правилу 50/30/20,
ведёт цели накопления, тянет курсы валют, ищет ответы в базе знаний с финансовыми советами,
а под капотом дублирует операции в plain-text hledger-журнал.

## Что делает PoC на демо

- 💬 `POST /chat` — агент LangGraph (ReAct) с tool-calling: добавление транзакций, отчёты,
  бюджеты, цели, конвертация валют, RAG-поиск советов, hledger-аналитика.
- 🔐 JWT-регистрация и логин (bcrypt, изоляция данных по `user_id`).
- 📚 База знаний на Chroma/Qdrant с эмбеддингами через OpenAI-совместимый API.
- 💱 Конвертация валют через exchangerate.host с кэшем и stale-fallback.
- 📒 Plain-text accounting: каждая транзакция дублируется в hledger journal; агент умеет дёргать
  `hledger balance/register`.
- 🧠 Долговременная память (предпочтения) + LangGraph PostgresSaver для истории беседы.
- 🛡️ Safety pre-step: PII-redaction (email/телефон/карта/IBAN), детектор prompt-injection,
  rule-based детектор токсичности, дисклеймер по инвестрекомендациям, гейт деструктивных
  инструментов.
- 📊 Наблюдаемость: структурные JSON-логи (loguru), Prometheus + Grafana, Langfuse-трейсинг
  LLM/tool-спанов, таблица `agent_events` для оффлайн-аналитики.
- 🧪 Качество: lightweight evals (`finpaws-evals`) + deepeval с LLM-as-a-judge (Faithfulness /
  Helpfulness / Safety / ToolCorrectness), бенчмарки детектора токсичности.

## Что НЕ делает PoC (out of scope)

- Подключение к банковским API и автоматический импорт транзакций (CSV/Excel импорт — не в
  PoC).
- Инвестиционные рекомендации и работа с ценными бумагами; любой совет идёт с дисклеймером,
  что это не индивидуальная инвест-рекомендация.
- Веб/мобильный UI — клиент только CLI/HTTP (Postman-коллекция в `docs/postman/`).
- Налоговое планирование, мультивалютные сложные операции, OCR чеков.
- Горизонтальное масштабирование: PoC рассчитан на single-instance запуск, in-memory
  rate-limiter, single-tenant Postgres.

## Архитектура (кратко)

```
HTTP /chat ─► JWT ─► run_agent ─► safety screen ─► LangGraph(ReAct)
                                              │
                                              ▼
                              tools = [add_expense, add_income, get_report,
                                       build_budget, add_goal, update_goal_progress,
                                       convert_currency, search_advice, hledger_query,
                                       get/set/list_preference]
                                              │
                              ┌───────────────┼─────────────────────────┐
                              ▼               ▼                         ▼
                       PostgreSQL       Currency API            hledger CLI
                       (transactions,    + cache              (data/finpaws.journal)
                        goals, prefs,
                        agent_events,
                        checkpoints)
                              ▲
                              │
                       Chroma / Qdrant + OpenAI-compatible embeddings (RAG)
```

Подробнее — в [`docs/architecture.md`](docs/architecture.md) (диаграммы), [`docs/system-design.md`](docs/system-design.md), [`docs/diagrams/`](docs/diagrams/), [`docs/specs/`](docs/specs/), [`docs/governance.md`](docs/governance.md), [`docs/benchmarks.md`](docs/benchmarks.md), [`docs/product-proposal.md`](docs/product-proposal.md).

## Запуск

### Локально (Docker Compose: API + Postgres + Prometheus + Grafana)

```bash
cp .env.example .env  # подставить LLM_API_KEY и т.п.
docker compose up --build
```

- API — `http://localhost:8000` (OpenAPI: `/docs`, метрики: `/metrics`)
- Prometheus — `http://localhost:9090`
- Grafana — `http://localhost:3000` (анонимный вход; дашборд **FinPaws API**: RPS, статусы, latency p50/p95/p99, доля 5xx, 429)

### + Langfuse (self-hosted, профиль `langfuse`)

```bash
make langfuse-up   # = LANGFUSE_PUBLIC_KEY=pk-lf-finpaws ... docker compose --profile langfuse up -d --build
```

Поднимает дополнительно Langfuse (web + worker + Postgres + ClickHouse + Redis + MinIO) и прокидывает API на него — каждый `POST /chat` оставляет trace со спанами LLM/tool.

- Langfuse UI — `http://localhost:3001` (логин `admin@finpaws.local` / `finpaws-local-admin`, проект **FinPaws**: Traces / Sessions / Dashboards)
- MinIO console — `http://localhost:9001` (`minio` / `miniosecret`)
- Остановить: `make langfuse-down` / `make down` (тома сохраняются). Снести вместе с томами: `make nuke`.

Альтернатива self-host — Langfuse Cloud: задать `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST=https://cloud.langfuse.com` в `.env` и обычный `docker compose up`.

### Без Docker

```bash
uv sync
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/finpaws"
uv run finpaws-api
```

### Установить как CLI на систему

Проект — обычный pip-пакет (`hatchling`), команды объявлены в `[project.scripts]`. Базовая установка крошечная — только бюджетный CLI `finpaws` (зависимости: `pydantic` + `pydantic-settings`):

```bash
uv tool install .                 # из чекаута; или: make install-cli
uv tool install git+https://github.com/nebaskov/finpaws.git
pipx install .
# затем где угодно:
finpaws add-expense --amount 850 --description "Яндекс Такси"
finpaws report --days 30
```

Полный набор команд (`finpaws-api`, `finpaws-chat`, `finpaws-evals`) тянет сервер/агент-стек — ставится через extra `all`:

```bash
uv tool install '.[all]'          # или: make install-cli-all
```

Удалить: `uv tool uninstall finpaws` (или `make uninstall-cli`). Дев-окружение со всем сразу: `make install` (= `uv sync --all-extras --dev`).

### CLI чат (in-memory SQLite, без Postgres)

```bash
uv run finpaws-chat --ephemeral
```

### Минимальный сценарий через HTTP

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"u@x.io","password":"Password123!"}' | jq -r .access_token)

curl -s -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"message":"потратил 850 на яндекс такси, потом покажи отчёт за месяц"}' | jq
```

## Наблюдаемость и лимиты

- **Langfuse-трейсинг LLM**: задай `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` (и `LANGFUSE_HOST`) — каждый запуск агента отправляет trace со спанами LLM/tool в Langfuse (`app/agent/tracing.py` → колбэк в `RunnableConfig`). Без ключей агент работает без трейсинга. Self-hosted Langfuse — `make langfuse-up` (UI на `:3001`); см. раздел «Запуск».
- **Prometheus + Grafana**: API экспортит `/metrics` (`prometheus-fastapi-instrumentator`); `docker compose up` поднимает Prometheus (скрейпит `api:8000/metrics`) и Grafana с готовым дашбордом. `METRICS_ENABLED=false` отключает endpoint.
- **API rate limiter**: `slowapi` — глобальный лимит на IP (`API_RATE_LIMIT=120/minute` по умолчанию), при превышении `429` с `Retry-After`. In-memory store (для продакшна — Redis). `API_RATE_LIMIT_ENABLED=false` отключает.
- **LLM rate limiter**: `LLM_RPS` (>0) включает клиентский троттлинг запросов к провайдеру модели (`langchain_core.rate_limiters.InMemoryRateLimiter` в `ChatOpenAI`), `LLM_RATE_LIMIT_BURST` — размер burst.

## Ключевые ENV переменные

`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_RPS`, `DATABASE_URL`, `JWT_SECRET`, `KB_BACKEND` (`chroma`/`qdrant`), `KB_PATH`, `QDRANT_URL`, `CURRENCY_API_URL`, `HLEDGER_JOURNAL`, `LOG_JSON`, `PII_REDACT`, `METRICS_ENABLED`, `API_RATE_LIMIT`, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`, `JUDGE_*`. Полный список — в [`docs/specs/serving.md`](docs/specs/serving.md) и [`.env.example`](.env.example).

LLM-блок намеренно построен в OpenAI-совместимом стиле: переключение между OpenAI / OpenRouter / vLLM / Ollama / LM Studio = смена env-переменных.

## Тесты, lint, типы, evals

```bash
make lint              # ruff check
make format            # ruff format
make typecheck         # mypy --strict
make test              # pytest
make coverage          # pytest --cov, fail-under 85
make check             # всё вместе: lint + format-check + typecheck + coverage
make coverage-badge    # перегенерировать coverage.svg (бейдж покрытия)
make evals             # лёгкий runner со сценариями (substring + tool checks)
make deepeval          # deepeval: LLM-as-a-judge (DeepSeek), метрики GEval + ToolCorrectness
make bench-toxicity    # тулзу-детектор токсичности: latency + качество на in-house корпусе
make bench-rutoxic     # тот же детектор против внешнего корпуса RuToxic (~25k, скачивается)
make diagrams          # перерисовать docs/diagrams/*.md (Mermaid) в SVG
make load              # нагрузочный тест (Locust) — UI на http://localhost:8089, API должен быть поднят
```

Сводка всех метрик (latency детектора, in-house + RuToxic качество, deepeval по golden-сценариям) — в [`docs/benchmarks.md`](docs/benchmarks.md).

CI: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — на каждый push/PR прогоняет `ruff check`, `ruff format --check`, `mypy --strict` и `pytest --cov --cov-fail-under=85`; на push в `master` обновляет бейдж покрытия `coverage.svg` в репозитории.

### Нагрузочное тестирование (Locust)

`locustfile.py` — `FinPawsUser` регистрируется и крутит взвешенный микс эндпоинтов (`/health`, `/metrics`, `/transactions/*`, `/report`, `/budget/plan`, и `/chat` с весом 1 и тегом `llm`).

```bash
make up        # или make langfuse-up — API на :8000
make load      # Locust web UI: http://localhost:8089 → задать users/spawn rate → Start
# headless:
uv run locust --host http://localhost:8000 --headless -u 20 -r 2 -t 60s
# без реальных LLM-вызовов:
uv run locust --host http://localhost:8000 --exclude-tags llm
```

Под нагрузкой с одной машины сработает API rate limiter (`API_RATE_LIMIT=120/minute` на IP) — это видно как `429` в колонке failures; для замера без троттлинга подними лимит или `API_RATE_LIMIT_ENABLED=false`.

### deepeval (LLM-as-a-judge)

`app/evals/deepeval_runner.py` гоняет агента по датасету сценариев (`app/evals/scenarios.py` →
`build_dataset()`), собирает `LLMTestCase`-ы и оценивает их метриками deepeval
(`ToolCorrectnessMetric` + три `GEval`: Faithfulness / Helpfulness / Safety). Судья —
OpenAI-совместимый клиент (`app/evals/judge.py::OpenAICompatibleJudge`), по умолчанию DeepSeek:
`JUDGE_BASE_URL`, `JUDGE_MODEL`, `JUDGE_API_KEY`. Без судьи: `python -m app.evals.deepeval_runner --dry-run`
печатает датасет и выходит.

Соглашения для контрибьюторов и агентов — в [`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md).

## Postman

- Коллекция: `docs/postman/finpaws.postman_collection.json`
- Окружение: `docs/postman/local.postman_environment.json`

## Безопасность

См. [`docs/governance.md`](docs/governance.md):
- регистр рисков (LLM hallucinations, prompt injection, утечка финданных, IDOR, ...)
- политика логов (PII-redaction, агрегаты вместо сырых записей)
- защита от injection (system prompt + ограниченный набор tools + Pydantic-валидация)
- подтверждение деструктивных действий (`safety._DESTRUCTIVE_TOOLS`)
