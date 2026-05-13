from __future__ import annotations

import shutil
from datetime import date
from decimal import Decimal

import pytest
from app.config import SETTINGS
from app.integrations import hledger as hledger_mod


def test_format_and_append(tmp_path, monkeypatch) -> None:
    journal = tmp_path / "test.journal"
    monkeypatch.setattr(SETTINGS, "hledger_journal", str(journal))
    monkeypatch.setattr(SETTINGS, "hledger_mirror_enabled", True)

    ok = hledger_mod.append_expense(Decimal("123.45"), "RUB", "Кофе у дома", "food", date(2026, 1, 5))
    assert ok
    text = journal.read_text(encoding="utf-8")
    assert "2026-01-05 Кофе у дома" in text
    assert "expenses:food" in text
    assert "123.45 RUB" in text


def test_import_journal_round_trip(tmp_path) -> None:
    src = tmp_path / "src.journal"
    src.write_text(
        "2026-02-01 Salary\n"
        "    income:salary    -50000.00 RUB\n"
        "    assets:cash    50000.00 RUB\n\n"
        "2026-02-02 Lunch\n"
        "    expenses:food    250.00 RUB\n"
        "    assets:cash    -250.00 RUB\n",
        encoding="utf-8",
    )
    entries = hledger_mod.import_journal(src)
    assert len(entries) == 2
    assert entries[0].description == "Salary"
    assert entries[1].postings[0].amount == Decimal("250.00")


def test_run_missing_binary(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(hledger_mod.HledgerError, match="binary not found"):
        hledger_mod._run(["balance"])
