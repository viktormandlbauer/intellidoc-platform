"""Processing status store interface and an in-process implementation."""
from __future__ import annotations

import threading
from typing import Protocol

from ..contracts import ProcessingState


class StatusStore(Protocol):
    def set(self, state: ProcessingState) -> None: ...

    def get(self, document_id: str) -> ProcessingState | None: ...

    def failed(self) -> list[ProcessingState]:
        """Documents whose processing failed (REQ-ING-7)."""


class InMemoryStatusStore:
    def __init__(self) -> None:
        self._states: dict[str, ProcessingState] = {}
        self._lock = threading.Lock()

    def set(self, state: ProcessingState) -> None:
        with self._lock:
            self._states[state.document_id] = state

    def get(self, document_id: str) -> ProcessingState | None:
        with self._lock:
            return self._states.get(document_id)

    def failed(self) -> list[ProcessingState]:
        with self._lock:
            return [s for s in self._states.values() if s.status == "failed"]
