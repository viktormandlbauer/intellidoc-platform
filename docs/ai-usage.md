# AI Usage in Requirements Engineering

This document records where AI was used in phase 1, with the prompts, the results and our critical assessment. Responsibility for the requirements lies with the team; AI output was treated as a proposal, not as a decision.

**Tool:** Claude (Anthropic), chat interface, November 2026.

> Sections marked **[Team assessment]** must be completed by the team. The bullets beneath them are notes on what to check, not a finished assessment.

## Overview

| # | AI application | Input | Output | Adopted? |
|---|---|---|---|---|
| 1 | Review of a draft for gaps, contradictions and MVP suitability | First requirements draft (v0) | List of gaps, contradictions, untestable requirements, scope proposal | Mostly; see 1.4 |
| 2 | Validation against the course specification (Vorgabe) | Draft v0 + course specification | Gap analysis per criterion, MoSCoW proposal, sample story with acceptance criteria | Mostly; see 2.4 |
| 3 | Generating the reduced specification (stories, acceptance criteria, NFRs, MVP) | Drafts + decision "use Docling" | `requirements.md`, `mvp.md`, this file (draft) | Reviewed and edited; see 3.4 |

## 1. Review of the first draft

### 1.1 Prompt
```
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
```
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
- Added sections 1 (conventions, MoSCoW), 3 (stories + acceptance criteria), 5 (NFRs) and 7 (Won't list) in `requirements.md`.
- Moved technology to section 6 as constraints with reasons.
- Added the cost table in `mvp.md`.

### 2.4 [Team assessment]
- The AI judged a semester scope without knowing our team size and experience. *Is the Must list realistic for our team?*
- Was any AI criticism a matter of taste rather than a real defect?

## 3. Generating the reduced specification

### 3.1 Prompt
```
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
| Reference environment | 8 cores, 16 GB, no GPU, 1,000 PDFs | Must match the hardware we can actually use (Q-2) |
| REQ-ACL-3 | 404 instead of 403 without a role | Design choice (hides existence vs. clearer errors) |
| REQ-AUT-1 | Token lifetime 60 min | Assumption |
| REQ-DOC-1 | Max. 50 MB | Assumption |
| REQ-SRCH-5 | DE+EN as Should | Depends on the target documents (Q-1) |
| Stories US-1…US-15 | Generated from the requirements | Check that they reflect real needs of our target group, not just the existing requirements reworded |

### 3.4 [Team assessment]
- Which stories did we rewrite, merge or drop, and why?
- Which numbers in 3.3 did we confirm or change?
- Are the acceptance criteria executable as automated tests in our stack?

## 4. Lessons learned [Team]
- Where did AI help most (e.g. finding inconsistencies quickly, structuring)?
- Where was it weak (e.g. no domain knowledge, invented numbers, judging the scope without knowing the team)?
- What would we do differently in the next phase?
