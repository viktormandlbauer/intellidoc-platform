# AI Usage in Requirements Engineering and Architecture

This document records where AI was used in phase 1 (requirements) and phase 2 (architecture), with the prompts, the results and our critical assessment. Responsibility for the requirements lies with the team; AI output was treated as a proposal, not as a decision.

**Tool:** Claude (Anthropic), chat interface, November 2026.

> Sections marked **[Team assessment]** must be completed by the team. The bullets beneath them are notes on what to check, not a finished assessment.

## Overview

| # | AI application | Input | Output | Adopted? |
|---|---|---|---|---|
| 1 | Review of a draft for gaps, contradictions and MVP suitability | First requirements draft (v0) | List of gaps, contradictions, untestable requirements, scope proposal | Mostly; see 1.4 |
| 2 | Validation against the course specification (Vorgabe) | Draft v0 + course specification | Gap analysis per criterion, MoSCoW proposal, sample story with acceptance criteria | Mostly; see 2.4 |
| 3 | Generating the reduced specification (stories, acceptance criteria, NFRs, MVP) | Drafts + decision "use Docling" | `requirements.md`, `mvp.md`, this file (draft) | Reviewed and edited; see 3.4 |
| 4 | Candidate architectures and ADRs (phase 2) | `requirements.md`, `mvp.md` | `architecture.md`, ADR-0001…0008 | *To be completed*; see 4.4 |
| 5 | Consistency review of requirements, MVP, architecture and ADRs | All documents in `docs/` | List of contradictions and gaps; fixes to test data, 403/404 criteria, demo steps and cross-references | *To be completed*; see 5.3 |
| 6 | Coherence review after the switch to PostgreSQL search, and resulting changes | All documents in `docs/`, README | List of contradictions and stale rationale; external answer provider enabled by a Global Admin; ADR-0003 and ADR-0006 merged | *To be completed*; see 6.3 |
| 7 | Pre-implementation review and relaxed NFR targets | Whole repository | List of open points before implementation; relaxed NFR targets; small cleanups | *To be completed*; see 7.3 |
| 8 | Resolving the design gaps found in 7 | Whole repository | Rules for job lifecycle, timeout, search result contract, answer relevance and upload; ADR-0012; requirement changes | *To be completed*; see 8.3 |

## 1. Review of the first draft

### 1.1 Prompt

```text
[requirements draft v0 attached]
Check these requirements. Are they suitable for an mvp?
```

### 1.2 Result (summary)

- **Dangling references:** REQ-VIEW-6, generated answers, classification and the review workflow were referenced but never specified; the Reviewer role had no permissions; numbering gaps (ACL-5, SRCH-4, ING-1).
- **Untestable wording:** "reliably" and "N = TBD" (SRCH-3), "found even with synonyms" (SRCH-2), "pluggable" (AUT-5), "extensible" (DOC-10).
- **Contradictions:**
  - The irreversible replace operation clashes with the archiving purpose.
  - Replace vs. "only indexed documents are searchable".
  - Unclear whether issued tokens survive user deactivation.
- **Missing operations:**
  - list my repositories
  - list members
  - password change
  - pagination
  - upload limits
  - OCR for scanned PDFs
  - protection of the last Global Admin
- **No NFRs** at all.
- **Scope proposal:** defer archiving, classification/review, replace and answers.

### 1.3 What we changed because of it

- Added REQ-REP-3, the member listing in REQ-ACL-2, REQ-USR-3 (last Global Admin), REQ-USR-4 (tokens rejected), REQ-DOC-1 (size limit) and OCR in REQ-ING-1.
- Replaced vague wording with measurable criteria (REQ-SRCH-4 + NFR-3).
- Moved "pluggable" and "extensible" out of the requirements.

### 1.4 [Team assessment]

- Was the AI right that archiving is optional? *Check against our problem statement: if long-term archiving were our core problem, the cut would be wrong.*
- Did the AI miss anything we know from the domain?
- Did we deliberately reject any AI suggestion? Document it here with the reason.

