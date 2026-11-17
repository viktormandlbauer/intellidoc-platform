"""PostgreSQL storage for classification results.

One row per PDF, keyed by the file's SHA-256, so re-classifying a file overwrites its row instead
of duplicating it, regardless of file name or location. A human review survives re-classification.

Row shape (columns, see `build_schema`):

    doc_id, file_name, file_path, sha256, size_bytes, pages_total, pages_used, ocr_used,
    content, content_tsv,                                        -- extracted text + search vector
    label, confidence, status, primary_question, model, config_hash,
    classified_at, elapsed_ms, low_confidence[], warnings[], alternatives[],
    answers jsonb,                                               -- every question's answer
    review_label, reviewed_by, reviewed_at, review_note,         -- set later by a human
    stored_at

`answers` (jsonb) follows the questions in config.yaml:

    {"<choice q>": {"label", "confidence", "probabilities": {...}},
     "<noul q>":   {"value", "p", "confidence"},
     "<score q>":  {"score", "level", "confidence", "probabilities": {...}}}

so adding or changing questions needs no migration. Typed columns and CHECK constraints reject a
malformed result instead of storing it. `alternatives` (labels with p >= 0.15) answers "was it close
to X?". `content_tsv` is built from one text search configuration per entry in
`database.text_search` (german, english) and backs `search`.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from .classifier import Result
from .config import Config

ALT_MIN_P = 0.15

COLUMNS = (
    "doc_id", "file_name", "file_path", "sha256", "size_bytes", "pages_total", "pages_used", "ocr_used",
    "content", "label", "confidence", "status", "primary_question", "model", "config_hash",
    "classified_at", "elapsed_ms", "low_confidence", "warnings", "alternatives", "answers",
)


# ---------------------------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------------------------
def build_schema(cfg: Config) -> str:
    t = cfg.db_table  # validated as a plain identifier in config.py
    return f"""\
