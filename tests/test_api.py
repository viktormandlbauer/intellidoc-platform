from fastapi.testclient import TestClient

from intellidoc.engine.api import create_app

from conftest import CONFIG


def test_http_api(samples):
    client = TestClient(create_app(str(CONFIG), backend="keyword"))
    assert client.get("/health").json() == {"status": "ok", "backend": "keyword-standin"}
    assert client.get("/labels").json()["primary"] == "document_type"
    assert client.get("/model").json()["trained"] is None
    with open(samples / "contract" / "contract_1.pdf", "rb") as fh:
        r = client.post("/classify", files={"file": ("vertrag.pdf", fh, "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["file"] == "vertrag.pdf" and body["status"] in ("auto", "review") and "text" not in body
    assert client.post("/classify", files={"file": ("x.pdf", b"hello", "application/pdf")}).status_code == 415


def test_classify_text():
    client = TestClient(create_app(str(CONFIG), backend="keyword"))
    r = client.post("/classify-text", json={"text": "Gehaltsabrechnung Brutto Netto Lohnsteuer"})
    assert r.status_code == 200 and r.json()["label"] == "payslip" and "text" not in r.json()


def test_response_schema_is_published():
    schema = TestClient(create_app(str(CONFIG), backend="keyword")).get("/openapi.json").json()
    result = schema["components"]["schemas"]["ClassificationResult"]
    assert result["properties"]["status"]["enum"] == ["auto", "review", "error"]
    assert "text" not in result["properties"]


def test_classify_does_not_block_other_requests(samples, monkeypatch):
    """While one PDF is being classified, /health still answers (classify runs in the threadpool)."""
    import threading

    from intellidoc.engine.api import app as api
    from intellidoc.engine.classification.keyword import KeywordBackend

    started, health_done, waited = threading.Event(), threading.Event(), []

    class Slow(KeywordBackend):
        def predict(self, text, questions):
            started.set()
            waited.append(health_done.wait(timeout=5))
            return super().predict(text, questions)

    monkeypatch.setattr(api, "make_classifier", lambda name, settings: Slow())
    client = TestClient(api.create_app(str(CONFIG)))
    with open(samples / "invoice" / "invoice_1.pdf", "rb") as fh:
        data = fh.read()
    t = threading.Thread(target=client.post, args=("/classify",), kwargs={"files": {"file": ("r.pdf", data)}})
    t.start()
    assert started.wait(timeout=60)
    assert client.get("/health").status_code == 200
    health_done.set()
    t.join()
    assert waited == [True]
