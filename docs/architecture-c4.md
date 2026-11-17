# Architecture – C4 Diagrams (Document API)

C4 views derived from `docs/requirements.md` and `docs/mvp.md`. Requirement IDs in labels point to the requirement a part serves.

Open decisions are shown as alternatives, not settled: the search engine (C-3: OpenSearch **or** PostgreSQL + pgvector) and the concrete embedding model (C-2). Parts that are Should only are marked *(S)*.

## 1. System Context

```mermaid
C4Context
    title System Context – Document API

    Person(operator, "Operator", "Deploys with docker compose, sets bootstrap credentials (US-1)")
    Person(gadmin, "Global Admin", "Manages users and repositories; Repo Admin rights everywhere")
    Person(radmin, "Repo Admin", "Manages members of a repository, deactivates documents, retries failed processing")
    Person(contrib, "Contributor", "Uploads PDFs, deactivates own documents")
    Person(reader, "Reader", "Lists, searches and downloads documents")

    System(docapi, "Document API", "Stores PDFs, processes them locally (extraction, OCR, chunking, embedding) and offers permission-safe hybrid search")

    System_Ext(script, "External system / script", "Uploads and searches with an API key bound to a user (US-12, S)")
    System_Ext(hub, "Model hub", "Source of OCR/layout and embedding models; downloaded once at install (NFR-5)")

    Rel(operator, docapi, "Starts, configures, bootstraps", "docker compose / CLI")
    Rel(gadmin, docapi, "Manages users, repositories, Repo Admins", "HTTPS/JSON")
    Rel(radmin, docapi, "Manages members, failed documents", "HTTPS/JSON")
    Rel(contrib, docapi, "Uploads, deactivates documents", "HTTPS/multipart")
    Rel(reader, docapi, "Lists, searches, downloads", "HTTPS/JSON")
    Rel(script, docapi, "Uploads, searches", "HTTPS + API key")
    Rel(docapi, hub, "Downloads models once", "HTTPS")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```

## 2. Containers

```mermaid
C4Container
    title Containers – Document API (single docker compose deployment)

    Person(user, "API user", "Global Admin, Repo Admin, Contributor or Reader")
    System_Ext(script, "External system / script", "API key (S)")
    Person(operator, "Operator", "")

    System_Boundary(sys, "Document API (docker compose, NFR-6)") {
        Container(proxy, "Reverse Proxy", "TLS termination", "TLS for all external traffic (NFR-4)")
        Container(api, "API Service", "Python, FastAPI", "Auth, access control, users, repositories, upload/list/download, search; OpenAPI + Swagger UI (NFR-8)")
        Container(worker, "Processing Worker", "Python, Docling + Tesseract", "Async extraction, OCR, chunking with page ref, embedding, indexing; timeout, idempotent (REQ-ING-1..4)")
        Container(cli, "Bootstrap CLI", "Python", "Creates the first Global Admin if none exists (REQ-USR-1)")
        Container(embed, "Embedding Model", "Local multilingual model (C-2)", "Embeds chunks and queries; no content leaves the system (NFR-5)")
        ContainerDb(index, "Search Index", "OpenSearch or PostgreSQL + pgvector (C-3)", "Chunks with page ref; keyword + vector index, filterable by repository ID")
        ContainerDb(db, "Metadata DB", "PostgreSQL", "Users, credential hashes, repositories, roles, document metadata, processing status")
        ContainerDb(files, "Original Store", "Docker volume", "Originals as uploaded, never modified (REQ-DOC-3)")
    }

    Rel(user, proxy, "Uses", "HTTPS")
    Rel(script, proxy, "Uses", "HTTPS + API key")
    Rel(operator, cli, "Runs at install")
    Rel(proxy, api, "Forwards", "HTTP")

    Rel(cli, db, "Creates Global Admin")
    Rel(api, db, "Roles per request (C-4), metadata")
    Rel(api, files, "Stores / streams originals")
    Rel(api, embed, "Embeds query")
    Rel(api, index, "Filtered hybrid query")

    Rel(worker, db, "Claims jobs, sets status")
    Rel(worker, files, "Reads originals")
    Rel(worker, embed, "Embeds chunks")
    Rel(worker, index, "Replaces chunks")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```

