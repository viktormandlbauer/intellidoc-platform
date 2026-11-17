from intellidoc.engine.classification.evaluation import evaluate
from intellidoc.engine.classification.keyword import KeywordBackend
from intellidoc.cli import main
from intellidoc.engine.parsing import ParsedDocument, head
from intellidoc.engine.pipeline import DocumentPipeline

from conftest import CONFIG


class SpyBackend(KeywordBackend):
    def predict(self, text, questions):
        self.seen = text
        return super().predict(text, questions)


def test_full_text_is_kept_but_model_reads_head(tmp_path, settings, multipage_pdf):
    pdf = multipage_pdf(tmp_path / "long.pdf", [
        "Rechnung Nr. 2026-0412 Rechnungsbetrag 84,20 EUR zahlbar bis 30.10.2026",
        "Seite zwei ohne besonderen Inhalt, nur etwas Fliesstext",
        "Kuendigungsfrist drei Monate zum Quartalsende",
    ])
    settings.classification.max_pages = 1
    spy = SpyBackend()
    r = DocumentPipeline(settings, spy).process_file(pdf)
    assert "Kuendigungsfrist" in r.text and "Rechnung" in r.text
    assert "Rechnung" in spy.seen and "Kuendigungsfrist" not in spy.seen
    assert (r.pages_used, r.pages_total) == (1, 3)
    assert head(r.text, 1, settings.classification.max_chars) == spy.seen  # rebuildable from stored text


def test_parsing_max_pages_caps_extraction(tmp_path, settings, multipage_pdf):
    pdf = multipage_pdf(tmp_path / "long.pdf", [f"Seite {i} mit genug Text fuer die Erkennung" for i in range(1, 5)])
    settings.classification.max_pages, settings.parsing.max_pages = 1, 2
    r = DocumentPipeline(settings, KeywordBackend()).process_file(pdf)
    assert "Seite 2" in r.text and "Seite 3" not in r.text and r.pages_total == 4
    assert any("first 2 of 4 pages" in w for w in r.warnings)


class FakeParser:
    def __init__(self, pages):
        self.pages = pages

    def parse(self, path):
        return ParsedDocument(path, self.pages, len(self.pages))


def test_parser_is_injectable(tmp_path, settings):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF")
    r = DocumentPipeline(settings, KeywordBackend(), FakeParser(["Gehaltsabrechnung Brutto Netto Lohnsteuer " * 3]))
    res = r.process_file(f)
    assert res.label == "payslip" and res.sha256 and res.size_bytes == 4


def test_blank_pdf_goes_to_review(samples, settings):
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "_unlabelled_scan.pdf")
    assert r.status == "review" and r.label is None and r.warnings


def test_corrupt_pdf_is_a_parsing_error(tmp_path, settings):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not really")
    r = DocumentPipeline(settings, KeywordBackend()).process_file(bad)
    assert (r.status, r.failed_step) == ("error", "parsing") and r.label is None
    assert r.warnings[0].startswith("unreadable PDF")


def test_model_failure_is_an_error(samples, settings):
    class Broken(KeywordBackend):
        def predict(self, text, questions):
            raise RuntimeError("boom")

    r = DocumentPipeline(settings, Broken()).process_file(samples / "invoice" / "invoice_1.pdf")
    assert r.status == "error" and r.warnings[-1] == "model failed: boom" and r.text


def test_classify_keyword_backend(samples, settings):
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "payslip" / "payslip_1.pdf")
    assert r.label == "payslip" and r.model == "keyword-standin"
    assert set(r.flags) == {"needs_payment", "contains_personal_data", "urgency"}
    assert "text" not in r.to_dict() and r.to_dict(include_text=True)["text"] == r.text


def test_evaluate_report(samples, settings, tmp_path):
    s = evaluate(DocumentPipeline(settings, KeywordBackend()), samples, tmp_path)
    assert s["samples"] == 10
    assert (tmp_path / "report.md").read_text().startswith("# Classification evaluation")
    assert len((tmp_path / "predictions.jsonl").read_text().splitlines()) == 10


def test_cli_sort_and_csv(samples, tmp_path):
    dest = tmp_path / "sorted"
    rc = main(["-c", str(CONFIG), "--backend", "keyword", "sort", str(samples), str(dest), "-r"])
    assert rc == 0
    assert (dest / "classification.jsonl").exists()
    assert (dest / "_review" / "_unlabelled_scan.pdf").exists()
    csv_out = tmp_path / "r.csv"
    assert main(["-c", str(CONFIG), "--backend", "keyword", "classify", str(samples), "-r", "-o", str(csv_out)]) == 0
    header = csv_out.read_text().splitlines()[0]
    assert header.startswith("file,label,confidence,status")


def test_cli_backend_from_config(samples, write_config, capsys):
    path = write_config(lambda raw: raw["classification"].update(backend="keyword"))
    assert main(["-c", str(path), "classify", str(samples / "receipt")]) == 0
    assert '"model": "keyword-standin"' in capsys.readouterr().out


def test_cli_reports_config_errors(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("decision: {}\n")
    assert main(["-c", str(p), "classify", str(tmp_path)]) == 2
