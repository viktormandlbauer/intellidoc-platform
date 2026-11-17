"""Confidence gate: turn a classifier payload into label, status and per-question flags."""
from __future__ import annotations

from typing import Any

from ..config import ClassificationSettings
from ...contracts.results import STATUS_AUTO, STATUS_REVIEW


def summarise(answer: dict[str, Any]) -> Any:
    """The single value that represents an answer (choice key, P(yes), expected score)."""
    t = answer.get("type")
    if t == "choice":
        return answer.get("choice")
    if t == "noul":
        return answer.get("noul")
    if t == "score":
        return answer.get("score")
    return None


def gate(payload: dict[str, Any], cfg: ClassificationSettings) -> dict[str, Any]:
    """`ClassificationResult` fields decided by the answers. The primary answer must reach its
    threshold for status "auto"; other questions below theirs are only listed in `low_confidence`."""
    answers = payload.get("answers", {})
    primary = answers.get(cfg.primary, {})
    label = primary.get("choice")

    low = [
        qid for qid, a in answers.items()
        if qid in cfg.questions and a.get("confidence") is not None and a["confidence"] < cfg.threshold(qid)
    ]
    return {
        "label": label,
        "confidence": primary.get("confidence"),
        "status": STATUS_AUTO if label is not None and cfg.primary not in low else STATUS_REVIEW,
        "answers": answers,
        "flags": {qid: summarise(a) for qid, a in answers.items() if qid != cfg.primary},
        "low_confidence": low,
        "model": (payload.get("routing") or {}).get("model"),
    }
