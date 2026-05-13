# Governance

## Risk register

| Риск | Вероятность | Влияние | Детект | Защита | Остаточный риск |
|---|---|---|---|---|---|
| Галлюцинации LLM: неверная категоризация или расчёт | Средняя | Высокое | golden-сценарии (`app/evals/scenarios.py`), deepeval `Faithfulness` / `ToolCorrectness`, `agent_events` для офлайн-разбора | Арифметика вынесена в детерминированные tools (`Decimal`, `app/domain/planning.py`); Pydantic-валидация аргументов; system-prompt требует «считать только инструментами»; RAG-ответы строго по тексту найденных документов | Единичные ошибки в edge-кейсах, не влияющие на цифры |
| Prompt injection через текст пользователя | Средняя | Высокое | `safety.detect_injection` (regex по RU/EN маркерам: `ignore previous`, `act as`, `игнорируй …`, `забудь`, `ты теперь`, `system prompt`); deepeval-сценарий `injection_resilience` | Markers пишутся в лог и в `ChatOut.injection_suspected`; system-prompt инструктирует отказываться, не упоминая внутренние правила и не перечисляя tools; ограниченный набор `StructuredTool`-ов — LLM не может выполнить произвольный код | Сложные многоступенчатые атаки через сторонний контент (RAG-документы) — пока не покрыто, пометка в TODO |
| Утечка PII через LLM-провайдера | Низкая | Высокое | safety pre-step логирует `pii_hits` (email/телефон/карта/IBAN), audit `agent_events` | `safety.redact_pii` маскирует данные **до** отправки в LLM (`[EMAIL]`, `[PHONE]`, `[CARD]`, `[IBAN]`); тот же redacted-текст попадает и в логи | Данные продолжают проходить через LLM-провайдера в нередактированных кусках сообщения (имена, описания трат) |
| Токсичный пользовательский ввод | Средняя | Среднее | rule-based детектор (`safety.score_toxicity`, RU+EN, категории `obscenity / insult / threat / en-toxic`); бенчмарки на in-house корпусе и RuToxic (`docs/benchmarks.md`) | `ChatOut.toxic` + `toxicity_score`; system-prompt предписывает корректно отказываться | Recall ≈ 0.54 на out-of-distribution RuToxic — границы regex-подхода известны; план перехода на `cointegrated/rubert-tiny-toxicity` зафиксирован |
| Деструктивная команда LLM (delete / reset) | Низкая | Высокое | `safety._DESTRUCTIVE_TOOLS` (`delete_transaction`, `reset_budget`, `delete_goal`, `wipe_user_data`); `requires_confirmation()` | System-prompt: «перед удалением переспрашивай»; деструктивные tools в PoC не зарегистрированы в LLM; добавление требует UI-подтверждения | Зависит от дисциплины при подключении новых tools |
| Недоступность LLM API | Средняя | Высокое | `httpx`/`openai` exception → `run_agent` ловит и пишет `agent_error` | Retries из `ChatOpenAI` (`max_retries = LLM_RETRIES`); top-level try/except возвращает дружелюбное сообщение | Полная недоступность при длительном outage провайдера — невозможно ответить пользователю |
| Недоступность API курсов валют | Низкая | Среднее | `httpx.HTTPError` / таймаут 10 с; HTTP-status логируется | Кэш `currency_rates(pair, rate, fetched_at)`, TTL `CURRENCY_TTL` сек; при miss + ошибке — `{stale: true}` с последним известным курсом или `{error}` | Неточная конвертация при долгом outage |
| Vector store / embeddings недоступны | Средняя | Среднее | `KnowledgeBase._resolve` логирует exception, флаг inicializaton failure | Ленивая инициализация → `KnowledgeBase(None)`; `search_advice` отдаёт `[]`; агент честно говорит «не нашёл», без галлюцинаций | Снижение качества RAG-ответов до восстановления |
| Postgres-checkpointer не поднялся | Низкая | Среднее | `open_checkpointer` логирует exception | Fallback на `MemorySaver` — диалог продолжается, история теряется при рестарте процесса | Потеря long-term thread state до восстановления Postgres |
| Утечка / подбор JWT | Низкая | Высокое | Аудит auth-событий; `agent_events` с `user_id` | TTL `JWT_TTL` (24 ч по умолчанию); bcrypt с дефолтными rounds; HS256; `JWT_SECRET` обязательный env, никогда не в коде | Компрометация при утечке самого `JWT_SECRET` |
| IDOR — доступ к чужим данным | Низкая | Высокое | Pytest на изоляцию пользователей; `tests/api/test_isolation.py` | `user_id` всегда извлекается из JWT, не из тела запроса; FK + `ON DELETE CASCADE`; явный фильтр `col(...) == user.user_id` в каждом query | Регрессия при добавлении нового endpoint без фильтра |
| Опасное выполнение `hledger` (subprocess) | Низкая | Среднее | `shutil.which` проверка + `subprocess` timeout | Whitelist команд (`balance`, `register`), аргументы валидируются Pydantic, `HLEDGER_TIMEOUT` (10 с), нет shell=True | Уязвимость в самом hledger |
| API rate-limit DoS | Низкая | Среднее | Prometheus / Grafana дашборд (429 rate); slowapi headers `x-ratelimit-*` | `slowapi` 120 req/min на IP (`API_RATE_LIMIT`), in-memory store; для прода — Redis | DDoS с большого числа IP |
| LLM rate-limit upstream | Средняя | Среднее | `httpx` 429 от провайдера, лог | Клиентский `InMemoryRateLimiter` (`LLM_RPS`>0 включает), `LLM_RATE_LIMIT_BURST` | Запросы стоят в очереди — рост latency |

