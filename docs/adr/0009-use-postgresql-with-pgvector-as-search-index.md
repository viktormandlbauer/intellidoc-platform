---
status: proposed
date: 2026-11-22
---

# Use PostgreSQL with pgvector and full-text search as the search index

## Context and Problem Statement

Architecture B ([ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md)) needs one index that supports lexical and semantic search over document chunks, filtered by the Principal's repositories in the same query ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)).
The search index and embeddings stay in the local deployment.
The candidates in constraint C-3 were OpenSearch and PostgreSQL with pgvector.
Where are chunks, their text index and their vectors stored, and how is hybrid search implemented?

## Decision Drivers

* Permission filter, document status and deactivation take effect with the next request and never leak (REQ-ACL-5, REQ-ACL-6, AC-7.5, AC-9.1).
* Combined lexical and semantic ranking in one result list (REQ-SRCH-2), German and English (REQ-SRCH-5).
* Exact identifiers such as "Rahmenvertrag 2024-117" are found in the top results (REQ-SRCH-4, NFR-3).
* Search latency (NFR-1).
* All document data on the company server in as few stores as possible (one backup, little operations effort).
* Operational and resource overhead of a separate search service.

## Considered Options

* PostgreSQL with pgvector, built-in full-text search and `pg_trgm`
* PostgreSQL with pgvector and a BM25 extension (e.g. ParadeDB `pg_search`)
* OpenSearch as a dedicated search engine next to PostgreSQL

## Decision Outcome

Chosen option: "PostgreSQL with pgvector, built-in full-text search and `pg_trgm`", because it keeps metadata, permissions and the index in one transactional store on the company server, needs no additional container, and is the simplest option that can meet the search requirements.

Rules:

* **Schema:** a `chunks` table with document ID, page, text, the document's text-search configuration (`german`, `english`, or `simple` if the language is unknown), a `tsvector` built with that configuration, a `simple`-configuration `tsvector` that keeps identifiers intact, and an `embedding vector(n)` column with the identifier of the embedding model that produced it.
  Indexes: GIN on both `tsvector` columns, GIN `pg_trgm` on the text, HNSW (cosine) on the embedding.
* **Language:** the worker detects the language of each document from its extracted text (German or English; anything else counts as unknown) and builds the language `tsvector` with the matching configuration.
  The language of a query is not detected: the language sub-query matches each chunk against the query parsed in that chunk's configuration, written with literal configurations (`config = 'german' AND tsv @@ websearch_to_tsquery('german', q) OR …`) so that the GIN index is used.
  A query therefore finds documents of either language lexically; matching across languages is the job of the vector sub-query (REQ-SRCH-5).
* **Embeddings:** the `Embedder` interface has separate operations for queries and for passages, because many retrieval models expect different prefixes or instructions for the two; the embedding service applies them, so callers do not depend on the model.
  The dimension `n` and the model are fixed by C-2; the vector sub-query only uses chunks of the configured model.
  Changing the model needs a migration and reprocessing of all documents (REQ-ING-4); until a document is reprocessed, it is found only lexically.
* **Hybrid query:** one SQL statement with three sub-queries – language full-text (`ts_rank_cd`), exact terms (`simple` vector and trigram match, boosted) and vector similarity – each returning at most a configurable number of candidate chunks (default 100).
  Vector candidates below a configurable minimum cosine similarity are dropped, so a query that matches nothing returns no hits instead of the nearest neighbours of everything.
  The candidates are fused with Reciprocal Rank Fusion.
* **Result list (REQ-SRCH-3):** the fused chunks are collapsed to one hit per document, ranked by its best chunk, which also provides page and excerpt.
  The total hit count is the number of documents in this list; because each sub-query is capped, it is the number of hits the system returns, not the number of all documents that mention a term.
* **Passages for answers:** a second operation returns the top k fused chunks without collapsing them, because several passages of one document can be relevant, with their full text and their match signals (exact-term match, cosine similarity) for the relevance rule of [ADR-0010](0010-generate-answers-locally-with-opt-in-external-provider.md).
  It runs the same statement with the same scope.
* **Permission filter:** every CTE joins `chunks → documents → repositories` and filters on the `RepositoryScope` ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)) plus `document.active AND document.status = 'indexed' AND repository.active`, before ranking and counting.
* **Filtered vector search:** pgvector's HNSW iterative index scans are enabled so that a restrictive repository filter does not reduce the number of vector hits.
* **Indexing (worker):** in one transaction, lock the document row (`SELECT … FOR UPDATE`); if the document and its repository are still active and the worker's attempt number is still current ([ADR-0007](0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md)), delete its chunks, insert the new chunks and set status `indexed`; otherwise write nothing; commit.
  Reprocessing is idempotent (REQ-ING-4).
* **Deactivation (API):** an ordinary update of the document row under the same row lock; the next search no longer finds it. No visibility flag and no reconciliation job are needed.
* **Interface:** search is accessed only through a `SearchIndex` interface with the two operations above (hits for search, passages for answers), both requiring a `RepositoryScope` ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)), so a different index can replace it.

### Consequences

* Good, because permission filtering, status and deactivation are transactionally correct by construction; no visibility flag has to be kept in sync with a second store.
* Good, because there is no additional container and no separate search engine heap, unlike OpenSearch.
* Good, because one backup covers metadata and index, and all document data stays in local stores.
* Bad, because PostgreSQL ranking is weaker than BM25 and German compound words are only handled by the dictionary of the `german` configuration.
* Bad, because exact-term matching depends on the extra `simple` column and trigram index, which must be tuned with the evaluation set.
* Bad, because search competes with ingestion writes on the same database; if NFR-1 is missed under load, batch inserts or a read replica for search are needed.
* Neutral, because the language of a document must be detected during processing to choose the text-search configuration; the detection library is a convention in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).
* Neutral, because capped candidate lists make the total hit count a property of the returned list rather than of the corpus.

### Confirmation

* MVP validation checks the NFR-3 targets, including the exact-term target.
* The `SearchIndex` contract test asserts that results never contain documents outside the scope or not in status `indexed`, for lexical, exact-term and vector matches.
* The contract test asserts that a document appears at most once among the hits (AC-7.6), and that a query without lexical matches and without vector candidates above the minimum similarity returns no hits.
* Test: a German query term is found in a German document and an English query term in an English document, without query language detection.
* AC-7.5 and AC-9.1 run as automated tests; a race test checks that deactivation during the final indexing step leaves the document not searchable.
* The NFR-1 load test, including its documented run while a worker is indexing.

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
* Bad, because it needs an additional container with its own JVM heap in the deployment.

## More Information

* Replaces constraint C-3 in [`architecture.md`](../architecture.md).
* If the MVP evaluation misses the exact-term target, the order of fallbacks is: tune the `simple`/trigram match, then a BM25 extension, then OpenSearch behind the `SearchIndex` interface.
* The embedding model that fills the vector column is decided separately (constraint C-2).
* If OpenSearch is reintroduced, document state lives in two stores again, and a new ADR decides how they are kept consistent.
  The design drafted for that case (formerly a separate ADR with number 0006, not reused) keeps PostgreSQL authoritative and fails closed:
  * every chunk in OpenSearch carries a `searchable` flag, and every query filters on it in addition to the repository scope;
  * the worker writes new chunks with `searchable = false` and sets the flag to `true` in the same PostgreSQL transaction that locks the document row and sets status `indexed`;
  * deactivation sets the flag to `false` under the same row lock before the API answers, and returns 503 if the index is unavailable;
  * a periodic reconciliation job corrects the flag from PostgreSQL and deletes chunks of unknown documents.
