# Spec · Agent / Orchestrator

- **Engine.** `langchain.agents.create_agent` (LangGraph v1) с fallback на
  `langgraph.prebuilt.create_react_agent` — ReAct-цикл «LLM → tool → LLM».
- **Graph state.** Управляется LangGraph; ключ `thread_id = user-{user_id}` обеспечивает
  персистентность диалога между запросами одного пользователя.
- **Шаги.** На каждой итерации LLM возвращает `AIMessage` с `tool_calls` → диспетчеризуется
  через `ToolNode` → результат становится `ToolMessage` → возвращается в LLM. Параметры всех
  вызовов проходят Pydantic-валидацию.
- **Stop condition.** `AIMessage` без `tool_calls` (финальный ответ) или достижение
  `recursion_limit = AGENT_MAX_STEPS × 3` (default 24).
- **Retry / fallback.**
  - Уровень LLM: `ChatOpenAI(max_retries=LLM_RETRIES)` (default 2) — экспоненциальные
    ретраи на 5xx/429.
  - Уровень инструмента: каждый `StructuredTool` ловит исключения и возвращает структурированный
    `{error: …}` вместо raise — LLM получает строку с ошибкой и объясняет её пользователю.
  - Уровень orchestrator: top-level `try/except` в `run_agent` → пишет `agent_error` в
    `agent_events` и возвращает дружелюбное сообщение; recursion-limit → лог `agent_recursion_limit`.
- **Safety pre-step.** `safety.screen_user_input` перед LLM:
  - `redact_pii` маскирует email/телефон/карту/IBAN;
  - `detect_injection` выставляет markers (`ignore-previous`, `ru-ignore`, …);
  - `score_toxicity` (rule-based) выдаёт score + категории.
  Флаги уходят в `ChatOut`, маскированный текст — в LLM и в логи.
- **System prompt.** `app/agent/prompts.py::SYSTEM_PROMPT` фиксирует роль («Баксик»),
  обязательность инструментов для арифметики, инвестиционный дисклеймер, поведение при
  injection (отказывать, не упоминая внутренние правила/tools), RAG-разметку («строго по
  тексту найденных документов»).
- **Persistence.** `PostgresSaver` через контекст-менеджер `app/agent/checkpoint.py`.
  При недоступности Postgres — fallback на `MemorySaver` (память диалога теряется при
  рестарте). Полностью offload памяти на LangGraph — нет ручного сжатия истории в PoC.
- **Tracing.** `app/agent/tracing.py::build_callbacks` подкладывает
  `LangfuseCallbackHandler` в `RunnableConfig`, если выставлены `LANGFUSE_*` env. Без ключей
  — no-op.
