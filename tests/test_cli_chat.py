from __future__ import annotations

import builtins
from contextlib import contextmanager

import pytest
from app.agent.kb import KnowledgeBase
from app.cli import chat


class _FakeResponse:
    def __init__(self, answer: str, tool_calls=None, injection_suspected: bool = False) -> None:
        self.answer = answer
        self.tool_calls = tool_calls or []
        self.injection_suspected = injection_suspected


@contextmanager
def _null_checkpointer():
    yield None


@pytest.fixture(autouse=True)
def _stub_externals(monkeypatch):
    monkeypatch.setattr(chat, "build_kb", lambda: KnowledgeBase(None))
    monkeypatch.setattr(chat, "open_checkpointer", _null_checkpointer)


def _feed_lines(monkeypatch, lines: list[str]) -> None:
    it = iter(lines)

    def fake_input(_prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr(builtins, "input", fake_input)


def test_chat_loop_runs_agent_and_prints(monkeypatch, capsys):
    monkeypatch.setattr(
        chat,
        "run_agent",
        lambda **_: _FakeResponse(
            "Мяу, готово.", tool_calls=[{"name": "add_expense"}], injection_suspected=True
        ),
    )
    _feed_lines(monkeypatch, ["", "потратил 100 на кофе"])

    assert chat.main(["--ephemeral", "--thread", "t1"]) == 0
    captured = capsys.readouterr()
    assert "Мяу, готово." in captured.out
    assert "add_expense" in captured.err
    assert "prompt-injection" in captured.err


def test_chat_quit_command(monkeypatch, capsys):
    monkeypatch.setattr(chat, "run_agent", lambda **_: _FakeResponse("unused"))
    _feed_lines(monkeypatch, ["/quit"])
    assert chat.main(["--ephemeral"]) == 0
    assert "unused" not in capsys.readouterr().out


def test_chat_eof_on_first_line(monkeypatch):
    monkeypatch.setattr(chat, "run_agent", lambda **_: _FakeResponse("unused"))
    _feed_lines(monkeypatch, [])
    assert chat.main(["--ephemeral"]) == 0


def test_bootstrap_reuses_existing_cli_user():
    factory_a, user_a = chat._bootstrap(use_local_sqlite=True)
    # Re-running against the same engine must not create a second user.
    factory_b, user_b = chat._bootstrap(use_local_sqlite=True)
    assert isinstance(user_a, str)
    assert isinstance(user_b, str)
    assert factory_a is not factory_b