## 2. Validation against the course specification

### 2.1 Prompt

```text
Check against the following Vorgabe:
[full text of the course specification: goals, quality requirements, deliverables, typical mistakes, assessment criteria, definition of done]
```

### 2.2 Result (summary)

- **Hard failures:**
  - no user stories included (only some referenced)
  - no acceptance criteria
  - no NFRs
  - no prioritisation
  - no MVP boundary
- **"Typical mistakes" hit:** technology names inside requirements (BM25/kNN, Gotenberg, LibreOffice, veraPDF) and a scope too large for a semester.
- **Missing cost consideration** for external models.
- **Proposed MoSCoW split** and one sample story with Given/When/Then criteria.

### 2.3 What we changed because of it

- Added conventions (MoSCoW), stories + acceptance criteria and NFRs to `requirements.md`, and a Won't list (now in `mvp.md`).
- Moved technology out of the requirements into constraints with reasons (now in `architecture.md`).
- Added the cost table in `mvp.md`.

### 2.4 [Team assessment]

- The AI judged a semester scope without knowing our team size and experience. *Is the Must list realistic for our team?*
- Was any AI criticism a matter of taste rather than a real defect?

## 3. Generating the reduced specification

### 3.1 Prompt

```text
Reduce and adapt the requirements accordingly. The MVP could just use Docling.
```

Follow-up: `[asked for the remaining deliverables mvp.md, ai-usage.md, README.md]`

### 3.2 Result (summary)

- Rewrote `requirements.md`:
  - 15 user stories (9 Must, 3 Should, 3 Could)
  - Given/When/Then criteria for every Must story, with shared test data
  - functional requirements renumbered without gaps
  - 8 NFRs with a reference environment and test method
  - Docling as constraint C-1
  - Won't list with reasons
  - open questions
- Roles simplified to a hierarchy (Reader ⊂ Contributor ⊂ Repo Admin) after the Reviewer role was dropped.
- New REQ-ING-3 processing timeout, motivated by a web source reporting a PDF on which Docling's parser hung.
- **Renumbering:** IDs in v1 do not match v0. Example: v0 REQ-ACL-6/7/8 → v1 REQ-ACL-5/6 (the old ACL-7 about answers was moved to Could/US-13).

### 3.3 Decisions made by the AI that need human validation

These are plausible but **not verified** and must be confirmed or changed by the team:

| Item | AI choice | Why it needs checking |
|---|---|---|
| NFR-1 | P95 ≤ 2 s, 5 concurrent users | Assumed; depends on hardware and the chosen engine |
| NFR-2 | 2 min / 5 min per 20 pages | Based on one public benchmark of Docling on CPU (about 3 s/page for a scanned document); our hardware may differ |
| NFR-3 | Recall@10 ≥ 0.8, exact term ≥ 95 % | Target values are a guess; calibrate after a first baseline |
| Reference environment | 8 cores, 16 GB, no GPU, 1,000 PDFs | Hardware assumptions were still open at this stage |
| REQ-ACL-3 | 404 instead of 403 without a role | Design choice (hides existence vs. clearer errors) |
| REQ-AUT-1 | Token lifetime 60 min | Assumption |
| REQ-DOC-1 | Max. 50 MB | Assumption |
| REQ-SRCH-5 | DE+EN as Should | Depends on the target documents (Q-1) |
| Stories US-1…US-13 | Generated from the requirements | Check that they reflect real needs of our target group, not just the existing requirements reworded. Two further Could stories (replace content, DOCX upload) were generated and later dropped |

### 3.4 [Team assessment]

- Which stories did we rewrite, merge or drop, and why?
- Which numbers in 3.3 did we confirm or change?
- Are the acceptance criteria executable as automated tests in our stack?

## 4. Candidate architectures and ADRs (phase 2)

### 4.1 Prompt

```text
[to be filled in by the team: the prompts used to create architecture.md and the ADRs]
```

### 4.2 Result (summary)

