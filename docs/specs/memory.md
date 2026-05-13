# Spec · Memory / Context

| Слой | Где живёт | TTL | Чем управляется |
|---|---|---|---|
| Беседа (короткая память) | `langgraph_checkpoints` (Postgres) | бессрочно, до удаления пользователя | LangGraph `PostgresSaver`, ключ `thread_id = user-{user_id}` |
| Финансовый контекст | `transactions`, `budget_plans`, `savings_goals` | бессрочно | прикладные сервисы / tools |
| Предпочтения | `user_preferences` | бессрочно | `app/agent/memory.py` (CRUD) + tool `set_preference` |
| Категорийные правила | `categorization_feedback` | бессрочно | reserved для расширения; используется в `_expense_category` |
| Кэш курсов | `currency_rates` | TTL `CURRENCY_TTL` сек | `currency.get_rate` |
| Аудит | `agent_events` | (PoC: бессрочно) | `_log_event` в orchestrator |

**Context budget.** В PoC не сжимается активно: рассчитываем на gpt-4o-mini (128K окно). При смене модели или отказе провайдера предусмотрено: 1) урезание истории через LangGraph `MessagesState` хук (TODO), 2) суммаризация `summarize_messages`.

**Privacy.** Persist всё, что отправляет пользователь (после PII-redaction). Удаление пользователя через каскад FK очищает все связанные строки; отдельно для `agent_events`/checkpoints — ручная зачистка по `user_id` / `thread_id`.
