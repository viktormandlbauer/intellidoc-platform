---
status: proposed
date: 2026-11-21
---

# Store originals in RustFS

## Context and Problem Statement

Uploaded PDF originals must be stored on the company server, streamed to users on download and read by the processing workers ([ADR-0001](0001-use-api-worker-pool-and-postgresql-search.md)).
Stored data must survive restarts, and the deployment should stay portable to an orchestrator such as Kubernetes (assumption A-7).
Which store holds the originals?

## Decision Drivers

* Shared access from API and worker containers, also on an orchestrator such as Kubernetes (A-7).
* Self-hosted, free, permissive licence (`mvp.md` §6).
* Low resource and operational overhead.

## Considered Options

* RustFS (S3-compatible, Apache-2.0)
* MinIO (S3-compatible)
* Shared filesystem volume

## Decision Outcome

Chosen option: "RustFS", because it offers the S3 API that works the same on a single host and on Kubernetes, under a permissive licence.

The code uses only basic S3 operations (put, get with streaming, head, delete) through an `ObjectStore` interface, so any S3-compatible store or the filesystem can replace RustFS by configuration.

### Consequences

* Good, because API and workers access originals over the network without a shared volume.
* Good, because the Apache-2.0 licence has no copyleft obligations for the deployment.
* Bad, because RustFS is a younger project than MinIO, with less operational track record; compatibility is secured by the contract test suite, not by reputation.

### Confirmation

* The `ObjectStore` contract test suite runs against RustFS in CI, including a streamed download of a large PDF.
* Originals survive `docker compose down && docker compose up`.

## Pros and Cons of the Options

### RustFS

* Good, because it is S3-compatible, lightweight and Apache-2.0 licensed.
* Bad, because it is young; features beyond basic object operations may differ from Amazon S3.

### MinIO

* Good, because it is the most widely used self-hosted S3-compatible store.
* Bad, because the community edition is AGPL-3.0 licensed and its distribution and feature scope have been reduced; this must be re-checked if MinIO is reconsidered.

### Shared filesystem volume

* Good, because it is the simplest option on a single host.
* Bad, because on Kubernetes it needs a volume that several pods can write to, which is not available everywhere.

## More Information

* Garage or SeaweedFS are further S3-compatible alternatives if RustFS fails the contract tests.
