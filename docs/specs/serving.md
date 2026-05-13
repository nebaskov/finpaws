# Spec · Serving / Config

- **Запуск API:** `uv run finpaws-api` (uvicorn, reload). В docker — `docker compose up`.
- **CLI:** `uv run finpaws-chat` (REPL); `--ephemeral` для in-memory SQLite.
- **Evals:** `uv run finpaws-evals --json` (CI-friendly).
- **Конфиг:** `app/config.Settings` (pydantic-settings, env-driven, поддержка `.env`).

## Env vars (без префиксов)

| Var | Default | Назначение |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/finpaws` | основная БД |
| `JWT_SECRET` / `JWT_TTL` | dev secret / 86400 | подпись и срок жизни токена |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | — / OpenAI / `gpt-4o-mini` | LLM |
| `LLM_TIMEOUT` / `LLM_RETRIES` / `AGENT_MAX_STEPS` | 30 / 2 / 8 | LLM-тайминги |
| `EMBEDDING_MODEL` / `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` | `text-embedding-3-small` / — / — | эмбеддинги (default reuse `LLM_*`) |
| `KB_BACKEND` / `KB_PATH` / `KB_COLLECTION` / `KB_SEED_PATH` / `QDRANT_URL` | chroma / `data/kb` / `finpaws-advice` / `data/kb_seed` / `http://localhost:6333` | KB |
| `CURRENCY_API_URL` / `CURRENCY_TTL` | exchangerate.host / 3600 | курсы |
| `HLEDGER_BIN` / `HLEDGER_JOURNAL` / `HLEDGER_MIRROR` / `HLEDGER_TIMEOUT` | `hledger` / `data/finpaws.journal` / true / 10 | hledger |
| `LOG_LEVEL` / `LOG_JSON` / `LOG_BACKTRACE` / `LOG_DIAGNOSE` | INFO / true / false / false | loguru |
| `PII_REDACT` / `SAFE_MODE` | true / true | safety |

## Версии моделей

PoC ориентирован на gpt-4o-mini. Альтернативы: gpt-4o, claude-haiku-4.5 (через прокси Anthropic→OpenAI), Llama 3.1 70B через vLLM.

## Секреты

`JWT_SECRET`, `LLM_API_KEY`, `EMBEDDING_API_KEY` — обязательно через env (`.env` для dev, secret manager для прода). Никаких секретов в репозитории.