## 3. Components – API Service

```mermaid
C4Component
    title Components – API Service

    Person(user, "API user", "Any role, via token or API key")

    Container_Boundary(api, "API Service (FastAPI)") {
        Component(auth, "Authentication", "Login, tokens, API keys (S)", "Signed, expiring tokens; 401 for unknown or deactivated principals (REQ-AUT-1..3, REQ-USR-4)")
        Component(acl, "Access Resolver", "Request dependency", "Loads current roles on every request; 403 vs 404 rules; Global Admin override (REQ-ACL-3..6)")
        Component(users, "Users", "Router", "CRUD + deactivate users; last-admin guard (REQ-USR-2..5)")
        Component(repos, "Repositories & Members", "Router", "Repositories, deactivation (S), role grants (REQ-REP-1..4, REQ-ACL-1..2)")
        Component(docs, "Documents", "Router", "Upload (content-based PDF check, size limit), list, download, deactivate (REQ-DOC-1..8)")
        Component(proc, "Processing Admin", "Router (S)", "List failed documents, restart processing (REQ-ING-5..6)")
        Component(search, "Search", "Router + service", "Hybrid keyword + semantic ranking over permitted, active, indexed documents (REQ-SRCH-1..5, REQ-ACL-5)")
    }

    ContainerDb(db, "Metadata DB", "PostgreSQL")
    ContainerDb(files, "Original Store", "Docker volume")
    ContainerDb(index, "Search Index", "OpenSearch or pgvector")
    Container(embed, "Embedding Model", "Local model")

    Rel(user, auth, "Requests", "HTTPS")
    Rel(auth, acl, "Principal")
    Rel(acl, users, "Authorized request")
    Rel(acl, repos, "Authorized request")
    Rel(acl, docs, "Authorized request")
    Rel(acl, proc, "Authorized request")
    Rel(acl, search, "Permitted repository IDs")

    Rel(auth, db, "Credentials, user state")
    Rel(acl, db, "Roles, repo/doc state")
    Rel(users, db, "Users")
    Rel(repos, db, "Repos, roles")
    Rel(docs, db, "Metadata, status")
    Rel(proc, db, "Reset to pending")
    Rel(docs, files, "Originals")
    Rel(search, embed, "Query vector")
    Rel(search, index, "Filtered query")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## 4. Components – Processing Worker

```mermaid
C4Component
    title Components – Processing Worker

    Container_Boundary(worker, "Processing Worker") {
        Component(runner, "Job Runner", "Python", "Claims pending documents, enforces per-document timeout, re-queues stuck jobs after restart (REQ-ING-3, NFR-7 S)")
        Component(extract, "Extractor", "Docling + Tesseract", "Text and layout extraction; OCR for pages without text layer (REQ-ING-1, C-1)")
        Component(chunk, "Chunker", "Docling chunker", "Splits text into chunks with page provenance (REQ-SRCH-3)")
        Component(embedder, "Embedder", "Client", "Requests chunk embeddings")
        Component(indexer, "Indexer", "Client", "Deletes and rewrites all chunks of a document, idempotent (REQ-ING-4)")
    }

    ContainerDb(db, "Metadata DB", "PostgreSQL")
    ContainerDb(files, "Original Store", "Docker volume")
    ContainerDb(index, "Search Index", "OpenSearch or pgvector")
    Container(embed, "Embedding Model", "Local model")

    Rel(runner, db, "Claims job; sets processing / indexed / failed + error and step")
    Rel(runner, extract, "Starts pipeline")
    Rel(extract, files, "Reads original")
    Rel(extract, chunk, "Document model")
    Rel(chunk, embedder, "Chunks")
    Rel(embedder, embed, "Embeds")
    Rel(embedder, indexer, "Chunks + vectors")
    Rel(indexer, index, "Replaces chunks of document")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```
