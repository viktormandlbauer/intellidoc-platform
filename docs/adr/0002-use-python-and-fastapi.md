---
status: proposed
date: 2026-11-17
---

# Use Python and FastAPI for the API and the workers

## Context and Problem Statement

The system consists of an HTTP API and processing workers (see [ADR-0001](0001-use-api-worker-pool-and-dedicated-search-engine.md)).
The workers must use Docling (constraint C-1) and a local embedding model, both of which are Python libraries.
The API must publish an OpenAPI 3 specification generated from the code (NFR-8).
Which language and web framework should the API and the workers use?

## Decision Drivers

* Docling and the embedding libraries (sentence-transformers, PyTorch) are Python (C-1, C-2).
* OpenAPI 3 specification generated from the code, one JSON error format (NFR-8).
* API and workers share domain code: document status transitions, access policy, configuration.
* Streaming of uploads up to 50 MB and of downloads without loading files into memory (REQ-DOC-1, REQ-DOC-5).
* One language keeps the toolchain, CI and onboarding small for a semester project.

## Considered Options

* Python with FastAPI
* Python with Django and Django REST Framework
* Java or Kotlin with Spring Boot for the API, Python for the workers
* Go for the API, Python for the workers

## Decision Outcome

Chosen option: "Python with FastAPI", because it is the only option that uses one language for the API and the workers while generating the OpenAPI specification directly from typed code.

### Consequences

* Good, because API and workers share one codebase and domain model.
* Good, because FastAPI generates OpenAPI 3 and Swagger UI from Pydantic models, which also serves as the demo client (`mvp.md` §3).
* Good, because FastAPI supports async request handling and streaming responses.
* Bad, because Python is slower than Java or Go for CPU-bound request handling; this is acceptable because search time is dominated by the search engine and query embedding.
* Bad, because FastAPI provides less out of the box than Django (no admin, no migrations, no ORM); SQLAlchemy and Alembic have to be added.

### Confirmation

* The running service publishes `/openapi.json` and Swagger UI; CI checks that the specification is generated and valid.
* CI runs linting and static type checking (e.g. ruff and mypy) on the whole codebase.

## Pros and Cons of the Options

### Python with FastAPI

* Good, because it is the same language as Docling and the embedding model.
* Good, because OpenAPI is generated from type hints and Pydantic models.
* Good, because it is lightweight and fits a ports-and-adapters structure (see [ADR-0003](0003-structure-code-as-ports-and-adapters.md)).
* Bad, because persistence, migrations and auth must be assembled from separate libraries.

### Python with Django and Django REST Framework

* Good, because ORM, migrations and authentication are included.
* Neutral, because OpenAPI generation needs an add-on (e.g. drf-spectacular).
* Bad, because the framework's model-centric structure works against keeping the domain free of framework code.
* Bad, because async support and streaming are less natural than in FastAPI.

### Java or Kotlin with Spring Boot for the API, Python for the workers

* Good, because Spring Boot is mature, fast and has strong security support.
* Bad, because two languages mean two toolchains and duplicated domain logic (status transitions, configuration).
* Bad, because query embedding would need a separate service or a Java runtime for the model.

### Go for the API, Python for the workers

* Good, because Go is fast and produces small images.
* Bad, because of the same duplication as with Spring Boot.
* Bad, because OpenAPI generation from code is less established in Go.

## More Information

* Libraries such as SQLAlchemy, Alembic, Pydantic and the dependency manager are conventions, not separate ADRs.
* Replaces assumption A-1 in [`architecture.md`](../architecture.md).
