"""What the engine produces for one document.

`ClassificationResult` is the engine API's response schema and what the worker hands to its
sinks: one document after parsing, classification and the confidence gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["auto", "review", "error"]
STATUS_AUTO: Status = "auto"      # primary answer is confident enough to act on
STATUS_REVIEW: Status = "review"  # low confidence or too little text: a human should look
STATUS_ERROR: Status = "error"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ClassificationResult(BaseModel):
    file: str
    label: str | None = None
    confidence: float | None = None
    status: Status
    failed_step: str | None = None  # with status "error": the stage that failed ("parsing", "classification")
    answers: dict[str, Any] = Field(default_factory=dict)  # every question's raw answer
    flags: dict[str, Any] = Field(default_factory=dict)    # one summary value per non-primary question
    low_confidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pages_used: int = 0
    pages_total: int = 0
    ocr_used: bool = False
    model: str | None = None
    elapsed_ms: int = 0
    sha256: str | None = None
    size_bytes: int | None = None
    classified_at: str | None = None  # ISO 8601, UTC
    text: str = Field("", exclude=True)  # full extracted text; left out of the API response

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        d = self.model_dump()
        if include_text:
            d["text"] = self.text
        return d
