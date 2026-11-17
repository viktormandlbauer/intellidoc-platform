"""PostgreSQL storage. Row building runs everywhere; the rest needs INTELLIDOC_TEST_DATABASE_URL (see conftest)."""
import json

from intellidoc.engine.classification.keyword import KeywordBackend
from intellidoc.cli import main
from intellidoc.engine.parsing import PAGE_BREAK
from intellidoc.engine.pipeline import DocumentPipeline
from intellidoc.engine.storage import postgres as db


def rows(conn, table):
    cur = conn.execute(f"SELECT * FROM {table}")
    names = [d.name for d in cur.description]
    return {r[0]: dict(zip(names, r)) for r in cur}


# ---- no database needed -----------------------------------------------------------------------
def test_schema_is_generated_from_config(settings):
    sql = db.build_schema(settings)
    assert "CREATE TABLE IF NOT EXISTS documents (" in sql
    for col in db.COLUMNS + ("content_tsv", "review_label"):
        assert f"\n    {col} " in sql
    assert "USING gin (content_tsv)" in sql


def test_row_from_result(samples, settings):
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "invoice" / "invoice_1.pdf")
    row = db.to_row(r, settings)
    assert tuple(row) == db.COLUMNS
    assert row["doc_id"] == r.sha256 and len(row["doc_id"]) == 64
    assert row["file_name"] == "invoice_1.pdf" and row["size_bytes"] > 0
    assert "Rechnung" in row["content"]
    assert row["config_hash"] == settings.classification.config_hash()
    assert set(row["answers"]) == {"document_type", "needs_payment", "contains_personal_data", "urgency"}
    assert isinstance(row["answers"]["needs_payment"]["value"], bool)
    assert row["answers"]["urgency"]["level"] in settings.classification.questions["urgency"].levels
    json.dumps(row["answers"])


def test_blank_pdf_row(samples, settings):
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "_unlabelled_scan.pdf")
    row = db.to_row(r, settings)
    assert row["status"] == "review" and row["label"] is None
    assert row["content"] is None


def test_store_text_false(samples, settings):
    settings.storage.store_text = False
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "receipt" / "receipt_1.pdf")
    assert db.to_row(r, settings)["content"] is None


# ---- against PostgreSQL -------------------------------------------------------------------------
def test_cli_index_is_idempotent_and_keeps_reviews(samples, pg):
    path, c, conn = pg
    args = ["-c", str(path), "--backend", "keyword", "index", str(samples), "-r"]
    assert main(args) == 0
    docs = rows(conn, c.storage.table)
    assert len(docs) == 11
    doc_id = next(iter(docs))
    assert main(["-c", str(path), "review", doc_id, "letter", "--by", "viktor"]) == 0

    assert main(args) == 0  # same files again -> same doc_ids, updated, not duplicated
    docs = rows(conn, c.storage.table)
    assert len(docs) == 11
    assert docs[doc_id]["review_label"] == "letter" and docs[doc_id]["reviewed_by"] == "viktor"


def test_cli_db_load_from_jsonl(samples, pg, tmp_path):
    path, c, conn = pg
    out = tmp_path / "r.jsonl"
    assert main(["-c", str(path), "--backend", "keyword", "classify", str(samples), "-r",
                 "-o", str(out), "--with-text"]) == 0
    assert "text" in json.loads(out.read_text().splitlines()[0])
    assert main(["-c", str(path), "db-load", str(out)]) == 0
    docs = rows(conn, c.storage.table)
    assert len(docs) == 11
    assert any(d["content"] for d in docs.values())


def test_review_feedback(samples, pg):
    path, c, conn = pg
    main(["-c", str(path), "--backend", "keyword", "index", str(samples / "contract"), "-r"])
    doc_id = next(iter(rows(conn, c.storage.table)))
    assert main(["-c", str(path), "review", doc_id, "contract", "--by", "viktor"]) == 0
    assert rows(conn, c.storage.table)[doc_id]["review_label"] == "contract"
    assert main(["-c", str(path), "review", doc_id, "nonsense"]) == 2
    assert main(["-c", str(path), "review", "no-such-doc", "contract"]) == 1


