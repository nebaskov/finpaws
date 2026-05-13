from __future__ import annotations

import asyncio
import json

from app.agent.kb import KnowledgeBase
from app.evals import deepeval_runner, runner
from app.evals.judge import OpenAICompatibleJudge
from app.evals.scenarios import SCENARIOS, Scenario
from pydantic import BaseModel


class _Completion:
    def __init__(self, content: str) -> None:
        message = type("Msg", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": message})()]


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = type("Completions", (), {"create": lambda _self, **_kw: _Completion(content)})()


class _FakeOpenAI:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


class _FakeAsyncChat:
    def __init__(self, content: str) -> None:
        async def _create(_self: object, **_kw: object) -> _Completion:
            return _Completion(content)

        self.completions = type("AsyncCompletions", (), {"create": _create})()


class _FakeAsyncOpenAI:
    def __init__(self, content: str) -> None:
        self.chat = _FakeAsyncChat(content)


class _Score(BaseModel):
    score: int
    reason: str


def test_judge_construct_and_model_name() -> None:
    judge = OpenAICompatibleJudge(model="judge-x", base_url="http://localhost/v1", api_key="k")
    assert judge.get_model_name() == "judge-x"
    assert judge.load_model() is not None


def test_judge_generate_text() -> None:
    judge = OpenAICompatibleJudge(model="j", api_key="k", client=_FakeOpenAI("a verdict"))
    assert judge.generate("rate this") == "a verdict"


def test_judge_generate_with_schema() -> None:
    judge = OpenAICompatibleJudge(model="j", api_key="k", client=_FakeOpenAI('{"score": 8, "reason": "ok"}'))
    result = judge.generate("rate this", schema=_Score)
    assert isinstance(result, _Score)
    assert result.score == 8


def test_judge_a_generate_text() -> None:
    judge = OpenAICompatibleJudge(
        model="j", api_key="k", client=_FakeOpenAI("sync"), async_client=_FakeAsyncOpenAI("async verdict")
    )
    assert asyncio.run(judge.a_generate("rate this")) == "async verdict"


def test_build_dataset_covers_all_scenarios() -> None:
    dataset = deepeval_runner.build_dataset()
    assert len(dataset.goldens) == len(SCENARIOS)
    by_input = {g.input: g for g in dataset.goldens}
    rag = by_input["объясни правило 50 30 20"]
    assert [t.name for t in rag.expected_tools] == ["search_advice"]
    assert rag.context


def test_build_metrics_includes_tool_correctness_and_geval() -> None:
    judge = OpenAICompatibleJudge(model="j", api_key="k", client=_FakeOpenAI("{}"))
    metrics = deepeval_runner.build_metrics(judge=judge)
    assert len(metrics) == 4
    names = {getattr(m, "name", type(m).__name__) for m in metrics}
    assert "Faithfulness" in names
    assert "Helpfulness" in names
    assert "Safety" in names


def test_run_agent_on_scenarios_builds_test_cases(monkeypatch) -> None:
    class _Resp:
        tool_calls = [
            {"name": "add_expense", "args": {"amount": "850"}, "output": '{"category": "transport"}'}
        ]
        answer = "записал"

    monkeypatch.setattr(deepeval_runner, "run_agent", lambda **_: _Resp())
    factory = runner._factory()
    scenario = Scenario(
        name="x",
        user_id="deepeval-test-u",
        messages=["раз", "два"],
        expected_tools=["add_expense"],
        expected_output="ok",
        reference_facts=["f"],
    )
    runs = deepeval_runner.run_agent_on_scenarios([scenario], factory=factory, kb=KnowledgeBase(None))
    assert len(runs) == 1
    assert runs[0].input == "два"
    assert runs[0].actual_output == "записал"
    assert [c["name"] for c in runs[0].tool_calls] == ["add_expense", "add_expense"]

    test_cases = deepeval_runner.to_test_cases(runs)
    assert test_cases[0].input == "два"
    called = test_cases[0].tools_called or []
    assert [t.name for t in called] == ["add_expense", "add_expense"]
    assert called[0].output == '{"category": "transport"}'
    assert [t.name for t in test_cases[0].expected_tools] == ["add_expense"]


def test_main_dry_run(capsys) -> None:
    rc = deepeval_runner.main(["--dry-run"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["goldens"] == len(SCENARIOS)
    assert {c["name"] for c in payload["cases"]} == {s.name for s in SCENARIOS}


def test_main_dry_run_filtered(capsys) -> None:
    rc = deepeval_runner.main(["--dry-run", "--name", "rag_advice"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [c["name"] for c in payload["cases"]] == ["rag_advice"]


def test_main_unknown_scenario(capsys) -> None:
    assert deepeval_runner.main(["--name", "does-not-exist"]) == 2
    assert "unknown scenario" in capsys.readouterr().err
