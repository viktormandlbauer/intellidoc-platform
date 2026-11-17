"""Settings: one YAML file, one section per pipeline stage.

    parsing:         PDF -> text (Docling, OCR)
    classification:  which backend, the questions it answers, the confidence gate
    storage:         PostgreSQL

Every section is a Pydantic model, so a typo or a value out of range fails at startup with the
offending key in the message instead of somewhere in the pipeline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

IDENT = r"^[a-z_][a-z0-9_]{0,62}$"
BACKENDS = ("laya", "ml", "hybrid", "keyword")


class ConfigError(ValueError):
    pass


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


# ---- parsing ----------------------------------------------------------------------------------
class ParsingSettings(_Section):
    max_pages: int | None = Field(None, ge=1)  # pages extracted, stored and searched; None = all
    ocr: bool = True                           # OCR scanned PDFs (Tesseract if installed)
    ocr_language: str = "deu+eng"              # Tesseract language codes


# ---- classification ---------------------------------------------------------------------------
class LayaSettings(_Section):
    checkpoint: Literal["english", "multilingual", "typed-decisions", "auto"] = "multilingual"
    device: str = "auto"                       # cpu | cuda | mps | auto
    scan: Literal["first", "long"] = "first"
    max_len: int | None = None                 # override the checkpoint's token window
    head_max_len: int | None = None            # override the token budget for the question/options


class TrainedSettings(_Section):
    model_path: str = "models/classifier.pkl"
    combine: Literal["ml", "average"] = "ml"   # hybrid only
    weight: float = Field(0.7, ge=0.0, le=1.0)
    min_df: float | int = 0.01


class Question(_Section):
    type: Literal["choice", "noul", "score"]
    instructions: str = Field(min_length=1)
    labels: dict[str, str] | None = None       # choice: label key -> description
    levels: list[str] | None = None            # score: ordered levels
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _criteria(self) -> Question:
        if self.type == "choice" and len(self.labels or {}) < 2:
            raise ValueError("choice needs at least 2 labels (key: description)")
        if self.type == "score" and len(self.levels or []) < 2:
            raise ValueError("score needs at least 2 levels")
        return self


class ClassificationSettings(_Section):
    backend: Literal[BACKENDS] = "hybrid"
    primary: str = "document_type"             # the choice question whose answer is "the" class
    min_confidence: float = Field(0.6, ge=0.0, le=1.0)
    max_pages: int = Field(3, ge=1)            # the classifier reads only the first N pages ...
    max_chars: int = Field(6000, ge=1)         # ... capped at this many characters
    laya: LayaSettings = Field(default_factory=LayaSettings)
    ml: TrainedSettings = Field(default_factory=TrainedSettings)
    questions: dict[str, Question] = Field(min_length=1)

    @model_validator(mode="after")
    def _primary(self) -> ClassificationSettings:
        if self.primary not in self.questions:
            raise ValueError(f"primary '{self.primary}' is not a defined question")
        if self.questions[self.primary].type != "choice":
            raise ValueError("primary must be a choice question")
        return self

    def laya_questions(self) -> dict[str, dict[str, Any]]:
        """Questions in the shape `laya.Router.predict` (and every backend) expects."""
        out = {}
        for qid, q in self.questions.items():
            item: dict[str, Any] = {"type": q.type, "instructions": q.instructions}
            if q.type == "choice":
                item["criteria"] = dict(q.labels)
            elif q.type == "score":
                item["criteria"] = list(q.levels)
            out[qid] = item
        return out

    def labels(self, qid: str | None = None) -> list[str]:
        return list(self.questions[qid or self.primary].labels or {})

    def threshold(self, qid: str) -> float:
        q = self.questions[qid]
        return self.min_confidence if q.min_confidence is None else q.min_confidence

    def config_hash(self) -> str:
        """Short hash of the question/label definitions. Stored with each result so you can tell
        which label set produced it after you change the config."""
        blob = json.dumps(self.laya_questions(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


# ---- storage ----------------------------------------------------------------------------------
class StorageSettings(_Section):
    url: str = "postgresql://intellidoc:intellidoc@localhost:5432/intellidoc"  # DATABASE_URL overrides
    table: str = Field("documents", pattern=IDENT)
    text_search: list[str] = Field(default_factory=lambda: ["german", "english"])
    store_text: bool = True

    @field_validator("text_search")
    @classmethod
    def _ts_names(cls, v: list[str]) -> list[str]:
        import re

        for ts in v:
            if not re.match(IDENT, str(ts)):
                raise ValueError(f"'{ts}' is not a text search configuration name")
        return v


# ---- root -------------------------------------------------------------------------------------
class Settings(_Section):
    parsing: ParsingSettings = Field(default_factory=ParsingSettings)
    classification: ClassificationSettings
    storage: StorageSettings = Field(default_factory=StorageSettings)

    @model_validator(mode="after")
    def _pages(self) -> Settings:
        if self.parsing.max_pages is not None and self.parsing.max_pages < self.classification.max_pages:
            raise ValueError("parsing.max_pages must be empty or at least classification.max_pages")
        return self


def _describe(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def load_settings(path: str | Path) -> Settings:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    legacy = {"model", "extraction", "decision", "database"} & set(raw)
    if legacy:
        raise ConfigError(f"{path} uses the old laya-pdf-classifier layout ({', '.join(sorted(legacy))}); "
                          "see config.example.yaml for the parsing/classification/storage sections")
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_describe(exc)) from None
