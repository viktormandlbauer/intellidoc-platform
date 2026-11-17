from intellidoc.engine.classification.keyword import KeywordBackend
from intellidoc.engine.pipeline import DocumentPipeline
from intellidoc.worker import InMemoryQueue, InMemoryStatusStore, Job, Worker


def _worker(settings, classifier=None, sinks=None):
    q, st = InMemoryQueue(), InMemoryStatusStore()
    return Worker(DocumentPipeline(settings, classifier or KeywordBackend()), q, st, sinks), q, st


def test_job_is_processed_and_indexed(samples, settings):
    seen = []

    def sink(job, result):
        seen.append((job.document_id, result.label))
    sink.name = "test-sink"

    w, q, st = _worker(settings, sinks=[sink])
    q.put(Job(document_id="d1", source=str(samples / "payslip" / "payslip_1.pdf"), display_name="lohn.pdf"))
    state = w.run_once()
    assert state.status == "indexed" and st.get("d1").status == "indexed"
    assert seen == [("d1", "payslip")]
    assert w.run_once() is None  # queue empty


def test_low_text_is_indexed_not_failed(samples, settings):
    w, q, st = _worker(settings)
    q.put(Job(document_id="blank", source=str(samples / "_unlabelled_scan.pdf"), display_name="scan.pdf"))
    assert w.run_once().status == "indexed"  # needs review, but processing succeeded


def test_failures_record_the_step(samples, settings):
    class Broken(KeywordBackend):
        def predict(self, text, questions):
            raise RuntimeError("boom")

    w, q, st = _worker(settings, Broken())
    q.put(Job(document_id="d2", source=str(samples / "invoice" / "invoice_1.pdf"), display_name="r.pdf"))
    state = w.run_once()
    assert (state.status, state.failed_step) == ("failed", "classification") and "boom" in state.error
    assert [s.document_id for s in st.failed()] == ["d2"]


def test_corrupt_pdf_fails_at_parsing(tmp_path, settings):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not really")
    w, q, st = _worker(settings)
    q.put(Job(document_id="d4", source=str(bad), display_name="bad.pdf"))
    state = w.run_once()
    assert (state.status, state.failed_step) == ("failed", "parsing") and "unreadable PDF" in state.error
    assert [s.document_id for s in st.failed()] == ["d4"]


def test_sink_failure_fails_the_job(samples, settings):
    def sink(job, result):
        raise ConnectionError("db down")
    sink.name = "postgres"

    w, q, _ = _worker(settings, sinks=[sink])
    q.put(Job(document_id="d3", source=str(samples / "receipt" / "receipt_1.pdf"), display_name="k.pdf"))
    state = w.run_once()
    assert (state.status, state.failed_step, state.error) == ("failed", "postgres", "db down")


def test_run_forever_survives_a_failing_iteration(samples, settings):
    class FlakyStatuses(InMemoryStatusStore):
        down = True

        def set(self, state):
            if self.down:
                self.down = False
                raise ConnectionError("status store down")
            super().set(state)

    q, st = InMemoryQueue(), FlakyStatuses()
    w = Worker(DocumentPipeline(settings, KeywordBackend()), q, st)
    q.put(Job(document_id="lost", source=str(samples / "invoice" / "invoice_1.pdf"), display_name="a.pdf"))
    q.put(Job(document_id="ok", source=str(samples / "invoice" / "invoice_1.pdf"), display_name="b.pdf"))
    w.run_forever(poll=0.01, stop=lambda: st.get("ok") is not None and st.get("ok").status == "indexed")
    assert st.get("ok").status == "indexed"
