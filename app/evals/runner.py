from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.kb import KnowledgeBase, build_kb
from app.agent.orchestrator import run_agent
from app.api.models import UserRow
from app.db import Base
from app.evals.scenarios import SCENARIOS, Scenario, ScenarioResult


def _factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_user(factory: sessionmaker[Session], user_id: str) -> str:
    with factory() as session:
        if session.get(UserRow, user_id) is None:
            session.add(UserRow(id=user_id, email=f"{user_id}@finpaws.eval", password_hash="!eval"))
            session.commit()
    return user_id


def run_scenario(scenario: Scenario, factory: sessionmaker[Session], kb: KnowledgeBase) -> ScenarioResult:
    user_id = _ensure_user(factory, scenario.user_id)
    thread = f"eval-{scenario.name}-{uuid.uuid4().hex[:8]}"
    tool_calls: list[str] = []
    final_answer = ""
    for message in scenario.messages:
        response = run_agent(
            session_factory=factory, kb=kb, user_id=user_id, message=message, thread_id=thread
        )
        tool_calls.extend(str(call["name"]) for call in response.tool_calls)
        final_answer = response.answer

    expected_tools = set(scenario.expected_tools)
    actual_tools = set(tool_calls)
    return ScenarioResult(
        scenario=scenario.name,
        tools_pass=expected_tools.issubset(actual_tools) if expected_tools else not actual_tools,
        substring_pass=all(s.lower() in final_answer.lower() for s in scenario.expected_substrings),
        tools_called=sorted(actual_tools),
        expected_tools=sorted(expected_tools),
        final_answer=final_answer[:240],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finpaws-evals")
    parser.add_argument("--name", default=None, help="Run only the named scenario")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    selected = [s for s in SCENARIOS if args.name is None or s.name == args.name]
    if not selected:
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        return 2

    factory = _factory()
    kb = build_kb()
    results = [run_scenario(scenario, factory, kb) for scenario in selected]
    passed = sum(1 for result in results if result.passed)

    if args.json:
        summary = {"total": len(results), "passed": passed, "results": [r.model_dump() for r in results]}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{status}] {result.scenario}  tools={result.tools_called} expected={result.expected_tools}"
            )
        print(f"---\n{passed}/{len(results)} scenarios passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
