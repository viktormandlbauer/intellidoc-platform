"""Ingestion: find input files, check they are PDFs by content, and identify them by checksum."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PDF_MAGIC = b"%PDF"


def is_pdf(data: bytes) -> bool:
    """Content check, not the file name or declared MIME type."""
    return data.startswith(PDF_MAGIC)


def file_identity(path: str | Path) -> tuple[str, int]:
    """SHA-256 and size of a file: the stable ID of a document, independent of name and location."""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def find_pdfs(paths: list[str | Path], recursive: bool = False) -> list[Path]:
    """PDF files named directly, plus those inside the given directories."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            out += sorted(f for f in it if f.is_file() and f.suffix.lower() == ".pdf")
        elif p.is_file():
            out.append(p)
        else:
            print(f"skip: {p} not found", file=sys.stderr)
    return out
