from __future__ import annotations

import threading
from collections import defaultdict


class Counter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, int] = defaultdict(int)

    def inc(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._values[name] += by

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


counter = Counter()
