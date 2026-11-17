"""Parsing: document file -> text, page by page.

The whole document is parsed once and kept per page: the full text is what gets stored and
indexed, `ParsedDocument.head()` is the short prefix the classifier reads. A `Parser` is anything
with `parse(path) -> ParsedDocument`; `DoclingParser` is the default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Separates pages in the stored text, so the classifier's head can be rebuilt from the database.
# Parsers turn form feeds inside a page into spaces, so this only ever marks a page boundary.
PAGE_BREAK = "\n\f\n"


def head(text: str, max_pages: int = 3, max_chars: int = 6000) -> str:
    """The first ``max_pages`` pages of a stored text, capped at ``max_chars``: what the classifier reads."""
    pages = text.split(PAGE_BREAK)[:max_pages]
    return "\n\n".join(p for p in pages if p)[:max_chars]


@dataclass
class ParsedDocument:
    path: Path
    pages: list[str]  # cleaned text per parsed page, page 1 first
    pages_total: int
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None  # set when the file could not be read at all (corrupt, encrypted, ...)

    @property
    def text(self) -> str:
        """Full text of all parsed pages, joined by PAGE_BREAK: what is stored and indexed."""
        return PAGE_BREAK.join(self.pages) if any(self.pages) else ""

    def head(self, max_pages: int = 3, max_chars: int = 6000) -> str:
        return head(self.text, max_pages, max_chars)

    @property
    def low_text(self) -> bool:
        return sum(len(p) for p in self.pages) < 50


class Parser(Protocol):
    def parse(self, path: str | Path) -> ParsedDocument:
        """Never raises for a bad file: an unreadable one comes back with no pages and `error` set.
        A readable file with little or no text (e.g. a scan) is not an error."""


def make_parser(settings) -> Parser:
    """The parser configured in `parsing`."""
    from .docling import DoclingParser

    p = settings.parsing
    return DoclingParser(p.max_pages, p.ocr, p.ocr_language)


__all__ = ["PAGE_BREAK", "ParsedDocument", "Parser", "head", "make_parser"]
