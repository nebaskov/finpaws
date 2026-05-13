# C4 · Components (ядро агента)

Внутреннее устройство `app/agent/*` — модули в одном Python-процессе, разворачиваемые
вызовом `run_agent(...)` из `app/api/main.py::/chat`.

```mermaid
flowchart TB
  subgraph api["API edge"]
    chat["FastAPI /chat<br/><code>app/api/main.py</code>"]
  end

  subgraph core["Agent core · app/agent"]
    direction TB
    orch["Orchestrator<br/><code>orchestrator.run_agent</code>"]
    safety["Safety pre-step<br/><code>safety.screen_user_input</code><br/>PII · injection · toxicity"]
    prompts["System prompt<br/><code>prompts.SYSTEM_PROMPT</code>"]
    llmf["LLM factory<br/><code>llm.build_llm</code><br/>ChatOpenAI · rate limiter"]
    tools["Tools registry<br/><code>tools.build_tools(user_id)</code><br/>StructuredTool × N"]
    kb["Knowledge base<br/><code>kb.KnowledgeBase</code>"]
    memlong["Long-term memory<br/><code>memory.set_preference/list_preferences</code>"]
    chk["Checkpointer<br/><code>checkpoint.open_checkpointer</code><br/>PostgresSaver → MemorySaver"]
    trace["Tracing<br/><code>tracing.build_callbacks</code><br/>Langfuse (env-gated)"]
  end

  subgraph deps["Ресурсы процесса"]
    direction LR
    pg[("🗄 Postgres")]
    vec[("🔎 Chroma / Qdrant")]
    journal["📒 hledger.journal"]
    fx["💱 Currency API"]
    llmext["🤖 LLM provider"]
    lf["📊 Langfuse"]
  end

  chat --> orch
  orch --> safety
  orch --> prompts
  orch --> llmf
  orch --> tools
  orch --> chk
  orch -. "callbacks" .-> trace
  tools --> kb
  tools --> memlong
  tools --> journal
  tools --> fx
  tools --> pg
  kb --> vec
  memlong --> pg
  chk --> pg
  llmf --> llmext
  trace --> lf

  classDef edge   fill:#f8fafc,stroke:#475569,color:#0f172a;
  classDef coreC  fill:#fff7ed,stroke:#f97316,color:#7c2d12;
  classDef extn   fill:#eef2ff,stroke:#6366f1,color:#1e1b4b;
  classDef store  fill:#ecfdf5,stroke:#10b981,color:#064e3b;
  class chat edge;
  class orch,safety,prompts,llmf,tools,kb,memlong,chk,trace coreC;
  class fx,llmext,lf extn;
  class pg,vec,journal store;
  style api fill:#f1f5f9,stroke:#94a3b8,stroke-dasharray:5 4;
  style core fill:#fffbeb,stroke:#f59e0b,stroke-width:1px;
  style deps fill:#f5f3ff,stroke:#a78bfa,stroke-dasharray:5 4;
```

## Ответственности компонентов

| Компонент | Файл | Ответственность | Stop / fallback |
|---|---|---|---|
| Orchestrator | `agent/orchestrator.py` | сборка ReAct-графа, цикл LLM↔tools, запись `agent_events`, top-level try/except | recursion limit → лог, дружелюбный ответ |
| Safety pre-step | `agent/safety.py` | PII regex-redaction, injection-маркеры, rule-based toxicity | при срабатывании — флаги в ответе, текст всё равно идёт в LLM в отредактированном виде |
| System prompt | `agent/prompts.py` | роль, дисклеймер, обязательное использование инструментов | — |
| LLM factory | `agent/llm.py` | `ChatOpenAI` поверх любого OpenAI-совместимого endpoint; `LLM_RPS` → `InMemoryRateLimiter` | retries из `ChatOpenAI` |
| Tools registry | `agent/tools.py` | `StructuredTool`-обёртки с Pydantic-схемой; набор зависит от `user_id` | каждый tool возвращает `{error: …}` вместо исключения |
| Knowledge base | `agent/kb.py` | ленивая инициализация retriever (Chroma/Qdrant + эмбеддинги) | при сбое — `KnowledgeBase(None)`, `search_advice` → `[]` |
| Long-term memory | `agent/memory.py` | CRUD пользовательских предпочтений и категорийных правил | DB-ошибка → `{saved: false}` |
| Checkpointer | `agent/checkpoint.py` | контекст-менеджер `PostgresSaver` | при сбое подключения — `MemorySaver` (память диалога теряется при рестарте) |
| Tracing | `agent/tracing.py` | колбэки `langfuse-langchain` при наличии ключей | без ключей — no-op, агент работает без трейсов |

Rendered: [`c4-component.svg`](c4-component.svg)
