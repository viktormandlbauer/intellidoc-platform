"""Trainable text classifier in the style of paperless-ngx.

paperless-ngx learns document types, correspondents and tags from the documents a user has
already filed: the text is turned into word uni- and bigram counts and fed to a small
scikit-learn neural network (MLPClassifier), which is retrained whenever the filed documents
change. This module does the same for the primary question:

    labelled PDFs / reviewed ES docs ──► preprocess ──► CountVectorizer(1-2 grams) ──► MLP ──► model file

Unlike Laya it knows nothing until trained, but it learns *your* documents (senders, layouts,
recurring phrases) and improves with every correction. `HybridBackend` (backends.py) combines
the two: Laya for the cold start and for the yes/no and score questions, the trained model for
the primary label.

The model file is a pickle: only load files you trained yourself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import re
import threading
import warnings
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FORMAT_VERSION = 1

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")
# words of 2+ letters; drops numbers (amounts, dates, invoice numbers), which differ per document
TOKEN_PATTERN = r"(?u)\b[^\W\d_]{2,}\b"


def preprocess(text: str) -> str:
    """paperless-ngx's preprocessing: lowercase, punctuation to spaces, collapse whitespace."""
    text = _PUNCT.sub(" ", text.lower())
    return _SPACE.sub(" ", text).strip()


def data_hash(texts: list[str], labels: list[str]) -> str:
    """Order-independent fingerprint of a training set, used to skip retraining when nothing changed."""
    items = sorted(f"{y}\t{hashlib.sha256(t.encode()).hexdigest()}" for t, y in zip(texts, labels))
    return hashlib.sha256("\n".join(items).encode()).hexdigest()[:16]


@dataclass
class TextModel:
    question: str
    vectorizer: Any
    classifier: Any
    counts: dict[str, int]
    data_hash: str
    trained_at: str
    sklearn_version: str
    cv_accuracy: float | None = None
    cv_folds: int = 0
    format_version: int = FORMAT_VERSION

    @property
    def labels(self) -> list[str]:
        return [str(c) for c in self.classifier.classes_]

    @property
    def n_samples(self) -> int:
        return sum(self.counts.values())

    def predict_proba(self, text: str) -> dict[str, float]:
        x = self.vectorizer.transform([preprocess(text)])
        return {str(k): float(p) for k, p in zip(self.classifier.classes_, self.classifier.predict_proba(x)[0])}

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)  # atomic: a running server never reads a half-written model

    def info(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "labels": self.counts,
            "samples": self.n_samples,
            "cv_accuracy": self.cv_accuracy,
            "cv_folds": self.cv_folds,
            "trained_at": self.trained_at,
            "data_hash": self.data_hash,
        }


def load_model(path: str | Path) -> TextModel:
    with open(path, "rb") as fh:
        model = pickle.load(fh)
    if not isinstance(model, TextModel) or model.format_version != FORMAT_VERSION:
        raise RuntimeError(f"{path} is not a compatible model file; retrain with `pdfclf train --force`")
    import sklearn

    if model.sklearn_version != sklearn.__version__:
        log.warning("model trained with scikit-learn %s, running %s; retrain if predictions look off",
                    model.sklearn_version, sklearn.__version__)
    return model


def _make_vectorizer(min_df: float | int):
    from sklearn.feature_extraction.text import CountVectorizer

    return CountVectorizer(analyzer="word", ngram_range=(1, 2), min_df=min_df, token_pattern=TOKEN_PATTERN)


def _make_classifier(seed: int):
    from sklearn.neural_network import MLPClassifier

    return MLPClassifier(tol=0.01, random_state=seed)


def cross_validate(docs: list[str], labels: list[str], min_df: float | int = 0.01, seed: int = 0,
                   max_folds: int = 5) -> tuple[float | None, int]:
    """Stratified k-fold accuracy, an honest estimate on data the model was not trained on.
    k is limited by the smallest class; returns (None, 0) if a class has a single sample."""
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline

    k = min(max_folds, min(Counter(labels).values()))
    if k < 2:
        return None, 0
    pipe = make_pipeline(_make_vectorizer(min_df), _make_classifier(seed))
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # ConvergenceWarning on small folds
        scores = cross_val_score(pipe, docs, labels, cv=cv)
    return float(scores.mean()), k


def train(texts: list[str], labels: list[str], question: str, min_df: float | int = 0.01,
          seed: int = 0, cv: bool = True) -> TextModel:
    from datetime import datetime, timezone

    import sklearn

    counts = Counter(labels)
    if len(counts) < 2:
        raise ValueError(f"need documents of at least 2 labels to train, got {dict(counts)}")
    docs = [preprocess(t) for t in texts]
    cv_acc, folds = cross_validate(docs, labels, min_df, seed) if cv else (None, 0)

    vec = _make_vectorizer(min_df)
    x = vec.fit_transform(docs)
    clf = _make_classifier(seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        clf.fit(x, labels)
    return TextModel(
        question=question,
        vectorizer=vec,
        classifier=clf,
        counts=dict(sorted(counts.items())),
        data_hash=data_hash(texts, labels),
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        sklearn_version=sklearn.__version__,
        cv_accuracy=cv_acc,
        cv_folds=folds,
    )


class MLBackend:
    """Answers the choice question the model was trained for; ignores the others.

    The model file is re-read when it changes on disk, so `pdfclf train` (e.g. from cron)
    takes effect in a running server without a restart.
    """

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        self._model: TextModel | None = None
        self._mtime: float | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        m = self.model()
        return f"ml:{m.trained_at}" if m else "ml:untrained"

    def model(self) -> TextModel | None:
        try:
            mtime = self.model_path.stat().st_mtime
        except FileNotFoundError:
            return None
        with self._lock:
            if mtime != self._mtime:
                self._model = load_model(self.model_path)
                self._mtime = mtime
                log.info("loaded ML model %s (%d samples)", self.model_path, self._model.n_samples)
            return self._model

    def answer(self, text: str, criteria: dict[str, str]) -> dict[str, Any] | None:
        """Choice answer restricted to the configured labels. Labels the model was trained on but
        that are no longer in the config are dropped and the rest renormalised."""
        m = self.model()
        if m is None:
            return None
        raw = m.predict_proba(text)
        probs = {k: raw.get(k, 0.0) for k in criteria}
        total = sum(probs.values())
        if total <= 0:
            return None
        probs = {k: v / total for k, v in probs.items()}
        best = max(probs, key=probs.__getitem__)
        return {
            "type": "choice",
            "choice": best,
            "probabilities": {k: round(v, 4) for k, v in probs.items()},
            "confidence": round(probs[best], 4),
        }

    def predict(self, text: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        m = self.model()
        if m is None:
            raise RuntimeError(f"no trained model at {self.model_path}; run `pdfclf train` first")
        answers = {}
        q = questions.get(m.question)
        if q and q["type"] == "choice":
            a = self.answer(text, q["criteria"])
            if a:
                answers[m.question] = a
        return {"answers": answers, "routing": {"model": self.name}}


# ---------------------------------------------------------------------------------------------
# Extracted-text cache: Docling is slow, and retraining re-reads every labelled PDF.
# ---------------------------------------------------------------------------------------------
@dataclass
class TextCache:
    path: Path
    _data: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._data[rec["key"]] = rec["text"]

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, text: str) -> None:
        self._data[key] = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "text": text}, ensure_ascii=False) + "\n")
