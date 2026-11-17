# MVP – IntelliDoc Platform

This document defines what the MVP contains, what it explicitly does not contain, and how the MVP is demonstrated. Detailed requirements and acceptance criteria are in [`requirements.md`](requirements.md); IDs below refer to it. Architecture and technical decisions are in [`architecture.md`](architecture.md) and [`adr/`](adr/README.md).

## 1. MVP goal

Prove one thing: **users find documents by their content in natural language, and they only ever find documents they are allowed to see.**

The MVP is successful when the demo scenario (section 2) runs end to end on a fresh installation and all Must acceptance criteria and Must NFRs pass.

## 2. Demo scenario (the complete use case)

| Step | Actor | Action | Expected result | Covers |
|---|---|---|---|---|
| 1 | Operator | `docker compose up` with bootstrap credentials in `.env` | System running, one Global Admin exists | US-1, NFR-6 |
| 2 | Global Admin | Creates users alice, bob, carol, dave and repositories R1 "Legal", R2 "HR" | Users can log in; repositories listed | US-2, US-3 |
| 3 | Global Admin | Appoints alice Repo Admin of R1; makes dave Reader in R2 | alice manages R1; her requests to R2 return 404 | US-3, US-4 |
| 4 | alice | Makes bob Contributor and carol Reader in R1 | Members of R1 listed with roles | US-4 |
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

**Won't – not in this semester:**

| Feature | Reason |
|---|---|
| PDF/A archive version and veraPDF validation | No user value for the core use case; large extra pipeline. Originals are retained, so it can be added later. |
| Automatic classification, labels, label filter and facets | Needs a taxonomy and its management first; not required for finding documents. |
| Reviewer role and review workflow | Depends on classification. Its removal also allows simple hierarchical roles. |
| OIDC / single sign-on | Local login suffices for the MVP; authentication is kept behind one interface so it can be added. |
| Document versions, duplicate detection | Not needed for the core use case. |
| Hard delete / purge of inactive data | Needed eventually (GDPR erasure), not for the MVP. |
| Reactivation of users, repositories or documents | Not needed for the MVP. |
| Audit log | Desirable for a document system; deferred. Application logs record security-relevant errors only. |
| Graphical user interface | The MVP is an HTTP API; Swagger UI serves as the demo client. |

Reasons for the Could stories: replacing content (US-14) is covered by upload + deactivate and complicates idempotency and permission semantics; generated answers (US-13) require an LLM (cost, hosting, data protection) and a separate decision on a local vs. external model; further formats (US-15) are cheap with Docling, but validation and tests per format add effort.

## 6. Dependencies and costs

| Dependency | Purpose | Cost | Risk / mitigation |
|---|---|---|---|
| Docling (MIT) | Extraction, OCR, chunking | Free, local; CPU time | Slow on scanned PDFs, single files may hang → timeout (REQ-ING-3), NFR-2 sized for CPU |
| Open multilingual embedding model | Semantic search; served by a shared embedding service ([ADR-0001](adr/0001-use-api-worker-pool-and-dedicated-search-engine.md)) | Free, local; ~1–2 GB RAM | Quality unknown → chosen by evaluation set (NFR-3) |
| Search engine (OpenSearch or PostgreSQL + pgvector) | Keyword + vector index | Free, self-hosted; OpenSearch ≈ 2–4 GB heap | Memory on reference host → decided by the spike ([`architecture.md`](architecture.md) §7) |
| RabbitMQ | Job queue between API and workers ([ADR-0007](adr/0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md)) | Free, self-hosted; ≈ 150–250 MB RAM | Extra container → fallback to a PostgreSQL job table if memory is short (Q-2) |
| PostgreSQL | Metadata, users, roles, status, outbox | Free | – |
| Object storage (filesystem or S3-compatible, e.g. MinIO) | Originals | Free | – |
| Reverse proxy (e.g. Caddy or Traefik) | TLS termination (NFR-4) | Free | – |
| Docker / Compose | Deployment | Free | – |

No external paid API is required for any Must or Should feature (NFR-5). Only US-13 (answers) could introduce LLM costs; that would need a separate decision.

## 7. Rough plan

| Phase | Content | Outcome |
|---|---|---|
| 1 | Requirements (this phase) | Documents in `docs/` |
| 2 | Architecture ([`architecture.md`](architecture.md), [ADRs](adr/README.md)), spike deciding C-2/C-3, skeleton with compose, auth, users | Login works, CI running |
| 3 | Repositories, roles, upload, list, download, deactivate | US-1…6, US-9 |
| 4 | Processing pipeline with Docling, embeddings, index | Documents reach `indexed` |
| 5 | Search with permission filter, evaluation set, load test | US-7, US-8, NFR-1…3 |
| 6 | Should features, hardening, demo | Demo scenario passes |

**Biggest risk:** search quality and processing time (phases 4–5). That's why the evaluation set and test corpus should be built early, in phase 2.

## 8. Open questions

- **Q-1** Which language dominates the target documents? If German only, REQ-SRCH-5 may drop to Could.
- **Q-2** Is the reference environment (`requirements.md`, section 5) realistic for the demo hardware available to the team?
- **Q-3** Source of the test corpus and evaluation set (public documents vs. anonymised real ones).
