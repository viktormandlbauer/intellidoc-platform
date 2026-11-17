"""Local development: the Document API with an in-process worker, in one process.

This is the composition root, the one place that wires service, worker and engine together.
In production the same pieces run as separate processes connected by a real queue.

    intellidoc serve-stack --port 8080
    uvicorn intellidoc.devstack:app_from_env --factory
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .engine.classification import make_classifier
from .engine.config import load_settings
from .engine.pipeline import DocumentPipeline
from .service import create_app as create_service
from .worker import InMemoryQueue, InMemoryStatusStore, Worker


def create_app(config_path: str, backend: str | None = None, originals_dir: str = "data/originals") -> FastAPI:
    settings = load_settings(config_path)
    pipeline = DocumentPipeline(settings, make_classifier(backend or settings.classification.backend, settings))
    queue, statuses = InMemoryQueue(), InMemoryStatusStore()
    worker = Worker(pipeline, queue, statuses)
    stop = threading.Event()

    app = create_service(queue, statuses, originals_dir)
    app.state.worker = worker

    @asynccontextmanager
    async def lifespan(_app):
        t = threading.Thread(target=worker.run_forever, kwargs={"poll": 0.2, "stop": stop.is_set},
                             name="intellidoc-worker", daemon=True)
        t.start()
        yield
        stop.set()
        t.join(timeout=5)

    app.router.lifespan_context = lifespan
    return app


def app_from_env() -> FastAPI:
    return create_app(os.environ.get("INTELLIDOC_CONFIG", "config.yaml"),
                      os.environ.get("INTELLIDOC_BACKEND") or None,
                      os.environ.get("INTELLIDOC_ORIGINALS_DIR", "data/originals"))
