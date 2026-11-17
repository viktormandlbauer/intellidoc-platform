"""Laya: zero-shot decision model (optional dependency, `pip install 'intellidoc[laya]'`).

Answers every configured question with typed answers and confidences, no training needed.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

# Laya reads each choice label with a share of one option budget; past ~16 labels the
# README recommends coarse-to-fine. predict_tournament answers groups, then the finalists.
TOURNAMENT_THRESHOLD = 16


class LayaBackend:
    def __init__(
        self,
        checkpoint: str = "multilingual",
        device: str = "auto",
        scan: str = "first",
        max_len: int | None = None,
        head_max_len: int | None = None,
        preload: bool = False,
    ):
        self.checkpoint = checkpoint
        self.device = None if device == "auto" else device
        self.scan = scan
        self.max_len = max_len
        self.head_max_len = head_max_len
        self.name = f"laya:{checkpoint}"
        self._router = None
        self._lock = threading.Lock()  # torch inference is not re-entrant across requests here
        if preload:
            self._get_router()

    def _get_router(self):
        if self._router is None:
            try:
                from laya import Router
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise RuntimeError("laya is not installed: pip install 'intellidoc[laya]'") from exc
            kwargs: dict[str, Any] = {}
            if self.device:
                kwargs["device"] = self.device
            if self.checkpoint != "auto":
                kwargs["max_loaded"] = 1
            log.info("loading Laya router (%s)", self.checkpoint)
            self._router = Router(**kwargs)
            if self.checkpoint != "auto":
                self._router.preload([self.checkpoint])
        return self._router

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        router = self._get_router()
        state = {"body": text}
        kw: dict[str, Any] = {}
        if self.checkpoint != "auto":
            kw["model"] = self.checkpoint

        big_choice = any(
            q["type"] == "choice" and len(q["criteria"]) > TOURNAMENT_THRESHOLD
            for q in questions.values()
        )
        with self._lock:
            if self.scan == "long":
                return router.predict_long(state, questions, **kw)
            if self.max_len:
                kw["max_len"] = self.max_len
            if self.head_max_len:
                kw["head_max_len"] = self.head_max_len
            if big_choice:
                from laya import predict_tournament

                return predict_tournament(router, state, questions, **kw)
            return router.predict(state, questions, **kw)
