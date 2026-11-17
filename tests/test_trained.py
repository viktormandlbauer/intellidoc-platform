"""Trained (paperless-ngx-style) classifier and the hybrid backend. Needs scikit-learn, not torch."""
import pytest

from intellidoc.engine.classification.hybrid import HybridBackend
from intellidoc.engine.classification.keyword import KeywordBackend
from intellidoc.engine.classification.trained import MLBackend, load_model, preprocess, train
from intellidoc.cli import main
from intellidoc.engine.pipeline import DocumentPipeline

from conftest import CONFIG

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


def test_ml_backend_restricts_to_config_labels(model_path, settings):
    b = MLBackend(model_path)
    r = DocumentPipeline(settings, b).process_text("Gehaltsabrechnung Brutto Netto Lohnsteuer")
    assert r.label == "payslip" and r.model.startswith("ml:")
    probs = r.answers["document_type"]["probabilities"]
    assert set(probs) == set(settings.classification.labels()) and probs["receipt"] == 0.0
    assert r.flags == {}  # the trained model only answers the primary question


def test_ml_backend_without_model(tmp_path, settings):
    b = MLBackend(tmp_path / "missing.pkl")
    assert b.model() is None and b.name == "ml:untrained"
    with pytest.raises(RuntimeError, match="intellidoc train"):
        DocumentPipeline(settings, b).process_text("x")


def test_hybrid_cold_start_is_zero_shot(tmp_path, settings):
    h = HybridBackend(KeywordBackend(), MLBackend(tmp_path / "missing.pkl"), "document_type")
    payload = h.predict("Kassenbon Summe bezahlt", settings.classification.laya_questions())
    assert "sources" not in payload["answers"]["document_type"]


def test_hybrid_ml_mode(model_path, settings):
    h = HybridBackend(KeywordBackend(), MLBackend(model_path), "document_type", combine="ml")
    r = DocumentPipeline(settings, h).process_text("Mietvertrag Kündigung Unterschrift")
    a = r.answers["document_type"]
    assert r.label == "contract" and a["sources"]["laya"] is None and a["sources"]["ml"]["choice"] == "contract"
    assert set(r.flags) == {"needs_payment", "contains_personal_data", "urgency"}  # still from zero-shot
    assert r.model == "keyword-standin+" + h.ml.name


def test_hybrid_average_mode(model_path, settings):
    h = HybridBackend(KeywordBackend(), MLBackend(model_path), "document_type", combine="average", weight=0.5)
    a = h.predict("Mietvertrag Kündigung Unterschrift", settings.classification.laya_questions())["answers"]["document_type"]
    assert a["sources"]["laya"] is not None
    assert sum(a["probabilities"].values()) == pytest.approx(1.0, abs=1e-3)


def test_cli_train_and_classify(samples, tmp_path, write_config):
    model = tmp_path / "models" / "clf.pkl"
    cfg_file = write_config(lambda raw: raw["classification"]["ml"].update(model_path=str(model)))

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


def test_cli_train_from_db(tmp_path, write_config, monkeypatch):
    """The --from-db path without a database: connect and the row iterator are stubbed."""
    from contextlib import nullcontext

    from intellidoc.engine.storage import postgres

    rows = [(f"{label}-{i}", label, text) for label, items in TEXTS.items() for i, text in enumerate(items)]
    monkeypatch.setattr(postgres, "connect", lambda settings: nullcontext(object()))
    monkeypatch.setattr(postgres, "iter_training_docs", lambda conn, settings, include_auto: iter(rows))

    model = tmp_path / "clf.pkl"
    cfg_file = write_config(lambda raw: raw["classification"]["ml"].update(model_path=str(model)))
    assert main(["-c", str(cfg_file), "train", "--from-db", "--no-cv"]) == 0
    assert load_model(model).n_samples == len(rows)
