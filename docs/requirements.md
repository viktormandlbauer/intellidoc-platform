# Requirements – IntelliDoc Platform

Scope of this document: user stories, functional and non-functional requirements, prioritisation and acceptance criteria for the IntelliDoc Platform. The MVP boundary and exclusions are in [`mvp.md`](mvp.md), technical decisions in [`architecture.md`](architecture.md), problem statement and target group in [`README.md`](../README.md).

## 1. Conventions

**Priority (MoSCoW):** tags used for user stories and requirements.

| Tag | Meaning |
|---|---|
| **M** – Must | Indispensable for the MVP demo scenario. Without it the core use case does not work or is insecure. |
| **S** – Should | Planned for this semester after all Musts are done. MVP is demonstrable without it. |
| **C** – Could | Only if time remains. Specified at story level only. |
| **W** – Won't (this semester) | Explicitly out of scope; listed with reasons in `mvp.md`, section 5. |

**Wording:** "The API" = the HTTP interface. "The system" = API plus processing worker and search index. Requirement IDs are stable (removed IDs are not reused); each requirement references the user story it serves.

**Core use case (demo scenario):** A Global Admin sets up a repository and members → a Contributor uploads PDFs (incl. a scanned one) → the documents are processed and become searchable → a Reader finds a document by a natural-language query and by an exact term, and downloads it → a Reader without access to that repository does not see it → after revoking access, the document disappears from that user's results with the next request.

## 2. Roles

| Role | Scope | Permissions |
|---|---|---|
| Global Admin | System | Manages users and repositories; has all Repo Admin permissions in every active repository without holding a repository role. |
| Repo Admin | One repository | Manages members of the repository; all Contributor permissions; deactivates any document; sees and retries failed processing. |
| Contributor | One repository | All Reader permissions; uploads documents; deactivates own documents. |
| Reader | One repository | Lists, searches and downloads documents of the repository. |

Repository roles are hierarchical (Reader ⊂ Contributor ⊂ Repo Admin). A user holds at most one role per repository.

## 3. User stories

### 3.1 Overview

| ID | Priority | Summary |
|---|---|---|
| US-1 | M | Bootstrap the first Global Admin |
| US-2 | M | Manage users |
| US-3 | M | Create repositories and appoint Repo Admins |
| US-4 | M | Manage repository membership |
| US-5 | M | Upload PDFs and see processing status |
| US-6 | M | List and download documents |
| US-7 | M | Search by natural language or exact term |
| US-8 | M | Permission-safe search |
| US-9 | M | Deactivate documents |
| US-10 | S | See and retry failed processing |
| US-11 | S | Deactivate repositories |
| US-12 | S | API keys for integrations |
| US-13 | C | Generated answers with sources |
| US-14 | C | Replace document content |
| US-15 | C | Upload DOCX files |

### 3.2 Test data

All acceptance criteria start from the following base state, unless their **Given** clause says otherwise. Each criterion is independent; changes made by one criterion do not carry over to the next.

| Name | Definition |
|---|---|
| **R1** | Active repository named "Legal". |
| **R2** | Active repository named "HR". |
| **admin** | Global Admin; holds no repository role. |
| **alice** | Repo Admin of R1. |
| **bob** | Contributor in R1. |
| **carol** | Reader in R1. |
| **dave** | Reader in R2 only. |
| **erin** | Active user without any repository role. |
| **frank** | Does not exist yet (created in AC-2.1). |
| **D1** | Active document in R1, uploaded by bob, status `indexed`, containing the term "Rahmenvertrag 2024-117". |

### 3.3 Must stories

#### US-1 – Bootstrap `M`

> As the **operator**, I want to create the first Global Admin at installation time, so that the system can be administered without self-registration.

**Requirements:** REQ-USR-1

| ID | Acceptance criterion |
|---|---|
| AC-1.1 | **Given** an empty database and configured bootstrap credentials, **when** the system starts (or the bootstrap CLI command runs), **then** exactly one active Global Admin with those credentials exists. |
| AC-1.2 | **Given** a Global Admin already exists, **when** the bootstrap runs again, **then** no further user is created and existing credentials are unchanged. |
| AC-1.3 | **When** a create-user request is sent without a token, **then** the API responds 401. |

