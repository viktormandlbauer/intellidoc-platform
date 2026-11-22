---
status: proposed
date: 2026-11-17
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
* Few additional containers and little memory on the reference host (Q-2).

## Considered Options

* RabbitMQ with a transactional outbox in PostgreSQL
* RabbitMQ, publishing directly after the database commit
* PostgreSQL job table, claimed with `SELECT … FOR UPDATE SKIP LOCKED`
* Redis (Streams or Celery with Redis broker)
* NATS JetStream

## Decision Outcome

Chosen option: "RabbitMQ with a transactional outbox in PostgreSQL", because it combines atomic job creation with a broker that redelivers unacknowledged jobs, and RabbitMQ is the most widely documented option for work queues in Python.

Details:

* **Outbox:** the upload use case inserts the document (`pending`) and an outbox row in one transaction.
  A relay in the API process publishes outbox rows to RabbitMQ with publisher confirms and marks them published.
  Retry (`failed → pending`, REQ-ING-6) and recovery (`processing → pending`) also write an outbox row in the same transaction as the status change.
* **Queue:** one durable queue `document.process`, persistent messages with `{document_id, job_id}`; a dead-letter queue receives messages after a configurable number of redeliveries, and the document is set to `failed`.
* **Consumer:** prefetch 1; the message is acknowledged only after the final status (`indexed` or `failed`) is committed.
  The broker's consumer timeout is set above the processing timeout of REQ-ING-3.
* **Delivery guarantee:** at least once.
  The worker claims a document with a conditional update that increments `processing_attempt` and sets status `processing`; it writes chunks and the final status only if its attempt number is still current (fencing).
  Duplicates without the redelivered flag for a document already in `processing` are acknowledged and dropped.
* **Recovery sweep:** at worker startup and periodically, documents in `processing` whose lease (`processing_started_at` + timeout) has expired are set back to `pending` with a new outbox row (NFR-7).

### Consequences

* Good, because no job is lost if the API or the broker is unavailable at upload time; the relay catches up.
* Good, because a stopped worker's job is redelivered by the broker without manual action.
* Good, because the fencing number makes concurrent processing of the same document harmless.
* Bad, because RabbitMQ is an additional container with its own memory use.
* Bad, because the outbox relay adds up to one polling interval of delay before processing starts.
* Bad, because the team must understand at-least-once delivery; idempotency is mandatory in every step.

### Confirmation

* Test: the API is killed after commit but before publishing; after restart the document is processed.
* Test: a worker is killed during processing; the document reaches `indexed` or `failed` after restart (NFR-7).
* Test: the same job is delivered twice; the document has exactly one set of chunks (REQ-ING-4).
* Status transitions outside REQ-ING-2 are rejected by the domain model (unit test).

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

* If the reference host runs short of memory (Q-2), the PostgreSQL job table is the fallback; the `JobPublisher` interface and the job consumer are the only code to change.
