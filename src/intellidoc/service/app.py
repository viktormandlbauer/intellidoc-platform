"""Document API (FastAPI). Sketch: no authentication or repositories yet."""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import __version__
from ..contracts import ClassificationResult, Job, ProcessingState
from .ports import JobSubmitter, ResultReader, StatusStore

MAX_UPLOAD = int(os.environ.get("INTELLIDOC_MAX_UPLOAD_MB", "50")) * 1024 * 1024


def is_pdf(data: bytes) -> bool:
    """REQ-DOC-2: judged by content, not by file name or declared MIME type."""
    return data.startswith(b"%PDF")


class DocumentAccepted(BaseModel):
    document_id: str
    name: str
    size_bytes: int
    sha256: str
    status: str


class DocumentOut(BaseModel):
    document_id: str
    name: str
    state: ProcessingState
    result: ClassificationResult | None = None  # set once the document is indexed


def create_app(queue: JobSubmitter, statuses: StatusStore, originals_dir: str | Path,
               results: ResultReader | None = None) -> FastAPI:
    """``originals_dir`` stands in for object storage (S3/MinIO) until that is wired.
    Without ``results``, `GET /documents/{id}` reports the state only."""
    originals = Path(originals_dir)
    originals.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="intellidoc document API", version=__version__)
    sources: dict[str, Job] = {}  # document_id -> last job; replaced by the document table

    def enqueue(job: Job) -> None:
        sources[job.document_id] = job
        statuses.set(ProcessingState(document_id=job.document_id, status="pending"))
        queue.put(job)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # plain `def`: hashing and writing up to MAX_UPLOAD bytes would block the event loop
    @app.post("/documents", status_code=202, response_model=DocumentAccepted)
    def upload(file: UploadFile = File(...)):
        """Store the original and start processing (REQ-DOC-1, REQ-ING-2). Every upload is a new
        document, even with identical content (REQ-DOC-8/9)."""
        data = file.file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        if not is_pdf(data):
            raise HTTPException(415, "not a PDF")
        document_id = uuid.uuid4().hex
        path = originals / f"{document_id}.pdf"
        path.write_bytes(data)
        name = file.filename or "upload.pdf"
        enqueue(Job(document_id=document_id, source=str(path), display_name=name))
        return DocumentAccepted(document_id=document_id, name=name, size_bytes=len(data),
                                sha256=hashlib.sha256(data).hexdigest(), status="pending")

    # declared before /documents/{document_id}/... so "failed" is not taken for an id
    @app.get("/documents/failed", response_model=list[ProcessingState])
    def failed():
        """REQ-ING-7 (the per-repository filter comes with repositories)."""
        return statuses.failed()

    @app.get("/documents/{document_id}", response_model=DocumentOut)
    def document(document_id: str):
        """Processing state and, once indexed, the classification result."""
        state, job = statuses.get(document_id), sources.get(document_id)
        if state is None or job is None:
            raise HTTPException(404, "unknown document")
        result = results.get(document_id) if results is not None else None
        return DocumentOut(document_id=document_id, name=job.display_name, state=state, result=result)

    @app.get("/documents/{document_id}/status", response_model=ProcessingState)
    def status(document_id: str):
        state = statuses.get(document_id)
        if state is None:
            raise HTTPException(404, "unknown document")
        return state

    @app.post("/documents/{document_id}/reprocess", status_code=202, response_model=ProcessingState)
    def reprocess(document_id: str):
        """Re-trigger processing of a failed document (REQ-ING-8)."""
        state, job = statuses.get(document_id), sources.get(document_id)
        if state is None or job is None:
            raise HTTPException(404, "unknown document")
        if state.status != "failed":
            raise HTTPException(409, f"document is {state.status}, only failed documents can be reprocessed")
        enqueue(job.model_copy(update={"job_id": uuid.uuid4().hex, "attempt": job.attempt + 1}))
        return statuses.get(document_id)

    return app
