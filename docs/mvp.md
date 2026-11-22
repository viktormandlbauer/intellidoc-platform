# MVP – IntelliDoc Platform

This document defines what the MVP contains, what it explicitly does not contain, and how the MVP is demonstrated. Detailed requirements and acceptance criteria are in [`requirements.md`](requirements.md); IDs below refer to it. Architecture and technical decisions are in [`architecture.md`](architecture.md) and [`adr/`](adr/README.md).

## 1. MVP goal

Prove one thing: **users find documents and answers by their content in natural language, and they only ever see content they are allowed to see.**

The MVP is successful when the demo scenario (section 2) runs end to end on a fresh installation and all Must acceptance criteria and Must NFRs pass.

## 2. Demo scenario (the complete use case)

| Step | Actor | Action | Expected result | Covers |
|---|---|---|---|---|
| 1 | Operator | `docker compose up` with bootstrap credentials in `.env` | System running, one Global Admin exists | US-1 |
| 2 | Global Admin | Creates users alice, bob, carol, dave and repositories R1 "Legal", R2 "HR" | Users can log in; repositories listed | US-2, US-3 |
| 3 | Global Admin | Appoints alice Repo Admin of R1; makes dave Reader in R2 | alice manages R1; her requests to R2 return 404 | US-3, US-4 |
| 4 | alice | Makes bob Contributor and carol Reader in R1 | Members of R1 listed with roles | US-4 |
| 5 | bob | Uploads 5 PDFs to R1, one of them scanned, plus a renamed `.txt` file | PDFs accepted (`pending`), fake PDF rejected (415) | US-5 |
| 6 | bob | Polls the status | All 5 reach `indexed` within NFR-2 limits | US-5 |
| 7 | carol | Searches "2024-117" (exact term) and a paraphrased question | Expected document in top 10 with page and excerpt, also the scanned one | US-7 |
| 8 | carol | Asks a question answered by one of the uploaded documents | Generated answer with a source reference to that document and page | US-13 |
| 9 | dave | Runs the same searches and asks the same question | No hit and no source from R1, count excludes R1; direct download of the document → 404 | US-8, US-13 |
| 10 | alice | Revokes carol's role; carol searches and asks again immediately | No hits and no sources from R1 | US-8, US-13 |
| 11 | bob | Deactivates one of his documents | Gone from list, search and download; still in storage | US-9 |

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
| Answers | Generated answers to questions with page-level source references, from permitted passages only | REQ-ANS-1…4 (US-13) |
| Quality | Performance, processing time, search quality, security, OpenAPI, answer time | NFR-1…4, NFR-8, NFR-9 |

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
| External answer provider, enabled system-wide by a Global Admin | REQ-ANS-5 (US-16) |

## 5. Excluded

**Could:** no Could stories are currently specified.

**Won't – not in this semester:**

| Feature | Reason |
|---|---|
| PDF/A archive version and veraPDF validation | No user value for the core use case; large extra pipeline. Originals are retained, so it can be added later. |
| Automatic classification, labels, label filter and facets | Needs a taxonomy and its management first; not required for finding documents. |
| Reviewer role and review workflow | Depends on classification. Its removal also allows simple hierarchical roles. |
| OIDC / single sign-on | Local login suffices for the MVP; authentication is kept behind one interface so it can be added. |
| Replacing a document's content while keeping its ID | Covered by upload + deactivate; replacing content complicates idempotency and permission semantics. |
| DOCX and other formats | Cheap with Docling, but validation and tests per format add effort; PDFs are enough to prove the use case. |
| Document versions, duplicate detection | Not needed for the core use case. |
| Hard delete / purge of inactive data | Needed eventually (GDPR erasure), not for the MVP. |
| Reactivation of users, repositories or documents | Not needed for the MVP. |
| Audit log | Desirable for a document system; deferred. Application logs record security-relevant errors only. |
| Graphical user interface | The MVP is an HTTP API; Swagger UI serves as the demo client. |

