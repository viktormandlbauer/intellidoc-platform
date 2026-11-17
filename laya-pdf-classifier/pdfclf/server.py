"""HTTP API: upload a PDF, get the classification back."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .backends import make_backend
from .classifier import PdfClassifier
from .config import load_config

MAX_UPLOAD = int(os.environ.get("PDFCLF_MAX_UPLOAD_MB", "50")) * 1024 * 1024


class TextIn(BaseModel):
    text: str


def create_app(config_path: str, backend: str = "laya") -> FastAPI:
    cfg = load_config(config_path)
    clf = PdfClassifier(cfg, make_backend(backend, cfg))
    app = FastAPI(title="laya-pdf-classifier", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": clf.backend.name}

    @app.get("/labels")
    def labels():
        return {"primary": cfg.primary, "labels": cfg.labels(), "questions": list(cfg.questions)}

    @app.get("/model")
    def model():
        """The trained classifier behind the ml/hybrid backends, if any."""
        ml = getattr(clf.backend, "ml", clf.backend)
        m = ml.model() if hasattr(ml, "model") else None
        return {"backend": clf.backend.name, "trained": m.info() if m else None}

    db_state: dict = {}

    def store(result):
        """Write to PostgreSQL (lazy connection, table created on first use, reconnect if dropped)."""
        from .db import bulk_index, connect, ensure_schema

        conn = db_state.get("conn")
        if conn is None or conn.closed or conn.broken:
            conn = db_state["conn"] = connect(cfg)
            ensure_schema(conn, cfg)
        stats = bulk_index(conn, cfg, [result])
        if stats["errors"]:
            raise HTTPException(502, f"storing failed: {stats['errors'][0]}")

    @app.post("/classify")
    async def classify(file: UploadFile = File(...), store_result: bool = False):
        """Classify an uploaded PDF. `?store_result=true` also stores it in PostgreSQL."""
        data = await file.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "not a PDF")
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            result = clf.classify_file(tmp, display_name=file.filename or "upload.pdf")
            if store_result:
                store(result)
            return result.to_dict()
        finally:
            Path(tmp).unlink(missing_ok=True)

    @app.post("/classify-text")
    def classify_text(body: TextIn):
        return clf.classify_text(body.text[: cfg.max_chars]).to_dict()

    return app


def app_from_env() -> FastAPI:
    """Entry point for `uvicorn pdfclf.server:app_from_env --factory`."""
    return create_app(os.environ.get("PDFCLF_CONFIG", "config.yaml"),
                      os.environ.get("PDFCLF_BACKEND", "laya"))
