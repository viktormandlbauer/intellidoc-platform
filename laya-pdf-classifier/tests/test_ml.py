"""Trained (paperless-ngx-style) classifier and the hybrid backend. Needs scikit-learn, not torch."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pdfclf.backends import HybridBackend, KeywordBackend  # noqa: E402
from pdfclf.classifier import PdfClassifier  # noqa: E402
from pdfclf.cli import main  # noqa: E402
from pdfclf.config import load_config  # noqa: E402
from pdfclf.ml import MLBackend, load_model, preprocess, train  # noqa: E402

CONFIG = ROOT / "config.example.yaml"

TEXTS = {
    "invoice": [
        "Rechnung Nr. 1 Stadtwerke Rechnungsbetrag zahlbar bis Ende des Monats",
        "Rechnung Nr. 2 Telekom Rechnungsbetrag inkl. USt zahlbar innerhalb 14 Tagen",
        "Invoice number 3 amount due payment terms 30 days",
    ],
    "payslip": [
        "Gehaltsabrechnung Brutto Netto Lohnsteuer Sozialversicherung Mitarbeiter",
        "Lohnabrechnung Brutto Netto Lohnsteuer Mitarbeiterin Oktober",
        "Payslip gross salary net pay income tax employee",
    ],
    "contract": [
        "Mietvertrag zwischen Vermieter und Mieter Kündigung Frist Unterschrift",
        "Dienstvertrag Vertragsparteien Laufzeit Kündigung Unterschrift beider Parteien",
        "Service agreement between the parties termination notice signatures",
    ],
}


def _data():
    texts, labels = [], []
    for label, items in TEXTS.items():
        texts += items
        labels += [label] * len(items)
    return texts, labels


@pytest.fixture
def cfg():
    return load_config(CONFIG)


@pytest.fixture
def model_path(tmp_path):
    texts, labels = _data()
    path = tmp_path / "m.pkl"
    train(texts, labels, "document_type").save(path)
    return path


def test_preprocess():
    assert preprocess("Rechnung Nr. 2026-04!\n\nBetrag:  84,20 EUR") == "rechnung nr 2026 04 betrag 84 20 eur"


def test_train_predict_and_reload(model_path):
    m = load_model(model_path)
    assert m.labels == ["contract", "invoice", "payslip"] and m.n_samples == 9
    assert m.cv_folds == 3 and m.cv_accuracy is not None
    probs = m.predict_proba("Ihre Rechnung: Rechnungsbetrag zahlbar bis 30.10.")
    assert max(probs, key=probs.get) == "invoice"
    assert sum(probs.values()) == pytest.approx(1.0)


def test_train_needs_two_labels():
    with pytest.raises(ValueError):
        train(["a b c", "d e f"], ["x", "x"], "q")


def test_ml_backend_restricts_to_config_labels(model_path, cfg):
    b = MLBackend(model_path)
    r = PdfClassifier(cfg, b).classify_text("Gehaltsabrechnung Brutto Netto Lohnsteuer")
    assert r.label == "payslip" and r.model.startswith("ml:")
    probs = r.answers["document_type"]["probabilities"]
    assert set(probs) == set(cfg.labels()) and probs["receipt"] == 0.0
    assert r.flags == {}  # the trained model only answers the primary question


def test_ml_backend_without_model(tmp_path, cfg):
    b = MLBackend(tmp_path / "missing.pkl")
    assert b.model() is None and b.name == "ml:untrained"
    with pytest.raises(RuntimeError, match="pdfclf train"):
        PdfClassifier(cfg, b).classify_text("x")


def test_hybrid_cold_start_is_zero_shot(tmp_path, cfg):
    h = HybridBackend(KeywordBackend(), MLBackend(tmp_path / "missing.pkl"), "document_type")
    payload = h.predict("Kassenbon Summe bezahlt", cfg.laya_questions())
    assert "sources" not in payload["answers"]["document_type"]


def test_hybrid_ml_mode(model_path, cfg):
    h = HybridBackend(KeywordBackend(), MLBackend(model_path), "document_type", combine="ml")
    r = PdfClassifier(cfg, h).classify_text("Mietvertrag Kündigung Unterschrift")
    a = r.answers["document_type"]
    assert r.label == "contract" and a["sources"]["laya"] is None and a["sources"]["ml"]["choice"] == "contract"
    assert set(r.flags) == {"needs_payment", "contains_personal_data", "urgency"}  # still from zero-shot
    assert r.model == "keyword-standin+" + h.ml.name


def test_hybrid_average_mode(model_path, cfg):
    h = HybridBackend(KeywordBackend(), MLBackend(model_path), "document_type", combine="average", weight=0.5)
    a = h.predict("Mietvertrag Kündigung Unterschrift", cfg.laya_questions())["answers"]["document_type"]
    assert a["sources"]["laya"] is not None
    assert sum(a["probabilities"].values()) == pytest.approx(1.0, abs=1e-3)


def test_cli_train_and_classify(tmp_path):
    import make_samples

    samples = tmp_path / "samples"
    make_samples.main(str(samples))
    cfg_file = tmp_path / "c.yaml"
    model = tmp_path / "models" / "clf.pkl"
    cfg_file.write_text(CONFIG.read_text().replace("models/classifier.pkl", str(model)))

    assert main(["-c", str(cfg_file), "train", str(samples)]) == 0
    m = load_model(model)
    assert m.n_samples == 10 and m.cv_folds == 2
    assert (model.parent / "text-cache.jsonl").exists()

    mtime = model.stat().st_mtime_ns
    assert main(["-c", str(cfg_file), "train", str(samples)]) == 0  # unchanged data: no retrain
    assert model.stat().st_mtime_ns == mtime

    out = tmp_path / "r.jsonl"
    assert main(["-c", str(cfg_file), "--backend", "ml", "classify", str(samples / "invoice"), "-o", str(out)]) == 0
    assert '"label": "invoice"' in out.read_text()


def test_cli_train_requires_input(tmp_path):
    assert main(["-c", str(CONFIG), "train"]) == 2
