"""Job queue interface and an in-process implementation."""
from __future__ import annotations

import queue
from typing import Protocol

from ..contracts import Job


class JobQueue(Protocol):
    def put(self, job: Job) -> None: ...

    def get(self, timeout: float | None = None) -> Job | None:
        """The next job, or None if none arrived within ``timeout`` seconds (None = don't wait)."""


class InMemoryQueue:
    """Single-process queue for tests and local development."""

    def __init__(self) -> None:
        self._q: queue.Queue[Job] = queue.Queue()

    def put(self, job: Job) -> None:
        self._q.put(job)

    def get(self, timeout: float | None = None) -> Job | None:
        try:
            return self._q.get(block=timeout is not None, timeout=timeout)
        except queue.Empty:
            return None
