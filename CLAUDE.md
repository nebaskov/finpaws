# CLAUDE.md

This project keeps all agent/contributor guidance in **[AGENTS.md](AGENTS.md)** — read that.

Quick reminders:

- Use **uv**. Before claiming done, run `make check` (ruff + ruff-format + `mypy --strict` + pytest +
  coverage ≥ 85%). For tests, `uv run python -m pytest` is the reliable invocation.
- Strict typing is non-negotiable: annotate everything, no bare `dict`/`list`, `Any` only at
  third-party boundaries.
- Prefer Pydantic models / `@dataclass(slots=True)` over loose dicts for data that crosses layers.
- DB tables are **SQLModel** (`app/api/models.py`); wrap column comparisons in `col()` for mypy.
- Money is `Decimal`; budget/report math lives in `app/domain/planning.py` — don't re-implement it.
- Deps are tiered: base = `pydantic`+`pydantic-settings` (the `finpaws` budget CLI, stdlib-only code);
  `[server]` extra = the API/agent stack; `[langfuse]` = tracing; `[all]` = both. `uv tool install .` →
  tiny `finpaws` CLI; dev needs `uv sync --all-extras --dev`. Don't add third-party imports to
  `app/main.py`/`app/domain/`/`app/services/` without moving the dep into base `dependencies`.
- Use loguru in `app/`; the CLIs (`finpaws*`) are the exception — their *output* goes to stdout via
  `print()`.
- Agent eval: `app/evals/deepeval_runner.py` (`make deepeval`) with an OpenAI-compatible judge
  (`app/evals/judge.py`, DeepSeek by default). Pass the judge as `model=` to every deepeval metric.
- Observability/limits: Langfuse LLM tracing (`app/agent/tracing.py`, env-gated), Prometheus `/metrics`
  (per-app `CollectorRegistry`) + Grafana via docker-compose, `slowapi` API rate limit, and a
  `langchain` `InMemoryRateLimiter` for the LLM (`LLM_RPS`). All env-toggleable.
- The assistant speaks Russian; Russian string literals are intentional.
- Comments explain *why*, not *what* — no comments that just restate the code.

See [AGENTS.md](AGENTS.md) for the full layout, commands, conventions, and gotchas.
