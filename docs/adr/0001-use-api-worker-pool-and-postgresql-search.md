---
status: proposed
date: 2026-11-21
---

# Use an API with a worker pool and PostgreSQL as the search index

## Context and Problem Statement

The IntelliDoc Platform must accept uploads, process them with compute-heavy OCR and embedding, answer permission-filtered hybrid searches and generate answers from the documents (US-13).
The README states the goal of separate services for upload, processing, embedding and answer generation, so that processing capacity grows by adding workers and a failing or overloaded worker or answer model does not take down search, upload or download.
Documents and all data derived from them must stay on the company server.
At the same time the system must start with one `docker compose up` on a single 16 GB host and be built within one semester.
Which overall system structure should the IntelliDoc Platform have?

## Decision Drivers

* Distributed-system goal of the README: separate services; scalable processing; failures of workers or the answer model do not affect search, upload or download.
* Documents, chunks, vectors and metadata stay on the company server.
* Correct permission filtering with immediate effect (REQ-ACL-5, REQ-ACL-6), also for generated answers (REQ-ANS-3).
* Exact-term ranking (REQ-SRCH-4) and search quality (NFR-3), the biggest project risks (`mvp.md` §7).
* Search latency P95 ≤ 2 s (NFR-1), processing time (NFR-2) and answer time (NFR-9).
* Single-command deployment on the reference host with 16 GB RAM.

## Considered Options

* A – Modular monolith on PostgreSQL (API + workers, PostgreSQL with pgvector as queue and index)
* B – API with worker pool (API, RabbitMQ, workers, embedding service, answer model service, PostgreSQL with pgvector as metadata store and search index, RustFS)
* C – Event-driven microservices (gateway, IAM, document, search services and pipeline stages on an event stream)

The chosen option B is described with C4 diagrams in [`architecture.md`](../architecture.md); the options are compared only briefly here.
The search index inside B is decided in [ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md); an earlier version of B used OpenSearch as a second store.

## Decision Outcome

Chosen option: "B – API with worker pool", because it is the only option that meets the distributed-system goal while keeping all document data in one local store and staying within the semester effort; whether it fits the memory of the reference host is confirmed by the spike.

### Consequences

* Good, because upload, processing, embedding and answer generation have separate load profiles and scale independently; a crashing worker does not affect search or upload.
* Good, because metadata, permissions and the search index are in one database, so permission filtering, status and deactivation are transactionally correct and cannot drift (see [ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md)).
* Good, because the embedding model is loaded once in a shared service instead of in every process.
* Good, because answers are orchestrated by the API on top of the search component, so they inherit the permission filter (see [ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md)).
* Bad, because lexical ranking in PostgreSQL is weaker than BM25 and exact-term matching needs custom tokenisation, which must be proven by the evaluation set (REQ-SRCH-4, NFR-3).
* Bad, because PostgreSQL is a single point of failure for metadata and search, and search competes with ingestion writes on the same database.
* Bad, because job delivery needs a broker and an outbox (see [ADR-0007](0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md)).
* Neutral, because the deployment has 8 containers (7 if the operator leaves out the local answer model, see [ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md)); whether they fit the reference host is measured in the spike (open question Q-2).

### Confirmation

* Spike in phase 2: the full stack runs on the reference environment with two workers under load, and its memory use is measured and documented.
* The NFR-3 evaluation set, including the exact-term queries, meets its targets on PostgreSQL search ([ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md)).
* The demo scenario (`mvp.md` §2) passes on a fresh checkout with `docker compose up`.
* Stopping all workers does not affect login, listing, download, search or answers (manual test, later automated).

## Pros and Cons of the Options

### A – Modular monolith on PostgreSQL

* Good, because it has the fewest containers and the lowest memory use.
* Bad, because only processing is distributed: the embedding model is loaded in every API and worker process, and search and answers are not separated from request handling.

### B – API with worker pool

* Good, because it meets the distributed-system goal with a manageable number of components and keeps A's transactional correctness for permissions and document state.
* Bad, because it needs a broker, an outbox and more containers than A.

### C – Event-driven microservices

* Good, because it has the strongest fault isolation and the most fine-grained scaling (OCR and embedding stages separately).
* Bad, because every search depends on a synchronous call to the IAM service (latency for NFR-1, an extra failure point), and the processing status is derived from events across services (REQ-ING-2).
* Bad, because it has the most containers and the highest memory use, and its implementation and test effort is far beyond one semester.

## More Information

* The search index is decided in [ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md) (replaces C-3), including the fallback to OpenSearch if PostgreSQL misses the search targets even with a BM25 extension.
* Answer generation is decided in [ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md) (replaces C-5), object storage in [ADR-0011](0011-store-originals-in-rustfs.md), language and code structure in [ADR-0002](0002-use-python-and-fastapi-with-ports-and-adapters.md).
* The pipeline is written as separate steps (extract → chunk → embed → index) so stages can later be split into services as in C if OCR becomes the bottleneck.
* Revisit if the reference host cannot run the stack (Q-2) or the semester scope changes.
