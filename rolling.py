from __future__ import annotations
import time
from collections import deque


def mono_ns() -> int:
    return time.monotonic_ns()


class RollingCounter:
    def __init__(self, window_s: int):
        self.window_s = int(window_s)
        self._q: deque[int] = deque()

    def add(self) -> None:
        self._q.append(mono_ns())
        self._trim()

    def _trim(self) -> None:
        cutoff = mono_ns() - int(self.window_s * 1e9)
        while self._q and self._q[0] < cutoff:
            self._q.popleft()

    def count(self) -> int:
        self._trim()
        return len(self._q)
