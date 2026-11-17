---
status: proposed
date: 2026-11-17
---

# Filter search by the Principal's repositories at query time

## Context and Problem Statement

Search must only return documents from repositories in which the Principal currently holds a role, and other documents must not influence hits, hit counts or excerpts (REQ-ACL-5).
Role, user and repository changes must take effect with the next request, without reindexing (REQ-ACL-6).
This is the core promise of the product (`mvp.md` §1) and is verified for every role in CI (AC-8.4).
How is the permission filter applied to searches?

## Decision Drivers

* No document outside the Principal's repositories appears in hits, counts or excerpts (REQ-ACL-5, AC-8.1).
* Revoking a role takes effect with the next request (REQ-ACL-6, AC-8.2).
* Global Admins search all active repositories without holding a role (REQ-ACL-4, AC-8.3).
* Restriction to selected repositories (REQ-SRCH-1, AC-7.4), and 404 for repositories without a role (REQ-ACL-3).
* Search latency P95 ≤ 2 s (NFR-1).
* The filter must be impossible to forget in code.

## Considered Options

* Pre-filter in the index query with repository IDs read from PostgreSQL on every request
* Post-filter: search without restriction, then drop hits the Principal may not see
* Access lists stored in the index (users or roles per chunk), updated on every membership change
* Pre-filter with repository IDs cached in the API and invalidated by events

## Decision Outcome

Chosen option: "Pre-filter in the index query with repository IDs read from PostgreSQL on every request", because it is the only option that gives correct hit counts and immediate effect of access changes without reindexing.

Rules:

1. On every search the API reads the IDs of all active repositories in which the Principal holds a role (Global Admin: all active repositories) from PostgreSQL, in the same request, without a cache.
2. If the request restricts the search to repository IDs, the scope is the intersection; if a requested repository is not accessible, the API responds 404 (REQ-ACL-3, no disclosure of existence).
3. If the scope is empty, the API returns an empty result without querying the index.
4. The scope is applied as a filter inside **both** the lexical and the vector sub-query, together with `searchable = true` (see [ADR-0006](0006-keep-postgresql-authoritative-and-update-index-visibility-synchronously.md)), so filtering happens before ranking and counting.
5. Fail closed: if the scope cannot be determined, the API responds 503 and never queries the index without a filter.
6. The `SearchIndex` port ([ADR-0003](0003-structure-code-as-ports-and-adapters.md)) accepts only a `RepositoryScope` value, which can only be created by the access policy and cannot be empty; there is no search method without a scope.

### Consequences

* Good, because revoking a role, deactivating a user or deactivating a repository needs no index update at all.
* Good, because hit counts are computed by the index over permitted documents only.
* Good, because the rule lives in one place and is enforced by the type of the port.
* Bad, because every search costs one additional indexed query on PostgreSQL.
* Bad, because filtered vector search can lose recall if the engine filters after the approximate nearest-neighbour step; the chosen engine must support efficient filtered k-NN, which the spike checks.
* Neutral, because the number of repositories per user is expected to be small, so the filter list stays short.

### Confirmation

* AC-7.4 and AC-8.1 to AC-8.3 run as automated tests for every role in CI (AC-8.4), including a check of the total hit count.
* A test asserts that the search use case returns 503 and sends no index query when the scope lookup fails.
* The `SearchIndex` contract test asserts that results never contain documents outside the scope, for both lexical and vector matches.
* Search latency including the scope lookup is part of the NFR-1 load test.

## Pros and Cons of the Options

### Pre-filter with repository IDs read on every request

* Good, because it is correct by construction for role, user and repository changes.
* Good, because it is simple to implement and to test.
* Bad, because it adds one database query to every search.

### Post-filter

* Good, because the index query stays simple.
* Bad, because hit counts and pagination include forbidden documents (violates REQ-ACL-5).
* Bad, because a page can end up empty or short, and forbidden documents still affect ranking.

### Access lists stored in the index

* Good, because no database lookup is needed at search time.
* Bad, because every membership change requires updating all chunks of the repository, which contradicts "without reindexing" (REQ-ACL-6).
* Bad, because a failed or delayed update leaks documents.

### Pre-filter with cached repository IDs

* Good, because it saves the database lookup.
* Bad, because cache invalidation across API instances can lag, violating AC-8.2.
* Bad, because a stale cache fails open, the most dangerous failure mode for this product.

## More Information

* Replaces constraint C-4 in [`architecture.md`](../architecture.md).
* Document deactivation is handled in [ADR-0006](0006-keep-postgresql-authoritative-and-update-index-visibility-synchronously.md); user deactivation in [ADR-0004](0004-authenticate-with-signed-jwt-and-per-request-user-check.md).
