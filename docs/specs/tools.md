# Spec · Tools / APIs

Все инструменты — LangChain `StructuredTool`, аргументы валидируются Pydantic-схемами
(`AddExpenseIn`, `BuildBudgetIn`, …). `user_id` инъектируется в замыкание при
`build_tools(user_id)` — LLM не передаёт его в аргументах и не может подменить.

## Контракты

| Tool | Аргументы | Side effect | Timeout | Возврат при ошибке |
|---|---|---|---|---|
| `add_expense` | `amount > 0`, `description ≥ 2`, `currency` (ISO), `occurred_on?` | INSERT в `transactions` + append в hledger journal (`HLEDGER_MIRROR=true`) | — | `{"error": "db error: …"}` |
| `add_income` | то же | INSERT + append journal | — | то же |
| `get_report` | `days ∈ [1, 3650]` | SELECT агрегатов | — | `{"error": "db error"}` |
| `build_budget` | `monthly_income > 0` | UPSERT в `budget_plans`, лимиты по 50/30/20 поверх 90-дневной истории | — | `{"error": …}` |
| `add_goal` | `name`, `target_amount > 0`, `horizon_months ≥ 1` | INSERT в `savings_goals` | — | `{"error": "exists"}` |
| `update_goal_progress` | `name`, `amount > 0` | UPDATE `saved_amount` | — | `{"error": "not found"}` |
| `list_goals` | — | SELECT | — | `[]` |
| `convert_currency` | `amount`, `from`, `to` (ISO) | HTTP GET к exchangerate.host + UPSERT кэша | 10 с | `{"error": …}` или `{"stale": true, "rate": …}` |
| `search_advice` | `query`, `k ∈ [1, 10]` | `retriever.invoke(query)` через Chroma/Qdrant | — | `{"hits": []}` |
| `get_preference` / `set_preference` / `list_preferences` | `key`/`value` | UPSERT в `user_preferences` | — | `{"saved": false}` |
| `hledger_query` | `command ∈ {balance, register}`, `account?`, `period?` | `subprocess` `hledger` (read-only) | `HLEDGER_TIMEOUT` (10 с) | `{"error": "binary not found" \| "timeout"}` |

## Защиты

- **Pydantic validation** на входе каждого tool — некорректные типы/диапазоны падают до
  обращения к БД или внешнему сервису.
- **DB-операции** обёрнуты в `try/except SQLAlchemyError` с `session.rollback()`; ошибка
  возвращается как структурированное поле `{error: …}`, не уходит наружу.
- **HTTP / subprocess** — таймауты + `try/except`; результат всегда — структурированный
  объект, никогда `raise`.
- **`user_id`-инъекция при сборке tools** через `build_tools(user_id)`; LLM не может задать
  чужой `user_id` через manipulated tool-call.
- **Destructive tools** (`safety._DESTRUCTIVE_TOOLS` = `delete_transaction`, `reset_budget`,
  `delete_goal`, `wipe_user_data`) перечислены явно и проверяются
  `safety.requires_confirmation()`. В PoC к LLM не подключены — добавление требует
  UI-подтверждения.
- **hledger subprocess** — whitelist команд (`balance`, `register`), без `shell=True`,
  таймаут; бинарь проверяется через `shutil.which` при старте.

## Failure modes

Тулы всегда возвращают результат — никогда не делают `raise`. Конкретные классы ошибок:

| Класс | Когда | Как агент об этом узнаёт |
|---|---|---|
| `db error` | SQLAlchemyError | `{error: "db error: <msg>"}`, LLM сообщает пользователю |
| `not found` / `exists` | бизнес-логика goals/transactions | `{error: …}`, агент уточняет/предлагает |
| `timeout` | currency API / hledger | `{error: "timeout"}`; для currency — fallback на `{stale: true}` если кэш есть |
| `binary not found` | hledger CLI не установлен | `{error}`, агент признаёт ограничение |
| `pydantic validation` | некорректные аргументы LLM | LLM получает trace и переписывает вызов |
