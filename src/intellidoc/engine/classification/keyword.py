"""Keyword-overlap stand-in with Laya's output shape.

Deterministic and model-free: it lets you test the pipeline, CLI, API and evaluation without
downloading weights or installing torch. It is NOT a classifier you should use for real.
"""
from __future__ import annotations

import math
import re
from typing import Any

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
