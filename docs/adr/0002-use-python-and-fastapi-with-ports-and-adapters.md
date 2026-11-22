---
status: proposed
date: 2026-11-21
---

# Use Python and FastAPI with a ports-and-adapters structure

## Context and Problem Statement

The system consists of an HTTP API and processing workers (see [ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md)).
The workers must use Docling (constraint C-1) and a local embedding model, both of which are Python libraries.
The API must publish an OpenAPI 3 specification generated from the code (NFR-8).
Several infrastructure parts are likely to change after the spike or later: the search index ([ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md) keeps OpenSearch as a fallback), the embedding model (C-2), the answer model ([ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md)), the object store ([ADR-0011](0011-store-originals-in-rustfs.md)) and authentication (OIDC later, `mvp.md` §5).
Which language and web framework should the API and the workers use, and how should the code be structured internally?

## Decision Drivers

* Docling and the embedding libraries (sentence-transformers, PyTorch) are Python (C-1, C-2).
* OpenAPI 3 specification generated from the code, one JSON error format (NFR-8).
* API and workers share domain code: document status transitions, access policy, configuration.
* Streaming of uploads up to 50 MB and of downloads without loading files into memory (REQ-DOC-1, REQ-DOC-5).
* Infrastructure that is likely to change can be replaced without touching use cases or HTTP handlers.
* The access policy and the search scope rule can be tested for every role without running the infrastructure (AC-8.4).
* One language and a structure simple enough for a small team keep the toolchain, CI and onboarding small for a semester project.

## Considered Options

Language and framework:

* Python with FastAPI
* Python with Django and Django REST Framework
* Java or Kotlin with Spring Boot for the API, Python for the workers
* Go for the API, Python for the workers

Code structure:

* Ports and adapters (hexagonal architecture)
* Classic layers (router → service → repository) without explicit ports
* Framework-centric code (FastAPI handlers call the ORM and clients directly)

## Decision Outcome

Chosen options: "Python with FastAPI", structured as "ports and adapters", because it is the only language option that uses one language for the API and the workers while generating the OpenAPI specification directly from typed code, and the only structure that keeps the open infrastructure decisions exchangeable and the access rules testable in isolation.

The package is split into `domain` (entities, access policy, status transitions), `application` (use cases and port definitions), `adapters` (inbound HTTP and worker, one outbound adapter per port) and `bootstrap` (one composition root per process).
`domain` and `application` depend on no framework or infrastructure library.
The concrete folder layout is a convention in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

Main ports: `MetadataRepository`, `SearchIndex`, `ObjectStore`, `JobPublisher`, `Embedder`, `AnswerModel`, `DocumentParser`, `Authenticator`, `PasswordHasher`, `Clock`.

### Consequences

* Good, because API and workers share one codebase and domain model; they are only two composition roots over the same use cases.
* Good, because FastAPI generates OpenAPI 3 and Swagger UI from Pydantic models.
* Good, because FastAPI supports async request handling and streaming responses.
* Good, because the search index, embedding model, answer model, object store and authentication can be replaced by writing a new adapter.
* Good, because the access policy and use cases are tested with in-memory adapters in milliseconds.
* Bad, because Python is slower than Java or Go for CPU-bound request handling; this is acceptable because search time is dominated by the database query and query embedding.
* Bad, because FastAPI provides less out of the box than Django (no admin, no migrations, no ORM); SQLAlchemy and Alembic have to be added.
* Bad, because ports and adapters add code (port definitions, mapping between domain objects and database rows), and the team must keep the dependency rule; without automated checks the structure erodes.

### Confirmation

* The running service publishes `/openapi.json` and Swagger UI; CI checks that the specification is generated and valid.
* CI runs linting and static type checking (e.g. ruff and mypy) on the whole codebase.
* CI enforces the dependency rule with import contracts (e.g. import-linter): `domain` imports nothing from `application` or `adapters`, and neither `domain` nor `application` imports FastAPI, SQLAlchemy, AMQP, S3 or Docling libraries.
* Each outbound port has a shared contract test suite that runs against the in-memory adapter and the real adapter, such as the `SearchIndex`, `AnswerModel` and `ObjectStore` suites of [ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md), [ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md) and [ADR-0011](0011-store-originals-in-rustfs.md).
* The permission tests (AC-8.1 to AC-8.4) run once against in-memory adapters and once end to end.

## Pros and Cons of the Options

### Python with FastAPI

* Good, because it is the same language as Docling and the embedding model.
* Good, because OpenAPI is generated from type hints and Pydantic models.
* Good, because it is lightweight and does not dictate a code structure.
* Bad, because persistence, migrations and auth must be assembled from separate libraries.

### Python with Django and Django REST Framework

* Good, because ORM, migrations and authentication are included.
* Neutral, because OpenAPI generation needs an add-on.
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

### Ports and adapters

* Good, because infrastructure dependencies point inwards and are replaceable.
* Good, because the fallbacks named in the other ADRs (OpenSearch behind `SearchIndex`, a PostgreSQL job table behind `JobPublisher`, another S3 store behind `ObjectStore`) need no change in use cases.
* Bad, because it has the most boilerplate of the three structures.

### Classic layers without explicit ports

* Good, because it is familiar and has less boilerplate.
* Neutral, because a repository layer already isolates the database.
* Bad, because services typically depend on concrete clients, so exchanging the search index or the answer model touches service code.
* Bad, because testing without infrastructure needs mocking of concrete classes.

### Framework-centric code

* Good, because it is the fastest way to a first working endpoint.
* Bad, because business rules end up in HTTP handlers and cannot be reused by the worker.
* Bad, because the access rules cannot be tested without the full stack.

## More Information

* Libraries such as SQLAlchemy, Alembic, Pydantic and the dependency manager are conventions in [`CONTRIBUTING.md`](../../CONTRIBUTING.md), not separate ADRs.
* The distribution is named `intellidoc-platform` after the repository; Python import names cannot contain hyphens, so the package is `intellidoc_platform`.
* The search scope type that enforces the permission filter is defined in [ADR-0005](0005-filter-search-by-repository-at-query-time.md).
* Replaces assumption A-1 in [`architecture.md`](../architecture.md).
* The code structure was first drafted as a separate ADR with number 0003 and merged into this ADR; number 0003 is not reused.
