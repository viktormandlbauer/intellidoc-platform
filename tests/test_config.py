import pytest

from intellidoc.engine.config import ConfigError, load_settings


def test_builds_laya_questions(settings):
    q = settings.classification.laya_questions()
    assert q["document_type"]["type"] == "choice"
    assert "invoice" in q["document_type"]["criteria"]
    assert q["urgency"]["criteria"][0].startswith("no action")
    assert q["needs_payment"] == {"type": "noul", "instructions": q["needs_payment"]["instructions"]}


def test_defaults(settings):
    assert settings.classification.backend == "hybrid"
    assert settings.parsing.max_pages is None
    assert settings.classification.threshold("urgency") == 0.6


def test_rejects_bad_primary(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("classification: {primary: x, questions: {y: {type: noul, instructions: hi}}}\n")
    with pytest.raises(ConfigError, match="primary 'x'"):
        load_settings(p)


def test_rejects_choice_with_one_label(write_config):
    def change(raw):
        raw["classification"]["questions"]["document_type"]["labels"] = {"invoice": "an invoice"}
    with pytest.raises(ConfigError, match="questions.document_type: choice needs at least 2 labels"):
        load_settings(write_config(change))


def test_rejects_unknown_keys(write_config):
    with pytest.raises(ConfigError, match="classification.min_confidnce"):
        load_settings(write_config(lambda raw: raw["classification"].update(min_confidnce=0.4)))


def test_rejects_old_layout(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("decision: {primary: x}\nquestions: {y: {type: noul, instructions: hi}}\n")
    with pytest.raises(ConfigError, match="old laya-pdf-classifier layout"):
        load_settings(p)


def test_rejects_parsing_cap_below_classifier_pages(write_config):
    with pytest.raises(ConfigError, match="parsing.max_pages"):
        load_settings(write_config(lambda raw: raw["parsing"].update(max_pages=2)))


def test_table_name_must_be_an_identifier(write_config):
    with pytest.raises(ConfigError, match="storage.table"):
        load_settings(write_config(lambda raw: raw["storage"].update(table="documents; DROP TABLE x")))
