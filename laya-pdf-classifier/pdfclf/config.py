"""Load and validate the YAML config and turn it into Laya question definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any

import yaml

ML_COMBINE = {"ml", "average"}
CHECKPOINTS = {"english", "multilingual", "typed-decisions", "auto"}
QTYPES = {"choice", "noul", "score"}
IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    checkpoint: str = "multilingual"
    device: str = "auto"
    scan: str = "first"
    max_len: int | None = None       # override the checkpoint's token window
    head_max_len: int | None = None  # override the token budget for the question/options
    max_pages: int = 3
    max_chars: int = 6000
    index_max_pages: int | None = None  # pages extracted for storage and search; None = all
    ocr: bool = True
    ocr_language: str = "deu+eng"
    primary: str = "document_type"
    min_confidence: float = 0.6
    questions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # postgres (db.py)
    db_url: str = "postgresql://pdfclf:pdfclf@localhost:5432/pdfclf"
    db_table: str = "documents"
    db_text_search: list[str] = field(default_factory=lambda: ["german", "english"])
    db_store_text: bool = True
    # trained classifier (ml.py)
    ml_model_path: str = "models/classifier.pkl"
    ml_combine: str = "ml"
    ml_weight: float = 0.7
    ml_min_df: float | int = 0.01

    def config_hash(self) -> str:
        """Short hash of the question/label definitions. Stored with each result so you can tell
        which label set produced it after you change the config."""
        import hashlib
        import json

        blob = json.dumps(self.laya_questions(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    # ---- derived -----------------------------------------------------------------------
    def laya_questions(self) -> dict[str, dict[str, Any]]:
        """Questions in the shape `laya.Router.predict` expects."""
        out = {}
        for qid, q in self.questions.items():
            item: dict[str, Any] = {"type": q["type"], "instructions": q["instructions"]}
            if q["type"] == "choice":
                item["criteria"] = dict(q["labels"])
            elif q["type"] == "score":
                item["criteria"] = list(q["levels"])
            out[qid] = item
        return out

    def labels(self, qid: str | None = None) -> list[str]:
        q = self.questions[qid or self.primary]
        return list(q.get("labels", {}))

    def threshold(self, qid: str) -> float:
        return float(self.questions[qid].get("min_confidence", self.min_confidence))


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    model = raw.get("model", {}) or {}
    ext = raw.get("extraction", {}) or {}
    dec = raw.get("decision", {}) or {}
    cfg = Config(
        checkpoint=str(model.get("checkpoint", "multilingual")),
        device=str(model.get("device", "auto")),
        scan=str(model.get("scan", "first")),
        max_len=model.get("max_len"),
        head_max_len=model.get("head_max_len"),
        max_pages=int(ext.get("max_pages", 3)),
        max_chars=int(ext.get("max_chars", 6000)),
        index_max_pages=int(ext["index_max_pages"]) if ext.get("index_max_pages") else None,
        ocr=bool(ext.get("ocr", True)),
        ocr_language=str(ext.get("ocr_language", "deu+eng")),
        primary=str(dec.get("primary", "document_type")),
        min_confidence=float(dec.get("min_confidence", 0.6)),
        questions=raw.get("questions", {}) or {},
    )
    db = raw.get("database", {}) or {}
    cfg.db_url = str(db.get("url", cfg.db_url))
    cfg.db_table = str(db.get("table", cfg.db_table))
    cfg.db_text_search = list(db.get("text_search", cfg.db_text_search) or [])
    cfg.db_store_text = bool(db.get("store_text", cfg.db_store_text))
    ml = raw.get("ml", {}) or {}
    cfg.ml_model_path = str(ml.get("model_path", cfg.ml_model_path))
    cfg.ml_combine = str(ml.get("combine", cfg.ml_combine))
    cfg.ml_weight = float(ml.get("weight", cfg.ml_weight))
    cfg.ml_min_df = ml.get("min_df", cfg.ml_min_df)
    validate(cfg)
    return cfg


def validate(cfg: Config) -> None:
    if cfg.checkpoint not in CHECKPOINTS:
        raise ConfigError(f"model.checkpoint must be one of {sorted(CHECKPOINTS)}")
    if cfg.scan not in {"first", "long"}:
        raise ConfigError("model.scan must be 'first' or 'long'")
    if cfg.max_pages < 1 or cfg.max_chars < 1:
        raise ConfigError("extraction.max_pages and max_chars must be positive")
    if cfg.index_max_pages is not None and cfg.index_max_pages < cfg.max_pages:
        raise ConfigError("extraction.index_max_pages must be empty or at least max_pages")
    if not 0.0 <= cfg.min_confidence <= 1.0:
        raise ConfigError("decision.min_confidence must be between 0 and 1")
    if cfg.ml_combine not in ML_COMBINE:
        raise ConfigError(f"ml.combine must be one of {sorted(ML_COMBINE)}")
    if not 0.0 <= cfg.ml_weight <= 1.0:
        raise ConfigError("ml.weight must be between 0 and 1")
    if not IDENT.match(cfg.db_table):
        raise ConfigError("database.table must be a lowercase identifier (letters, digits, _)")
    for ts in cfg.db_text_search:
        if not IDENT.match(str(ts)):
            raise ConfigError(f"database.text_search: '{ts}' is not a text search configuration name")
    if not cfg.questions:
        raise ConfigError("at least one question is required")
    for qid, q in cfg.questions.items():
        t = q.get("type")
        if t not in QTYPES:
            raise ConfigError(f"question '{qid}': type must be one of {sorted(QTYPES)}")
        if not q.get("instructions"):
            raise ConfigError(f"question '{qid}': instructions are required")
        if t == "choice":
            labels = q.get("labels")
            if not isinstance(labels, dict) or len(labels) < 2:
                raise ConfigError(f"question '{qid}': choice needs at least 2 labels (key: description)")
        if t == "score":
            levels = q.get("levels")
            if not isinstance(levels, list) or len(levels) < 2:
                raise ConfigError(f"question '{qid}': score needs at least 2 levels")
    if cfg.primary not in cfg.questions:
        raise ConfigError(f"decision.primary '{cfg.primary}' is not a defined question")
    if cfg.questions[cfg.primary]["type"] != "choice":
        raise ConfigError("decision.primary must be a choice question")
