"""Classification: text -> typed answers to the configured questions -> confidence gate.

A `Classifier` returns Laya's payload shape, whatever model is behind it:

    {"answers": {qid: {"type", "choice" | "noul" | "score", "confidence", ...}}, "routing": {"model"}}

Backends:
    laya     zero-shot decision model (optional dependency), answers every question
    ml       trained n-gram MLP (paperless-ngx style), answers the primary question only
    hybrid   ml for the primary question, laya for the rest; plain laya until a model is trained
    keyword  deterministic stand-in for tests and dry runs
"""
from __future__ import annotations

from typing import Any, Protocol

from ..config import BACKENDS


class Classifier(Protocol):
    name: str

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Return Laya's payload: {"answers": {qid: {...}}, ...}."""


def make_classifier(name: str, settings) -> Classifier:
    c = settings.classification
    if name == "keyword":
        from .keyword import KeywordBackend

        return KeywordBackend()

    def laya():
        from .laya import LayaBackend

        return LayaBackend(c.laya.checkpoint, c.laya.device, c.laya.scan, c.laya.max_len, c.laya.head_max_len)

    if name == "laya":
        return laya()
    if name in ("ml", "hybrid"):
        from .trained import MLBackend

        ml = MLBackend(c.ml.model_path)
        if name == "ml":
            return ml
        from .hybrid import HybridBackend

        return HybridBackend(laya(), ml, c.primary, c.ml.combine, c.ml.weight)
    raise ValueError(f"unknown backend '{name}' (use one of {', '.join(BACKENDS)})")


__all__ = ["BACKENDS", "Classifier", "make_classifier"]
