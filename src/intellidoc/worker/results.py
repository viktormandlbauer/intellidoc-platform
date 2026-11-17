"""Result store sink: keeps each document's latest result so the Document API can return it."""
from __future__ import annotations

import threading

from ..contracts import ClassificationResult, Job


class InMemoryResultStore:
    """Single-process stand-in for the results table; a worker `Sink` and the service's `ResultReader`."""

    name = "results"

    def __init__(self) -> None:
        self._results: dict[str, ClassificationResult] = {}
        self._lock = threading.Lock()

    def __call__(self, job: Job, result: ClassificationResult) -> None:
        with self._lock:
            self._results[job.document_id] = result

    def get(self, document_id: str) -> ClassificationResult | None:
        with self._lock:
            return self._results.get(document_id)
