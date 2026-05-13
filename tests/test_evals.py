from __future__ import annotations

import json

from app.agent.kb import KnowledgeBase
from app.evals import runner
from app.evals.scenarios import SCENARIOS, Scenario


def test_scenarios_loaded() -> None:
    assert SCENARIOS
    assert all(isinstance(s, Scenario) for s in SCENARIOS)


def test_run_scenario_with_stubbed_agent(monkeypatch) -> None:
    factory = runner._factory()

    class _Resp:
        def __init__(self, tool_calls, answer):
            self.tool_calls = [{"name": n} for n in tool_calls]
            self.answer = answer

    answers = iter([_Resp(["add_expense"], "ok")])

    def fake_run_agent(**kwargs):
        return next(answers)

    monkeypatch.setattr(runner, "run_agent", fake_run_agent)
    scen = Scenario(name="x", user_id="u-eval", messages=["hi"], expected_tools=["add_expense"])
    result = runner.run_scenario(scen, factory, kb=KnowledgeBase(None))
    assert result.tools_pass
    assert result.substring_pass
    assert result.passed


def test_runner_main_with_stubbed_agent(monkeypatch, capsys) -> None:
    class _Resp:
        tool_calls = [{"name": "add_expense"}]
        answer = "transport income 50"

    monkeypatch.setattr(runner, "build_kb", lambda: KnowledgeBase(None))
    monkeypatch.setattr(runner, "run_agent", lambda **kw: _Resp())
    rc = runner.main(["--name", "single_expense_categorized"])
    assert rc == 0
    assert "PASS" in capsys.readouterr().out


def test_runner_main_unknown_scenario(capsys) -> None:
    rc = runner.main(["--name", "does-not-exist"])
    assert rc == 2
    assert "unknown scenario" in capsys.readouterr().err


def test_runner_main_json_output(monkeypatch, capsys) -> None:
    class _Resp:
        tool_calls = [{"name": "add_expense"}]
        answer = "transport"

    monkeypatch.setattr(runner, "build_kb", lambda: KnowledgeBase(None))
    monkeypatch.setattr(runner, "run_agent", lambda **kw: _Resp())
    rc = runner.main(["--name", "single_expense_categorized", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
