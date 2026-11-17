---
status: proposed
date: 2026-11-17
---

# Authenticate with signed JWTs and a per-request user check

## Context and Problem Statement

Users log in with username and password and receive a token with a configurable lifetime, default 60 minutes (REQ-AUT-1).
A deactivated user's tokens and API keys must be rejected from the next request on (REQ-USR-4, AC-2.3), and integrations use API keys bound to a user (REQ-AUT-3, Should).
API instances must stay stateless so they can be scaled (see [ADR-0001](0001-use-api-worker-pool-and-dedicated-search-engine.md)), and OIDC should be addable later (`mvp.md` §5).
How are tokens and API keys issued and validated?

## Decision Drivers

* Immediate rejection of deactivated users (REQ-USR-4, AC-2.3) and of their API keys.
* Configurable token lifetime (REQ-AUT-1); 401 for every request without valid authentication except login and health check (REQ-AUT-2).
* Passwords hashed with Argon2id or bcrypt; API keys stored only as hashes; signed, expiring tokens; no secrets in logs (NFR-4).
* Stateless API instances without shared session storage.
* Authentication behind one interface so OIDC can be added later.

## Considered Options

* Signed JWT plus a lookup of the user in PostgreSQL on every request
* Purely stateless JWT (no lookup)
* Opaque session tokens stored in PostgreSQL or Redis
* Signed JWT plus a revocation list

## Decision Outcome

Chosen option: "Signed JWT plus a lookup of the user in PostgreSQL on every request", because it rejects deactivated users immediately without a revocation list or session store, and the lookup is needed anyway to load the Principal's Global Admin flag.

Details:

* **Tokens:** JWT signed with HS256 and a secret from configuration (one issuer; RS256 becomes relevant with OIDC).
  Claims: `sub` (user ID), `iat`, `exp`, `ver` (the user's `token_version`).
  Lifetime from configuration, default 60 minutes; no refresh tokens in the MVP.
* **Per-request check:** the authentication adapter loads the user by primary key and rejects with 401 if the user does not exist, is inactive, or `ver` differs from the stored `token_version`.
  `token_version` is incremented on deactivation and on password change or reset (REQ-USR-5), which invalidates all existing tokens of that user.
* **Passwords:** Argon2id.
* **API keys:** format `idk_<key-id>_<secret>` with 32 random bytes of secret; stored as key ID, SHA-256 hash of the secret, owner, optional expiry and revocation time.
  Shown in clear text only once at creation.
  A fast hash is sufficient because the secret has high entropy; comparison is constant-time.
  An API key request runs the same user check as a token request.
* **Interface:** an `Authenticator` port turns a request credential (bearer token or API key) into a `Principal`; OIDC becomes another adapter.

### Consequences

* Good, because deactivation and password changes take effect with the next request.
* Good, because API instances need no shared session state.
* Good, because tokens and API keys follow the same validation path.
* Bad, because every request costs one primary-key lookup in PostgreSQL; this is cheap and also required for the access filter ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)).
* Bad, because a leaked signing secret allows forging tokens for any user until the secret is rotated, which invalidates all tokens.

### Confirmation

* Automated tests for AC-1.3, AC-2.2 and AC-2.3 (token and new login rejected after deactivation).
* Automated test that a deactivated user's API key returns 401 (NFR-4).
* Code review checklist item: no passwords, tokens or API keys in logs; a log-capture test asserts this for login and upload.

## Pros and Cons of the Options

### Signed JWT plus per-request user lookup

* Good, because it meets REQ-USR-4 without extra infrastructure.
* Good, because `token_version` also covers logout of all sessions after a password change.
* Bad, because tokens are not usable without the database, which removes the main benefit of JWTs; the format is kept for OIDC compatibility.

### Purely stateless JWT

* Good, because no database access is needed for authentication.
* Bad, because a deactivated user's token stays valid until it expires, violating AC-2.3.

### Opaque session tokens in PostgreSQL or Redis

* Good, because tokens can be revoked individually.
* Neutral, because the lookup cost is the same as with the chosen option.
* Bad, because Redis would add a container; storing sessions in PostgreSQL requires cleanup of expired sessions.
* Bad, because the token format differs from what OIDC will deliver later.

### Signed JWT plus revocation list

* Good, because individual tokens can be revoked.
* Bad, because the list must be shared by all API instances and still requires a lookup per request.
* Bad, because deactivating a user would require knowing all of that user's issued tokens.

## More Information

* Replaces assumption A-2 in [`architecture.md`](../architecture.md).
* Bootstrap of the first Global Admin (REQ-USR-1) uses the same password hasher.