#### US-2 – Manage users `M`

> As a **Global Admin**, I want to create, edit and deactivate users, so that only known people can access documents.

**Requirements:** REQ-USR-2, REQ-USR-3, REQ-USR-4, REQ-AUT-1, REQ-AUT-2

| ID | Acceptance criterion |
|---|---|
| AC-2.1 | **When** admin creates user "frank", **then** frank can log in and receives a token. |
| AC-2.2 | **When** carol calls the create-user endpoint, **then** the API responds 403. |
| AC-2.3 | **Given** bob holds a valid token, **when** admin deactivates bob, **then** bob's next request with that token returns 401, a new login returns 401, and D1 remains listed with bob as uploader. |
| AC-2.4 | **When** admin attempts to deactivate the last active Global Admin, **then** the API responds 409 and nothing changes. |

#### US-3 – Repositories `M`

> As a **Global Admin**, I want to create repositories and appoint Repo Admins, so that each team manages its own documents.

**Requirements:** REQ-REP-1, REQ-REP-2, REQ-ACL-1, REQ-ACL-4

| ID | Acceptance criterion |
|---|---|
| AC-3.1 | **When** admin creates repository "Finance", **then** it gets a system-generated ID and appears in admin's repository list. |
| AC-3.2 | **When** admin creates a repository "legal" (R1 is named "Legal"), **then** the API responds 409. |
| AC-3.3 | **When** admin appoints erin as Repo Admin of R1, **then** erin can grant roles in R1 and receives 404 when granting roles in R2 (no role there, REQ-ACL-3). |

#### US-4 – Membership `M`

> As a **Repo Admin**, I want to grant, change and revoke roles in my repository, so that I control who may read or upload.

**Requirements:** REQ-REP-2, REQ-REP-3, REQ-ACL-2, REQ-ACL-3

| ID | Acceptance criterion |
|---|---|
| AC-4.1 | **When** alice grants erin the Reader role in R1, **then** erin sees R1 in her repository list and can list its documents. |
| AC-4.2 | **When** carol tries to upload to R1, **then** the API responds 403. |
| AC-4.3 | **When** alice changes carol's role in R1 from Reader to Contributor, **then** carol can upload to R1 with her next request. |
| AC-4.4 | **When** alice lists the members of R1, **then** each member is shown with exactly one role. |
| AC-4.5 | **When** dave requests any resource of R1 (repository, document, members), **then** the API responds 404 (existence is not disclosed). |

#### US-5 – Upload and status `M`

> As a **Contributor**, I want to upload PDFs (also scanned ones) and see their processing status, so that I know when they are searchable.

**Requirements:** REQ-DOC-1, REQ-DOC-2, REQ-DOC-3, REQ-DOC-8, REQ-ING-1, REQ-ING-2, REQ-ING-3, REQ-ING-4

| ID | Acceptance criterion |
|---|---|
| AC-5.1 | **When** bob uploads a valid PDF to R1, **then** the API responds 201 with document ID, status `pending`, name, size, SHA-256 checksum, uploader and upload timestamp. |
| AC-5.2 | **When** bob uploads a text file renamed to `.pdf` with MIME type `application/pdf`, **then** the API responds 415 and no document is created. |
| AC-5.3 | **When** bob uploads a PDF larger than the configured limit (default 50 MB), **then** the API responds 413. |
| AC-5.4 | **Given** bob uploaded a valid PDF, **when** processing completes, **then** its status has passed through `processing` and is `indexed`. |
| AC-5.5 | **Given** a scanned PDF without a text layer was uploaded, **when** processing completes, **then** a search for a word printed on its first page returns it (OCR). |

#### US-6 – List and download `M`

> As a **Reader**, I want to list and download the documents of my repositories, so that I can work with the originals.

**Requirements:** REQ-DOC-4, REQ-DOC-5

| ID | Acceptance criterion |
|---|---|
| AC-6.1 | **When** carol lists R1, **then** she receives all active documents of R1 with name, size, uploader, upload timestamp and status, paginated (default 50 per page). |
| AC-6.2 | **When** carol downloads D1, **then** the received bytes have the SHA-256 checksum stored for D1. |
| AC-6.3 | **When** dave downloads D1, **then** the API responds 404. |

#### US-7 – Search `M`