CREATE TABLE IF NOT EXISTS {t} (
    doc_id           text PRIMARY KEY,
    file_name        text NOT NULL,
    file_path        text,
    sha256           text,
    size_bytes       bigint,
    pages_total      integer,
    pages_used       smallint,
    ocr_used         boolean NOT NULL DEFAULT false,
    content          text,
    content_tsv      tsvector,
    label            text,
    confidence       real CHECK (confidence BETWEEN 0 AND 1),
    status           text NOT NULL CHECK (status IN ('auto', 'review', 'error')),
    primary_question text NOT NULL,
    model            text,
    config_hash      text NOT NULL,
    classified_at    timestamptz,
    elapsed_ms       integer,
    low_confidence   text[] NOT NULL DEFAULT '{{}}',
    warnings         text[] NOT NULL DEFAULT '{{}}',
    alternatives     text[] NOT NULL DEFAULT '{{}}',
    answers          jsonb NOT NULL DEFAULT '{{}}',
    review_label     text,
    reviewed_by      text,
    reviewed_at      timestamptz,
    review_note      text,
    stored_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS {t}_content_tsv_idx ON {t} USING gin (content_tsv);
CREATE INDEX IF NOT EXISTS {t}_label_idx ON {t} (label);
CREATE INDEX IF NOT EXISTS {t}_status_idx ON {t} (status);
CREATE INDEX IF NOT EXISTS {t}_review_label_idx ON {t} (review_label) WHERE review_label IS NOT NULL;
"""


def _ts_params(cfg: Config) -> dict[str, str]:
    """Text search configurations as named query parameters: {"ts0": "german", "ts1": "english"}."""
    return {f"ts{i}": c for i, c in enumerate(cfg.db_text_search or ["simple"])}


def _ts_sql(cfg: Config, fn: str, arg: str) -> str:
    """`fn('german', arg) || fn('english', arg)`, e.g. to_tsvector or websearch_to_tsquery."""
    return " || ".join(f"{fn}(%({k})s::regconfig, {arg})" for k in _ts_params(cfg))


# ---------------------------------------------------------------------------------------------
# Result -> row
# ---------------------------------------------------------------------------------------------
def _answer_doc(q: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    t = q["type"]
    conf = a.get("confidence")
    if t == "choice":
        return {"label": a.get("choice"), "confidence": conf, "probabilities": a.get("probabilities") or {}}
    if t == "noul":
        p = a.get("noul")
        return {"value": None if p is None else p >= 0.5, "p": p, "confidence": conf}
    score = a.get("score")
    levels = list(q.get("levels") or [])
    level = levels[min(len(levels) - 1, max(0, round(score)))] if score is not None and levels else None
    return {"score": score, "level": level, "confidence": conf, "probabilities": a.get("probabilities") or {}}


def to_row(r: Result | dict[str, Any], cfg: Config) -> dict[str, Any]:
    """Return the column values for one classification result."""
    d = r.to_dict(include_text=True) if isinstance(r, Result) else dict(r)
    sha = d.get("sha256")
    path = d.get("file") or ""

    primary = (d.get("answers") or {}).get(cfg.primary) or {}
    probs = primary.get("probabilities") or {}
    alternatives = [k for k, p in sorted(probs.items(), key=lambda kv: -kv[1])
                    if p >= ALT_MIN_P and k != d.get("label")]

    answers = {}
    for qid, a in (d.get("answers") or {}).items():
        if qid in cfg.questions:  # answers to questions no longer in the config are dropped
            answers[qid] = _drop_none(_answer_doc(cfg.questions[qid], a))

    return {
        "doc_id": sha or _fallback_id(path),
        "file_name": Path(path).name,
        "file_path": path,
        "sha256": sha,
        "size_bytes": d.get("size_bytes"),
        "pages_total": d.get("pages_total"),
        "pages_used": d.get("pages_used"),
        "ocr_used": bool(d.get("ocr_used", False)),
        "content": (d.get("text") or None) if cfg.db_store_text else None,
        "label": d.get("label"),
        "confidence": d.get("confidence"),
        "status": d.get("status"),
        "primary_question": cfg.primary,
        "model": d.get("model"),
        "config_hash": cfg.config_hash(),
        "classified_at": d.get("classified_at"),
        "elapsed_ms": d.get("elapsed_ms"),
        "low_confidence": d.get("low_confidence") or [],
        "warnings": d.get("warnings") or [],
        "alternatives": alternatives,
        "answers": answers,
    }


def _fallback_id(name: str) -> str:
    import hashlib

    return "name-" + hashlib.sha256(name.encode()).hexdigest()


def _drop_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _drop_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_drop_none(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------------------------
# Connection, schema setup, loading
# ---------------------------------------------------------------------------------------------
def connect(cfg: Config):
    """Autocommit connection; DATABASE_URL overrides `database.url`."""
    import psycopg

    return psycopg.connect(os.environ.get("DATABASE_URL", cfg.db_url), autocommit=True)


def ensure_schema(conn, cfg: Config) -> str:
    """Create the table and its indexes if missing. Adding questions or labels needs nothing here:
    answers live in jsonb. Changing a column means an ALTER TABLE by hand."""
    existed = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (cfg.db_table,)).fetchone()[0]
    conn.execute(build_schema(cfg))
    return "exists" if existed else "created"


def _upsert_sql(cfg: Config) -> str:
    cols = ", ".join(COLUMNS)
    vals = ", ".join(f"%({c})s" for c in COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "doc_id")
    # the review columns are not touched: a human decision outlives re-classification
    return (f"INSERT INTO {cfg.db_table} ({cols}, content_tsv) "
            f"VALUES ({vals}, {_ts_sql(cfg, 'to_tsvector', '%(content)s')}) "
            f"ON CONFLICT (doc_id) DO UPDATE SET {updates}, content_tsv = EXCLUDED.content_tsv, "
            f"stored_at = now()")


def bulk_index(conn, cfg: Config, results: Iterable[Result | dict[str, Any]]) -> dict[str, Any]:
    """Upsert results one transaction each, so one bad result doesn't block the rest."""
    import psycopg
    from psycopg.types.json import Jsonb

    sql = _upsert_sql(cfg)
    ts_params = _ts_params(cfg)

    ok = 0
    errors: list[dict[str, Any]] = []
    for r in results:
        row = to_row(r, cfg)
        try:
            with conn.transaction():
                conn.execute(sql, {**row, "answers": Jsonb(row["answers"]), **ts_params})
            ok += 1
        except psycopg.Error as exc:
            errors.append({"doc_id": row["doc_id"], "file": row["file_name"], "error": str(exc).strip()})
    return {"indexed": ok, "errors": errors}


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def set_review(conn, cfg: Config, doc_id: str, label: str, reviewed_by: str = "",
               note: str = "") -> None:
    """Record a human decision. Keeps the model output intact for later evaluation and fine-tuning."""
    cur = conn.execute(
        f"UPDATE {cfg.db_table} SET review_label = %s, reviewed_by = %s, reviewed_at = now(), "
        f"review_note = %s WHERE doc_id = %s",
        (label, reviewed_by or None, note or None, doc_id),
    )
    if cur.rowcount == 0:
        raise KeyError(doc_id)


def iter_training_docs(conn, cfg: Config, include_auto: bool = False) -> Iterator[tuple[str, str, str]]:
    """(doc_id, label, text) for training the ML model: documents with a human review, and with
    `include_auto` also unreviewed results that were confident enough to be filed automatically.
    The review wins over the model's label. Documents stored without `content` are skipped."""
    cur = conn.execute(
        f"SELECT doc_id, coalesce(review_label, label), content FROM {cfg.db_table} "
        f"WHERE content IS NOT NULL AND (review_label IS NOT NULL OR (%s AND status = 'auto')) "
        f"ORDER BY doc_id",
        (include_auto,),
    )
    for doc_id, label, text in cur:
        if label and text:
            yield doc_id, label, text


def search(conn, cfg: Config, query: str, labels: list[str] | None = None,
           limit: int = 10) -> list[dict[str, Any]]:
    """Full-text search over `content`, best match first. A reviewed label counts as the label."""
    params: dict[str, Any] = {**_ts_params(cfg), "query": query, "labels": labels or None, "limit": limit}
    rows = conn.execute(
        f"SELECT doc_id, file_name, coalesce(review_label, label), status, ts_rank(content_tsv, q) AS rank, "
        f"       ts_headline(%(ts0)s::regconfig, content, q, 'MaxFragments=2, MaxWords=20, MinWords=8') "
        f"FROM {cfg.db_table}, (SELECT {_ts_sql(cfg, 'websearch_to_tsquery', '%(query)s')} AS q) AS tsq "
        f"WHERE content_tsv @@ q "
        f"AND (%(labels)s::text[] IS NULL OR coalesce(review_label, label) = ANY(%(labels)s::text[])) "
        f"ORDER BY rank DESC LIMIT %(limit)s",
        params,
    ).fetchall()
    return [{"doc_id": d, "file": f, "label": lab, "status": s, "rank": round(rk, 4),
             "excerpt": ex.replace("\f", "") if ex else ex}
            for d, f, lab, s, rk, ex in rows]
