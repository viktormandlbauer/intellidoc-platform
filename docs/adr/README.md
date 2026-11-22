# Architectural Decision Records

This folder records the significant architectural decisions of the IntelliDoc Platform in [MADR 4.0.0](https://adr.github.io/madr/) format.
The architecture overview (C4 diagrams) is in [`../architecture.md`](../architecture.md); the considered system structures are compared briefly in [ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md).
Requirement IDs refer to [`../requirements.md`](../requirements.md).

## When to write an ADR

Write an ADR when a decision

* is hard or expensive to reverse (e.g. it forces a full reindex or a data migration),
* involves a real trade-off between considered options, or
* affects several components or the security of the system.

Conventions that are easy to change (logging library, endpoint naming, linting) belong in the code conventions ([`CONTRIBUTING.md`](../../CONTRIBUTING.md)), not here.

## Conventions

* **File name:** `NNNN-title-with-dashes.md`, four-digit number, lowercase, imperative or noun phrase (e.g. `0005-filter-search-by-repository-at-query-time.md`).
  Numbers are never reused.
* **Template:** copy [`template/adr-template.md`](template/adr-template.md) (all sections with explanations) or [`template/adr-template-bare.md`](template/adr-template-bare.md) (all sections, empty).
  Use the minimal templates ([`template/adr-template-minimal.md`](template/adr-template-minimal.md), [`template/adr-template-bare-minimal.md`](template/adr-template-bare-minimal.md)) only for small decisions.
* **Front matter:** `status` and `date` are mandatory; `decision-makers`, `consulted` and `informed` are optional.
* **Status values:** `proposed` → `accepted`; later `deprecated` or `superseded by ADR-NNNN`.
  For now, a proposal that is rejected or folded into another decision is not kept as a file: its relevant points are merged into the related ADR, and its number stays unused (0003 → ADR-0002, 0006 → ADR-0009).
  An accepted ADR is not rewritten: a changed decision gets a new ADR, and the old one is set to `superseded by ADR-NNNN`.
* **Traceability:** name the requirement IDs (REQ-…, NFR-…, AC-…) the decision serves under *Decision Drivers*, and say under *Confirmation* how compliance is checked (test, review, measurement).
* **Style:** one sentence per line (linted with the repository-wide [`.markdownlint-cli2.yaml`](../../.markdownlint-cli2.yaml)).
* **Index:** add every new ADR to the table below in the same commit.

## Index

| ADR | Title | Status | Replaces |
| --- | --- | --- | --- |
| [0001](0001-use-api-worker-pool-and-postgresql-search.md) | Use an API with a worker pool and PostgreSQL as the search index | proposed | – |
| [0002](0002-use-python-and-fastapi-with-ports-and-adapters.md) | Use Python and FastAPI with a ports-and-adapters structure | proposed | assumption A-1 |
| [0004](0004-authenticate-with-signed-jwt-and-per-request-user-check.md) | Authenticate with signed JWTs and a per-request user check | proposed | assumption A-2 |
| [0005](0005-filter-search-by-repository-at-query-time.md) | Filter search by the Principal's repositories at query time | proposed | C-4 |
| [0007](0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md) | Deliver processing jobs via RabbitMQ with a transactional outbox | proposed | – |
| [0008](0008-process-documents-with-docling-in-isolated-child-process.md) | Process documents with Docling in an isolated child process | proposed | C-1, assumption A-5 |
| [0009](0009-use-postgresql-with-pgvector-as-search-index.md) | Use PostgreSQL with pgvector and full-text search as the search index | proposed | C-3 |
| [0010](0010-generate-answers-locally-with-opt-in-external-provider.md) | Generate answers with a local language model and an opt-in external provider | proposed | C-5 |
| [0011](0011-store-originals-in-rustfs.md) | Store originals in RustFS | proposed | – |
| [0012](0012-validate-uploads-before-storing-original-and-metadata.md) | Validate uploads in a temporary file and store the original before the metadata | proposed | – |