> As a **Reader**, I want to search all my repositories with a natural-language query or an exact term, so that I find documents without knowing their name or location.

**Requirements:** REQ-REP-3, REQ-SRCH-1, REQ-SRCH-2, REQ-SRCH-3, REQ-SRCH-4

| ID | Acceptance criterion |
|---|---|
| AC-7.1 | **When** carol searches "2024-117", **then** D1 is among the first 10 hits. |
| AC-7.2 | **When** carol searches for a paraphrase of D1's content that shares no keyword with it (from the evaluation set, NFR-3), **then** D1 is among the first 10 hits. |
| AC-7.3 | **When** carol searches, **then** each hit contains document ID and name, repository ID and name, page number and a text excerpt, and hits are ordered by descending relevance. |
| AC-7.4 | **When** carol restricts the search to R1, **then** only hits from R1 are returned. |
| AC-7.5 | **Given** a document with status `pending`, `processing` or `failed` contains "2024-117", **when** carol searches "2024-117", **then** that document is not among the hits. |

#### US-8 – Permission-safe search `M`

> As a **Repo Admin**, I want search to show only documents the searcher may read, and access changes to apply immediately, so that confidential documents never leak.

**Requirements:** REQ-ACL-5, REQ-ACL-6

| ID | Acceptance criterion |
|---|---|
| AC-8.1 | **When** dave searches "2024-117", **then** D1 does not appear in the hits and the total hit count does not include it. |
| AC-8.2 | **Given** carol found D1, **when** alice revokes carol's role in R1 and carol repeats the search immediately, **then** D1 does not appear. |
| AC-8.3 | **When** admin searches "2024-117", **then** D1 appears although admin holds no role in R1. |
| AC-8.4 | AC-7.x and AC-8.x run as automated tests for every role and are part of CI. |

#### US-9 – Deactivate documents `M`

> As a **Contributor**, I want to deactivate my own wrongly uploaded documents (and as Repo Admin any document), so that they no longer appear anywhere.

**Requirements:** REQ-DOC-6, REQ-DOC-7

| ID | Acceptance criterion |
|---|---|
| AC-9.1 | **When** bob deactivates D1, **then** with the next request it is gone from listing, download (404) and search. |
| AC-9.2 | **Given** alice uploaded a document to R1, **when** bob tries to deactivate it, **then** the API responds 403. |
| AC-9.3 | **When** alice deactivates D1, **then** the request succeeds. |
| AC-9.4 | **Given** D1 was deactivated, **then** its original and metadata still exist in storage (verified by database/storage inspection, not via the API). |

### 3.4 Should and Could stories

| ID | Priority | Story | Requirements |
|---|---|---|---|
| US-10 | S | As a **Repo Admin**, I want to see documents whose processing failed and restart processing, so that no document silently stays unsearchable. | REQ-ING-5, REQ-ING-6 |
| US-11 | S | As a **Global Admin**, I want to deactivate a whole repository, so that obsolete collections disappear without data loss. | REQ-REP-4 |
| US-12 | S | As a **developer of another system**, I want to access the API with an API key bound to a user, so that scripts can upload and search without interactive login. | REQ-AUT-3 |
| US-13 | C | As a **Reader**, I want a generated answer to my question with page-level source references, so that I get the information without reading every hit. | – |
| US-14 | C | As a **Contributor**, I want to replace a document's content while keeping its ID, so that links to it stay valid. | – |
| US-15 | C | As a **Contributor**, I want to upload DOCX files as well as PDFs, so that I need not convert them first. | – |

## 4. Functional requirements

### 4.1 Users and authentication

- **REQ-USR-1** [M] (US-1) The system shall provide a bootstrap mechanism (configuration or CLI) that creates the initial Global Admin if none exists, and does nothing otherwise.
- **REQ-USR-2** [M] (US-2) The API shall allow a Global Admin to create, read, list and update users. There shall be no self-registration.
- **REQ-USR-3** [M] (US-2) The API shall allow a Global Admin to deactivate a user. The last active Global Admin shall not be deactivatable.
- **REQ-USR-4** [M] (US-2) A deactivated user's tokens and API keys shall be rejected (401) from the next request on. Their documents and uploader information shall be retained.
- **REQ-USR-5** [S] (US-2) The API shall allow a user to change their own password, and a Global Admin to set a new password for any user.
- **REQ-AUT-1** [M] (US-2) The API shall allow a user to log in with username and password and receive a token with a configurable lifetime (default 60 minutes).
- **REQ-AUT-2** [M] (US-2) The API shall reject every request without valid authentication with 401, except login and health check.
- **REQ-AUT-3** [S] (US-12) The API shall allow a user to create, list and revoke their own API keys. A key is shown in clear text only once at creation, grants exactly the permissions of its user, and can have an optional expiry date.

