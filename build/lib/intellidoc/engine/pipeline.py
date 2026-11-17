"""The document pipeline: ingest -> parse -> classify -> gate.

Each stage is a separate module behind an interface (`parsing.Parser`, `classification.Classifier`),
so a stage can be swapped without touching the others. Structured extraction and validation will
slot in after the gate, for documents whose type is known.
"""
from __future__ import annotations

import time
from pathlib import Path

from .classification import Classifier
from .classification.gating import gate
from .config import Settings
from ..contracts.results import STATUS_ERROR, STATUS_REVIEW, ClassificationResult, now_iso
from .ingestion import file_identity
from .parsing import Parser


class DocumentPipeline:
    def __init__(self, settings: Settings, classifier: Classifier, parser: Parser | None = None):
        if parser is None:
            from .parsing import make_parser

            parser = make_parser(settings)
        self.settings = settings
        self.classifier = classifier
        self.parser = parser
        self.questions = settings.classification.laya_questions()

    def process_text(self, text: str, name: str = "<text>") -> ClassificationResult:
        t0 = time.perf_counter()
        res = self._classify(name, text, t0)
        res.text = text
        return res

    def process_file(self, path: str | Path, display_name: str | None = None) -> ClassificationResult:
        res = self._process_file(path, display_name or str(path))
        try:
            res.sha256, res.size_bytes = file_identity(path)
        except OSError:
            pass
        return res

    def _process_file(self, path: str | Path, name: str) -> ClassificationResult:
        c = self.settings.classification
        t0 = time.perf_counter()
        try:
            doc = self.parser.parse(path)
        except Exception as exc:
            return ClassificationResult(file=name, status=STATUS_ERROR, failed_step="parsing",
                                        warnings=[f"extraction failed: {exc}"], classified_at=now_iso())

        # the full text is stored and indexed; the classifier only reads the head of the document
        head = doc.head(c.max_pages, c.max_chars)
        meta = dict(pages_used=min(len(doc.pages), c.max_pages), pages_total=doc.pages_total,
                    ocr_used=doc.ocr_used, text=doc.text)
        if len(head.strip()) < 50:
            return ClassificationResult(
                file=name, status=STATUS_REVIEW,
                warnings=doc.warnings or ["no usable text"],
                elapsed_ms=int((time.perf_counter() - t0) * 1000),
                classified_at=now_iso(), **meta,
            )
        try:
            res = self._classify(name, head, t0)
        except Exception as exc:
            return ClassificationResult(file=name, status=STATUS_ERROR, failed_step="classification",
                                        warnings=doc.warnings + [f"model failed: {exc}"],
                                        classified_at=now_iso(), **meta)
        res.warnings = doc.warnings + res.warnings
        for k, v in meta.items():
            setattr(res, k, v)
        return res

    def _classify(self, name: str, text: str, t0: float) -> ClassificationResult:
        payload = self.classifier.predict(text, self.questions)
        fields = gate(payload, self.settings.classification)
        fields["model"] = fields["model"] or getattr(self.classifier, "name", None)
        return ClassificationResult(
            file=name, **fields,
            elapsed_ms=int((time.perf_counter() - t0) * 1000),
            classified_at=now_iso(),
        )
