# FinPaws · System Design

## Ключевые архитектурные решения

1. **Агент = LangGraph ReAct с Postgres-чекпоинтером.** `langchain.agents.create_agent` (fallback `langgraph.prebuilt.create_react_agent`) даёт цикл "LLM → tool → LLM" с автоматической персистенцией состояния через `PostgresSaver`. Поток беседы (`thread_id = user-{user_id}`) переживает рестарты API.
2. **Provider-agnostic LLM.** Слой `app/agent/llm.py` строит `ChatOpenAI` поверх любого OpenAI-совместимого провайдера (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Это даёт переключение OpenAI ↔ OpenRouter ↔ vLLM/Ollama без изменения кода.
3. **Детерминизм там, где можно.** Арифметика и работа с БД выполняются в инструментах; LLM отвечает за интент, извлечение сущностей и формулировку. См. `docs/governance.md` (политика рисков).
4. **Векторная база знаний.** `app/agent/kb.py` оборачивает Chroma (по умолчанию) или Qdrant (`KB_BACKEND=qdrant`) с эмбеддингами через тот же OpenAI-совместимый API. Сидинг советов из `data/kb_seed/` или встроенных дефолтов при пустой коллекции.
5. **Plain-text ledger как 2-й контур правды.** Каждый расход/доход дублируется в hledger journal (`HLEDGER_JOURNAL`). Агент может запускать `hledger balance/register` через инструмент.
6. **Безопасность как pre-step.** Перед вызовом LLM пользовательский ввод проходит `screen_user_input` (PII-redaction + injection-detection). System-prompt запрещает ролевые подмены и выдачу финансовых рекомендаций без дисклеймера.
7. **Failover.** При недоступности LLM `run_agent` ловит исключение, пишет `agent_error` событие и возвращает дружелюбное сообщение. Постгрес-чекпоинтер падает на in-memory. Курсы валют — кэш + stale-флаг.

## Модули

| Модуль | Роль |
|---|---|
| `app/agent/orchestrator.py` | сборка react-agent, безопасность, логирование, persistence событий |
| `app/agent/tools.py` | LangChain `StructuredTool` обёртки над БД, KB, currency, hledger |
| `app/agent/llm.py` | фабрика `ChatOpenAI` |
| `app/agent/kb.py` | Chroma/Qdrant retriever + дефолтный seed |
| `app/agent/memory.py` | пользовательские предпочтения в Postgres |
| `app/agent/safety.py` | PII-redaction, injection-markers, destructive tool gate |
| `app/agent/checkpoint.py` | контекст-менеджер `PostgresSaver` ↔ `MemorySaver` fallback |
| `app/agent/prompts.py` | system prompt Баксика |
| `app/api/main.py` | FastAPI: `/auth/*`, `/chat`, CRUD endpoints, `/preferences`, `/agent/events` |
| `app/auth/*` | JWT (PyJWT) + bcrypt |
| `app/integrations/currency.py` | exchangerate.host клиент с кэшем и stale-fallback |
| `app/integrations/hledger.py` | append journal + `balance`/`register` + import |
| `app/observability/logging.py` | loguru с настройкой через `LOG_*` env |
| `app/evals/*` | сценарии и runner |
| `app/cli/chat.py` | REPL для локальной работы без HTTP |

## Workflow выполнения запроса

```
HTTP POST /chat ── JWT ──▶ run_agent
                              │
                              ▼
                    screen_user_input ── injection? ──▶ markers logged, не блокируем (system-prompt держит роль)
                              │
                              ▼
                    build_tools(user_id) ──▶ list[StructuredTool]
                              │
                              ▼
                    create_agent(model, tools, checkpointer)
                              │
                              ▼
                    invoke({thread_id: user-X}, recursion_limit)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        AIMessage(tool_calls)          AIMessage(content)  → возвращаем answer
              │
              ▼
        ToolNode → выполнение Pydantic-валидированного payload
              │
              ▼
        ToolMessage(result) ── обратно в LLM
```

## State / Memory / Context

- **Долгосрочная память пользователя**: таблицы `users`, `transactions`, `savings_goals`, `budget_plans`, `user_preferences`, `categorization_feedback`.
- **Память агента (короткая)**: `PostgresSaver` хранит сообщения по `thread_id`. Полностью offload на LangGraph — нет ручного сжатия истории в PoC, окно ограничено бюджетом модели.
- **Кэш курсов**: `currency_rates(pair, rate, fetched_at)` с TTL = `CURRENCY_TTL` сек.
- **Аудит**: `agent_events` (kind, payload jsonb, latency_ms) — основа для офлайн-аналитики и оценки качества.

## Retrieval-контур

- Источник: `data/kb_seed/*.md` или встроенные документы (правило 50/30/20, подушка, методы погашения долгов, категории, цели).
- Бэкенд: Chroma (`KB_BACKEND=chroma`, `KB_PATH`) — embedded, без отдельного сервиса. Qdrant (`KB_BACKEND=qdrant`, `QDRANT_URL`) для боевого окружения.
- Эмбеддинги: `OpenAIEmbeddings(model=EMBEDDING_MODEL)` — переиспользуем LLM-провайдера (`LLM_BASE_URL`/`LLM_API_KEY`) или отдельный (`EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY`).
- Top-k: 5 в retriever, инструмент `search_advice` возвращает k≤10 по запросу LLM.
- Деградация: при невозможности построить эмбеддинги — `KnowledgeBase(None)`, `search_advice` возвращает пустой список, агент честно отвечает "не нашёл".

## Tool / API контракты (сжато)

| Tool | Args (Pydantic) | Side effects | Failure mode |
|---|---|---|---|
| `add_expense` | amount, description, currency, occurred_on? | INSERT transaction + append journal | `{error: "db error: ..."}` |
| `add_income` | то же | INSERT transaction + append journal | то же |
| `get_report` | days (1..3650) | SELECT агрегаты | `{error}` |
| `build_budget` | monthly_income | UPSERT budget_plans | `{error}` |
| `add_goal` | name, target_amount, horizon_months | INSERT savings_goals | `{error: "exists"}` |
| `update_goal_progress` | name, amount | UPDATE saved_amount | `{error: "not found"}` |
| `convert_currency` | amount, from, to | HTTP GET + cache | stale=True / `{error}` |
| `search_advice` | query, k | RAG retrieve | `[]` при сбое |
| `set_preference` / `get_preference` / `list_preferences` | key, value | UPSERT user_preferences | `{saved: false}` |
| `hledger_query` | command, account?, period? | subprocess | `{error: "binary not found"|"timeout"}` |

## Ограничения

| Тип | Значение |
|---|---|
| p95 latency `/chat` | < 10 сек (обычно ≤ 5 с при gpt-4o-mini) |
| recursion_limit | `AGENT_MAX_STEPS × 3` (default 24) |
| LLM timeout | `LLM_TIMEOUT` сек (default 30), retries `LLM_RETRIES` (default 2) |
| Currency timeout | 10 сек, кэш TTL `CURRENCY_TTL` (default 3600) |
| hledger timeout | `HLEDGER_TIMEOUT` сек (default 10) |
| LLM cost (PoC) | gpt-4o-mini ≈ $0.15/$0.60 за 1M input/output токенов; ожидаемый бюджет $5–10 на разработку |
| Доступность | 95% (PoC, single-instance) |

## Failure modes & guardrails

| Failure | Detect | Fallback |
|---|---|---|
| LLM down/timeout | `run_agent` ловит исключение | `agent_error` event + дружелюбное сообщение |
| Postgres недоступен | DB error в инструменте | tool возвращает `{error}`, LLM объясняет пользователю |
| Postgres-checkpointer init упал | `open_checkpointer` логирует | `MemorySaver` (потеря истории при рестарте) |
| Currency API down | `httpx.HTTPError` | кэш с `stale=True`; если кэша нет — `{error}` |
| hledger binary отсутствует | `shutil.which` is None | `HledgerError` → `{error}` в tool |
| Vector store unreachable | Chroma/Qdrant exception | `KnowledgeBase(None)` + warning |
| Prompt injection | markers detected | флаг в логе/ответе; system-prompt держит роль |
| PII в сообщении | regex hit | редактируется до отправки в LLM |
| Превышение recursion | LangGraph raises | сообщение "ответ пуст" + лог |

## Observability / Evals

- **Логи**: loguru → JSON (`LOG_JSON=true`). Поля: `user_id`, `thread_id`, `kind`, `payload`,
  `latency_ms`. PII-редактирование уже на pre-step.
- **Метрики**: `/metrics` через `prometheus-fastapi-instrumentator` (per-app
  `CollectorRegistry`); Prometheus + Grafana поднимаются `docker compose up` с дашбордом
  «FinPaws API» (RPS, статусы, p50/p95/p99 latency, доля 5xx и 429). Дополнительно —
  `agent_events` агрегаты (latency / tool-mix).
- **Трейсы**: Langfuse через колбэк (`app/agent/tracing.py`), env-gated
  (`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`). Self-hosted поднимается
  профилем `make langfuse-up`. Без ключей трейсинг — no-op.
- **Evals**:
  - lightweight (`app/evals/runner.py`, `finpaws-evals --json`) — tool-call recall +
    substring-match по 5 сценариям;
  - deepeval (`app/evals/deepeval_runner.py`, `make deepeval`) — LLM-as-a-judge через
    OpenAI-совместимого судью (`OpenAICompatibleJudge`, DeepSeek по умолчанию), метрики
    `ToolCorrectnessMetric` + три `GEval` (Faithfulness ≥ 0.7, Helpfulness ≥ 0.6, Safety
    ≥ 0.8). Текущий результат — 5/5 100% (`docs/benchmarks.md`).
- **Бенчмарки токсичности**: `make bench-toxicity` (in-house) и `make bench-rutoxic`
  (~25k комментариев); latency p50/p95/p99 + precision/recall/F1.

## Запуск, конфиг, секреты

- Все секреты — через env (`.env` подхватывается `pydantic-settings`). `JWT_SECRET`, `LLM_API_KEY`, `DATABASE_URL`, `EMBEDDING_API_KEY` — обязательные в проде.
- Постгрес поднимается через `docker compose up`; миграций нет, `Base.metadata.create_all` на старте API. Для прода — Alembic (out of scope).
- Версия модели — `LLM_MODEL` (default `gpt-4o-mini`). Сменить на любой OpenAI-совместимый ID.
