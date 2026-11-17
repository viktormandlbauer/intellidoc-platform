"""LayaBackend against a fake `laya` module: checks the Router calls without torch or weights."""
import sys
import types

from intellidoc.engine.classification import make_classifier
from intellidoc.engine.classification.laya import LayaBackend
from intellidoc.engine.pipeline import DocumentPipeline


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


def test_laya_backend_uses_router_api(monkeypatch, settings):
    fake_mod = types.SimpleNamespace(Router=FakeRouter,
                                     predict_tournament=lambda r, s, q, **kw: r.predict(s, q, tournament=True, **kw))
    monkeypatch.setitem(sys.modules, "laya", fake_mod)

    b = LayaBackend("multilingual", device="cpu", head_max_len=320)
    r = DocumentPipeline(settings, b).process_text("Rechnung über 10 EUR")
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
    b.predict("x", settings.classification.laya_questions())
    assert router.calls[-2][0] == "predict_long"


def test_make_classifier(settings):
    assert isinstance(make_classifier("laya", settings), LayaBackend)  # lazy: no import of laya yet
    hybrid = make_classifier("hybrid", settings)
    assert hybrid.zero_shot.checkpoint == "multilingual" and hybrid.primary == "document_type"
