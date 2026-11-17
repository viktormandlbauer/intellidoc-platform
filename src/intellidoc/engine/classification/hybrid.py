"""Hybrid: the trained model decides the primary label, Laya answers the rest."""
from __future__ import annotations

from typing import Any

from . import Classifier


def _brief(a: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"choice": a.get("choice"), "confidence": a.get("confidence")} if a else None


class HybridBackend:
    """Laya for every question, the trained model (trained.py) for the primary one.

    Until a model has been trained this is plain Laya, so you can start zero-shot and switch to
    learned labels once you have filed or reviewed enough documents (the paperless-ngx workflow).
    `combine`:
      - "ml":      the trained model decides the primary label; Laya is not asked that question.
      - "average": weighted mean of both probability distributions (`weight` = share of the model).
    The primary answer records both opinions under `sources`.
    """

    def __init__(self, zero_shot: Classifier, ml, primary: str, combine: str = "ml", weight: float = 0.7):
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