- `architecture.md`: three candidate designs (A – modular monolith on PostgreSQL, B – API with worker pool and dedicated search engine, C – event-driven microservices) as C4 diagrams on levels 1–3, a comparison against the requirements and a recommendation for B with an early evaluation proposal.
- ADR-0001…0008 (overall structure, Python/FastAPI, ports and adapters, authentication, query-time permission filter, index visibility, job delivery, Docling execution), all `proposed`.

### 4.3 Decisions made by the AI that need human validation

| Item | AI choice | Why it needs checking |
|---|---|---|
| Memory estimates | A ≈ 7–9 GB, B ≈ 11–13 GB, C ≈ 13–15 GB | Early estimates under the original fixed-host assumption |
| ADR-0001 | Design B | Initially depended on the proposed evaluation and the team's experience with OpenSearch and RabbitMQ |
| ADR-0007 | RabbitMQ with outbox instead of a PostgreSQL job table | Adds a container and the outbox relay; the simpler job table is the fallback |
| ADR-0003 (later merged into ADR-0002) | Ports and adapters | More boilerplate; check that the team will keep the dependency rule |

### 4.4 [Team assessment]

- Which options did we reject or change, and why?
- Are the considered options in each ADR the real alternatives, or were any added only for completeness?

## 5. Consistency review (phase 2)

### 5.1 Prompt

```text
Review the current requirement and adr docs and check if the repo is clear
```

Follow-ups: `Fix section 1 and 3` (the contradictions and the outdated cross-references from the review), then `make intellidoc-platform consistent` (the system name).

### 5.2 Result (summary)

- Restored the deleted test data for the acceptance criteria (`requirements.md` §3.2) and added the users and document state that the rewritten criteria rely on.
- Fixed contradictions: AC-3.3 and demo step 3 expected 403 where REQ-ACL-3 requires 404; in demo step 4, alice granted a role in R2 without having rights there.
- Shortened the entries in `architecture.md` §1 that duplicated ADRs and had started to drift from them; updated status lines, the dependency table and outdated references.
- Made the name consistent: the system was called "Document API" in the documents and `intellidoc` in ADR-0003; it is now "IntelliDoc Platform", with the distribution named `intellidoc-platform` and the Python package `intellidoc_platform`.
- Identified ADR gaps (reconciliation race in ADR-0006, since merged into ADR-0009; deactivation during processing; dead-letter handling), which are left for a team decision.

### 5.3 [Team assessment]

- Do we agree with the ADR gaps, and how do we resolve them?

## 6. Coherence review and revision (phase 2)

### 6.1 Prompt

```text
Review the docs of the project for coherence
```

Follow-up: `Update the architecture since opt-in external LLM provider is now a feature which should be enabled globally by an admin. The mentioned design comparison should only be mentioned shortly in ADR-0001. Remove or merge "rejected" ADRs for now; ADR-0003 was about the code architecture which would be ports and adapters (hexagonal).`

### 6.2 Result (summary)

- Review: contradictions (runtime outbound traffic vs. the external provider, who enables it, outdated pointers), rationale that went stale after the move to PostgreSQL search (ADR-0002, ADR-0007), and gaps in test data, NFR-3 and traceability.
- New Should story US-16 and REQ-ANS-5: a Global Admin enables or disables the external answer provider for the whole system; the operator only configures the connection. ADR-0010 and `architecture.md` were updated accordingly.
- ADR-0001 compares the system structures only briefly; the former option B′ (OpenSearch) is covered by ADR-0009.
- ADR-0003 (ports and adapters) was merged into ADR-0002, the rejected ADR-0006 into ADR-0009; both numbers stay unused.

### 6.3 [Team assessment]

- Is the split between operator (connection) and Global Admin (setting) what we want, or should a Global Admin also configure the provider?
- Is US-16 correctly a Should?
- Which of the remaining review findings do we fix, and how?

## 7. Pre-implementation review (phase 2)

### 7.1 Prompt

```text
Review the project. What should be addressed before i start implementing?
```

Follow-up: `NFRs can be reformulated so they arent that critical formulated. Also do the quick cleanups. No concrete versions yet`

