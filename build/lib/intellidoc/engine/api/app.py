"""HTTP API: upload a PDF, get the classification back."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from ... import __version__
from ..classification import make_classifier
from ..config import load_settings
from ...contracts.results import ClassificationResult
from ..ingestion import is_pdf
from ..pipeline import DocumentPipeline

MAX_UPLOAD = int(os.environ.get("INTELLIDOC_MAX_UPLOAD_MB", "50")) * 1024 * 1024


class TextIn(BaseModel):
    text: str


def create_app(config_path: str, backend: str | None = None) -> FastAPI:
    """``backend`` overrides `classification.backend`."""
    settings = load_settings(config_path)
    c = settings.classification
    pipeline = DocumentPipeline(settings, make_classifier(backend or c.backend, settings))
    app = FastAPI(title="intellidoc", version=__version__)

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": pipeline.classifier.name}

    @app.get("/labels")
    def labels():
        return {"primary": c.primary, "labels": c.labels(), "questions": list(c.questions)}

    @app.get("/model")
    def model():
        """The trained classifier behind the ml/hybrid backends, if any."""
        ml = getattr(pipeline.classifier, "ml", pipeline.classifier)
        m = ml.model() if hasattr(ml, "model") else None
        return {"backend": pipeline.classifier.name, "trained": m.info() if m else None}

    db_state: dict = {}

    def store(result: ClassificationResult):
        """Write to PostgreSQL (lazy connection, table created on first use, reconnect if dropped)."""
        from ..storage.postgres import bulk_index, connect, ensure_schema

        conn = db_state.get("conn")
        if conn is None or conn.closed or conn.broken:
            conn = db_state["conn"] = connect(settings)
            ensure_schema(conn, settings)
        stats = bulk_index(conn, settings, [result])
        if stats["errors"]:
            raise HTTPException(502, f"storing failed: {stats['errors'][0]}")

    @app.post("/classify", response_model=ClassificationResult)
    async def classify(file: UploadFile = File(...), store_result: bool = False):
        """Classify an uploaded PDF. `?store_result=true` also stores it in PostgreSQL."""
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        if not is_pdf(data):
            raise HTTPException(415, "not a PDF")
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            result = pipeline.process_file(tmp, display_name=file.filename or "upload.pdf")
            if store_result:
                store(result)
            return result
        finally:
            Path(tmp).unlink(missing_ok=True)

    @app.post("/classify-text", response_model=ClassificationResult)
    def classify_text(body: TextIn):
        return pipeline.process_text(body.text[: c.max_chars])

    return app


def app_from_env() -> FastAPI:
    """Entry point for `uvicorn intellidoc.engine.api.app:app_from_env --factory`."""
    return create_app(os.environ.get("INTELLIDOC_CONFIG", "config.yaml"),
                      os.environ.get("INTELLIDOC_BACKEND") or None)
