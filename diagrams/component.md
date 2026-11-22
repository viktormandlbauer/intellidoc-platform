# Component diagrams

These C4 diagrams show the processing worker and the answer path in the API. See the [architecture overview](../docs/architecture.md#4-level-3--components).

## Processing worker

```mermaid
C4Component
  title Component diagram – processing worker

  ContainerQueue(mq, "Job queue", "RabbitMQ", "")
  Container_Boundary(worker, "Processing worker") {
    Component(consumer, "Job consumer", "AMQP client", "Prefetch 1, conditional claim; ack after final status or drop")
    Component(runner, "Pipeline runner", "Python", "One deadline for all steps (REQ-ING-3), records current step, fenced writes")
    Component(extract, "Extractor", "Docling in child process", "Text layer + OCR per page, layout")
    Component(chunker, "Chunker", "Docling", "Chunks with page reference")
    Component(indexer, "Indexer", "Python, SQL", "One transaction: lock doc, check active and attempt, replace chunks, set indexed")
    Component(sweep, "Recovery sweep", "Python, SQL", "Startup and periodic: expired lease → pending, or failed after repeated interruptions")
    Component(dlq, "Dead-letter consumer", "AMQP client", "Undeliverable job → failed, step deliver")
  }
  Container(embed, "Embedding service", "HTTP", "")
  ContainerDb(pg, "PostgreSQL", "pgvector", "")
  ContainerDb(s3, "RustFS", "", "")

  Rel(mq, consumer, "Job(document_id)", "AMQP")
  Rel(consumer, runner, "Runs")
  Rel(runner, pg, "pending → processing → indexed | failed", "SQL")
  Rel(runner, extract, "1. extract")
  Rel(extract, s3, "Reads original", "S3")
  Rel(runner, chunker, "2. chunk")
  Rel(runner, embed, "3. embed", "HTTP")
  Rel(runner, indexer, "4. index")
  Rel(indexer, pg, "Batch insert", "SQL")
  Rel(sweep, pg, "Reset or fail, outbox row", "SQL")
  Rel(mq, dlq, "Dead-lettered job", "AMQP")
  Rel(dlq, pg, "Set failed", "SQL")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Answer path in the API

Answers are orchestrated in the API, not in the answer model: retrieval goes through the same search component as `/search`, so the permission filter is applied in exactly one place (REQ-ANS-3). The answer model – local or external – only ever receives the question and passages the Principal may currently find. Which of the two is used is decided per request by the system-wide setting that only a Global Admin can change (REQ-ANS-5).

```mermaid
C4Component
  title Component diagram – answer path in the API

  Container_Boundary(api, "API") {
    Component(ep, "Answer endpoint", "FastAPI router", "Validates question (1–500 chars) and optional repository IDs")
    Component(ans, "Answer service", "Python", "Retrieve → check relevance → build prompt → select provider → generate → attach sources")
    Component(search, "Search component", "Python", "Same component as /search; one SQL hybrid query with ACL join")
    Component(prompt, "Prompt builder", "Python", "Numbered passages [1]…[k], token budget, instruction to answer only from passages and cite [n]")
    Component(cite, "Source mapper", "Python", "Maps [n] to document, repository and page; drops unknown markers")
    Component(sel, "Provider selector", "Python", "Reads the answer-provider setting on every request, no cache; external only if enabled by a Global Admin")
    Component(llmc, "AnswerModel interface", "HTTP client", "Connections from configuration (external API key as secret); timeout, max output tokens, concurrency limit")
  }
  ContainerDb(pg, "PostgreSQL", "pgvector", "")
  Container(embed, "Embedding service", "HTTP", "")
  Container(llm, "Answer model service", "HTTP", "Default")
  System_Ext(llmprov, "External LLM provider", "HTTPS", "If enabled")

  Rel(ep, ans, "Question, Principal")
  Rel(ans, search, "1. top-k passages for the same Principal")
  Rel(search, embed, "Embeds question", "HTTP")
  Rel(search, pg, "Hybrid query with ACL join", "SQL")
  Rel(ans, prompt, "2. passages above relevance threshold")
  Rel(ans, sel, "3. local or external?")
  Rel(sel, pg, "Answer-provider setting", "SQL")
  Rel(ans, llmc, "4. generate")
  Rel(llmc, llm, "Chat completion (setting local)", "HTTP")
  Rel(llmc, llmprov, "Chat completion (setting external)", "HTTPS")
  Rel(ans, cite, "5. answer text + passages")

  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```