### 7.2 Result (summary)

- Review: the proposed evaluation depends on the test corpus and evaluation set (Q-3); open design points in the search result contract (hits per chunk or document, total hit count, query language, relevance threshold for answers), the job lifecycle (claim rule vs. REQ-ING-2, deactivation during processing, dead-letter handling, timeout scope) and the upload path; small inconsistencies.
- NFRs relaxed:
  - corpus reduced from 1,000 to ≥ 200 PDFs
  - NFR-1 P95 from 2 s to 3 s, measured without concurrent processing
  - NFR-2 from a limit per PDF to an average (3 / 6 minutes) without timeouts
  - NFR-3 targets from 95 % / 0.8 to 90 % / 0.7
  - NFR-8 limited to errors generated by the API
  - NFR-9 P95 from 30 s to 60 s, measured without concurrent processing
  - the runs under concurrent processing are documented without a target
  - all targets are confirmed or adjusted once after the first baseline measurement
- Target values now appear only in `requirements.md`; ADRs and REQ-SRCH-4 refer to the NFR instead of repeating the number.
- Cleanups: stale reference to a removed NFR in `.gitignore`, duplicate PostgreSQL row in `mvp.md` §6, no concrete Python version in `CONTRIBUTING.md`.

### 7.3 [Team assessment]

- Are the relaxed targets still meaningful for the target group, or did we only make them easy to pass?
- Which of the open design points do we resolve before implementing, and in which ADR?

## 8. Resolving the design gaps (phase 2)

### 8.1 Prompt

```text
Now focus on the design gaps
```

### 8.2 Result (summary)

- **Job lifecycle (ADR-0007):**
  - the claim only moves `pending → processing`; a redelivered message for a document in `processing` is dropped and the sweep recovers the document
  - fenced writes; a `recovery_count` limit fails documents that crash the worker repeatedly
  - inactive documents are never processed and their status is frozen
  - quorum queue with delivery limit; a dead-letter consumer sets `pending → failed` (step `deliver`)
  - the outbox relay claims rows with `SKIP LOCKED` in every API instance
- **Timeout and memory (ADR-0008):** one deadline per document for all steps; the parent kills the child above a resident-memory limit instead of using `RLIMIT_AS`.
- **Search contract (ADR-0009):**
  - one hit per document, ranked by its best chunk
  - capped candidates per sub-query, so the total hit count is the size of the returned list
  - minimum cosine similarity for vector candidates
  - per-chunk text-search configuration with no query language detection
  - separate query and passage embedding; the embedding model is stored per chunk
  - a separate passage operation for answers
- **Answer relevance (ADR-0010):** a passage is relevant only with an exact-term match or a cosine similarity above the answer threshold.
- **Upload (new ADR-0012):** streaming into a temporary file with size limit and checksum, content validation, then object store, then document and outbox row in one transaction.
- **Migration job:** a one-shot job runs migrations and the bootstrap before the API and the workers (`architecture.md` §3, ADR-0004).
- **Requirements:**
  - REQ-SRCH-3 and the glossary: one hit per document; new AC-7.6
  - REQ-ACL-2: roles granted by username; a Repo Admin cannot change a Repo Admin's role
  - REQ-DOC-2: password-protected PDFs rejected
  - REQ-DOC-7: inactive documents not processed
  - REQ-ING-2: `pending → failed`
  - NFR-3: ≥ 5 unanswerable questions; new AC-13.7
  - NFR-7: three times the processing timeout

### 8.3 [Team assessment]

- Is one hit per document what our readers want, or do they need several passages per document in the result list?
- Is granting roles by username acceptable, given that it lets a Repo Admin find out whether a username exists?
- Are the default values (100 candidates per sub-query, 3 recoveries) plausible, and which of them need tuning?

## 9. Lessons learned [Team]

- Where did AI help most (e.g. finding inconsistencies quickly, structuring)?
- Where was it weak (e.g. no domain knowledge, invented numbers, judging the scope without knowing the team)?
- What would we do differently in the next phase?
