# Document API

A distributed, self-hosted document platform with permission-aware semantic search: teams upload PDFs, independent services process and index them, and users find them by asking in natural language, while only ever seeing documents they are allowed to read.

> **Status:** Phase 1 – requirements. No code yet.

## Problem

In many organisations, documents such as contracts, policies, reports and scanned letters live in file shares or document systems that can only be searched by file name or exact keyword. People have to know *where* a document is and *what* it is called. Scanned documents are not searchable at all. Asking a general-purpose AI tool is not an option, because the documents are confidential and access differs per team.

The result: time lost searching, duplicate work, and documents that exist but are never found.

Making documents searchable by content is expensive: OCR, text extraction and embedding are compute-heavy and slow. On a single server, a large upload blocks everyone, and one failure stops the whole system. The platform is therefore built as a distributed system: upload, processing and search run as separate services, so processing capacity can grow by adding workers, and the failure of one node does not take down search or upload.

## Target group

| Group | Needs |
|---|---|
| **Readers** (employees of a team) | Find a document by its content or a question, including exact terms such as contract numbers; trust that results are complete for what they may see. |
| **Contributors** | Upload documents quickly, including scans, and know when they are searchable. |
| **Repo Admins** (team leads, document owners) | Decide who sees which documents; be sure that revoked access applies immediately. |
| **Global Admins** (IT operations) | Run the system on-premises with little effort; no document content leaves the organisation. |
| **Integrators** (developers of other systems) | Upload and search via API without interactive login. |

## Value

- **Find by meaning, not by file name:** combined keyword and semantic search, including scanned PDFs (OCR).
- **Permission-safe by design:** search applies the user's repository permissions on every request, and access changes take effect immediately.
- **Local and cost-free to run:** extraction, OCR and embeddings run inside the deployment; no external paid AI services and no data leaving the system.

## Project goal (this semester)

Deliver an MVP of the distributed document platform that demonstrates the complete use case: set up repositories and members → upload PDFs → automatic processing → permission-filtered natural-language search → download. The scope, the demo scenario and what is excluded are defined in [`docs/mvp.md`](docs/mvp.md).

## Documentation

| File | Content |
|---|---|
| [`docs/requirements.md`](docs/requirements.md) | User stories, functional and non-functional requirements, priorities, acceptance criteria |
| [`docs/mvp.md`](docs/mvp.md) | MVP scope, demo scenario, included/excluded functions, dependencies and costs |
| [`docs/ai-usage.md`](docs/ai-usage.md) | How AI was used in requirements engineering, prompts, results and critical assessment |
