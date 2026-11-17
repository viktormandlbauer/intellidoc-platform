"""The worker loop: job -> engine -> sinks, with a status update at every transition."""
from __future__ import annotations

import logging
from typing import Callable, Protocol

from ..contracts import STATUS_ERROR, ClassificationResult, Job, ProcessingState
from ..engine.pipeline import DocumentPipeline
from .queue import JobQueue
from .status import StatusStore

log = logging.getLogger(__name__)


class Sink(Protocol):
    """Where results go after processing, e.g. PostgreSQL. A sink that raises fails the job."""
    name: str

    def __call__(self, job: Job, result: ClassificationResult) -> None: ...


class Worker:
    def __init__(self, pipeline: DocumentPipeline, queue: JobQueue, statuses: StatusStore,
                 sinks: list[Sink] | None = None):
        self.pipeline = pipeline
        self.queue = queue
        self.statuses = statuses
        self.sinks = sinks or []

    def run_once(self, timeout: float | None = None) -> ProcessingState | None:
        """Process the next job, if there is one. Returns the document's final state."""
        job = self.queue.get(timeout)
        return None if job is None else self.process(job)

    def run_forever(self, poll: float = 1.0, stop: Callable[[], bool] = lambda: False) -> None:
        while not stop():
            self.run_once(timeout=poll)

    def process(self, job: Job) -> ProcessingState:
        self.statuses.set(ProcessingState(document_id=job.document_id, status="processing"))
        try:
            result = self.pipeline.process_file(job.source, display_name=job.display_name)
        except Exception as exc:  # the pipeline reports expected failures in the result; this is a bug
            log.exception("pipeline crashed on %s", job.document_id)
            return self._fail(job, "pipeline", str(exc))

        if result.status == STATUS_ERROR:
            return self._fail(job, result.failed_step or "pipeline", "; ".join(result.warnings))
        for sink in self.sinks:
            try:
                sink(job, result)
            except Exception as exc:
                return self._fail(job, sink.name, str(exc))
        # "indexed" is the processing status; whether the label needs review is in the result
        state = ProcessingState(document_id=job.document_id, status="indexed")
        self.statuses.set(state)
        return state

    def _fail(self, job: Job, step: str, error: str) -> ProcessingState:
        state = ProcessingState(document_id=job.document_id, status="failed", failed_step=step, error=error)
        self.statuses.set(state)
        return state