## 6. Dependencies and costs

| Dependency | Purpose | Cost | Risk / mitigation |
|---|---|---|---|
| Docling (MIT) | Extraction, OCR, chunking | Free, local; CPU time | Slow on scanned PDFs, single files may hang → timeout (REQ-ING-3), NFR-2 sized for CPU |
| Open multilingual embedding model | Semantic search; served by a shared embedding service ([ADR-0001](adr/0001-use-api-worker-pool-and-postgresql-search.md)) | Free, local; RAM measured in the spike | Quality unknown → chosen by evaluation set (NFR-3) |
| PostgreSQL + pgvector (local) | Keyword + vector index, in the same database as metadata | Free, self-hosted; no extra container | Lexical ranking weaker than BM25 → exact-term guarantee (REQ-SRCH-4) proven by the evaluation set in the spike; fallbacks BM25 extension, then OpenSearch ([`architecture.md`](architecture.md) §7) |
| RabbitMQ | Job queue between API and workers ([ADR-0007](adr/0007-deliver-processing-jobs-via-rabbitmq-with-transactional-outbox.md)) | Free, self-hosted; one extra container | Extra container → fallback to a PostgreSQL job table if memory is short (Q-2) |
| Open language model (local) | Answer generation (US-13), default | Free, local; RAM depends on model size, measured in the spike | CPU-only inference is slow and competes for memory with search and embeddings → small quantised model, answer time bounded by NFR-9, chosen with the evaluation set |
| External LLM provider (optional, [ADR-0010](adr/0010-generate-answers-locally-with-opt-in-external-provider.md)) | Answer generation (US-13), opt-in alternative via the same interface | Pay per token; no local RAM | Passages leave the deployment → off by default, enabled only by a Global Admin for the whole system (REQ-ANS-5), only question + selected passages sent; prefer EU-hosted providers (GDPR, data processing agreement, no third-country transfer); a provider is supported only if it passes the `AnswerModel` contract tests; provider outage → answers return 503, search unaffected |
| PostgreSQL | Metadata, users, roles, status, outbox | Free | – |
| Object storage (RustFS, S3-compatible, local) | Originals | Free, self-hosted (Apache-2.0) | Younger project than other S3-compatible stores → only the plain S3 API is used, behind an `ObjectStore` interface ([ADR-0011](adr/0011-store-originals-in-rustfs.md)); a contract test suite runs against it, so another S3-compatible store or the filesystem can replace it by configuration |
| Reverse proxy | TLS termination (NFR-4) | Free | – |
| Docker / Compose | Deployment | Free | – |

In the default configuration no external paid service is required for any Must or Should feature. The only optional running cost is the external LLM provider for answers, paid per token once a Global Admin enables it.

## 7. Rough plan

| Phase | Content | Outcome |
|---|---|---|
| 1 | Requirements (this phase) | Documents in `docs/` |
| 2 | Architecture ([`architecture.md`](architecture.md), [ADRs](adr/README.md)), spike deciding C-2, C-3 and the default answer model (C-5), skeleton with compose, auth, users | Login works, CI running |
| 3 | Repositories, roles, upload, list, download, deactivate | US-1…6, US-9 |
| 4 | Processing pipeline with Docling, embeddings, index | Documents reach `indexed` |
| 5 | Search with permission filter, evaluation set, load test; answers on top of search | US-7, US-8, US-13, NFR-1…3, NFR-9 |
| 6 | Should features, hardening, demo | Demo scenario passes |

**Biggest risk:** search quality, processing time and answer time on CPU only (phases 4–5). That's why the evaluation set and test corpus should be built early, in phase 2.

## 8. Open questions

- **Q-1** Which language dominates the target documents? If German only, REQ-SRCH-5 may drop to Could.
- **Q-2** Is the reference environment (`requirements.md`, section 5) realistic for the demo hardware available to the team?
- **Q-3** Source of the test corpus and evaluation set (public documents vs. anonymised real ones).
