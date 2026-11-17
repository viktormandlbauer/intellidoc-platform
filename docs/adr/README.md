# Architectural Decision Records

This folder records the significant architectural decisions of the IntelliDoc Platform in [MADR 4.0.0](https://adr.github.io/madr/) format.
The architecture overview (C4 diagrams, design comparison) is in [`../architecture.md`](../architecture.md); requirement IDs refer to [`../requirements.md`](../requirements.md).

## When to write an ADR

Write an ADR when a decision

* is hard or expensive to reverse (e.g. it forces a full reindex or a data migration),
* involves a real trade-off between considered options, or
* affects several components or the security of the system.

Conventions that are easy to change (logging library, endpoint naming, linting) belong in the code conventions, not here.

## Conventions

* **File name:** `NNNN-title-with-dashes.md`, four-digit number, lowercase, imperative or noun phrase (e.g. `0005-filter-search-by-repository-at-query-time.md`).
  Numbers are never reused.
* **Template:** copy [`template/adr-template.md`](template/adr-template.md) (all sections with explanations) or [`template/adr-template-bare.md`](template/adr-template-bare.md) (all sections, empty).
  Use the minimal templates ([`template/adr-template-minimal.md`](template/adr-template-minimal.md), [`template/adr-template-bare-minimal.md`](template/adr-template-bare-minimal.md)) only for small decisions.
* **Front matter:** `status` and `date` are mandatory; `decision-makers`, `consulted` and `informed` are optional.
* **Status values:** `proposed` → `accepted` | `rejected`; later `deprecated` or `superseded by ADR-NNNN`.
  An accepted ADR is not rewritten: a changed decision gets a new ADR, and the old one is set to `superseded by ADR-NNNN`.
* **Traceability:** name the requirement IDs (REQ-…, NFR-…, AC-…) the decision serves under *Decision Drivers*, and say under *Confirmation* how compliance is checked (test, review, measurement).
* **Style:** one sentence per line (linted with the repository-wide [`.markdownlint-cli2.yaml`](../../.markdownlint-cli2.yaml)).
* **Index:** add every new ADR to the table below in the same commit.

## Index

| ADR | Title | Status | Replaces |
| --- | --- | --- | --- |
| [0001](0001-use-api-worker-pool-and-dedicated-search-engine.md) | Use an API with a worker pool and a dedicated search engine | proposed | – |
| [0002](0002-use-python-and-fastapi.md) | Use Python and FastAPI for the API and the workers | proposed | assumption A-1 |
| [0003](0003-structure-code-as-ports-and-adapters.md) | Structure the code as ports and adapters (hexagonal architecture) | proposed | – |
| [0004](0004-authenticate-with-signed-jwt-and-per-request-user-check.md) | Authenticate with signed JWTs and a per-request user check | proposed | assumption A-2 |
| [0005](0005-filter-search-by-repository-at-query-time.md) | Filter search by the Principal's repositories at query time | proposed | C-4 |
| [0006](0006-keep-postgresql-authoritative-and-update-index-visibility-synchronously.md) | Keep PostgreSQL authoritative and update index visibility synchronously | proposed | – |
| [0007](0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md) | Deliver processing jobs via RabbitMQ with a transactional outbox | proposed | – |
| [0008](0008-process-documents-with-docling-in-isolated-child-process.md) | Process documents with Docling in an isolated child process | proposed | C-1, assumption A-5 |
