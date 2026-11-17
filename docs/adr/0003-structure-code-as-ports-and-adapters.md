---
status: proposed
date: 2026-11-17
---

# Structure the code as ports and adapters (hexagonal architecture)

## Context and Problem Statement

Several infrastructure choices are still open or likely to change: the search engine (OpenSearch vs PostgreSQL + pgvector, constraint C-3), the embedding model (C-2), the OCR engine, and authentication (OIDC is planned for later, `mvp.md` §5).
The access rules are the most critical logic of the system and must be tested for every role in CI (AC-8.4).
The API and the workers run the same domain logic in different processes (see [ADR-0001](0001-use-api-worker-pool-and-dedicated-search-engine.md)).
How should the code be structured internally?

## Decision Drivers

* Exchange the search engine after the spike without touching use cases or HTTP handlers.
* Test the access policy and the search scope rule without running PostgreSQL or OpenSearch (AC-8.4).
* Reuse the same use cases in the API process and in the worker process.
* Add OIDC later behind the existing authentication interface (`mvp.md` §5).
* Keep the structure simple enough for a small team.

## Considered Options

* Ports and adapters (hexagonal architecture)
* Classic layers (router → service → repository) without explicit ports
* Framework-centric code (FastAPI handlers call the ORM and clients directly)

## Decision Outcome

Chosen option: "Ports and adapters", because it is the only option that makes the open infrastructure decisions exchangeable and lets the access rules be tested in isolation.

The package layout is:

```text
src/intellidoc_platform/
  domain/          entities, value objects, access policy, status transitions; no framework imports
  application/     use cases and port definitions (typing.Protocol)
  adapters/
    inbound/
      http/        FastAPI routers, request/response schemas, error mapping
      worker/      job consumer
    outbound/
      postgres/    metadata repositories, outbox
      search/      SearchIndex implementations (OpenSearch; pgvector if needed)
      storage/     ObjectStore (MinIO)
      queue/       JobPublisher (RabbitMQ)
      embedding/   Embedder (HTTP client to the embedding service)
      parsing/     DocumentParser (Docling)
      auth/        TokenService, PasswordHasher, ApiKeyHasher
  bootstrap/       composition root per process (api, worker), reads configuration
```

Main ports: `MetadataRepository`, `SearchIndex`, `ObjectStore`, `JobPublisher`, `Embedder`, `DocumentParser`, `TokenService`, `PasswordHasher`, `Clock`.

### Consequences

* Good, because the search engine, embedding model, OCR engine and authentication can be replaced by writing a new adapter.
* Good, because the access policy and use cases are tested with in-memory adapters in milliseconds.
* Good, because the API and the worker are only two different composition roots over the same use cases.
* Bad, because there is more code (port definitions, mapping between domain objects and ORM/index documents).
* Bad, because the team must keep the dependency rule; without automated checks the structure erodes.

### Confirmation

* CI enforces the dependency rule with import contracts (e.g. import-linter): `domain` imports nothing from `application` or `adapters`; `domain` and `application` do not import FastAPI, SQLAlchemy, OpenSearch, pika or Docling.
* Each outbound port has a shared contract test suite that runs against the in-memory adapter and the real adapter.
* The permission tests (AC-8.1 to AC-8.4) run once against in-memory adapters and once end to end.

## Pros and Cons of the Options

### Ports and adapters

* Good, because infrastructure dependencies point inwards and are replaceable.
* Good, because it directly supports the spike comparison of two search engines behind one `SearchIndex` port.
* Bad, because it has the most boilerplate of the three options.

### Classic layers without explicit ports

* Good, because it is familiar and has less boilerplate.
* Neutral, because a repository layer already isolates the database.
* Bad, because services typically depend on concrete clients, so exchanging the search engine touches service code.
* Bad, because testing without infrastructure needs mocking of concrete classes.

### Framework-centric code

* Good, because it is the fastest way to a first working endpoint.
* Bad, because business rules end up in HTTP handlers and cannot be reused by the worker.
* Bad, because the access rules cannot be tested without the full stack.

## More Information

* The distribution is named `intellidoc-platform` after the repository; Python import names cannot contain hyphens, so the package is `intellidoc_platform`.
* The search scope type that enforces the permission filter is defined in [ADR-0005](0005-filter-search-by-repository-at-query-time.md).
