# Contributing to the IntelliDoc Platform

This file describes how the repository is organised and which conventions apply to code and documentation.
What the system does and why is in the [README](README.md) and [`docs/`](docs/).
The conventions here are easy to change: change them in the same pull request that needs the change.
Anything hard to reverse is recorded as an architectural decision in `docs/adr/` instead.

> **Status:** there is no code yet. The layout and tooling below are the target for the phase 2 skeleton ([`mvp.md`](docs/mvp.md) §7); commands marked *planned* work once the skeleton exists.

## Repository layout

```text
README.md, CONTRIBUTING.md
pyproject.toml, uv.lock        one Python package for the API and the worker
compose.yaml                   the services of architecture.md §3
.env.example                   every configuration variable, with comments
docker/                        Dockerfiles (API/worker, embedding service, answer model), reverse proxy config
src/intellidoc_platform/       application code, see below
tests/
  unit/                        domain and use cases with in-memory adapters
  contract/                    one suite per port, run against the in-memory and the real adapter
  integration/                 against the running containers, incl. the permission tests
evaluation/                    search and answer evaluation set (queries, questions, expected documents and pages), scripts, corpus manifest
docs/                          requirements, MVP, architecture, ADRs, AI usage
scripts/                       repository tooling, e.g. check_ids.py
.github/workflows/             CI
```

The application code is structured as ports and adapters:

```text
src/intellidoc_platform/
  domain/          entities, value objects, access policy, status transitions; no framework imports
  application/     use cases and port definitions (typing.Protocol)
  adapters/
    inbound/
      http/        FastAPI routers, request/response schemas, error mapping
      worker/      job consumer
    outbound/
      postgres/    metadata repositories, outbox, system settings
      search/      SearchIndex (PostgreSQL with pgvector)
      storage/     ObjectStore (S3 API)
      queue/       JobPublisher (RabbitMQ)
      embedding/   Embedder (HTTP client to the embedding service)
      answer/      AnswerModel (OpenAI-compatible chat completions)
      parsing/     DocumentParser (Docling in a child process)
      auth/        Authenticator, PasswordHasher, ApiKeyHasher
  bootstrap/       composition root per process (api, worker), reads configuration
```

**Dependency rule:** `domain` imports nothing from `application` or `adapters`; `application` imports only `domain`; adapters are wired to ports only in `bootstrap`.
Neither `domain` nor `application` imports FastAPI, SQLAlchemy, AMQP, S3 or Docling libraries.
import-linter enforces this in CI.

Test corpus PDFs are not committed while their source is still open; `evaluation/` holds a manifest and a script that downloads them.

## Tooling

| Purpose | Tool |
|---|---|
| Python version | 3.12 |
| Dependencies and virtual environment | uv (`pyproject.toml`, `uv.lock` committed) |
| Linting and formatting | ruff |
| Static type checking | mypy in strict mode for `src/` |
| Tests | pytest |
| Dependency rule | import-linter |
| Markdown | markdownlint-cli2 ([`.markdownlint-cli2.yaml`](.markdownlint-cli2.yaml)), lychee for links |
| Requirement and ADR IDs | [`scripts/check_ids.py`](scripts/check_ids.py) |

## Local setup *(planned)*

```sh
uv sync                    # install dependencies
cp .env.example .env       # set at least the bootstrap credentials of the first Global Admin
docker compose up          # start the full stack
```

## Checks before pushing

Code *(planned)*:

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest tests/unit tests/contract
uv run pytest tests/integration      # needs the running stack
```

Documentation:

```sh
python3 scripts/check_ids.py
npx markdownlint-cli2
```

CI runs the same checks: [`docs.yml`](.github/workflows/docs.yml) for documentation, a code workflow added with the skeleton, and [`codeql.yml`](.github/workflows/codeql.yml) for security scanning.

## Code conventions

- **Structure:** follow the package layout and the dependency rule above.
- **New infrastructure** goes behind a port in `application`, with an in-memory adapter for unit tests and a contract test suite in `tests/contract/`.
- **Configuration** comes only from environment variables, so the deployment stays portable to an orchestrator; every variable is documented in `.env.example` with its default.
- **Secrets** (signing secret, bootstrap password, the external answer provider's API key) are never committed, logged, stored in the database or returned by the API.
- **Logging:** no passwords, tokens, API keys or document text in logs.
- **Errors:** every error response uses the one JSON error format with code and message.
  An operation the Principal's role does not permit returns 403; a repository or document the Principal has no role for returns 404, so its existence is not disclosed.
- **Permission filter:** search and answers get their scope only from the access policy as a `RepositoryScope`; never add a query path without it.
- **Types:** all functions are type-annotated; `Any` and `type: ignore` need a comment with the reason.

## Tests

- A test that verifies an acceptance criterion names it in the form `test_ac_<story>_<criterion>_<description>`, so the criteria can be traced to tests.
- The permission tests for search and answers run in CI for every role and must never be skipped.
- Unit tests use in-memory adapters and need no running services; integration tests may assume the compose stack.

## Documentation conventions

- All documents are in English.
- **Where things go:** requirements and acceptance criteria in [`requirements.md`](docs/requirements.md), scope and plan in [`mvp.md`](docs/mvp.md), the architecture overview in [`architecture.md`](docs/architecture.md), architectural decisions in `docs/adr/`.
  Each fact is written down in one place; other documents link to it instead of repeating it.
- **IDs** (US, REQ, NFR, AC, C, A, Q, ADR) are stable and never reused; every referenced ID must be defined (`check_ids.py`).
- **Architectural decisions** follow the conventions in `docs/adr/README.md`.
- **Behaviour changes** update the affected requirements, ADRs or docs in the same pull request.
- **AI usage:** significant AI-assisted work on requirements, architecture or code is recorded in [`ai-usage.md`](docs/ai-usage.md) with the prompt, a summary of the result and the team's assessment.

## Branches, commits and pull requests

- `main` holds the state that is handed in or released; `develop` is the integration branch.
- Work happens on short-lived branches from `develop` (e.g. `feature/upload-validation`, `docs/search-requirements`) and is merged into `develop` by pull request; `develop` is merged into `main` by pull request at a milestone.
- Commit messages start with a short summary in the imperative (e.g. "Run docs workflow on pushes to develop"), at most 72 characters.
- A pull request names the stories, requirements or decisions it implements or changes, and is merged only when CI passes.
