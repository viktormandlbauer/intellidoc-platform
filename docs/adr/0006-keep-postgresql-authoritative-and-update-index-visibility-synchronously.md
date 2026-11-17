---
status: proposed
date: 2026-11-17
---

# Keep PostgreSQL authoritative and update index visibility synchronously

## Context and Problem Statement

In Architecture B ([ADR-0001](0001-use-api-worker-pool-and-dedicated-search-engine.md)) document metadata and status live in PostgreSQL, while chunks live in the search index.
Role, user and repository changes are handled by the query-time filter ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)), but two document states must also be reflected in the index:
a deactivated document must disappear from search with the next request (REQ-ACL-6, AC-9.1), and documents that are `pending`, `processing` or `failed` must never be found (AC-7.5), even while their chunks are being written.
How are PostgreSQL and the search index kept consistent?

## Decision Drivers

* Deactivated documents are gone from search with the next request (REQ-ACL-6, REQ-DOC-7, AC-9.1).
* Only `indexed` documents are searchable (REQ-ACL-5, AC-7.5).
* Hit counts must not include hidden documents (REQ-ACL-5).
* Processing is idempotent and can be repeated (REQ-ING-4, NFR-7).
* Any inconsistency must make documents hidden, never visible (fail closed).

## Considered Options

* PostgreSQL authoritative, a `searchable` flag on every chunk, updated synchronously by the API on deactivation, plus a reconciliation job
* Check every hit against PostgreSQL after the search
* Asynchronous propagation of document state to the index (events or change data capture)
* Delete the document's chunks from the index on deactivation

## Decision Outcome

Chosen option: "PostgreSQL authoritative with a synchronously updated `searchable` flag and a reconciliation job", because it gives immediate effect and correct counts, and every failure leaves the document hidden.

Rules:

* **Source of truth:** PostgreSQL holds document state; the index holds derived data and can be rebuilt.
* **Search filter:** every query filters on `searchable = true` in addition to the repository scope ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)).
* **Indexing (worker):**
  1. delete all existing chunks of the document;
  2. bulk insert the new chunks with `searchable = false` and refresh;
  3. in one PostgreSQL transaction, lock the document row (`SELECT … FOR UPDATE`), and if the document is still active, set status `indexed`, set `searchable = true` for its chunks with refresh, then commit.
  If step 3's index update fails, the transaction is rolled back and the job is retried.
* **Deactivation (API):** in one PostgreSQL transaction, lock the document row, set it inactive, set `searchable = false` for its chunks with refresh, then commit and answer.
  If the index update fails, the transaction is rolled back and the API answers 503; the document stays active and visible in all places.
* **Row lock:** indexing and deactivation both take the document row lock, so a worker cannot make a document searchable after it has been deactivated.
* **Reconciliation:** at worker startup and periodically (e.g. every 10 minutes) a job compares PostgreSQL with the index per document and corrects the `searchable` flag; chunks of unknown documents are deleted.
  The number of corrections is logged.

### Consequences

* Good, because deactivation is visible in search before the API answers.
* Good, because half-written or reprocessed documents are never visible.
* Good, because a commit failure after the index update leaves the document hidden but active, which errs on the safe side and is corrected by reconciliation.
* Bad, because a deactivation fails with 503 while the search index is unavailable.
* Bad, because a document row lock is held during an index update; deactivation and indexing of the same document are serialised (rare and short).
* Bad, because the `searchable` flag adds write volume (`update_by_query` over a document's chunks).
* Neutral, because inactive chunks remain in the index; they can be removed later together with hard delete (`mvp.md` §5).

### Confirmation

* Automated tests for AC-7.5 (document in `processing` with matching chunks is not found) and AC-9.1 (deactivated document gone from listing, download and search with the next request).
* Fault-injection test: with the index unavailable, deactivation returns 503 and the document is still listed and active.
* Race test: deactivation during the final indexing step leaves the document not searchable.
* Reconciliation test: a manually flipped `searchable` flag is corrected by the next run.

## Pros and Cons of the Options

### Synchronous `searchable` flag with reconciliation

* Good, because it meets REQ-ACL-6 and AC-7.5 with correct hit counts.
* Good, because the same flag serves two purposes: hiding unfinished and deactivated documents.
* Bad, because it couples deactivation to index availability.

### Check every hit against PostgreSQL

* Good, because the index never needs to be updated for state changes.
* Bad, because hit counts and pagination include hidden documents (violates REQ-ACL-5).
* Bad, because pages can be short or empty after filtering.

### Asynchronous propagation

* Good, because the API does not depend on the index for deactivation.
* Bad, because there is a delay in which deactivated documents are still found (violates REQ-ACL-6).

### Delete chunks on deactivation

* Good, because the index stays smaller.
* Neutral, because it is equally synchronous.
* Bad, because it does not solve hiding unfinished documents during indexing, so a flag or a second index would be needed anyway.
* Bad, because a later reactivation would require reprocessing.

## More Information

* The concrete index operations depend on the search engine decision (planned ADR, replaces C-3); for PostgreSQL + pgvector the whole procedure collapses into one transaction.
* Repository deactivation (US-11) needs no index update, because inactive repositories are excluded by the scope ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)).
