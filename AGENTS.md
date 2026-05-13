# AGENTS.md

Guidance for AI agents and human contributors working in this repository.
`CLAUDE.md` points here — this file is the single source of truth.

## What this is

**FinPaws** — a proof-of-concept agentic personal-finance assistant (mascot: the black cat *Баксик*).
A LangGraph ReAct agent with tool-calling sits behind a FastAPI service; it records transactions,
builds budgets, tracks goals, converts currency, mirrors entries into an hledger journal, and answers
finance questions via a small RAG knowledge base. There is also a no-infrastructure CLI.

Read [`README.md`](README.md) for the product framing and [`docs/`](docs/) for system design, diagrams,
specs, and the risk/governance register.

## Layout

```
app/
  api/            FastAPI app (main.py = routes, models.py = SQLModel tables, schemas.py = request/response models)
  agent/          LangGraph orchestrator, tools, LLM client (+ rate limiter), KB/RAG, memory, safety screen, checkpointing, prompts, Langfuse tracing
  auth/           JWT register/login, bcrypt hashing, current-user dependency
  domain/         Pure domain types (models.py) + budget/report math (planning.py) — no I/O, fully typed
  services/       CLI-side FinanceService + JSON file storage; rule-based categorizer
  integrations/   exchangerate.host currency client (+ cache & stale fallback); hledger CLI wrapper
  observability/  loguru JSON logging setup; in-memory counter
  evals/          scenarios + lightweight runner (`finpaws-evals`); deepeval runner + OpenAI-compatible judge
  cli/            interactive chat REPL (`finpaws-chat`)
  main.py         budget CLI (`finpaws ...`)
tests/            pytest suite (mirrors app/ module-for-module)
locustfile.py     load test for the API (`make load` → Locust web UI)
```

Entry points (see `[project.scripts]`): `finpaws`, `finpaws-api`, `finpaws-chat`, `finpaws-evals`,
`finpaws-deepeval`. **Dependency tiers**: base `dependencies` = `pydantic` + `pydantic-settings`
(enough for the `finpaws` budget CLI — `app/main.py` + `app/domain/` + `app/services/` are stdlib-only);
`[project.optional-dependencies] server` = fastapi/uvicorn/sqlmodel/langchain/langgraph/… (the API +
agent CLI + evals); `langfuse` = tracing; `all` = `server` + `langfuse`. So `pip install finpaws` /
`uv tool install .` gives a tiny `finpaws` CLI; `finpaws-api`/`-chat`/`-evals` need `[server]` (or `[all]`),
`finpaws-deepeval` needs the `dev` group. Dev setup pulls everything: `uv sync --all-extras --dev`
(= `make install`). When adding an import to `app/main.py`/`app/domain/`/`app/services/`, keep them
third-party-free or move the dep into the base `dependencies`.

## Environment & commands

This project uses **uv**. Python 3.12.

```bash
make sync           # uv sync --all-extras --dev   (or: uv sync)
make lint           # ruff check .
make format         # ruff format .
make format-check   # ruff format --check .
make typecheck      # mypy   (strict; see [tool.mypy] in pyproject.toml)
make test           # pytest
make coverage       # pytest --cov=app --cov-fail-under=85
make coverage-badge # regenerate coverage.svg (the README badge)
make check          # lint + format-check + typecheck + coverage  ← run this before you call it done
```

