---
status: proposed
date: 2026-11-17
---

# Process documents with Docling in an isolated child process

## Context and Problem Statement

Workers must extract text from PDFs, including OCR for pages without a text layer, and split it into chunks with page references (REQ-ING-1, REQ-SRCH-3), entirely locally.
Constraint C-1 already chose Docling, and its known risk is that individual malformed PDFs can make the parser hang.
Processing must fail with status `failed`, the error message and the failed step when it exceeds a timeout, default 10 minutes (REQ-ING-3), and the worker must continue with the next document.
Which tool is used for extraction and chunking, and how is it run so that a hanging or crashing parse cannot block a worker?

## Decision Drivers

* OCR for scanned PDFs out of the box (REQ-ING-1, AC-5.5).
* Page number per chunk (REQ-SRCH-3).
* Local processing without external services.
* Enforceable timeout and memory limit per document; failed step recorded (REQ-ING-3).
* Processing time: 20 pages in 2 minutes (born-digital) and 5 minutes (scanned) on CPU (NFR-2).
* Further formats such as DOCX later.

## Considered Options

Extraction tool:

* Docling
* Unstructured (open-source library)
* Self-assembled pipeline: PyMuPDF for the text layer, OCRmyPDF/Tesseract for scanned pages, own chunker
* Apache Tika with Tesseract

Execution:

* In the worker process, with a timer
* In a reusable child process that is killed on timeout
* In a separate container per document

## Decision Outcome

Chosen options: "Docling" in "a reusable child process that is killed on timeout", because Docling covers OCR, layout, page provenance and chunking in one MIT-licensed library, and only a separate process can be reliably stopped when native code hangs.

Details:

* The worker's pipeline runner starts a child process (spawn) that loads Docling and its models once and then converts documents one at a time.
* For each document the parent waits at most the configured timeout; on expiry it kills the child, sets status `failed` with step `extract` and message "timeout", and starts a new child.
* The child is also restarted after a configurable number of documents and runs with a memory limit, to contain memory leaks.
* The child returns chunks with text, page numbers and headings; embedding and indexing run in the parent (steps `embed` and `index`).
* The failed step (`extract`, `chunk`, `embed`, `index`) and the error message are stored with the document (REQ-ING-3).
* The OCR engine used by Docling (e.g. EasyOCR, Tesseract or RapidOCR, languages German and English) is chosen in the spike based on NFR-2 and AC-5.5.

### Consequences

* Good, because one library covers extraction, OCR, layout and chunking, and later DOCX.
* Good, because a hanging or crashing parse costs at most the timeout and never blocks the worker.
* Good, because models are loaded once per child, not once per document.
* Bad, because Docling with OCR models has a high memory use per worker, which limits the number of workers on the reference host; it is measured in the spike.
* Bad, because OCR on CPU is slow; NFR-2's 5-minute limit for scanned documents must be verified.
* Bad, because Docling evolves quickly; the version must be pinned and upgrades tested against the evaluation set.

### Confirmation

* Test with a PDF that makes the parser hang (or a stub child that sleeps): the document becomes `failed` with step `extract` within timeout plus a small margin, and the worker processes the next document.
* AC-5.5 (word on the first page of a scanned PDF is found) runs in CI with a small scanned sample.
* NFR-2 timed run on the reference environment, results documented.
* The deployment runs with outbound internet blocked.

## Pros and Cons of the Options

### Docling

* Good, because OCR, layout analysis, tables, page provenance and chunkers are built in.
* Good, because it is MIT-licensed, runs locally and supports further formats.
* Bad, because of high memory use and the known hang risk with malformed PDFs.

### Unstructured

* Good, because it supports many formats and has chunking strategies.
* Neutral, because OCR relies on Tesseract and extra system packages.
* Bad, because some features are reserved for the hosted service, and page metadata per chunk is less precise.

### Self-assembled pipeline (PyMuPDF + OCRmyPDF/Tesseract)

* Good, because each part is fast, well understood and lightweight.
* Bad, because the team has to build page-wise OCR detection, layout handling and chunking with page references itself.
* Bad, because PyMuPDF is AGPL-licensed, which matters for redistribution.

### Apache Tika with Tesseract

* Good, because it is mature and supports many formats.
* Bad, because it is a Java service (extra container and runtime) and provides no chunking or page provenance per element.

### Execution in the worker process with a timer

* Good, because it is the simplest.
* Bad, because a hang in native code cannot be interrupted from Python, so the worker is blocked.

### Separate container per document

* Good, because it gives the strongest isolation.
* Bad, because container start-up and model loading per document cost too much time for NFR-2, and the worker would need access to the container runtime.

## More Information

* Replaces constraint C-1 and assumption A-5 in [`architecture.md`](../architecture.md).
* A `DocumentParser` interface hides Docling, so the self-assembled pipeline stays a fallback.
