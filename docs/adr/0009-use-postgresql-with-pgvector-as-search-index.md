---
status: proposed
date: 2026-11-21
---

# Use PostgreSQL with pgvector and full-text search as the search index

## Context and Problem Statement

Architecture B ([ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md)) needs one index that supports lexical and semantic search over document chunks, filtered by the Principal's repositories in the same query ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)).
Documents and all data derived from them must stay on the company server, and the stack must fit the 16 GB reference host.
The candidates in constraint C-3 were OpenSearch and PostgreSQL with pgvector.
Where are chunks, their text index and their vectors stored, and how is hybrid search implemented?

## Decision Drivers

* Permission filter, document status and deactivation take effect with the next request and never leak (REQ-ACL-5, REQ-ACL-6, AC-7.5, AC-9.1).
* Combined lexical and semantic ranking in one result list (REQ-SRCH-2), German and English (REQ-SRCH-5).
* Exact identifiers such as "Rahmenvertrag 2024-117" are found in the top results (REQ-SRCH-4, NFR-3).
* Search latency P95 ≤ 2 s (NFR-1).
* All document data on the company server in as few stores as possible (one backup, little operations effort).
* Memory on the reference host (Q-2).

## Considered Options

* PostgreSQL with pgvector, built-in full-text search and `pg_trgm`
* PostgreSQL with pgvector and a BM25 extension (e.g. ParadeDB `pg_search`)
* OpenSearch as a dedicated search engine next to PostgreSQL

## Decision Outcome

Chosen option: "PostgreSQL with pgvector, built-in full-text search and `pg_trgm`", because it keeps metadata, permissions and the index in one transactional store on the company server, needs no additional container, and is the simplest option that can meet the search requirements – provided the spike confirms REQ-SRCH-4 and NFR-3.

Rules:

* **Schema:** a `chunks` table with document ID, page, text, a language-specific `tsvector` (German or English configuration, chosen per document), a `simple`-configuration `tsvector` that keeps identifiers intact, and an `embedding vector(n)` column.
  Indexes: GIN on both `tsvector` columns, GIN `pg_trgm` on the text, HNSW (cosine) on the embedding.
* **Hybrid query:** one SQL statement with three CTEs – language full-text (`ts_rank_cd`), exact terms (`simple` vector and trigram match, boosted) and vector similarity – fused with Reciprocal Rank Fusion.
* **Permission filter:** every CTE joins `chunks → documents → repositories` and filters on the `RepositoryScope` ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)) plus `document.active AND document.status = 'indexed' AND repository.active`, before ranking and counting.
* **Filtered vector search:** HNSW iterative index scans (pgvector ≥ 0.8) are enabled so that a restrictive repository filter does not reduce the number of vector hits.
* **Indexing (worker):** in one transaction, lock the document row (`SELECT … FOR UPDATE`); if the document is still active, delete its chunks, insert the new chunks and set status `indexed`; commit. Reprocessing is idempotent (REQ-ING-4).
* **Deactivation (API):** an ordinary update of the document row under the same row lock; the next search no longer finds it. No visibility flag and no reconciliation job are needed.
* **Interface:** search is accessed only through a `SearchIndex` interface, so a different index can replace it.

### Consequences

* Good, because permission filtering, status and deactivation are transactionally correct by construction; no visibility flag has to be kept in sync with a second store.
* Good, because there is no additional container and no separate search engine heap, unlike OpenSearch.
* Good, because one backup covers metadata and index, and all document data stays in local stores.
* Bad, because PostgreSQL ranking is weaker than BM25 and German compound words are only handled by the dictionary of the `german` configuration.
* Bad, because exact-term matching depends on the extra `simple` column and trigram index, which must be tuned with the evaluation set.
* Bad, because search competes with ingestion writes on the same database; if NFR-1 is missed under load, batch inserts or a read replica for search are needed.
* Neutral, because the language of a document must be detected during processing to choose the text-search configuration.

### Confirmation

* Spike (phase 2): the NFR-3 evaluation set reaches its targets on a sample of the test corpus, including ≥ 95 % of exact-term queries with the expected document in the top 10.
* The `SearchIndex` contract test asserts that results never contain documents outside the scope or not in status `indexed`, for lexical, exact-term and vector matches.
* AC-7.5 and AC-9.1 run as automated tests; a race test checks that deactivation during the final indexing step leaves the document not searchable.
* The NFR-1 load test runs while a worker is indexing.

## Pros and Cons of the Options

### PostgreSQL with pgvector, full-text search and `pg_trgm`

* Good, because it uses only PostgreSQL and widely available extensions.
* Good, because the ACL join and the ranking are one statement in one transaction.
* Bad, because lexical ranking is weaker than BM25 and needs tuning for exact terms.

### PostgreSQL with pgvector and a BM25 extension

* Good, because it adds BM25 ranking while keeping one store and one transaction.
* Neutral, because it is the first fallback if the built-in full-text search misses NFR-3.
* Bad, because it needs a custom PostgreSQL image with an extension that is younger and less widely deployed than PostgreSQL's built-in search.
* Bad, because licence and German-language support of the extension must be checked before use.

### OpenSearch

* Good, because it offers BM25, language analyzers and exact keyword subfields, the lowest risk for REQ-SRCH-4 and NFR-3.
* Bad, because document state lives in two stores, which need a synchronous visibility update and a reconciliation job (see More Information).
* Bad, because it needs an additional container with its own JVM heap on the reference host.

## More Information

* Replaces constraint C-3 in [`architecture.md`](../architecture.md).
* If the spike misses the exact-term target, the order of fallbacks is: tune the `simple`/trigram match, then a BM25 extension, then OpenSearch behind the `SearchIndex` interface.
* The embedding model that fills the vector column is decided separately (constraint C-2).
* If OpenSearch is reintroduced, document state lives in two stores again, and a new ADR decides how they are kept consistent.
  The design drafted for that case (formerly a separate ADR with number 0006, not reused) keeps PostgreSQL authoritative and fails closed:
  * every chunk in OpenSearch carries a `searchable` flag, and every query filters on it in addition to the repository scope;
  * the worker writes new chunks with `searchable = false` and sets the flag to `true` in the same PostgreSQL transaction that locks the document row and sets status `indexed`;
  * deactivation sets the flag to `false` under the same row lock before the API answers, and returns 503 if the index is unavailable;
  * a periodic reconciliation job corrects the flag from PostgreSQL and deletes chunks of unknown documents.
