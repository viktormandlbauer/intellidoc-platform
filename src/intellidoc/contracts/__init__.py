"""Contracts: the types that cross process boundaries (queue messages, status, results).

Pydantic is the only dependency, so the API service can use them without installing the engine.
Only data shapes belong here: no I/O, no interfaces to infrastructure, no helpers.
"""
from .jobs import JOB_SCHEMA_VERSION, Job, ProcessingState, ProcessingStatus
from .results import STATUS_AUTO, STATUS_ERROR, STATUS_REVIEW, ClassificationResult, Status, now_iso

__all__ = [
    "JOB_SCHEMA_VERSION", "STATUS_AUTO", "STATUS_ERROR", "STATUS_REVIEW", "ClassificationResult", "Job",
    "ProcessingState", "ProcessingStatus", "Status", "now_iso",
]
