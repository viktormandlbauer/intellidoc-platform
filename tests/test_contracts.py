import pytest
from pydantic import ValidationError

from intellidoc.contracts import JOB_SCHEMA_VERSION, Job


def test_job_round_trips_through_json():
    job = Job(document_id="d1", source="s3://originals/d1.pdf", display_name="a.pdf")
    again = Job.model_validate_json(job.model_dump_json())
    assert again == job and again.schema_version == JOB_SCHEMA_VERSION


def test_unknown_schema_version_is_rejected():
    raw = Job(document_id="d1", source="x", display_name="a.pdf").model_dump()
    with pytest.raises(ValidationError, match="schema_version"):
        Job.model_validate({**raw, "schema_version": JOB_SCHEMA_VERSION + 1})