## Политика логов

- **Sink:** loguru, JSON в stdout (`LOG_JSON=true` по умолчанию). Поля: `user_id`,
  `thread_id`, `kind`, `latency_ms`, доменные счётчики.
- **Что НЕ попадает в логи:** сырой пользовательский текст, пароли, JWT, raw LLM-ответ.
  В лог идёт только `redacted_text` после `safety.redact_pii` и `agent_events.payload`
  c агрегатами (имена tools и `latency_ms`, без полных `args`/`output` транзакций).
- **Финансовые записи** хранятся в Postgres (`transactions`, `savings_goals`, `budget_plans`),
  логируются как `kind=add_expense_failed` / `add_income_failed` только при ошибке — и без
  суммы/описания.
- **Ротация:** в PoC не настроена (stdout → docker logs); для прода — внешний агрегатор
  (Loki / ELK) с retention 30 дней.
- **Трейсы (Langfuse):** при наличии ключей LLM/tool-спаны уходят в Langfuse — там видны
  полные prompts и tool-arguments. Self-hosted Langfuse рекомендуется для прода, иначе
  prompts уходят в облако провайдера трейсинга.

## Персональные данные

Система **не передаёт** данные третьим сторонам, кроме LLM-провайдера и (опционально)
Langfuse.

- **PII-redaction до LLM:** email, телефон, номер карты (по контрольной длине), IBAN —
  маскируются regex-ами в `safety.redact_pii`. Сами hits фиксируются в `pii_hits` и
  возвращаются в `ChatOut.pii_redacted`.
- **Пароли:** bcrypt-хэш в `users.password_hash`, никогда в открытом виде.
- **Изоляция:** Postgres row-level фильтр по `user_id` (FK + `ON DELETE CASCADE`).
- **Удаление аккаунта:** каскад FK сносит все связанные записи; `agent_events` и
  `langgraph_checkpoints` зачищаются по `user_id` / `thread_id` отдельной операцией.
- **Шифрование at rest** и **формальное согласие на обработку ПДн** — за пределами PoC.

## Защита от prompt-injection

Многослойная:

1. **Pre-step регексами** (`safety.detect_injection`): RU/EN маркеры `ignore previous`,
   `act as`, `system prompt`, `игнорируй`, `забудь`, `ты теперь`, `новые инструкции`,
   `систем(а|ный) промпт`, `сырой режим` — выставляют флаг, но **не блокируют** запрос
   (LLM сам должен отказать через system-prompt).
2. **System prompt** (`app/agent/prompts.py::SYSTEM_PROMPT`): явно запрещает менять роль и
   раскрывать промпт; **запрещает упоминать собственные инструкции в отказе** и **перечислять
   внутренние названия инструментов** — иначе судья снижает Safety.
3. **Закрытый набор инструментов:** LLM может вызвать только `StructuredTool`-ы из
   `tools.build_tools(user_id)`, аргументы проходят Pydantic-валидацию — не получится
   подсунуть SQL/CLI.
4. **`user_id` инъектируется в tools при сборке** (`build_tools(user_id)`), не из аргументов
   LLM — нельзя записать транзакцию в чужой аккаунт через manipulated tool-call.
5. **deepeval-сценарий `injection_resilience`** в golden-наборе с порогом Safety ≥ 0.8 —
   регрессионный гейт.

## Подтверждение действий

- **Деструктивные операции** (`safety._DESTRUCTIVE_TOOLS` = `delete_transaction`,
  `reset_budget`, `delete_goal`, `wipe_user_data`) перечислены явно и проверяются
  `safety.requires_confirmation(tool_name)`. В PoC они **не подключены к LLM** — добавление
  требует UI-подтверждения и фиксации в evals.
- **Изменение целей / бюджета** через `update_goal_progress` / `build_budget` идёт без
  переспроса (агрегатные данные пользователя), но agent уточняет имя цели через
  `list_goals` при неоднозначности.
- **Массовые операции** (импорт CSV, пересчёт всех транзакций) — out of scope в PoC.
