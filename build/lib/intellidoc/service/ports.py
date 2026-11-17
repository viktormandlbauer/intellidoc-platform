"""What the service needs from the processing side, and nothing more.

The worker's queue and status store satisfy these structurally; so will a Redis queue client and
a PostgreSQL status table. The service never imports the worker.
"""
from __future__ import annotations

from typing import Protocol

from ..contracts import Job, ProcessingState


class JobSubmitter(Protocol):
    def put(self, job: Job) -> None: ...


class StatusStore(Protocol):
    def set(self, state: ProcessingState) -> None: ...

    def get(self, document_id: str) -> ProcessingState | None: ...

    def failed(self) -> list[ProcessingState]: ...
