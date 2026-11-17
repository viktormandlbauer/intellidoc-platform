"""PDF -> plain text.

The whole document is converted once and kept page by page: the full text is what gets stored
and indexed, `Extracted.head()` is the short prefix the classifier reads.

Uses Docling (layout analysis + table structure) on the embedded text layer. When the result
has (almost) no text the file is most likely a scan; if OCR is enabled, it is converted again
with full-page OCR (Tesseract when installed, otherwise Docling's default engine). Scans that
still yield little text are flagged so the caller can route them to review.
"""
from __future__ import annotations

import logging
import re
import shutil
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


# Separates pages in the stored text, so the classifier's head can be rebuilt from the database.
# `_clean` turns form feeds inside a page into spaces, so this only ever marks a page boundary.
PAGE_BREAK = "\n\f\n"


def head(text: str, max_pages: int = 3, max_chars: int = 6000) -> str:
    """The first ``max_pages`` pages of a stored text, capped at ``max_chars``: what the classifier reads."""
    pages = text.split(PAGE_BREAK)[:max_pages]
    return "\n\n".join(p for p in pages if p)[:max_chars]


@dataclass
class Extracted:
    path: Path
    pages: list[str]  # cleaned text per converted page, page 1 first
    pages_total: int
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Full text of all converted pages, joined by PAGE_BREAK: what is stored and indexed."""
        return PAGE_BREAK.join(self.pages) if any(self.pages) else ""

    def head(self, max_pages: int = 3, max_chars: int = 6000) -> str:
        return head(self.text, max_pages, max_chars)

    @property
    def low_text(self) -> bool:
        return sum(len(p) for p in self.pages) < 50


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


def extract_text(
    path: str | Path,
    max_pages: int | None = None,
    ocr: bool = True,
    ocr_language: str = "deu+eng",
) -> Extracted:
    """Return the cleaned text of the first ``max_pages`` pages (all pages if None)."""
    path = Path(path)
    warnings: list[str] = []
    try:
        pages, total = _convert(path, max_pages, ocr=False, language=ocr_language)
    except Exception as exc:
        return Extracted(path, [], 0, warnings=[f"unreadable PDF: {exc}"])

    ex = Extracted(path, pages, total, warnings=warnings)
    if ex.low_text and ocr:
        try:
            ex.pages, ex.pages_total = _convert(path, max_pages, ocr=True, language=ocr_language)
            ex.ocr_used = True
        except Exception as exc:
            log.warning("OCR failed for %s: %s", path.name, exc)
            warnings.append(f"OCR failed: {exc}")

    if len(ex.pages) < ex.pages_total:
        warnings.append(f"only the first {len(ex.pages)} of {ex.pages_total} pages were extracted")
    if ex.low_text:
        warnings.append("very little text extracted")
    return ex
