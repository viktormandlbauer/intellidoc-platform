"""Messages between the service and the worker: queue payloads and processing status."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from .results import now_iso

# Bump when Job changes incompatibly. A worker rejects versions it doesn't know instead of
# misreading them, so service and worker can be deployed separately.
JOB_SCHEMA_VERSION = 1

# REQ-ING-5: the lifecycle of a document in the pipeline
ProcessingStatus = Literal["pending", "processing", "indexed", "failed"]


class Job(BaseModel):
    """Process one document. Re-sending the same document is safe: results are keyed by
    `document_id` (REQ-ING-4)."""
    schema_version: Literal[1] = JOB_SCHEMA_VERSION
    document_id: str
    source: str              # where the original is: a local path today, an object-storage key later
    display_name: str
    job_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    attempt: int = 1
    enqueued_at: str = Field(default_factory=now_iso)


class ProcessingState(BaseModel):
    document_id: str
    status: ProcessingStatus
    failed_step: str | None = None  # REQ-ING-6: which step failed, and why
    error: str | None = None
    updated_at: str = Field(default_factory=now_iso)
