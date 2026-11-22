# IntelliDoc Platform

A distributed, self-hosted document platform with permission-aware semantic search: teams upload PDFs, independent services process and index them, and users find them by asking in natural language, while only ever seeing documents they are allowed to read.

## Problem

In many organisations, documents such as contracts, policies, reports and scanned letters live in file shares or document systems that can only be searched by file name or exact keyword. People have to know *where* a document is and *what* it is called. Scanned documents are not searchable at all. Asking a general-purpose AI tool is not an option, because the documents are confidential and access differs per team.

The result: time lost searching, duplicate work, and documents that exist but are never found.

Making documents searchable by content is expensive: OCR, text extraction and embedding are compute-heavy and slow. In a single process, a large upload blocks everyone, and a hanging or crashing conversion stops the whole system. The platform therefore runs upload, processing, embedding and answer generation as separate services: processing capacity grows by adding workers, and a failing or overloaded worker or answer model does not take down search, upload or download. The database is shared by all services and remains a single point of failure.

## Target group

| Group | Needs |
|---|---|
| **Readers** (employees of a team) | Find a document by its content or a question, including exact terms such as contract numbers; trust that results are complete for what they may see. |
| **Contributors** | Upload documents quickly, including scans, and know when they are searchable. |
| **Repo Admins** (team leads, document owners) | Decide who sees which documents; be sure that revoked access applies immediately. |
| **Global Admins** (IT operations) | Run the system on-premises with little effort; no document content leaves the organisation unless they explicitly enable an external model provider for answers. |
| **Integrators** (developers of other systems) | Upload and search via API without interactive login. |

## Value

- **Find by meaning, not by file name:** combined keyword and semantic search, including scanned PDFs (OCR).
- **Permission-safe by design:** search applies the user's repository permissions on every request, and access changes take effect immediately.
- **Local and cost-free to run:** extraction, OCR, embeddings and answer generation run inside the deployment; no external paid AI services and no data leaving the system. A Global Admin who prefers faster or better answers can enable an external language model provider for the whole system, for answer generation only, and disable it again at any time.

## Documentation

| File | Content |
|---|---|
| [`docs/requirements.md`](docs/requirements.md) | User stories, functional and non-functional requirements, priorities, acceptance criteria |
| [`docs/mvp.md`](docs/mvp.md) | MVP scope, demo scenario, included/excluded functions with reasons, dependencies and costs, open questions |
| [`docs/architecture.md`](docs/architecture.md) | Technical constraints, the chosen architecture (C4 levels 1–3), how it meets the key requirements, spike |
| [`docs/adr/`](docs/adr/README.md) | Architectural Decision Records (MADR), including the alternatives considered |
| [`docs/ai-usage.md`](docs/ai-usage.md) | How AI was used in requirements engineering, prompts, results and critical assessment |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Repository layout, tooling, code, test and documentation conventions, branches and pull requests |
