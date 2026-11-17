"""The Document API: what clients talk to.

It accepts documents, stores the original, enqueues a `contracts.Job` and reports processing status.
It never runs models: everything heavy happens in the worker, so the API stays fast and can be
scaled separately. It imports only `contracts` (the message types) and reaches the queue and
status store through its own `ports`, so it runs without the engine's dependencies installed
(enforced by tests/test_boundaries.py).

Sketch so far: upload, status, failed list, reprocess (REQ-DOC-1/2/3, REQ-ING-2/5/7/8).
To come: users and API keys (REQ-USR, REQ-AUT), repositories and roles (REQ-REP, REQ-ACL),
download/replace/deactivate (REQ-DOC), search and answers (REQ-SRCH, REQ-ANS), review list (REQ-CLS).
"""
from .app import create_app

__all__ = ["create_app"]
