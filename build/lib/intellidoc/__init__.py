"""intellidoc: document analysis platform.

    contracts  the types that cross process boundaries: Job, ProcessingState, ClassificationResult
    engine     processes one document: ingest -> parse -> classify -> gate (library)
    worker     runs the engine on queued jobs and tracks each document's processing status
    service    the Document API: upload, status, later users/repositories/search; enqueues work,
               never runs models itself

    service ──► contracts ◄── worker ──► engine ──► contracts

tests/test_boundaries.py enforces these dependencies.
"""
__version__ = "0.3.0"
