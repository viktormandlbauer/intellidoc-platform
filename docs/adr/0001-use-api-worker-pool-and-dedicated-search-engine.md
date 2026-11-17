---
status: proposed
date: 2026-11-17
---

# Use an API with a worker pool and a dedicated search engine

## Context and Problem Statement

The IntelliDoc Platform must accept uploads, process them with compute-heavy OCR and embedding, and answer permission-filtered hybrid searches.
The README states the goal of a distributed system in which upload, processing and search run separately, processing capacity grows by adding workers, and the failure of one node does not take down search or upload.
At the same time the system must start with one `docker compose up` on a single 16 GB host and be built within one semester.
Which overall system structure should the IntelliDoc Platform have?

## Decision Drivers

* Distributed-system goal of the README: separate upload, processing and search; scalable processing; fault isolation.
* Exact-term ranking (REQ-SRCH-4) and search quality (NFR-3), the biggest project risks (`mvp.md` §7).
* Search latency P95 ≤ 2 s (NFR-1) and processing time (NFR-2).
* Correct permission filtering with immediate effect (REQ-ACL-5, REQ-ACL-6).
* Single-command deployment on the reference host with 16 GB RAM (NFR-6).
* Implementation and test effort within one semester.

## Considered Options

* A – Modular monolith on PostgreSQL (API + workers, PostgreSQL with pgvector as queue and index)
* B – API with worker pool and dedicated search engine (API, RabbitMQ, workers, embedding service, OpenSearch, PostgreSQL, MinIO)
* C – Event-driven microservices (gateway, IAM, document, search services and pipeline stages on an event stream)

The options are described with C4 container and component diagrams in [`architecture.md`](../architecture.md), sections 3–5.

## Decision Outcome

Chosen option: "B – API with worker pool and dedicated search engine", because it is the only option that meets the distributed-system goal while staying within the semester effort and the memory of the reference host, and it carries the lowest risk for REQ-SRCH-4 and NFR-3.

### Consequences

* Good, because upload, processing and search have separate load profiles and scale independently; a crashing worker does not affect search or upload.
* Good, because a dedicated search engine offers BM25, language analyzers and exact keyword subfields.
* Good, because the embedding model is loaded once in a shared service instead of in every process.
* Bad, because document state lives in two stores (PostgreSQL and the search index), which must be kept consistent (see [ADR-0006](0006-keep-postgresql-authoritative-and-update-index-visibility-synchronously.md)).
* Bad, because the deployment has about eight containers and needs an estimated 11–13 GB RAM, leaving little headroom on the reference host (open question Q-2).
* Bad, because job delivery needs a broker and an outbox (see [ADR-0007](0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md)).

### Confirmation

* Spike in phase 2: the full stack runs on the reference environment with two workers under load, and its memory use is measured and documented.
* The demo scenario (`mvp.md` §2) passes on a fresh checkout with `docker compose up`.
* Stopping all workers does not affect login, listing, download or search (manual test, later automated).

## Pros and Cons of the Options

### A – Modular monolith on PostgreSQL

* Good, because it has the fewest containers (4) and the lowest memory use (≈ 7–9 GB estimated).
* Good, because permission filtering is one transactional SQL query, so index and metadata cannot drift apart.
* Good, because one backup covers metadata and index.
* Bad, because PostgreSQL's default text parser splits identifiers such as "2024-117", so REQ-SRCH-4 needs custom tokenisation that is not yet proven.
* Bad, because lexical ranking is weaker than BM25 and German compound handling is limited.
* Bad, because PostgreSQL is a single point of failure, and search competes with ingestion writes on the same database.
* Bad, because only processing is distributed, not search.

### B – API with worker pool and dedicated search engine

* Good, because it matches the distributed-system goal with a manageable number of components.
* Good, because it has the strongest lexical search for exact terms and German/English text.
* Neutral, because the search engine itself (OpenSearch vs PostgreSQL + pgvector) can still be exchanged behind a port (see [ADR-0003](0003-structure-code-as-ports-and-adapters.md)).
* Bad, because it requires synchronisation between PostgreSQL and the index.
* Bad, because it needs more memory and more containers than A.

### C – Event-driven microservices

* Good, because it has the strongest fault isolation and the most fine-grained scaling (OCR and embedding stages separately).
* Good, because new formats (US-15) or an answer service (US-13) fit in as new services.
* Bad, because every search depends on a synchronous call to the IAM service, adding latency (NFR-1) and a failure point.
* Bad, because the processing status is derived from events across services, which makes REQ-ING-2 harder to keep strictly correct.
* Bad, because about eleven containers need an estimated 13–15 GB RAM, and implementation and test effort is far beyond one semester.

## More Information

* The choice of search engine is a separate decision (planned ADR, replaces constraint C-3); B remains valid if PostgreSQL + pgvector wins the spike, because search is accessed through a port.
* The pipeline is written as separate steps (extract → chunk → embed → index) so stages can later be split into services as in C if OCR becomes the bottleneck.
* Revisit if the reference host cannot run the stack (Q-2) or the semester scope changes.
