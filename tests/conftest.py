"""Shared fixtures. Nothing here needs torch or Laya weights.

The PostgreSQL tests need a database:

    INTELLIDOC_TEST_DATABASE_URL=postgresql://intellidoc:intellidoc@localhost:5432/intellidoc pytest

Each of them gets its own table, dropped afterwards.
"""
import os
import uuid
from pathlib import Path

import pytest
import yaml

from intellidoc.engine.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.example.yaml"
TEST_DB = os.environ.get("INTELLIDOC_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    import make_samples

    out = tmp_path_factory.mktemp("samples")
    make_samples.main(str(out))
    return out


@pytest.fixture
def settings():
    return load_settings(CONFIG)


@pytest.fixture
def write_config(tmp_path):
    """Write config.example.yaml with changes applied: ``write_config(lambda raw: ...)`` -> path."""
    def write(change=None, name="config.yaml"):
        raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        if change:
            change(raw)
        path = tmp_path / name
        path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        return path
    return write


@pytest.fixture
def multipage_pdf():
    def make(path, pages):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(path), pagesize=A4)
        for text in pages:  # body text: a lone line at the top of the page is dropped as a page header
            c.drawString(60, 500, text)
            c.drawString(60, 480, "Mit freundlichen Gruessen, Ihre Hausverwaltung.")
            c.showPage()
        c.save()
        return path
    return make


@pytest.fixture
def pg(write_config, monkeypatch):
    """A config file pointing at a fresh table in the test database: (config path, settings, connection)."""
    if not TEST_DB:
        pytest.skip("set INTELLIDOC_TEST_DATABASE_URL to run the PostgreSQL tests")
    psycopg = pytest.importorskip("psycopg")

    path = write_config(lambda raw: raw["storage"].update(table=f"test_{uuid.uuid4().hex[:12]}"))
    monkeypatch.setenv("DATABASE_URL", TEST_DB)

    s = load_settings(path)
    conn = psycopg.connect(TEST_DB, autocommit=True)
    yield path, s, conn
    conn.execute(f"DROP TABLE IF EXISTS {s.storage.table}")
    conn.close()
