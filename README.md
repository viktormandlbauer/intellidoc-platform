# IntelliDoc Platform

IntelliDoc is a self-hosted HTTP API for finding PDFs by keyword or meaning.
It uses OCR to make scans searchable and answers questions with page-level sources.
Search and answers use the reader's current repository permissions.

Teams upload PDFs and track their processing status.
A pool of workers extracts and indexes content in the background.
Models run locally by default. An optional external answer provider requires a Global Admin to enable it.

| Role | Main tasks |
|---|---|
| Reader | Search, ask questions, and download documents. |
| Contributor | Upload PDFs, check processing status, and deactivate their own uploads. |
| Repo Admin | Manage repository membership and deactivate any document in the repository. |
| Global Admin | Manage users and repositories, appoint Repo Admins, and configure system settings. |

## Documentation

| File | Content |
|---|---|
| [MVP](docs/mvp.md) | Scope, demo, and implementation plan |
| [Requirements](docs/requirements.md) | User stories, acceptance criteria, and performance targets |
| [Architecture](docs/architecture.md) | System context, containers, and design trade-offs |
| [Diagrams](diagrams/use-case.md) | MVP use cases. See also the [components](diagrams/component.md) and [ERD](diagrams/erd.md). |
| [Architecture decisions](docs/adr/README.md) | Decisions and alternatives |
| [Contributing](CONTRIBUTING.md) | Repository layout, tooling, and conventions |
| [AI usage](docs/ai-usage.md) | Prompts, results, and team review |