def test_rejects_a_bad_document(pg):
    _, c, conn = pg
    db.ensure_schema(conn, c)
    bad = {"file": "x.pdf", "label": "invoice", "status": "auto", "confidence": "high", "answers": {}}
    worse = {"file": "y.pdf", "label": "invoice", "status": "maybe", "confidence": 0.9, "answers": {}}
    stats = db.bulk_index(conn, c, [bad, worse])
    assert stats["indexed"] == 0 and len(stats["errors"]) == 2
    assert rows(conn, c.storage.table) == {}


def test_api_store_result(samples, pg):
    from fastapi.testclient import TestClient

    from intellidoc.engine.api import create_app

    path, c, conn = pg
    client = TestClient(create_app(str(path), backend="keyword"))
    with open(samples / "payslip" / "payslip_2.pdf", "rb") as fh:
        r = client.post("/classify?store_result=true", files={"file": ("lohn.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    docs = rows(conn, c.storage.table)
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


def test_search_finds_text_beyond_the_classified_pages(pg, tmp_path, multipage_pdf):
    path, c, conn = pg
    pdf = multipage_pdf(tmp_path / "vertrag.pdf", [
        "Mietvertrag zwischen Vermieter und Mieterin.",
        "Paragraph 2 regelt die Miete.",
        "Die Kaution betraegt drei Monatsmieten.",
    ])
    r = DocumentPipeline(c, KeywordBackend()).process_file(pdf)
    db.ensure_schema(conn, c)
    db.bulk_index(conn, c, [r])
    assert [h["file"] for h in db.search(conn, c, "Kaution")] == ["vertrag.pdf"]  # page 3 > max_pages
    assert "\f" not in db.search(conn, c, "Kaution")[0]["excerpt"]
    content = rows(conn, c.storage.table)[r.sha256]["content"]
    assert content.count(PAGE_BREAK) == 2


def test_train_from_reviews(samples, pg, tmp_path):
    from intellidoc.engine.classification.trained import load_model

    path, c, conn = pg
    assert main(["-c", str(path), "--backend", "keyword", "index", str(samples), "-r"]) == 0
    by_name = {d["file_name"]: i for i, d in rows(conn, c.storage.table).items()}
    main(["-c", str(path), "review", by_name["invoice_1.pdf"], "invoice"])
    main(["-c", str(path), "review", by_name["contract_1.pdf"], "contract"])
    main(["-c", str(path), "review", by_name["receipt_1.pdf"], "letter"])  # human overrides the model

    model = tmp_path / "m.pkl"
    assert main(["-c", str(path), "train", "--from-db", "--model", str(model)]) == 0
    assert load_model(model).counts == {"contract": 1, "invoice": 1, "letter": 1}

    assert main(["-c", str(path), "train", "--from-db", "--include-auto", "--model", str(model)]) == 0
    assert load_model(model).n_samples > 3  # plus the confident unreviewed results


def test_row_id_can_be_the_document_id(samples, settings):
    r = DocumentPipeline(settings, KeywordBackend()).process_file(samples / "invoice" / "invoice_1.pdf")
    row = db.to_row(r, settings, doc_id="upload-1")
    assert row["doc_id"] == "upload-1" and row["sha256"] == r.sha256


def test_sink_keeps_uploads_of_the_same_file_apart(samples, pg):
    from intellidoc.contracts import Job

    _, c, conn = pg
    pdf = samples / "invoice" / "invoice_1.pdf"
    r = DocumentPipeline(c, KeywordBackend()).process_file(pdf)
    sink = db.PostgresSink(c)
    for doc in ("a", "b"):
        sink(Job(document_id=doc, source=str(pdf), display_name="r.pdf"), r)
    docs = rows(conn, c.storage.table)
    assert set(docs) == {"a", "b"} and docs["a"]["sha256"] == docs["b"]["sha256"] == r.sha256
