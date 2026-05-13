from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import col

from app.agent.kb import KnowledgeBase
from app.agent.llm import build_chat_model
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.safety import screen_user_input
from app.agent.tools import build_tools
from app.agent.tracing import langfuse_callbacks
from app.api.models import AgentEventRow
from app.api.schemas import AgentEventOut
from app.config import SETTINGS

_FALLBACK_ANSWER = (
    "Ой, у Баксика лапки в LLM не дотянулись. Попробуйте чуть позже — "
    "а пока могу подсказать через прямые API-эндпоинты."
)
_EMPTY_ANSWER = "Хм, ответ пуст. Уточните вопрос — Баксик внимательнее."


class AgentResponse(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]]
    pii_redacted: bool
    injection_suspected: bool
    toxic: bool
    toxicity_score: float
    latency_ms: int


class OrchestratorError(Exception):
    pass


def _build_react_agent(model: Any, tools: Sequence[Any], *, checkpointer: Any) -> Any:
    """Build a tool-calling ReAct agent, supporting both the new (`langchain.agents`)
    and the legacy (`langgraph.prebuilt`) factory names."""
    try:
        from langchain.agents import create_agent
    except ImportError:  # pragma: no cover - exercised only against older langgraph
        from langgraph.prebuilt import create_react_agent as create_agent
    return create_agent(model, tools, checkpointer=checkpointer)


def _log_event(
    session_factory: sessionmaker[Session],
    *,
    user_id: str,
    thread_id: str,
    kind: str,
    payload: dict[str, Any],
    latency_ms: int = 0,
) -> None:
    session = session_factory()
    try:
        session.add(
            AgentEventRow(
                user_id=user_id,
                thread_id=thread_id,
                kind=kind,
                payload=payload,
                latency_ms=latency_ms,
            )
        )
        session.commit()
    except SQLAlchemyError:
        logger.bind(user_id=user_id, kind=kind).exception("agent_event log failed")
        session.rollback()
    finally:
        session.close()


def _msg_text(content: Any) -> str:
    if isinstance(content, list):
        return "\n".join(str(part) for part in content)
    return str(content or "").strip()


def _extract_answer_and_calls(messages: Sequence[Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return the final answer and the ordered tool calls, each enriched with the tool's
    output (matched by ``tool_call_id``) so downstream evals can check faithfulness."""
    answer = ""
    tool_calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for msg in messages:
        calls = getattr(msg, "tool_calls", None) or []
        for call in calls:
            entry: dict[str, Any] = {"name": call.get("name"), "args": call.get("args", {}), "output": None}
            tool_calls.append(entry)
            call_id = call.get("id")
            if call_id:
                by_id[str(call_id)] = entry
        if getattr(msg, "type", "") == "tool":
            call_id = str(getattr(msg, "tool_call_id", "") or "")
            if call_id in by_id:
                by_id[call_id]["output"] = _msg_text(getattr(msg, "content", ""))
        if getattr(msg, "type", "") == "ai" and not calls:
            answer = _msg_text(getattr(msg, "content", ""))
    return answer, tool_calls


def run_agent(
    *,
    session_factory: sessionmaker[Session],
    kb: KnowledgeBase,
    user_id: str,
    message: str,
    checkpointer: Any | None = None,
    chat_model: BaseChatModel | None = None,
    thread_id: str | None = None,
) -> AgentResponse:
    started = time.perf_counter()
    thread = thread_id or f"user-{user_id}"
    bound = logger.bind(user_id=user_id, thread_id=thread)

    safety = screen_user_input(message)
    bound.info(
        "user_message",
        pii_hits=safety.pii_hits,
        injection=safety.injection_suspected,
        toxic=safety.toxic,
        toxicity_score=safety.toxicity_score,
    )

    tools = build_tools(session_factory=session_factory, user_id=user_id, kb=kb)
    model = chat_model or build_chat_model()

    try:
        agent = _build_react_agent(model, tools, checkpointer=checkpointer)
    except Exception as exc:
        bound.exception("react agent build failed")
        raise OrchestratorError(f"failed to build agent: {exc}") from exc

    config = {
        "configurable": {"thread_id": thread},
        "recursion_limit": SETTINGS.llm_max_tool_steps * 3,
        "callbacks": langfuse_callbacks(),
        "metadata": {"finpaws_user_id": user_id, "finpaws_thread_id": thread},
    }
    inputs = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=safety.redacted_text),
        ]
    }

    try:
        result = agent.invoke(inputs, config=config)
    except Exception as exc:  # noqa: BLE001 - the LLM call can fail in many ways; degrade gracefully
        bound.exception("agent invoke failed")
        latency = int((time.perf_counter() - started) * 1000)
        _log_event(
            session_factory,
            user_id=user_id,
            thread_id=thread,
            kind="agent_error",
            payload={"error": str(exc)},
            latency_ms=latency,
        )
        return AgentResponse(
            answer=_FALLBACK_ANSWER,
            tool_calls=[],
            pii_redacted=bool(safety.pii_hits),
            injection_suspected=safety.injection_suspected,
            toxic=safety.toxic,
            toxicity_score=safety.toxicity_score,
            latency_ms=latency,
        )

    answer, tool_calls = _extract_answer_and_calls(result.get("messages", []))
    latency = int((time.perf_counter() - started) * 1000)
    _log_event(
        session_factory,
        user_id=user_id,
        thread_id=thread,
        kind="agent_run",
        payload={
            "tool_calls": [{"name": call["name"], "args": call["args"]} for call in tool_calls],
            "pii_hits": safety.pii_hits,
            "injection_markers": safety.injection_markers,
            "toxic": safety.toxic,
            "toxicity_score": safety.toxicity_score,
            "toxicity_categories": safety.toxicity_categories,
            "answer_chars": len(answer),
        },
        latency_ms=latency,
    )

    return AgentResponse(
        answer=answer or _EMPTY_ANSWER,
        tool_calls=tool_calls,
        pii_redacted=bool(safety.pii_hits),
        injection_suspected=safety.injection_suspected,
        toxic=safety.toxic,
        toxicity_score=safety.toxicity_score,
        latency_ms=latency,
    )


def recent_events(session: Session, user_id: str, limit: int = 20) -> list[AgentEventOut]:
    try:
        rows = (
            session.execute(
                select(AgentEventRow)
                .where(col(AgentEventRow.user_id) == user_id)
                .order_by(col(AgentEventRow.id).desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    except SQLAlchemyError:
        logger.exception("recent_events failed")
        session.rollback()
        return []
    return [AgentEventOut.model_validate(row, from_attributes=True) for row in rows]