### 4.2 Repositories and access control

- **REQ-REP-1** [M] (US-3) The API shall allow a Global Admin to create a repository. Repositories are identified by a system-generated ID; names of active repositories shall be unique (case-insensitive).
- **REQ-REP-2** [M] (US-3, US-4) The API shall allow a Global Admin or the repository's Repo Admin to rename a repository, and every member to read its name and ID.
- **REQ-REP-3** [M] (US-4, US-7) The API shall list for a Principal all active repositories in which they hold a role (for a Global Admin: all active repositories).
- **REQ-REP-4** [S] (US-11) The API shall allow a Global Admin to deactivate a repository. This marks the repository and all its documents inactive without physically removing them; the name may then be reused.
- **REQ-ACL-1** [M] (US-3) The API shall allow a Global Admin to assign and revoke the Repo Admin role in any repository.
- **REQ-ACL-2** [M] (US-4) The API shall allow a Repo Admin to grant, change and revoke the Contributor and Reader roles in their repository, and to list its members with their roles.
- **REQ-ACL-3** [M] (US-4) The API shall reject operations not permitted by the Principal's role with 403. For repositories or documents the Principal has no role for, the API shall respond 404.
- **REQ-ACL-4** [M] (US-3) A Global Admin shall have all Repo Admin permissions in every active repository without holding a role there.
- **REQ-ACL-5** [M] (US-8) Every search shall be restricted to active, indexed documents in repositories in which the Principal currently holds a role (Global Admin: all active repositories). Other documents shall not appear in hits, hit counts or excerpts.
- **REQ-ACL-6** [M] (US-8) Changes to roles, user state, repository state and document state shall take effect for listing, download and search with the next request, without reindexing.

### 4.3 Documents

- **REQ-DOC-1** [M] (US-5) The API shall allow a Contributor or Repo Admin to upload a PDF document to a repository, up to a configurable maximum size (default 50 MB).
- **REQ-DOC-2** [M] (US-5) The API shall reject files that are not valid PDFs (415), validated by file content, not by extension or declared MIME type.
- **REQ-DOC-3** [M] (US-5) The system shall store for each document: ID, repository, name, size, SHA-256 checksum, uploader, upload timestamp and processing status. The original shall be stored unchanged.
- **REQ-DOC-4** [M] (US-6) The API shall allow every member of a repository to list its active documents (paginated) and to read a document's metadata.
- **REQ-DOC-5** [M] (US-6) The API shall allow every member of a repository to download the original of an active document.
- **REQ-DOC-6** [M] (US-9) The API shall allow a Contributor to deactivate documents they uploaded, and a Repo Admin to deactivate any document in their repository. Deactivation shall not physically remove the original or metadata.
- **REQ-DOC-7** [M] (US-9) Inactive documents and documents of inactive repositories shall be excluded from listing, download and search.
- **REQ-DOC-8** [M] (US-5) Every upload shall create a new, independent document. The system shall not keep versions and shall not detect duplicates.

### 4.4 Processing

- **REQ-ING-1** [M] (US-5) The system shall process every uploaded document asynchronously: text extraction (with OCR for pages without a text layer), chunking with page reference, embedding and indexing. The upload request shall not wait for processing.
- **REQ-ING-2** [M] (US-5) The system shall store and the API shall expose a processing status per document: `pending`, `processing`, `indexed`, `failed`. Allowed transitions: `pending → processing → indexed | failed`; `failed → pending` on retry (REQ-ING-6); `processing → pending` on recovery after a worker interruption (NFR-7).
- **REQ-ING-3** [M] (US-5, US-10) When processing fails or exceeds a configurable timeout (default 10 minutes per document), the system shall set the status `failed` and store the error message and the failed step.
- **REQ-ING-4** [M] (US-5) Processing shall be idempotent: repeating it for a document shall replace that document's chunks and index entries and never create duplicates.
- **REQ-ING-5** [S] (US-10) The API shall allow a Repo Admin to list the failed documents of their repositories, and a Global Admin those of all repositories, with document name, repository, failed step and error message.
- **REQ-ING-6** [S] (US-10) The API shall allow a Repo Admin or Global Admin to restart processing of a failed document.

