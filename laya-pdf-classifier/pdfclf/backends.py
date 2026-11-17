"""Model backends.

`LayaBackend` is the zero-shot model, `MLBackend` (ml.py) the trained paperless-ngx-style one,
`HybridBackend` combines them. `KeywordBackend` is a deterministic, model-free stand-in
with the same output shape: it lets you test the pipeline, CLI, API and evaluation without
downloading weights or installing torch. It is NOT a classifier you should use for real.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Laya reads each choice label with a share of one option budget; past ~16 labels the
# README recommends coarse-to-fine. predict_tournament answers groups, then the finalists.
TOURNAMENT_THRESHOLD = 16


class Backend(Protocol):
    name: str

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Return Laya's payload: {"answers": {qid: {...}}, ...}."""


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
                raise RuntimeError("laya is not installed: pip install laya") from exc
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


_TOKEN = re.compile(r"[a-zäöüß]{3,}", re.IGNORECASE)
_STOP = {
    "the", "and", "for", "not", "with", "above", "anything", "else", "such", "this", "that",
    "der", "die", "das", "und", "oder", "mit", "von", "für",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text)} - _STOP


def _softmax(xs: list[float]) -> list[float]:
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e)
    return [v / s for v in e]


class KeywordBackend:
    """Keyword-overlap stand-in returning Laya-shaped answers. For tests and dry runs only."""

    name = "keyword-standin"

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        words = _tokens(text)
        answers: dict[str, Any] = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                keys = list(q["criteria"])
                scores = [
                    1.5 * len(words & _tokens(f"{k.replace('_', ' ')} {desc}"))
                    for k, desc in q["criteria"].items()
                ]
                probs = _softmax(scores)
                best = max(range(len(keys)), key=probs.__getitem__)
                answers[qid] = {
                    "type": "choice",
                    "choice": keys[best],
                    "probabilities": {k: round(p, 4) for k, p in zip(keys, probs)},
                    "confidence": round(probs[best], 4),
                }
            elif q["type"] == "score":
                n = len(q["criteria"])
                answers[qid] = {
                    "type": "score",
                    "score": (n - 1) / 2,
                    "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                    "confidence": round(1 / n, 4),
                }
            else:
                hit = len(words & _tokens(q["instructions"])) >= 2
                p = 0.7 if hit else 0.3
                answers[qid] = {"type": "noul", "noul": p, "confidence": max(p, 1 - p)}
        return {"answers": answers, "routing": {"model": self.name}}


def _brief(a: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"choice": a.get("choice"), "confidence": a.get("confidence")} if a else None


class HybridBackend:
    """Laya for every question, the trained model (ml.py) for the primary one.

    Until a model has been trained this is plain Laya, so you can start zero-shot and switch to
    learned labels once you have filed or reviewed enough documents (the paperless-ngx workflow).
    `combine`:
      - "ml":      the trained model decides the primary label; Laya is not asked that question.
      - "average": weighted mean of both probability distributions (`weight` = share of the model).
    The primary answer records both opinions under `sources`.
    """

    def __init__(self, zero_shot: Backend, ml, primary: str, combine: str = "ml", weight: float = 0.7):
        self.zero_shot = zero_shot
        self.ml = ml
        self.primary = primary
        self.combine = combine
        self.weight = weight

    @property
    def name(self) -> str:
        return f"{self.zero_shot.name}+{self.ml.name}"

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        q = questions.get(self.primary)
        if self.ml.model() is None or not q or q["type"] != "choice":
            return self.zero_shot.predict(text, questions)
        ml_ans = self.ml.answer(text, q["criteria"])
        if ml_ans is None:
            return self.zero_shot.predict(text, questions)

        if self.combine == "ml":
            rest = {k: v for k, v in questions.items() if k != self.primary}
            payload = self.zero_shot.predict(text, rest) if rest else {"answers": {}}
            zs_ans = None
            combined = dict(ml_ans)
        else:
            payload = self.zero_shot.predict(text, questions)
            zs_ans = payload.get("answers", {}).get(self.primary)
            combined = self._average(ml_ans, zs_ans) if zs_ans else dict(ml_ans)

        combined["sources"] = {"ml": _brief(ml_ans), "laya": _brief(zs_ans)}
        payload.setdefault("answers", {})[self.primary] = combined
        routing = payload.setdefault("routing", {})
        routing["model"] = f"{routing.get('model') or self.zero_shot.name}+{self.ml.name}"
        return payload

    def _average(self, ml_ans: dict[str, Any], zs_ans: dict[str, Any]) -> dict[str, Any]:
        w = self.weight
        p_ml, p_zs = ml_ans["probabilities"], zs_ans.get("probabilities") or {}
        if not p_zs:  # e.g. a tournament answer without the full distribution
            p_zs = {zs_ans.get("choice"): zs_ans.get("confidence") or 0.0}
        probs = {k: w * p_ml.get(k, 0.0) + (1 - w) * p_zs.get(k, 0.0) for k in p_ml}
        best = max(probs, key=probs.__getitem__)
        return {
            "type": "choice",
            "choice": best,
            "probabilities": {k: round(v, 4) for k, v in probs.items()},
            "confidence": round(probs[best], 4),
        }


BACKENDS = ("laya", "ml", "hybrid", "keyword")


def make_backend(name: str, cfg) -> Backend:
    if name == "laya":
        return LayaBackend(cfg.checkpoint, cfg.device, cfg.scan, cfg.max_len, cfg.head_max_len)
    if name == "keyword":
        return KeywordBackend()
    if name in ("ml", "hybrid"):
        from .ml import MLBackend

        ml = MLBackend(cfg.ml_model_path)
        if name == "ml":
            return ml
        laya = LayaBackend(cfg.checkpoint, cfg.device, cfg.scan, cfg.max_len, cfg.head_max_len)
        return HybridBackend(laya, ml, cfg.primary, cfg.ml_combine, cfg.ml_weight)
    raise ValueError(f"unknown backend '{name}' (use one of {', '.join(BACKENDS)})")
