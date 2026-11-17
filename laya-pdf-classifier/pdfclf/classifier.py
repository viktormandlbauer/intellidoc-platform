"""Glue: PDF -> text -> Laya -> a flat, gated result."""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .backends import Backend
from .config import Config
from .extract import extract_text

STATUS_AUTO = "auto"      # primary answer is confident enough to act on
STATUS_REVIEW = "review"  # low confidence or too little text: a human should look
STATUS_ERROR = "error"


@dataclass
class Result:
    file: str
    label: str | None
    confidence: float | None
    status: str
    answers: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    low_confidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages_used: int = 0
    pages_total: int = 0
    ocr_used: bool = False
    model: str | None = None
    elapsed_ms: int = 0
    sha256: str | None = None
    size_bytes: int | None = None
    classified_at: str | None = None  # ISO 8601, UTC
    text: str = ""                    # full extracted text; omitted from to_dict() unless asked for

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        d = asdict(self)
        if not include_text:
            d.pop("text", None)
        return d

    def to_row(self) -> dict[str, Any]:
        """Flat row for CSV output."""
        row = {
            "file": self.file,
            "label": self.label,
            "confidence": self.confidence,
            "status": self.status,
            "low_confidence": ";".join(self.low_confidence),
            "warnings": ";".join(self.warnings),
            "ocr_used": self.ocr_used,
            "elapsed_ms": self.elapsed_ms,
        }
        row.update({f"q_{k}": v for k, v in self.flags.items()})
        return row


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_identity(path: str | Path) -> tuple[str, int]:
    """SHA-256 and size of a file: the stable ID of a PDF, independent of name and location."""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _summarise(answer: dict[str, Any]) -> Any:
    """The single value that represents an answer (choice key, P(yes), expected score)."""
    t = answer.get("type")
    if t == "choice":
        return answer.get("choice")
    if t == "noul":
        return answer.get("noul")
    if t == "score":
        return answer.get("score")
    return None


class PdfClassifier:
    def __init__(self, cfg: Config, backend: Backend):
        self.cfg = cfg
        self.backend = backend
        self.questions = cfg.laya_questions()

    def classify_text(self, text: str, name: str = "<text>") -> Result:
        t0 = time.perf_counter()
        payload = self.backend.predict(text, self.questions)
        res = self._build(name, payload, t0)
        res.text = text
        return res

    def classify_file(self, path: str | Path, display_name: str | None = None) -> Result:
        res = self._classify_file(path, display_name or str(path))
        try:
            res.sha256, res.size_bytes = file_identity(path)
        except OSError:
            pass
        return res

    def _classify_file(self, path: str | Path, name: str) -> Result:
        t0 = time.perf_counter()
        try:
            ex = extract_text(
                path,
                max_pages=self.cfg.index_max_pages,
                ocr=self.cfg.ocr,
                ocr_language=self.cfg.ocr_language,
            )
        except Exception as exc:
            return Result(name, None, None, STATUS_ERROR, warnings=[f"extraction failed: {exc}"],
                          classified_at=_now())

        # the full text is stored and indexed; the model only reads the head of the document
        head = ex.head(self.cfg.max_pages, self.cfg.max_chars)
        meta = dict(pages_used=min(len(ex.pages), self.cfg.max_pages), pages_total=ex.pages_total,
                    ocr_used=ex.ocr_used, text=ex.text)
        if len(head.strip()) < 50:
            return Result(
                name, None, None, STATUS_REVIEW,
                warnings=ex.warnings or ["no usable text"],
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                classified_at=_now(), **meta,
            )
        try:
            payload = self.backend.predict(head, self.questions)
        except Exception as exc:
            return Result(name, None, None, STATUS_ERROR, warnings=ex.warnings + [f"model failed: {exc}"],
                          classified_at=_now(), **meta)

        res = self._build(name, payload, t0)
        res.warnings = ex.warnings + res.warnings
        for k, v in meta.items():
            setattr(res, k, v)
        return res

    def _build(self, name: str, payload: dict[str, Any], t0: float) -> Result:
        answers = payload.get("answers", {})
        primary = answers.get(self.cfg.primary, {})
        label = primary.get("choice")
        conf = primary.get("confidence")

        low = [
            qid for qid, a in answers.items()
            if a.get("confidence") is not None and a["confidence"] < self.cfg.threshold(qid)
        ]
        status = STATUS_AUTO if label is not None and self.cfg.primary not in low else STATUS_REVIEW
        return Result(
            file=name,
            label=label,
            confidence=conf,
            status=status,
            answers=answers,
            flags={qid: _summarise(a) for qid, a in answers.items() if qid != self.cfg.primary},
            low_confidence=low,
            model=(payload.get("routing") or {}).get("model") or getattr(self.backend, "name", None),
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            classified_at=_now(),
        )
