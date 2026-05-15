"""
mem_log.py – In-memory circular log buffer.

Stores the last N formatted log records in a deque (no disk I/O).
Accessible via /api/debug/logs while the process is alive.

Memory footprint: ~200 bytes/record × 500 records ≈ 100 KB.
"""
from __future__ import annotations
import logging
import signal
import sys
import faulthandler
from collections import deque
from typing import List

_buffer: deque = deque(maxlen=500)


class _MemHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append(self.format(record))
        except Exception:
            pass


def setup(maxlen: int = 500) -> None:
    """Attach in-memory handler to root logger and register SIGUSR2 thread dump."""
    global _buffer
    _buffer = deque(maxlen=maxlen)

    h = _MemHandler()
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root = logging.getLogger()
    root.addHandler(h)
    if root.level == logging.NOTSET:
        root.setLevel(logging.DEBUG)

    # SIGUSR2: dump all Python thread stacks to stderr → captured by journald.
    # Safe: faulthandler handles the signal without terminating the process.
    try:
        faulthandler.register(signal.SIGUSR2, file=sys.stderr,
                               all_threads=True, chain=False)
    except (AttributeError, OSError):
        pass  # faulthandler.register not available on all platforms


def get_lines(n: int = 200) -> List[str]:
    """Return up to n most recent log lines."""
    return list(_buffer)[-min(n, len(_buffer)):]
