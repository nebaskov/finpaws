# Spec · Observability / Evals

## Логи

- **Sink:** loguru, JSON через stdout (`LOG_JSON=true`, по умолчанию включено).
- **Поля:** `user_id`, `thread_id`, `kind` (`user_message`, `agent_run`, `agent_error`,
  `add_expense_failed`, …), `latency_ms`, доменные счётчики (`pii_hits`, `injection_markers`,
  `toxicity_score`, `tool_calls`).
- **PII:** маскируется до записи (`screen_user_input` → `redacted_text`); сырой текст не
  попадает ни в логи, ни в `agent_events`.

## Метрики (Prometheus + Grafana)

- API экспортит `/metrics` через `prometheus-fastapi-instrumentator` (per-app
  `CollectorRegistry`, чтобы `create_app()` оставался переиспользуемым).
- `docker compose up` поднимает Prometheus (скрейпит `api:8000/metrics`) и Grafana с готовым
  дашбордом **FinPaws API**: RPS, статусы, p50/p95/p99 latency, доля 5xx и 429.
- `METRICS_ENABLED=false` полностью отключает endpoint и инструментацию.

## Трейсы (Langfuse)

- `app/agent/tracing.py` строит `LangfuseCallbackHandler` и подкладывает его в
  `RunnableConfig` каждого вызова агента — есть LLM/tool-спаны, usage, latency.
- Подключение через env: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`. Без
  ключей агент работает без трейсинга (no-op).
- Self-hosted поднимается профилем `make langfuse-up` (web + worker + Postgres + ClickHouse +
  Redis + MinIO); UI на `:3001` (логин `admin@finpaws.local` / `finpaws-local-admin`).

## Доменные события

- Таблица `agent_events` (`kind`, `payload jsonb`, `latency_ms`) — основа для оффлайн-разбора
  и оценки качества; читается через `GET /agent/events?limit=…`.

## Evals

- **Lightweight runner** (`app/evals/runner.py`, `finpaws-evals --json`): прогоняет
  golden-сценарии (`app/evals/scenarios.py` — расход, отчёт, цели, RAG, injection),
  проверяет `tool-call recall` (всем ли `expected_tools` сработали) и `substring-match`
  по финальному ответу. CI-friendly.
- **deepeval** (`app/evals/deepeval_runner.py`, `make deepeval`): LLM-as-a-judge через
  OpenAI-совместимого судью (`app/evals/judge.py::OpenAICompatibleJudge`, по умолчанию
  DeepSeek). Метрики: `ToolCorrectnessMetric` (детерминированная) + три `GEval`
  (Faithfulness ≥ 0.7, Helpfulness ≥ 0.6, Safety ≥ 0.8). Текущий результат — 5/5 100%
  (см. `docs/benchmarks.md`).
- **Бенчмарки токсичности** (`make bench-toxicity`, `make bench-rutoxic`): in-house корпус
  + внешний RuToxic, latency p50/p95/p99, precision/recall/F1.
- **Нагрузочное тестирование** (`make load`, Locust): `locustfile.py::FinPawsUser`
  регистрируется и крутит взвешенный микс эндпоинтов с тегом `llm` для `/chat`.
