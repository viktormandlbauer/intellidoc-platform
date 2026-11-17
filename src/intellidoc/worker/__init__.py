"""The worker: runs the engine on queued jobs and records each document's processing status.

    service --Job--> JobQueue --> Worker --> engine.DocumentPipeline --> sinks (storage, index, ...)
                                    |
                                    +--> StatusStore: pending -> processing -> indexed | failed

`JobQueue` and `StatusStore` are interfaces. The in-memory implementations here run everything in
one process (tests, local development); Redis/Celery and a PostgreSQL status table replace them
in production without changing the worker or the service.
"""
from ..contracts import Job, ProcessingState, ProcessingStatus  # re-exported for convenience
from .queue import InMemoryQueue, JobQueue
from .results import InMemoryResultStore
from .runner import Sink, Worker
from .status import InMemoryStatusStore, StatusStore

__all__ = [
    "InMemoryQueue", "InMemoryResultStore", "InMemoryStatusStore", "Job", "JobQueue", "ProcessingState", "ProcessingStatus",
    "Sink", "StatusStore", "Worker",
]
