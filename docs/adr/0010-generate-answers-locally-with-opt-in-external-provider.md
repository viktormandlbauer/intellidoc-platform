---
status: proposed
date: 2026-11-21
---

# Generate answers with a local language model and an opt-in external provider

## Context and Problem Statement

Readers ask questions and get a generated answer with page-level sources, based only on passages they may currently find (US-13, REQ-ANS-1 to REQ-ANS-4).
Answer generation needs a language model.
A local model on the CPU-only reference host is free and keeps all data on the server, but it is slow on CPU and needs memory that OCR, embedding and search also need (NFR-9, Q-2).
Hosted providers such as Scaleway Generative APIs or Mistral AI are fast and need no local memory, but the passages used for an answer would leave the company server.
Whether that is acceptable is a decision of the organisation, so a Global Admin enables or disables an external provider for the whole system (US-16, REQ-ANS-5).
Which language model generates answers, how is it integrated, and how is the external provider switched on and off?

## Decision Drivers

* Answers use only passages the Principal may currently find, and cite them (REQ-ANS-2, REQ-ANS-3, AC-13.3).
* No answer is generated without evidence (REQ-ANS-4).
* Answer time P95 ≤ 30 s for a single user (NFR-9).
* Documents and derived data stay on the company server; Must features work without external paid services and without outbound traffic in the default configuration.
* Sending passages to an external provider is a conscious, system-wide decision of a Global Admin; it is off by default and can be revoked with immediate effect (REQ-ANS-5).
* The provider's API key never appears in the database, in API responses or in logs (NFR-4).
* Memory and CPU on the reference host, shared with OCR, embedding and search (Q-2, NFR-2).
* The model can be exchanged after the spike without code changes in the use case.

## Considered Options

Model:

* Local model only
* Local model by default, external OpenAI-compatible provider as opt-in, for answer generation only
* External provider by default
* External provider for answer generation and embeddings (as in Scaleway's RAG tutorial)

Activation of the external provider:

* Configuration flag set by the operator, read at startup
* System-wide setting changed by a Global Admin through the API, with the provider connection configured by the operator
* System-wide setting and provider connection, including the API key, entered by a Global Admin through the API

## Decision Outcome

Chosen options: "Local model by default, external OpenAI-compatible provider as opt-in, for answer generation only", activated by "a system-wide setting changed by a Global Admin through the API, with the provider connection configured by the operator", because it keeps all data on the server by default, gives the decision to send passages out to the role responsible for the system, lets that decision be revoked without a restart, and keeps the provider's API key out of the database and the API.

Rules:

* **Orchestration in the API:** the answer use case retrieves passages through the search use case with the requesting Principal ([ADR-0005](0005-filter-search-by-repository-at-query-time.md)); there is no second retrieval path.
  The optional repository list can only narrow the scope.
* **No answer without evidence:** if no passage is above a relevance threshold (tuned with the evaluation set), the API states that no answer is available and does not call the model.
* **Prompt and sources:** at most k passages within a token budget, numbered `[1]…[k]`; the model is instructed to answer only from them and cite `[n]`.
  The response contains a source reference (document ID and name, repository ID and name, page) for every passage sent to the model, marks the cited ones and drops markers that refer to no passage.
* **One interface, one protocol:** the `AnswerModel` interface has one implementation for the OpenAI-compatible chat completions API, used for both the local model and the external provider.
  The local default is a llama.cpp server (or Ollama) with a small quantised open model in its own container.
* **Connection (operator):** base URL, model and API key of the external provider are deployment configuration; the API key is a secret that is never stored in the database, returned by the API or logged.
  Without a configured connection the external provider cannot be enabled.
* **Activation (Global Admin):** a system-wide setting `answer_provider` (`local` or `external`) is stored in PostgreSQL, default `local`.
  Only a Global Admin can change it (REQ-ANS-5); other Principals get 403, and enabling without a configured connection returns 409.
  Every change stores who made it and when, and is logged as a security-relevant event.
* **Effect per request:** the answer use case reads the setting on every request, without a cache, so a change takes effect with the next answer request, like the permission scope in [ADR-0005](0005-filter-search-by-repository-at-query-time.md).
  If the setting cannot be read, nothing is sent to the external provider (fail closed).
  The health/info endpoint shows the active provider.
* **Local container:** the local answer model service is part of the default deployment.
  An operator who uses only the external provider may leave it out; while the setting is `local`, answers then return 503.
* **What leaves the server:** while the external provider is enabled, per answer only the question and the selected passages, over TLS; never whole documents, vectors, metadata of other documents or credentials.
  Embeddings are always computed locally; no other feature calls the external provider.
* **Provider choice:** EU-hosted providers are preferred (Scaleway Generative APIs, Mistral AI); a provider counts as supported only if it passes the `AnswerModel` contract test suite.
* **Time and load bounds:** request timeout, cap on output tokens, and a concurrency limit in the API; excess or timed-out requests get 503 in the JSON error format.
* **No tools:** the model has no tool or database access; text in passages is treated as untrusted data.

### Consequences

* Good, because the default deployment keeps all data on the server and runs with outbound traffic blocked.
* Good, because answers inherit the permission filter of search instead of re-implementing it.
* Good, because switching between the local model and the external provider is a setting that a Global Admin changes at runtime, and switching between providers is configuration, not code.
* Good, because enabling needs both a configured connection (operator) and the setting (Global Admin), so no single configuration mistake sends passages out.
* Good, because an operator who uses the external provider permanently can leave out the local answer container, which frees its memory and the CPU time of generation.
* Bad, because with the local model on CPU only, answer time is the least predictable figure (NFR-9) and generation competes with OCR and embedding.
* Bad, because enabling sends passages to a third party, so a Global Admin must check the provider's data processing terms before enabling it, and a compromised Global Admin account can now also make passages leave the server.
* Bad, because the setting adds a settings table, an admin endpoint and one lookup per answer request.
* Bad, because "OpenAI-compatible" differs between providers in optional parameters, errors and rate limits, so each provider needs its own contract test run.
* Neutral, because if the model service or provider is unavailable, only answers fail (503); search, upload and download are unaffected.

### Confirmation

* AC-13.1 to AC-13.5 run as automated tests; for AC-13.3 a recording model adapter asserts that no passage outside the Principal's scope was sent.
* The default configuration runs with outbound internet blocked.
* Automated tests for REQ-ANS-5: the setting is `local` after installation; a Principal who is not a Global Admin gets 403; enabling without a configured connection returns 409; after a Global Admin disables the external provider, the next answer request sends nothing to it (recording adapter); the API key never appears in responses or logs.
* Spike (phase 2): the answer questions of the evaluation set run against two or three local models and once against Scaleway Generative APIs (test corpus only), measuring source correctness and answer time (NFR-9) while a worker is processing; the result decides the default model.
* The `AnswerModel` contract test suite runs against the local server and every supported provider.

## Pros and Cons of the Options

### Local model only

* Good, because no data ever leaves the server and there are no running costs.
* Bad, because organisations with slow hardware have no way to meet NFR-9.

### Local model by default, external provider as opt-in

* Good, because it combines local-only operation by default with a fast alternative.
* Bad, because two runtime modes must be tested.

### External provider by default

* Good, because answers are fast and the reference host needs less memory.
* Bad, because the default deployment would send passages to a third party and need outbound access, contradicting the README's promise of local operation.

### External provider for answers and embeddings

* Good, because it needs no local model at all and indexing is faster.
* Bad, because every chunk of every document is sent to the provider at indexing time, far beyond the passages of single answers.
* Bad, because the index would depend on the provider's embedding model, so changing providers forces a full reindex.

### Configuration flag set by the operator

* Good, because it is the simplest option: no endpoint and no stored state.
* Bad, because the decision lies with whoever edits the deployment rather than with the Global Admin who is responsible for the system's data (README target group).
* Bad, because changing it, including switching it off in an emergency, needs a restart.

### Setting changed by a Global Admin, connection configured by the operator

* Good, because the decision is made, visible and revocable in the application by the responsible role, with effect on the next request.
* Good, because the API key stays a deployment secret.
* Neutral, because enabling needs both roles, which is slower but acts as a second check.

### Setting and connection entered by a Global Admin

* Good, because no deployment change is needed.
* Bad, because the API key would be stored in the database and handled by the API, which needs encryption at rest that NFR-4 does not cover.
* Bad, because a Global Admin could direct passages to any URL, not only to a provider the operator has approved.

## More Information

* Replaces constraint C-5 in [`architecture.md`](../architecture.md).
* Before enabling an external provider, the Global Admin checks the provider's data processing agreement, data retention and whether inputs are used for training.
* Scaleway's tutorial "Implementing Retrieval-Augmented Generation (RAG) with LangChain and Scaleway Generative APIs" uses the same chat completions call (`ChatOpenAI` with Scaleway's base URL); its ingestion part (remote embeddings, managed database, no access control) is not adopted.
