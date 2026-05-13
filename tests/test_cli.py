from __future__ import annotations

import sys

import pytest
from app.main import main


def test_cli_add_expense(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["finpaws", "add-expense", "--amount", "500", "--description", "Яндекс Такси"],
    )

    main()

    assert "Added expense" in capsys.readouterr().out


def test_cli_report(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["finpaws", "add-income", "--amount", "10000", "--description", "Зарплата"],
    )
    main()
    monkeypatch.setattr(sys, "argv", ["finpaws", "report", "--days", "30"])

    main()

    out = capsys.readouterr().out
    assert "Period: 30 days" in out
    assert "Income:" in out


def _run_cli(monkeypatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["finpaws", *argv])
    main()


def test_cli_full_workflow(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _run_cli(monkeypatch, "add-income", "--amount", "100000")
    _run_cli(monkeypatch, "add-expense", "--amount", "5000", "--description", "продукты в магазине")
    _run_cli(monkeypatch, "plan", "--income", "100000")
    _run_cli(monkeypatch, "add-goal", "--name", "Подушка", "--target", "120000", "--months", "12")
    _run_cli(monkeypatch, "goal-progress", "--name", "Подушка", "--amount", "10000")
    _run_cli(monkeypatch, "report", "--days", "30")

    out = capsys.readouterr().out
    assert "Budget plan created for income 100000" in out
    assert "Goal 'Подушка' added" in out
    assert "Goal 'Подушка' progress: 10000/120000" in out
    assert "Categories:" in out
    assert "Goals:" in out


def test_cli_invalid_decimal_prints_clean_error(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["finpaws", "add-expense", "--amount", "notanumber", "--description", "x"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "not a valid decimal" in err
    assert "Traceback" not in err


def test_cli_goal_progress_missing_prints_clean_error(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["finpaws", "goal-progress", "--name", "ghost", "--amount", "100"])
    rc = main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "Goal 'ghost' not found" in err
    assert "Traceback" not in err


def test_cli_negative_amount_rejected(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["finpaws", "add-expense", "--amount", "-50", "--description", "x"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "must be > 0" in err
    assert "Traceback" not in err


def test_cli_duplicate_goal_name_rejected(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _run_cli(monkeypatch, "add-goal", "--name", "Подушка", "--target", "100000", "--months", "12")
    monkeypatch.setattr(
        sys, "argv", ["finpaws", "add-goal", "--name", "Подушка", "--target", "200000", "--months", "6"]
    )
    rc = main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err
    assert "Traceback" not in err


def test_cli_report_formatting_is_consistent(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _run_cli(monkeypatch, "add-income", "--amount", "100000")
    _run_cli(monkeypatch, "add-expense", "--amount", "1500", "--description", "продукты")
    _run_cli(monkeypatch, "report", "--days", "30")
    out = capsys.readouterr().out
    # Every money amount is quantised to 2 decimals — no mix of integer and decimal output.
    assert "Income: 100000.00" in out
    assert "Spent: 1500.00" in out
    assert "Balance: 98500.00" in out
    assert "- food: 1500.00" in out
    # Pluralisation of 'day'/'days' is correct.
    _run_cli(monkeypatch, "report", "--days", "1")
    assert "Period: 1 day\n" in capsys.readouterr().out
