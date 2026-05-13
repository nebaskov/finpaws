from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _empty_state() -> dict[str, Any]:
    return {"transactions": [], "budget_plan": None, "goals": []}


class JsonStorage:
    """A tiny JSON-file state store for the local CLI (``finpaws ...``).

    The API and the agent use PostgreSQL instead; this exists so the CLI works
    with zero infrastructure.
    """

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path

    def load(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return _empty_state()
        raw = self._file_path.read_text(encoding="utf-8").strip()
        if not raw:
            return _empty_state()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return _empty_state()
        return data

    def save(self, payload: dict[str, Any]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
