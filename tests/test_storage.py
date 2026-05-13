from __future__ import annotations

from app.services.storage import JsonStorage


def test_load_missing_file(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "missing.json")

    state = storage.load()

    assert state == {"transactions": [], "budget_plan": None, "goals": []}


def test_save_then_load(tmp_path) -> None:
    storage = JsonStorage(tmp_path / "state.json")
    payload = {
        "transactions": [{"id": "1"}],
        "budget_plan": {"monthly_income": "100"},
        "goals": [{"name": "Подушка"}],
    }

    storage.save(payload)
    loaded = storage.load()

    assert loaded == payload


def test_load_empty_file(tmp_path) -> None:
    file_path = tmp_path / "state.json"
    file_path.write_text("", encoding="utf-8")
    storage = JsonStorage(file_path)

    assert storage.load() == {"transactions": [], "budget_plan": None, "goals": []}