CI (`.github/workflows/ci.yml`) mirrors `make check` — two jobs, `lint` (ruff check / ruff format / mypy)
and `test` (pytest + coverage, `--cov-fail-under=85`) — and on push to `master` regenerates and commits
`coverage.svg` (the README badge, `[skip ci]` so it doesn't loop). `coverage.svg` is committed; `coverage.xml` is not.

`uv run mypy` / `uv run ruff …` work directly; for pytest prefer `uv run python -m pytest`
(the bare `uv run pytest` console script can be flaky in this environment — the Makefile already does the right thing).

Docker: `make up` / `make down` (keeps volumes) / `make nuke` (drops volumes) / `make logs`; `make langfuse-up` adds the self-hosted Langfuse stack (`langfuse` compose profile).
Config is env-driven via `pydantic-settings`; copy `.env.example` to `.env`. Key vars: `LLM_API_KEY`,
`LLM_BASE_URL`, `LLM_MODEL`, `DATABASE_URL`, `JWT_SECRET`, `KB_BACKEND`, `CURRENCY_API_URL`,
`HLEDGER_JOURNAL`, `LOG_JSON`, `PII_REDACT`.

## Coding standards (these are enforced — `make check` must pass)

- **Strict typing.** `mypy --strict` over `app/` and `tests/` must be clean. Annotate every function
  (params and return). Don't use bare `dict`/`list`/`tuple` — parametrize them. `Any` is allowed only
  where a third-party boundary genuinely forces it (LangChain / LangGraph internals).
- **Ruff.** `ruff check` and `ruff format --check` must be clean. Rule set lives in `[tool.ruff.lint]`
  (`E,W,F,I,N,UP,B,C4,SIM,RET,RSE,PIE,PT,T20,PERF,PGH,PLW,PTH,BLE,FA,ASYNC,RUF`). Per-file ignores
  cover `tests/` (print/PLW/BLE) and the CLIs (`T20`). No blanket `# type: ignore` / `# noqa` — always
  give a code, and a one-line reason for any `# noqa: BLE001` (intentional resilience catches).
- **Prefer typed structures over loose dicts.** Use Pydantic models or `@dataclass(slots=True)` for
  anything that flows between layers (`app/domain/`, `app/api/schemas.py`, `app/evals/scenarios.py`,
  `_State`/`ReportTotals`). Bare `dict[str, Any]` is acceptable only at protocol boundaries: LangChain
  tool return values, free-form telemetry payloads (`AgentEventRow.payload`), and the raw JSON
  read/written by `JsonStorage`.
- **Database = SQLModel.** Tables live in `app/api/models.py` as `SQLModel, table=True` classes (they
  double as Pydantic models). `app/db.py` exposes `Base = SQLModel`, `engine`, `SessionLocal`. We use
  plain SQLAlchemy `Session`s + `select(...).execute().scalars()`. **Because SQLModel's column
  attributes are typed as their Python type, wrap every comparison in `col()`** —
  `select(TransactionRow).where(col(TransactionRow.user_id) == user_id)` — or mypy will reject `bool`
  where it wants a SQL expression. Read paths catch `SQLAlchemyError`, log via loguru, `rollback()`,
  and degrade gracefully.
- **Money is `Decimal`**, rounded to kopecks/cents via `app.domain.planning.round_money` / `CENTS`.
  Never use `float` for amounts. Budget and report math lives in `app/domain/planning.py` — keep it
  there (the API, agent tools, and CLI all call it; don't re-implement).
- **Enums** that are also strings use `enum.StrEnum` (`TransactionKind`, `ExpenseCategory`).
- **Logging** is loguru, JSON by default; bind context (`logger.bind(user_id=…)`) rather than
  string-formatting it in. Never log raw PII or raw transaction rows — aggregates only (see
  `docs/governance.md`). The CLIs (`finpaws`, `finpaws-chat`, `finpaws-evals`) are the exception: their
  *output* is stdout, so they use `print()` (and `print(file=sys.stderr)` for meta-info / errors), not
  the log stream — those modules carry a `T20` per-file ignore. Everything in `app/` that isn't a CLI
  uses loguru.
- **Comments**: match the surrounding density. Explain *why*, not *what*. Russian user-facing strings
  are intentional (the assistant speaks Russian); the `RUF001-003` ambiguous-unicode lints are ignored
  for that reason.

## Tests

- `pytest`, in `tests/`, one module per `app/` module. Coverage gate is **85%** (`--cov-fail-under=85`);
  it currently sits ~89% — keep it there.
- Tests get a relaxed mypy profile (untyped defs allowed, no `disallow_any_generics`, etc.) — see the
  `[[tool.mypy.overrides]] module = "tests.*"` block — but they are still type-checked.
- Use in-memory SQLite (`StaticPool`) for DB-touching tests; `Base.metadata.create_all(bind=engine)`.
  Stub the LLM with a `BaseChatModel` subclass returning canned `AIMessage`s (see `tests/test_agent.py`).
  Monkeypatch external effects on the *real* module (`monkeypatch.setattr(shutil, "which", …)`,
  `monkeypatch.setattr(httpx, "Client", …)`), not via a re-exported name on our module — mypy's
  no-implicit-reexport rule will complain about the latter.
- Don't write to the network or the real filesystem (use `tmp_path`, `monkeypatch.chdir`).
- `deepeval` is a dev dep; its pytest plugin is disabled via `-p no:deepeval` in `addopts`.

## Evaluating the agent

Two layers:

- `app/evals/runner.py` (`finpaws-evals`) — fast, deterministic: feeds each scenario to the agent and
  checks tools-called ⊇ expected and substrings present. No LLM judge.
- `app/evals/deepeval_runner.py` (`finpaws-deepeval`, `make deepeval`) — deepeval-based:
  `build_dataset()` turns `app/evals/scenarios.py::SCENARIOS` into an `EvaluationDataset` of `Golden`s
  (the eval cases); `run_agent_on_scenarios` runs the agent and `to_test_cases` produces `LLMTestCase`s;
  `build_metrics(judge)` returns `ToolCorrectnessMetric` + three `GEval`s (Faithfulness / Helpfulness /
  Safety). `--dry-run` prints the dataset and exits without touching the agent or the judge.
- The judge (`app/evals/judge.py::OpenAICompatibleJudge`) is a `DeepEvalBaseLLM` over any
  OpenAI-compatible `/chat/completions` endpoint — DeepSeek by default (`JUDGE_BASE_URL`, `JUDGE_MODEL`,
  `JUDGE_API_KEY`). It supports schema-constrained generation via JSON mode. **Pass it (or another
  `DeepEvalBaseLLM`) as `model=` to every deepeval metric** — including `ToolCorrectnessMetric` — or
  deepeval falls back to `GPTModel` and demands `OPENAI_API_KEY`.
- New eval cases: add a `Scenario` to `SCENARIOS` with `expected_output` (a reference good answer for
  the judge) and `reference_facts` (what the answer must be consistent with).
- `app/evals/judge.py` and `app/evals/deepeval_runner.py` carry a per-module mypy relaxation
  (`disallow_subclassing_any` etc.) — they're thin glue over `deepeval` + the `openai` SDK, both of
  which are `follow_imports = skip`.

## Observability & limits

- **Langfuse LLM tracing** — `app/agent/tracing.py::langfuse_callbacks()` returns a LangChain callback
  handler when `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` are set (else `[]`). `run_agent` puts it in
  the agent's `RunnableConfig` (`callbacks` + `metadata`). It is best-effort — any init failure logs and
  degrades to no tracing; never raise from there. The Langfuse *server* is not in the default compose;
  `make langfuse-up` brings up a self-hosted Langfuse (web + worker + its Postgres/ClickHouse/Redis/MinIO,
  all behind the `langfuse` compose profile) with an auto-provisioned project (`pk-lf-finpaws` /
  `sk-lf-finpaws`) and wires the API to it (UI: `http://localhost:3001`). Or point at Langfuse Cloud via
  the env vars. Traces show up as a `LangGraph` trace with `GENERATION`/`TOOL`/`CHAIN` observations.
- **Prometheus** — `app/api/main.py::_install_metrics` wires `prometheus-fastapi-instrumentator`,
  exposing `GET /metrics`. It uses a **fresh `CollectorRegistry()` per app** so `create_app()` stays
  reusable in tests and doesn't pollute `prometheus_client`'s global `REGISTRY`. `docker compose`
  runs Prometheus + Grafana (`docker/prometheus.yml`, `docker/grafana/...`, dashboard
  `docker/grafana/dashboards/finpaws-api.json`). `METRICS_ENABLED=false` disables it.
- **API rate limiter** — `app/api/main.py::_install_rate_limiter` sets up `slowapi` with a per-IP
  `default_limits=[API_RATE_LIMIT]` (`SlowAPIMiddleware` + the `RateLimitExceeded` handler). In-memory
  store (per process); for production point it at Redis and exempt `/health` / `/metrics`.
  `API_RATE_LIMIT_ENABLED=false` disables it. Tests that need a 429 monkeypatch `SETTINGS.api_rate_limit`
  before `create_app()`.
- **LLM rate limiter** — `app/agent/llm.py::_build_rate_limiter()` returns a
  `langchain_core.rate_limiters.InMemoryRateLimiter` (passed to `ChatOpenAI(rate_limiter=...)`) when
  `LLM_RPS > 0`, else `None`.
- **Safety screen** — `app/agent/safety.py::screen_user_input` runs three checks on every chat input:
  PII redaction (email/phone/card/IBAN → tagged), prompt-injection detection (regex-based, catches
  inflected variants like "игнорируй ВСЕ инструкции" / "ignore all previous"), and a rule-based
  toxicity classifier (`score_toxicity` — Russian + English stems, categorised obscenity/insult/threat,
  CPU-instant, zero deps). The toxicity flag rides through `AgentResponse.toxic` / `ChatOut.toxic` and
  is logged in `agent_events.payload`. Threshold is `TOXICITY_THRESHOLD` (default `0.5`).
- **Load testing** — `locustfile.py` at repo root (`FinPawsUser`, `make load` → web UI on `:8089`).
  Weighted task mix; the real-LLM `/chat` task is `@tag("llm")` so `--exclude-tags llm` skips it. Under
  load from one IP the API rate limiter shows up as 429s. **Do not `import locust` from the test suite** —
  `locust/__init__.py` calls gevent's `monkey.patch_all()`, which would monkey-patch the pytest process
  and wreck the rest of the run. `locustfile.py` is not in `[tool.mypy] files`, so it's not type-checked.
- `langfuse.*` / `slowapi.*` / `limits.*` / `prometheus_fastapi_instrumentator.*` are
  `follow_imports = skip` in mypy — `Any`-typed glue, like the langchain/deepeval set.

## Gotchas

- `app/agent/orchestrator._build_react_agent` supports both the new `langchain.agents.create_agent`
  and the legacy `langgraph.prebuilt.create_react_agent`; keep that fallback.
- `app/agent/checkpoint.open_checkpointer` yields a Postgres saver only if `DATABASE_URL` is Postgres,
  otherwise an in-memory one, and falls back to in-memory if Postgres is unreachable.
- `langchain*` / `langgraph*` / `qdrant_client` are `follow_imports = "skip"` in mypy config — their
  symbols are `Any` on purpose. Don't fight it; keep app logic typed around the edges.
- `app/observability/logging.py` configures loguru once (module import time and again from
  `create_app`); the one-element `_configured` list is the intentional idempotency flag.
- The KB (`app/agent/kb.py`) is best-effort: missing keys / no vector store / a Chroma import blowup
  all degrade to "no KB", never an error. Preserve that.

## Definition of done

`make check` is green (ruff, ruff-format, mypy strict, pytest, coverage ≥ 85%) and any behavior change
is covered by a test. If you touched docs/specs, keep them consistent with the code.