### 4.5 Search

- **REQ-SRCH-1** [M] (US-7) The API shall accept a free-text query (1–500 characters) and search all repositories accessible to the Principal (REQ-ACL-5), optionally restricted to a list of repository IDs.
- **REQ-SRCH-2** [M] (US-7) The system shall combine lexical (keyword) and semantic (embedding) matching in one ranked result list.
- **REQ-SRCH-3** [M] (US-7) Each hit shall contain document ID and name, repository ID and name, page number and a text excerpt of the matching passage. Hits shall be ordered by relevance and paginated (default 10 per page).
- **REQ-SRCH-4** [M] (US-7) For queries consisting of an identifier-like term (e.g. a contract number or name), the document containing that term shall rank within the first 10 hits in at least 95 % of the exact-term queries of the evaluation set (NFR-3).
- **REQ-SRCH-5** [S] (US-7) The system shall support documents and queries in German and English, including queries in one language matching documents in the other (semantic part).

## 5. Non-functional requirements

All measurements on the **reference environment**: one host, 8 CPU cores, 16 GB RAM, no GPU, test corpus of 1,000 PDFs (≈ 20,000 pages, of which ≥ 10 % scanned).

- **NFR-1 Search performance** [M] – Search response time P95 ≤ 2 s with 5 concurrent users on the reference corpus. *Test:* load test script (e.g. k6/Locust) in the repository.
- **NFR-2 Processing time** [M] – A 20-page born-digital PDF reaches `indexed` within 2 minutes; a 20-page scanned PDF within 5 minutes, measured from upload. *Test:* timed run of the reference set.
- **NFR-3 Search quality** [M] – An evaluation set of ≥ 30 queries (German and English; at least 10 exact-term and 10 paraphrase queries) with expected documents is part of the repository. Targets: exact-term queries ≥ 95 % with the expected document in the top 10; all queries Recall@10 ≥ 0.8. *Test:* evaluation script, results documented per release.
- **NFR-4 Security** [M] – Passwords stored with Argon2id or bcrypt; API keys stored only as hashes; tokens signed and expiring; no passwords, tokens or document contents in logs; TLS for all external traffic (via reverse proxy). *Test:* code review checklist + automated test that a revoked/deactivated principal receives 401/404.
- **NFR-5 Data protection and cost** [M] – All Must features run without external paid services: text extraction, OCR and embeddings run locally inside the deployment, so no document content leaves the system. *Test:* deployment runs with outbound internet blocked (after model download).
- **NFR-6 Deployability** [M] – The whole system starts with a single `docker compose up` on the reference environment, with documented configuration (`.env.example`). Data (database, originals, index) survives a restart. *Test:* fresh checkout → demo scenario passes.
- **NFR-7 Robustness** [S] – If the worker is stopped during processing, the affected documents are processed again after restart and reach `indexed` or `failed`; none stays in `processing` permanently.
- **NFR-8 API documentation** [M] – The API is described by an OpenAPI 3 specification generated from the code and published by the running service; all errors use one JSON error format with code and message.

## 6. Glossary

| Term | Definition |
|---|---|
| Principal | A user authenticated by token or API key. |
| Repository | Named container of documents and the unit of access control. Identified by a system-generated ID. |
| Document | An uploaded file plus metadata, stored in exactly one repository. |
| Original | The file exactly as uploaded; never modified. |
| Uploader | The user who uploaded a document; used for Contributor deactivation rights. |
| Chunk | A text passage of a document with page reference; the unit of search. |
| Hit | A search result: a chunk with document, repository, page and excerpt. |
| Processing status | `pending`, `processing`, `indexed` or `failed`. |
| Inactive | Soft-deleted: data is retained. Inactive documents and repositories are excluded from listing, download and search; inactive users cannot authenticate. |
