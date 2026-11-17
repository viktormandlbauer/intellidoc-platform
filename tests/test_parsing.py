from intellidoc.engine.parsing import PAGE_BREAK, head
from intellidoc.engine.parsing.docling import DoclingParser


def test_docling_parser(samples):
    doc = DoclingParser(ocr=False).parse(samples / "invoice" / "invoice_1.pdf")
    assert "Rechnung" in doc.text and doc.pages_total == 1 and not doc.low_text


def test_unreadable_file_is_an_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not really")
    doc = DoclingParser(ocr=False).parse(bad)
    assert doc.pages == [] and doc.warnings and doc.warnings[0].startswith("unreadable PDF")
    assert doc.error and doc.error.startswith("unreadable PDF")


def test_head():
    text = PAGE_BREAK.join(["eins", "", "drei", "vier"])
    assert head(text, 3, 100) == "eins\n\ndrei"
    assert head(text, 9, 6) == "eins\n\n"
    assert head("no page breaks, stored before PAGE_BREAK", 1, 9) == "no page b"
