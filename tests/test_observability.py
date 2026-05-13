from __future__ import annotations

from app.observability.metrics import Counter


def test_counter_inc_snapshot() -> None:
    c = Counter()
    c.inc("a")
    c.inc("a", 2)
    c.inc("b")
    snap = c.snapshot()
    assert snap == {"a": 3, "b": 1}
