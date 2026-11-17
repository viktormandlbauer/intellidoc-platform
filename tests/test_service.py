import time

from fastapi.testclient import TestClient

from intellidoc.devstack import create_app as create_stack
from intellidoc.service import create_app
from intellidoc.contracts import ClassificationResult
from intellidoc.worker import InMemoryQueue, InMemoryResultStore, InMemoryStatusStore, ProcessingState

from conftest import CONFIG


def _service(tmp_path):
    q, st = InMemoryQueue(), InMemoryStatusStore()
    return TestClient(create_app(q, st, tmp_path / "originals")), q, st


def _upload(client, path, name="doc.pdf"):
    with open(path, "rb") as fh:
        return client.post("/documents", files={"file": (name, fh, "application/pdf")})


def test_upload_stores_original_and_enqueues(samples, tmp_path):
    client, q, st = _service(tmp_path)
    r = _upload(client, samples / "invoice" / "invoice_1.pdf", "rechnung.pdf")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending" and body["name"] == "rechnung.pdf" and len(body["sha256"]) == 64
    job = q.get()
    assert job.document_id == body["document_id"] and (tmp_path / "originals" / f"{job.document_id}.pdf").exists()
    assert client.get(f"/documents/{job.document_id}/status").json()["status"] == "pending"


def test_same_content_is_a_new_document(samples, tmp_path):
    client, _, _ = _service(tmp_path)
    a = _upload(client, samples / "invoice" / "invoice_1.pdf").json()
    b = _upload(client, samples / "invoice" / "invoice_1.pdf").json()
    assert a["document_id"] != b["document_id"] and a["sha256"] == b["sha256"]  # REQ-DOC-8/9


def test_rejects_non_pdf_and_unknown_ids(tmp_path):
    client, q, _ = _service(tmp_path)
    assert client.post("/documents", files={"file": ("x.pdf", b"hello", "application/pdf")}).status_code == 415
    assert q.get() is None
    assert client.get("/documents/nope/status").status_code == 404
    assert client.post("/documents/nope/reprocess").status_code == 404


def test_reprocess_only_failed(samples, tmp_path):
    client, q, st = _service(tmp_path)
    doc = _upload(client, samples / "invoice" / "invoice_1.pdf").json()["document_id"]
    first = q.get()
    assert client.post(f"/documents/{doc}/reprocess").status_code == 409  # still pending

    st.set(ProcessingState(document_id=doc, status="failed", failed_step="parsing", error="x"))
    assert [d["document_id"] for d in client.get("/documents/failed").json()] == [doc]
    r = client.post(f"/documents/{doc}/reprocess")
    assert r.status_code == 202 and r.json()["status"] == "pending"
    again = q.get()
    assert again.attempt == 2 and again.job_id != first.job_id and again.source == first.source


def test_devstack_processes_uploads_end_to_end(samples, tmp_path):
    with TestClient(create_stack(str(CONFIG), "keyword", str(tmp_path / "originals"))) as client:
        doc = _upload(client, samples / "contract" / "contract_1.pdf").json()["document_id"]
        for _ in range(100):
            state = client.get(f"/documents/{doc}/status").json()
            if state["status"] in ("indexed", "failed"):
                break
            time.sleep(0.1)
        body = client.get(f"/documents/{doc}").json()
    assert state["status"] == "indexed"
    assert body["state"]["status"] == "indexed" and body["result"]["file"] == "doc.pdf" and body["result"]["label"]
    assert "text" not in body["result"]


def test_document_returns_result_once_indexed(samples, tmp_path):
    q, st, results = InMemoryQueue(), InMemoryStatusStore(), InMemoryResultStore()
    client = TestClient(create_app(q, st, tmp_path / "originals", results))
    doc = _upload(client, samples / "invoice" / "invoice_1.pdf", "rechnung.pdf").json()["document_id"]
    body = client.get(f"/documents/{doc}").json()
    assert body["name"] == "rechnung.pdf" and body["state"]["status"] == "pending" and body["result"] is None

    results(q.get(), ClassificationResult(file="rechnung.pdf", label="invoice", status="auto"))
    st.set(ProcessingState(document_id=doc, status="indexed"))
    assert client.get(f"/documents/{doc}").json()["result"]["label"] == "invoice"
    assert client.get("/documents/nope").status_code == 404
