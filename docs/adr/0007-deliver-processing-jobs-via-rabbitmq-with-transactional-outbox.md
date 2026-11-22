---
status: proposed
date: 2026-11-22
---

# Deliver processing jobs via RabbitMQ with a transactional outbox

## Context and Problem Statement

Every upload must be processed asynchronously by a pool of workers (REQ-ING-1, [ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md)).
A job must not be lost if the API crashes between saving the document and publishing the job, and a document whose worker is stopped mid-processing must be processed again (NFR-7).
Retries of failed documents (REQ-ING-6) and the status transitions of REQ-ING-2 must work with the chosen mechanism.
How are processing jobs delivered from the API to the workers?

## Decision Drivers

* No lost jobs: saving the document and scheduling its processing are atomic.
* Recovery after a worker interruption (NFR-7) and idempotent reprocessing (REQ-ING-4).
* Workers scale horizontally and independently of the API (README goal).
* Allowed status transitions only (REQ-ING-2); timeout handling (REQ-ING-3).
* Operational effort from additional services.

## Considered Options

* RabbitMQ with a transactional outbox in PostgreSQL
* RabbitMQ, publishing directly after the database commit
* PostgreSQL job table, claimed with `SELECT … FOR UPDATE SKIP LOCKED`
* Redis (Streams or Celery with Redis broker)
* NATS JetStream

## Decision Outcome

Chosen option: "RabbitMQ with a transactional outbox in PostgreSQL", because it combines atomic job creation with a broker that redelivers unacknowledged jobs, and RabbitMQ is the most widely documented option for work queues in Python.

Details:

* **Outbox:** the upload use case inserts the document (`pending`) and an outbox row in one transaction, after the original is stored ([ADR-0012](0012-validate-uploads-before-storing-original-and-metadata.md)).
  A relay publishes outbox rows to RabbitMQ with publisher confirms and marks them published.
  The relay runs in every API instance and claims rows with `SELECT … FOR UPDATE SKIP LOCKED`, so instances do not publish the same row concurrently; a crash between publishing and marking produces a duplicate message, which the claim below absorbs.
  Retry (`failed → pending`, REQ-ING-6) and recovery (`processing → pending`) also write an outbox row in the same transaction as the status change.
* **Queue:** one durable quorum queue `document.process` with persistent messages `{document_id}`.
  Its delivery limit (configurable) dead-letters a message that is redelivered too often without acknowledgement, e.g. because the worker crashes before it claims the document.
  A dead-letter consumer in the worker sets such a document to `failed` with step `deliver`, if it is still `pending` (REQ-ING-2).
* **Delivery guarantee:** at least once; every step below is safe to repeat.
* **Claim:** the worker claims a document with one conditional update that sets status `processing`, increments `processing_attempt`, sets `processing_started_at` and the current step `extract`, and succeeds only if the document and its repository are active and the status is `pending`.
  If no row is updated – another worker holds the document, it is already finished, or it is inactive – the message is acknowledged and dropped.
  A message redelivered after a worker crash therefore finds `processing` and is dropped; the document is recovered by the sweep, so the claim needs no transition other than `pending → processing`.
* **Deadline:** the processing timeout of REQ-ING-3 is one deadline per document, counted from `processing_started_at` and covering all steps ([ADR-0008](0008-process-documents-with-docling-in-isolated-child-process.md)).
  The pipeline runner records the current step (`extract`, `chunk`, `embed`, `index`) in the document row when the step starts, so a failure or interruption always has a step.
* **Fencing:** every later write of the worker (current step, chunks, status `indexed` or `failed`) is conditional on status `processing` and on `processing_attempt` still being the claimed number; writes of a stale worker change nothing.
* **Acknowledgement:** prefetch 1; the message is acknowledged after the final status is committed, or when it is dropped.
  The broker's consumer timeout is set above the processing timeout.
* **Recovery sweep:** at worker startup and periodically (interval configurable, well below the processing timeout), documents in `processing` whose lease (`processing_started_at` + timeout + a small margin) has expired are set back to `pending` with a new outbox row, and their `recovery_count` is incremented, in one transaction (NFR-7).
  When `recovery_count` reaches a configurable maximum (default 3), the document is set to `failed` instead, with the recorded step and the message "processing interrupted repeatedly", so a document that crashes the worker every time cannot loop forever.
  Upload and retry start with `recovery_count` 0; `processing_attempt` is never reset, because it is the fencing number.
  Sweeps in several workers may overlap; each reset is a conditional update and happens once.
* **Inactive documents:** claim, sweep and indexing ([ADR-0009](0009-use-postgresql-with-pgvector-as-search-index.md)) act only on active documents in active repositories (REQ-DOC-7).
  A document deactivated during processing is never set to `indexed`: the worker checks at each step boundary and at the latest in the indexing transaction, writes nothing, acknowledges the message and leaves the status unchanged.
  Reactivation is out of scope (`mvp.md` §5), so the status of an inactive document is frozen and is not shown by any endpoint.

### Consequences

* Good, because no job is lost if the API or the broker is unavailable at upload time; the relay catches up.
* Good, because a stopped worker's job is redelivered by the broker without manual action.
* Good, because the fencing number makes concurrent processing of the same document harmless.
* Bad, because RabbitMQ is an additional container with its own memory use.
* Bad, because the outbox relay adds up to one polling interval of delay before processing starts.
* Bad, because the team must understand at-least-once delivery; idempotency is mandatory in every step.
* Bad, because a document whose worker crashed waits until its lease has expired before it is processed again, i.e. up to the processing timeout; NFR-7 allows for this.

### Confirmation

* Test: the API is killed after commit but before publishing; after restart the document is processed.
* Test: a worker is killed during processing; the document reaches `indexed` or `failed` after restart (NFR-7).
* Test: the same job is delivered twice; the document has exactly one set of chunks (REQ-ING-4).
* Status transitions outside REQ-ING-2 are rejected by the domain model (unit test).
* Test: a stub parser that crashes the worker on every attempt leaves the document `failed` after the maximum number of recoveries, with the recorded step.
* Test: a document deactivated while it is processed never becomes searchable, and its message is acknowledged.
* Test: a message that reaches the delivery limit before any claim sets its `pending` document to `failed` with step `deliver`.

## Pros and Cons of the Options

### RabbitMQ with transactional outbox

* Good, because job creation is atomic with the document insert.
* Good, because redelivery, dead-lettering and work distribution are handled by the broker.
* Bad, because it needs a broker and an outbox relay.

### RabbitMQ, publishing directly after commit

* Good, because it is simpler and has no polling delay.
* Bad, because a crash between commit and publish leaves the document in `pending` forever; a sweep would be needed, which is a hidden outbox.

### PostgreSQL job table with `SKIP LOCKED`

* Good, because it needs no extra container, and job creation is trivially atomic.
* Good, because it is a proven pattern at this scale.
* Bad, because workers poll the metadata database, which couples processing load to the database that search and the API depend on.
* Bad, because redelivery, leases and dead-lettering must be built by hand.

### Redis

* Good, because Celery is popular and Redis is lightweight.
* Bad, because Redis persistence is weaker for durable work queues, and Celery's acknowledgement semantics need careful configuration (`acks_late`).
* Bad, because it still needs an outbox for atomicity.

### NATS JetStream

* Good, because it is lightweight and supports durable consumers and redelivery.
* Neutral, because it would also fit a later move to event-driven services (Architecture C).
* Bad, because the Python ecosystem and documentation for work queues are smaller than for RabbitMQ.

## More Information

* A PostgreSQL job table remains an alternative if operating a separate broker is impractical.
