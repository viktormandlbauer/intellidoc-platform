import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pdfclf import backends as be  # noqa: E402
from pdfclf.backends import KeywordBackend, LayaBackend  # noqa: E402
from pdfclf.classifier import PdfClassifier  # noqa: E402
from pdfclf.cli import main  # noqa: E402
from pdfclf.config import ConfigError, load_config  # noqa: E402
from pdfclf.evaluate import evaluate  # noqa: E402
from pdfclf.extract import PAGE_BREAK, extract_text, head  # noqa: E402

CONFIG = ROOT / "config.example.yaml"


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    import make_samples

    out = tmp_path_factory.mktemp("samples")
    make_samples.main(str(out))
    return out


@pytest.fixture
def cfg():
    return load_config(CONFIG)


def test_config_builds_laya_questions(cfg):
    q = cfg.laya_questions()
    assert q["document_type"]["type"] == "choice"
    assert "invoice" in q["document_type"]["criteria"]
    assert q["urgency"]["criteria"][0].startswith("no action")
    assert q["needs_payment"] == {"type": "noul", "instructions": q["needs_payment"]["instructions"]}


def test_config_rejects_bad_primary(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("decision: {primary: x}\nquestions: {y: {type: noul, instructions: hi}}\n")
    with pytest.raises(ConfigError):
        load_config(p)


def test_extract_text(samples):
    ex = extract_text(samples / "invoice" / "invoice_1.pdf", ocr=False)
    assert "Rechnung" in ex.text and ex.pages_total == 1 and not ex.low_text


class SpyBackend(KeywordBackend):
    def predict(self, text, questions):
        self.seen = text
        return super().predict(text, questions)


def _multipage_pdf(path, pages):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for text in pages:  # body text: a lone line at the top of the page is dropped as a page header
        c.drawString(60, 500, text)
        c.drawString(60, 480, "Mit freundlichen Gruessen, Ihre Hausverwaltung.")
        c.showPage()
    c.save()
    return path


def test_full_text_is_kept_but_model_reads_head(tmp_path, cfg):
    pdf = _multipage_pdf(tmp_path / "long.pdf", [
        "Rechnung Nr. 2026-0412 Rechnungsbetrag 84,20 EUR zahlbar bis 30.10.2026",
        "Seite zwei ohne besonderen Inhalt, nur etwas Fliesstext",
        "Kuendigungsfrist drei Monate zum Quartalsende",
    ])
    cfg.max_pages = 1
    spy = SpyBackend()
    r = PdfClassifier(cfg, spy).classify_file(pdf)
    assert "Kuendigungsfrist" in r.text and "Rechnung" in r.text
    assert "Rechnung" in spy.seen and "Kuendigungsfrist" not in spy.seen
    assert (r.pages_used, r.pages_total) == (1, 3)
    assert head(r.text, 1, cfg.max_chars) == spy.seen  # the head can be rebuilt from stored text


def test_index_max_pages_caps_extraction(tmp_path, cfg):
    pdf = _multipage_pdf(tmp_path / "long.pdf", [f"Seite {i} mit genug Text fuer die Erkennung" for i in range(1, 5)])
    cfg.max_pages, cfg.index_max_pages = 1, 2
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(pdf)
    assert "Seite 2" in r.text and "Seite 3" not in r.text and r.pages_total == 4
    assert any("first 2 of 4 pages" in w for w in r.warnings)


def test_head():
    text = PAGE_BREAK.join(["eins", "", "drei", "vier"])
    assert head(text, 3, 100) == "eins\n\ndrei"
    assert head(text, 9, 6) == "eins\n\n"
    assert head("no page breaks, stored before PAGE_BREAK", 1, 9) == "no page b"


def test_config_rejects_index_cap_below_max_pages(tmp_path):
    raw = CONFIG.read_text().replace("  index_max_pages:", "  index_max_pages: 2\n  # was:")
    p = tmp_path / "c.yaml"
    p.write_text(raw.replace("max_pages: 3", "max_pages: 3", 1))
    with pytest.raises(ConfigError):
        load_config(p)


def test_blank_pdf_goes_to_review(samples, cfg):
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(samples / "_unlabelled_scan.pdf")
    assert r.status == "review" and r.label is None and r.warnings


def test_classify_keyword_backend(samples, cfg):
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(samples / "payslip" / "payslip_1.pdf")
    assert r.label == "payslip"
    assert set(r.flags) == {"needs_payment", "contains_personal_data", "urgency"}


def test_evaluate_report(samples, cfg, tmp_path):
    s = evaluate(PdfClassifier(cfg, KeywordBackend()), samples, tmp_path)
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


def test_http_api(samples):
    from fastapi.testclient import TestClient

    from pdfclf.server import create_app

    client = TestClient(create_app(str(CONFIG), backend="keyword"))
    assert client.get("/health").json()["status"] == "ok"
    with open(samples / "contract" / "contract_1.pdf", "rb") as fh:
        r = client.post("/classify", files={"file": ("vertrag.pdf", fh, "application/pdf")})
    assert r.status_code == 200 and r.json()["file"] == "vertrag.pdf"
    assert client.post("/classify", files={"file": ("x.pdf", b"hello", "application/pdf")}).status_code == 415


class FakeRouter:
    """Records how LayaBackend calls the real Router API."""

    def __init__(self, **kw):
        self.init_kw, self.calls, self.preloaded = kw, [], None

    def preload(self, names):
        self.preloaded = names

    def predict(self, state, questions, **kw):
        self.calls.append(("predict", kw))
        return {"answers": {qid: ({"type": "choice", "choice": next(iter(q["criteria"])), "confidence": 0.9}
                                  if q["type"] == "choice" else {"type": q["type"], "noul": 0.5, "score": 1.0,
                                                                  "confidence": 0.5})
                            for qid, q in questions.items()},
                "routing": {"model": kw.get("model", "auto")}}

    def predict_long(self, state, questions, **kw):
        self.calls.append(("predict_long", kw))
        return self.predict(state, questions, **kw)


def test_laya_backend_uses_router_api(monkeypatch, cfg):
    import types

    fake_mod = types.SimpleNamespace(Router=FakeRouter,
                                     predict_tournament=lambda r, s, q, **kw: r.predict(s, q, tournament=True, **kw))
    monkeypatch.setitem(sys.modules, "laya", fake_mod)

    b = LayaBackend("multilingual", device="cpu", head_max_len=320)
    clf = PdfClassifier(cfg, b)
    r = clf.classify_text("Rechnung über 10 EUR")
    router = b._router
    assert router.init_kw == {"device": "cpu", "max_loaded": 1} and router.preloaded == ["multilingual"]
    assert router.calls[-1] == ("predict", {"model": "multilingual", "head_max_len": 320})
    assert r.label == "invoice" and r.status == "auto"
    assert "needs_payment" in r.low_confidence  # 0.5 < 0.6

    # > 16 labels switches to the tournament
    many = {f"l{i}": f"label {i}" for i in range(20)}
    b.predict("x", {"t": {"type": "choice", "instructions": "?", "criteria": many}})
    assert router.calls[-1][1].get("tournament") is True

    b.scan = "long"
    b.predict("x", cfg.laya_questions())
    assert router.calls[-2][0] == "predict_long"
