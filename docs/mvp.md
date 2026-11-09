# MVP – Document API

This document defines what the MVP contains, what it explicitly does not contain, and how the MVP is demonstrated. Detailed requirements and acceptance criteria are in `docs/requirements.md`; IDs below refer to it.

## 1. MVP goal

Prove one thing: **users find documents by their content in natural language, and they only ever find documents they are allowed to see.**

The MVP is successful when the demo scenario (section 2) runs end to end on a fresh installation and all Must acceptance criteria and Must NFRs pass.

## 2. Demo scenario (the complete use case)

| Step | Actor | Action | Expected result | Covers |
|---|---|---|---|---|
| 1 | Operator | `docker compose up` with bootstrap credentials in `.env` | System running, one Global Admin exists | US-1, NFR-6 |
| 2 | Global Admin | Creates users alice, bob, carol, dave and repositories R1 "Legal", R2 "HR" | Users can log in; repositories listed | US-2, US-3 |
| 3 | Global Admin | Appoints alice Repo Admin of R1 | alice manages R1, gets 403 on R2 | US-3 |
| 4 | alice | Makes bob Contributor and carol Reader in R1; dave is Reader in R2 only | Members listed with roles | US-4 |
| 5 | bob | Uploads 5 PDFs to R1, one of them scanned, plus a renamed `.txt` file | PDFs accepted (`pending`), fake PDF rejected (415) | US-5 |
| 6 | bob | Polls the status | All 5 reach `indexed` within NFR-2 limits | US-5 |
| 7 | carol | Searches "2024-117" (exact term) and a paraphrased question | Expected document in top 10 with page and excerpt, also the scanned one | US-7 |
| 8 | dave | Runs the same searches | No hit from R1, count excludes R1; direct download of the document → 404 | US-8 |
| 9 | alice | Revokes carol's role; carol searches again immediately | No hits from R1 | US-8 |
| 10 | bob | Deactivates one of his documents | Gone from list, search and download; still in storage | US-9 |

## 3. Included (Must)

| Area | Functionality | Requirements |
|---|---|---|
| Setup | Bootstrap of the first Global Admin | REQ-USR-1 |
| Users | Create, read, list, update, deactivate users; local login with token | REQ-USR-2…4, REQ-AUT-1…2 |
| Repositories | Create, rename, list own repositories | REQ-REP-1…3 |
| Access control | Roles Repo Admin / Contributor / Reader (hierarchical); Global Admin superuser; 403/404 rules | REQ-ACL-1…4 |
| Documents | PDF upload with content validation and size limit; metadata; list; download; deactivate (soft delete) | REQ-DOC-1…8 |
| Processing | Asynchronous pipeline: extraction incl. OCR, chunking with page reference, embedding, indexing; status; timeout; idempotent | REQ-ING-1…4 |
| Search | Hybrid keyword + semantic search across permitted repositories; exact-term guarantee; hits with page and excerpt | REQ-SRCH-1…4 |
| Security of search | Mandatory permission filter, immediate effect of access changes | REQ-ACL-5…6 |
| Quality | Performance, processing time, search quality, security, local processing, one-command deployment, OpenAPI | NFR-1…6, NFR-8 |

**Interface:** the MVP is an HTTP API with OpenAPI documentation (Swagger UI serves as the demo client). A graphical user interface is not part of the MVP.

## 4. Planned after the Musts (Should)

| Functionality | Requirements |
|---|---|
| List and retry failed documents | REQ-ING-5…6 (US-10) |
| Deactivate repositories | REQ-REP-4 (US-11) |
| API keys | REQ-AUT-3 (US-12) |
| Own password change / admin password reset | REQ-USR-5 |
| German and English, incl. cross-language search | REQ-SRCH-5 |
| Worker restart robustness | NFR-7 |

## 5. Excluded

**Could – only if time remains:** generated answers with source references (US-13), replacing document content (US-14), DOCX upload (US-15).

**Won't – not in this semester:** PDF/A archiving and validation, classification / labels / facets, Reviewer role and review workflow, OIDC/SSO, versioning, duplicate detection, hard delete/purge, reactivation, audit log, web UI.

Reasons for each exclusion: `docs/requirements.md`, section 7.

## 6. Dependencies and costs

| Dependency | Purpose | Cost | Risk / mitigation |
|---|---|---|---|
| Docling (MIT) | Extraction, OCR, chunking | Free, local; CPU time | Slow on scanned PDFs, single files may hang → timeout (REQ-ING-3), NFR-2 sized for CPU |
| Open multilingual embedding model | Semantic search | Free, local; ~1–2 GB RAM | Quality unknown → chosen by evaluation set (NFR-3) |
| Search engine (OpenSearch or PostgreSQL + pgvector) | Keyword + vector index | Free, self-hosted | Memory on reference host → decide in architecture phase |
| PostgreSQL | Metadata, users, roles, status | Free | – |
| Object storage (filesystem or S3-compatible, e.g. MinIO) | Originals | Free | – |
| Docker / Compose | Deployment | Free | – |

No external paid API is required for any Must or Should feature (NFR-5). Only US-13 (answers) could introduce LLM costs; that would need a separate decision.

## 7. Rough plan

| Phase | Content | Outcome |
|---|---|---|
| 1 | Requirements (this phase) | Documents in `docs/` |
| 2 | Architecture, tech decisions C-2/C-3, skeleton with compose, auth, users | Login works, CI running |
| 3 | Repositories, roles, upload, list, download, deactivate | US-1…6, US-9 |
| 4 | Processing pipeline with Docling, embeddings, index | Documents reach `indexed` |
| 5 | Search with permission filter, evaluation set, load test | US-7, US-8, NFR-1…3 |
| 6 | Should features, hardening, demo | Demo scenario passes |

**Biggest risk:** search quality and processing time (phases 4–5). That's why the evaluation set and test corpus should be built early, in phase 2.
