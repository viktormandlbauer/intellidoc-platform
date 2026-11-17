"""PostgreSQL layer. Row building runs everywhere; the rest needs a database:

    PDFCLF_TEST_DATABASE_URL=postgresql://pdfclf:pdfclf@localhost:5432/pdfclf pytest

Each test gets its own table, dropped afterwards.
"""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from pdfclf import db  # noqa: E402
from pdfclf.backends import KeywordBackend  # noqa: E402
from pdfclf.classifier import PdfClassifier  # noqa: E402
from pdfclf.cli import main  # noqa: E402
from pdfclf.config import ConfigError, load_config  # noqa: E402
from pdfclf.extract import PAGE_BREAK  # noqa: E402

CONFIG = ROOT / "config.example.yaml"
TEST_DB = os.environ.get("PDFCLF_TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    import make_samples

    out = tmp_path_factory.mktemp("samples")
    make_samples.main(str(out))
    return out


@pytest.fixture
def cfg():
    return load_config(CONFIG)


@pytest.fixture
def pg(tmp_path, monkeypatch):
    """A config file pointing at a fresh table in the test database: (config path, cfg, connection)."""
    if not TEST_DB:
        pytest.skip("set PDFCLF_TEST_DATABASE_URL to run the PostgreSQL tests")
    psycopg = pytest.importorskip("psycopg")

    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw["database"]["table"] = f"test_{uuid.uuid4().hex[:12]}"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", TEST_DB)

    c = load_config(path)
    conn = psycopg.connect(TEST_DB, autocommit=True)
    yield path, c, conn
    conn.execute(f"DROP TABLE IF EXISTS {c.db_table}")
    conn.close()


def rows(conn, table):
    cur = conn.execute(f"SELECT * FROM {table}")
    names = [d.name for d in cur.description]
    return {r[0]: dict(zip(names, r)) for r in cur}


# ---- no database needed -----------------------------------------------------------------------
def test_schema_is_generated_from_config(cfg):
    sql = db.build_schema(cfg)
    assert "CREATE TABLE IF NOT EXISTS documents (" in sql
    for col in db.COLUMNS + ("content_tsv", "review_label"):
        assert f"\n    {col} " in sql
    assert "USING gin (content_tsv)" in sql


def test_table_name_must_be_an_identifier(tmp_path):
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw["database"]["table"] = "documents; DROP TABLE x"
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_row_from_result(samples, cfg):
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(samples / "invoice" / "invoice_1.pdf")
    row = db.to_row(r, cfg)
    assert tuple(row) == db.COLUMNS
    assert row["doc_id"] == r.sha256 and len(row["doc_id"]) == 64
    assert row["file_name"] == "invoice_1.pdf" and row["size_bytes"] > 0
    assert "Rechnung" in row["content"]
    assert row["config_hash"] == cfg.config_hash()
    assert set(row["answers"]) == {"document_type", "needs_payment", "contains_personal_data", "urgency"}
    assert isinstance(row["answers"]["needs_payment"]["value"], bool)
    assert row["answers"]["urgency"]["level"] in cfg.questions["urgency"]["levels"]
    json.dumps(row["answers"])


def test_blank_pdf_row(samples, cfg):
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(samples / "_unlabelled_scan.pdf")
    row = db.to_row(r, cfg)
    assert row["status"] == "review" and row["label"] is None
    assert row["content"] is None


def test_store_text_false(samples, cfg):
    cfg.db_store_text = False
    r = PdfClassifier(cfg, KeywordBackend()).classify_file(samples / "receipt" / "receipt_1.pdf")
    assert db.to_row(r, cfg)["content"] is None


# ---- against PostgreSQL -------------------------------------------------------------------------
def test_cli_index_is_idempotent_and_keeps_reviews(samples, pg):
    path, c, conn = pg
    args = ["-c", str(path), "--backend", "keyword", "index", str(samples), "-r"]
    assert main(args) == 0
    docs = rows(conn, c.db_table)
    assert len(docs) == 11
    doc_id = next(iter(docs))
    assert main(["-c", str(path), "review", doc_id, "letter", "--by", "viktor"]) == 0

    assert main(args) == 0  # same files again -> same doc_ids, updated, not duplicated
    docs = rows(conn, c.db_table)
    assert len(docs) == 11
    assert docs[doc_id]["review_label"] == "letter" and docs[doc_id]["reviewed_by"] == "viktor"


def test_cli_db_load_from_jsonl(samples, pg, tmp_path):
    path, c, conn = pg
    out = tmp_path / "r.jsonl"
    assert main(["-c", str(path), "--backend", "keyword", "classify", str(samples), "-r",
                 "-o", str(out), "--with-text"]) == 0
    assert "text" in json.loads(out.read_text().splitlines()[0])
    assert main(["-c", str(path), "db-load", str(out)]) == 0
    docs = rows(conn, c.db_table)
    assert len(docs) == 11
    assert any(d["content"] for d in docs.values())


def test_review_feedback(samples, pg):
    path, c, conn = pg
    main(["-c", str(path), "--backend", "keyword", "index", str(samples / "contract"), "-r"])
    doc_id = next(iter(rows(conn, c.db_table)))
    assert main(["-c", str(path), "review", doc_id, "contract", "--by", "viktor"]) == 0
    assert rows(conn, c.db_table)[doc_id]["review_label"] == "contract"
    assert main(["-c", str(path), "review", doc_id, "nonsense"]) == 2
    assert main(["-c", str(path), "review", "no-such-doc", "contract"]) == 1


def test_rejects_a_bad_document(pg):
    _, c, conn = pg
    db.ensure_schema(conn, c)
    bad = {"file": "x.pdf", "label": "invoice", "status": "auto", "confidence": "high", "answers": {}}
    worse = {"file": "y.pdf", "label": "invoice", "status": "maybe", "confidence": 0.9, "answers": {}}
    stats = db.bulk_index(conn, c, [bad, worse])
    assert stats["indexed"] == 0 and len(stats["errors"]) == 2
    assert rows(conn, c.db_table) == {}


def test_api_store_result(samples, pg):
    from fastapi.testclient import TestClient

    from pdfclf.server import create_app

    path, c, conn = pg
    client = TestClient(create_app(str(path), backend="keyword"))
    with open(samples / "payslip" / "payslip_2.pdf", "rb") as fh:
        r = client.post("/classify?store_result=true", files={"file": ("lohn.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    docs = rows(conn, c.db_table)
    assert len(docs) == 1
    assert next(iter(docs.values()))["file_name"] == "lohn.pdf"


def test_search(samples, pg, capsys):
    path, c, conn = pg
    assert main(["-c", str(path), "--backend", "keyword", "index", str(samples), "-r"]) == 0
    names = lambda hits: {h["file"] for h in hits}  # noqa: E731

    assert "contract_1.pdf" in names(db.search(conn, c, "Kündigungen"))      # german stemming
    assert "contract_2.pdf" in names(db.search(conn, c, "terminate"))        # english stemming
    iban = db.search(conn, c, "IBAN", labels=["bank_statement"])
    assert "bank_statement_1.pdf" in names(iban) and {h["label"] for h in iban} == {"bank_statement"}
    assert db.search(conn, c, "IBAN", labels=["payslip"]) == []
    hit = db.search(conn, c, "Rechnung")[0]
    assert hit["file"] == "invoice_1.pdf" and "Rechnung" in hit["excerpt"]

    capsys.readouterr()
    assert main(["-c", str(path), "search", "Rechnung", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["file"] == "invoice_1.pdf"


def test_search_finds_text_beyond_the_classified_pages(pg, tmp_path):
    from test_pipeline import _multipage_pdf

    path, c, conn = pg
    pdf = _multipage_pdf(tmp_path / "vertrag.pdf", [
        "Mietvertrag zwischen Vermieter und Mieterin.",
        "Paragraph 2 regelt die Miete.",
        "Die Kaution betraegt drei Monatsmieten.",
    ])
    r = PdfClassifier(c, KeywordBackend()).classify_file(pdf)
    db.ensure_schema(conn, c)
    db.bulk_index(conn, c, [r])
    assert [h["file"] for h in db.search(conn, c, "Kaution")] == ["vertrag.pdf"]  # page 3 > max_pages
    assert "\f" not in db.search(conn, c, "Kaution")[0]["excerpt"]
    content = rows(conn, c.db_table)[r.sha256]["content"]
    assert content.count(PAGE_BREAK) == 2


def test_train_from_reviews(samples, pg, tmp_path):
    from pdfclf.ml import load_model

    path, c, conn = pg
    assert main(["-c", str(path), "--backend", "keyword", "index", str(samples), "-r"]) == 0
    by_name = {d["file_name"]: i for i, d in rows(conn, c.db_table).items()}
    main(["-c", str(path), "review", by_name["invoice_1.pdf"], "invoice"])
    main(["-c", str(path), "review", by_name["contract_1.pdf"], "contract"])
    main(["-c", str(path), "review", by_name["receipt_1.pdf"], "letter"])  # human overrides the model

    model = tmp_path / "m.pkl"
    assert main(["-c", str(path), "train", "--from-db", "--model", str(model)]) == 0
    assert load_model(model).counts == {"contract": 1, "invoice": 1, "letter": 1}

    assert main(["-c", str(path), "train", "--from-db", "--include-auto", "--model", str(model)]) == 0
    assert load_model(model).n_samples > 3  # plus the confident unreviewed results
