"""Docling parser: layout analysis + table structure on the embedded text layer.

When the result has (almost) no text the file is most likely a scan; if OCR is enabled, it is
converted again with full-page OCR (Tesseract when installed, otherwise Docling's default engine).
Scans that still yield little text are flagged so the caller can route them to review.
"""
from __future__ import annotations

import logging
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from . import ParsedDocument

log = logging.getLogger(__name__)

_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def _clean(text: str) -> str:
    text = text.replace("\x00", " ")
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _NL.sub("\n\n", text).strip()


@lru_cache(maxsize=4)
def _converter(ocr: bool, language: str):
    """Docling converters load layout/table models, so build each configuration once."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_table_structure = True
    opts.do_ocr = ocr
    if ocr:
        if shutil.which("tesseract"):
            opts.ocr_options = TesseractCliOcrOptions(lang=language.split("+"))
        try:  # docling >= 2.1xx replaced force_full_page_ocr with mode
            from docling.datamodel.pipeline_options import OcrMode

            opts.ocr_options.mode = OcrMode.FULL_PAGE
        except ImportError:
            opts.ocr_options.force_full_page_ocr = True
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def _convert(path: Path, max_pages: int | None, ocr: bool, language: str) -> tuple[list[str], int]:
    """Markdown per page for the first ``max_pages`` pages (all if None), and the page count."""
    from docling.datamodel.base_models import ConversionStatus

    last = max_pages or sys.maxsize
    res = _converter(ocr, language).convert(path, page_range=(1, last), raises_on_error=False)
    if res.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        errors = "; ".join(e.error_message for e in res.errors) or str(res.status)
        raise RuntimeError(errors)
    if res.status == ConversionStatus.PARTIAL_SUCCESS:
        log.warning("partial conversion of %s: %s", path.name, [e.error_message for e in res.errors])
    total = res.input.page_count
    pages = [_clean(res.document.export_to_markdown(page_no=n, image_placeholder=""))
             for n in range(1, min(total, last) + 1)]
    return pages, total


class DoclingParser:
    def __init__(self, max_pages: int | None = None, ocr: bool = True, ocr_language: str = "deu+eng"):
        self.max_pages = max_pages  # None = all pages
        self.ocr = ocr
        self.ocr_language = ocr_language

    def parse(self, path: str | Path) -> ParsedDocument:
        path = Path(path)
        warnings: list[str] = []
        try:
            pages, total = _convert(path, self.max_pages, ocr=False, language=self.ocr_language)
        except Exception as exc:
            return ParsedDocument(path, [], 0, warnings=[f"unreadable PDF: {exc}"])

        doc = ParsedDocument(path, pages, total, warnings=warnings)
        if doc.low_text and self.ocr:
            try:
                doc.pages, doc.pages_total = _convert(path, self.max_pages, ocr=True, language=self.ocr_language)
                doc.ocr_used = True
            except Exception as exc:
                log.warning("OCR failed for %s: %s", path.name, exc)
                warnings.append(f"OCR failed: {exc}")

        if len(doc.pages) < doc.pages_total:
            warnings.append(f"only the first {len(doc.pages)} of {doc.pages_total} pages were extracted")
        if doc.low_text:
            warnings.append("very little text extracted")
        return doc
