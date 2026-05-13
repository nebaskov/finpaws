# Data flow · one chat turn

```mermaid
flowchart LR
  msg["✉️ User message"]
  safety["🛡 safety screen<br/>PII redact · injection · toxicity"]
  llm["🤖 LLM"]
  tools["🔧 Tools"]
  answer["💬 Answer"]

  pg[("🗄 Postgres<br/>transactions · goals · prefs")]
  fxc[("💱 currency_rates cache")]
  journal["📒 hledger.journal<br/>plain text"]
  chk[("⏪ Postgres checkpoints<br/>conversation history")]
  events[("📈 agent_events<br/>tool summary · usage · latency")]
  logs[("📝 loguru sink<br/>JSON → stdout")]

  msg -- "raw" --> safety
  safety -- "redacted text" --> llm
  msg -. "raw, ephemeral" .-> logs
  safety -. "hits + markers" .-> logs

  llm <-- "tool calls / results" --> tools
  tools --> pg
  tools --> fxc
  tools --> journal

  llm --> answer
  msg -- "HumanMessage" --> chk
  answer -- "AIMessage" --> chk

  tools -. "call summary" .-> events
  llm  -. "usage / latency" .-> events

  classDef io    fill:#f8fafc,stroke:#475569,color:#0f172a;
  classDef step  fill:#fff7ed,stroke:#f97316,color:#7c2d12;
  classDef store fill:#ecfdf5,stroke:#10b981,color:#064e3b;
  class msg,answer io;
  class safety,llm,tools step;
  class pg,fxc,journal,chk,events,logs store;
```

**Storage & privacy**

- **Logs** — redacted text only; raw PII (email / phone / card / IBAN) is masked by regex before anything is logged.
- **Postgres** — financial data is isolated by `user_id` (FK to `users`, `ON DELETE CASCADE`).
- **Checkpoints** — hold conversation history (may include names / transaction details); keyed by `thread_id = "user-{user_id}"` and dropped with the user via cascade.
- **Currency cache** — impersonal.
- **Journal file** — local, plain-text, owned by the user.

Rendered: [`data-flow.svg`](data-flow.svg)
