# AI ARCHITECTURE — propose, verify, degrade

How AI is used in MAHA-GR-ALIGN, why it is safe to use it in a legal domain, and how that
safety becomes a *demo feature* rather than a hidden implementation detail.

Read `CLAUDE.md` for domain rules and `DESIGN.md` for the deterministic layers. This file
supersedes the old reading of rule 4 ("LLMs only for obligation extraction and draft
generation"), which was too narrow. Rule 4's *intent* — never let a model assert a fact we
could have computed — is preserved and made mechanical below.

---

## 1. The thesis

> **The model proposes. A deterministic layer verifies against the corpus. Nothing unverified
> reaches the user, and what fails verification is shown as a failure rather than hidden.**

The domain forces this. A hallucinated legal citation is not a bug, it is a credibility
death sentence — tell a Deputy Secretary that GR X supersedes GR Y when it does not and the
system is a liability. So the honest options are "no AI" or "AI whose every claim is
machine-checked." The first is what this project was doing and it is the wrong answer at an AI
hackathon. The second is strictly better *and* a stronger pitch:

| most submissions | this one |
| --- | --- |
| "our model answers questions about GRs" | "our model proposes findings; the corpus adjudicates them" |
| trust the demo | trust is unnecessary — check the evidence |
| hallucinations are a caveat in the Q&A | hallucinations are **a number on a slide** (§7.8) |

The asymmetry to exploit: **verification is cheap and generation is expensive.** Deciding
whether a quoted Marathi sentence really occurs in GR `2018...08` is a string search. Deciding
what that sentence *means* is not. So let the model do meaning and let the corpus do truth.

---

## 2. The verification contract

Every AI-produced claim passes six gates before display. Implemented once in `ai/verify.py`,
applied uniformly, and each gate is a pure function of (claim, corpus) with no model in it.

| gate | rule | catches |
| --- | --- | --- |
| **G1 Grounding** | every quoted span must occur **verbatim** in the cited source document, after whitespace/punctuation normalisation | invented quotes, paraphrase presented as quotation |
| **G2 Referential** | every `uid` must exist in the index; every citation must resolve through the **deterministic resolver**, not the model | invented GRs — the classic failure, and the fatal one here |
| **G3 Closed vocabulary** | every type/label must be in an enum (`REFERENCES`/`AMENDS`/`SUPERSEDES`; conflict classes; lint codes) | freelanced categories that break downstream consumers |
| **G4 Numeric** | every number asserted must appear in the source text, digit-normalised across Devanagari and ASCII | amounts drifting by a factor of 1000 — a measured pathology in this corpus |
| **G5 Temporal** | no supersession pointing forward in time beyond the ±3d publication-drift window; dates consistent with uid prefixes | chains that violate causality |
| **G6 Determinism** | temperature 0 and cached; a re-run that disagrees downgrades the claim | silent nondeterminism in a legal artefact |

**Three outcomes, all recorded:**

- `VERIFIED` — passed every applicable gate. Displayed normally, with its evidence.
- `FLAGGED` — passed G2/G3/G5 but soft-failed grounding or numerics. Displayed **with a
  warning badge** and the specific gate named.
- `REJECTED` — failed a hard gate. **Never displayed as a finding**, but counted and browsable
  in the Trust Ledger, with the gate that killed it.

Rejections are logged to `out/ai_rejections.json` with claim, gate, and cache key. That file is
the evidence base for §7.8 and it is the most persuasive artefact in the project, because it is
the one thing no competing team will be able to produce.

### Why this is not circular

The model never sees the answer key. Edge typing gets the *sentence* and must name the cited
GR; the resolver — which never calls a model — decides whether that GR exists and which uid it
is. Conflict adjudication gets two documents and must quote from both; grounding decides whether
those quotes are real. **The verifier's inputs are the corpus and the claim, never the model's
reasoning.** Cross-language checking already in `resolver.py` follows the same principle: value
comes from uncorrelated failure modes, not from a second opinion by the same mechanism.

---

## 3. Where AI is load-bearing

Not bolted on. Each of these is a place the deterministic approach **provably failed or cannot
reach**, with the measurement that proves it.

### 3.1 Edge typing — `[MEASURED]` regex demonstrably insufficient

`DESIGN.md` §3.3: of 40 cue-bearing Marathi sentences, only 11 (28%) contain a citation, and
inspection showed `सुधारणा` and `पुढे चालू` occurring **inside file numbers and section codes**
(`वित्तीय सुधारणा-१` = "Financial Reforms-1"). Cue matching cannot distinguish *"this order is
hereby cancelled"* from *"file no. Financial-Reforms-1"*. That is a semantic distinction.

- **Capability:** Multilingual + Reasoning, JSON out
- **Input:** one Marathi sentence + the citations the resolver already found in it
- **Output:** `{type, cited_ref_index, evidence_span, confidence, rationale_mr}`
- **Guardrails:** G1 (span verbatim), G2 (target must resolve deterministically), G3 (three
  types only), G5 (no forward supersession), G6
- **Degradation:** falls back to `REFERENCES`. An untyped edge is honest; a wrongly-typed one
  corrupts the audit, chains, and blast radius simultaneously.

### 3.2 Obligation extraction — no regex reaches this

"Who must do what, by when, under what condition, for how much" is the unit conflict detection
compares. It is prose. There is no pattern.

- **Capability:** Multilingual + Reasoning
- **Output:** the `obligation` contract already in `CLAUDE.md`
- **Guardrails:** G4 is the strong one — every amount and date must appear in the source, digits
  normalised across scripts. An obligation whose ₹ figure is not in the document is rejected
  outright.

### 3.3 Conflict adjudication — the marquee feature

Given two GRs both apparently in force, do they contradict? Requires reading both.

- **Capability:** Reasoning + Multilingual, long context
- **Input:** two obligation sets + the relevant paragraphs of both documents
- **Output:** `{verdict, class, quote_a, quote_b, explanation}` where `class ∈ {AMOUNT,
  ELIGIBILITY, EFFECTIVE_DATE, AUTHORITY, PROCEDURE}`
- **Guardrails:** G1 on **both** quotes, G2 (both live in the graph), G3, G4 (any contradictory
  figures must be real), G6
- **Candidate generation stays deterministic** — the model never scans the corpus. Pairs come
  from graph adjacency plus subject-token overlap plus obligation-scope overlap. This bounds
  cost and, more importantly, makes recall explainable: we can state exactly which pairs were
  considered.

### 3.4 Terminology clustering

Does `प्राध्यापक` render as "Professor", "Teacher", "Faculty", "Lecturer" across departments?
Deterministic alignment finds co-occurrence; deciding which variants are *the same legal term*
is semantic.

- **Capability:** Multilingual
- **Guardrails:** a proposed pair must co-occur in ≥N aligned documents (deterministic,
  measured), else rejected. The model may cluster; it may not invent a pair.

### 3.5 Lint explanation and auto-fix — verdict stays deterministic

The **rule engine decides** violations (mined empirically, with support counts). The model only
writes the human explanation and the suggested corrected Marathi text.

- **Capability:** Multilingual + Text generation
- **Guardrail:** the suggested fix is re-run through the lint engine. **If the fix does not
  pass, it is not shown.** A suggestion that fails its own rule is worse than no suggestion.

### 3.6 Draft generation and the drafting agent

The "AI Assisted GR drafting" in the title. Here the architecture does something I like a lot:

> **The model cannot invent a citation because the only way it can obtain one is by calling our
> resolver.** The tool *is* the guardrail.

- **Capability:** Function Calling / Tool Use
- **Tools:** `search_corpus(query, dept, date_range)`, `resolve_citation(number, date)`,
  `get_gr(uid)`, `check_template(text)`, `blast_radius(draft)`
- **Guardrails:** every citation in generated text must have come from a tool result — checked
  by diffing citations in the output against the tool-call transcript. Any citation with no
  provenance is stripped and logged. G2 applies to the final text as a backstop.

### 3.7 Marathi dictation

An officer speaks; Draft Studio transcribes into the editor. Real accessibility — Devanagari
typing is slow — and a strong live moment.

- **Capability:** Speech to Text (Marathi)
- **Guardrail:** transcription is *input*, never a finding. Nothing downstream trusts it; it
  lands in an editable field.
- `[UNKNOWN]` Marathi quality on the available STT model. **Must be tested early** — if it is
  poor, cut it rather than demo it badly.

### 3.8 Bring-your-own-GR (Vision)

A judge uploads a scanned GR that is not in the corpus; we check it against 17,253 existing
ones. Converts a canned demo into an unfakeable one.

- **Capability:** Vision
- **Note:** this does *not* violate "do not build an OCR pipeline" — the corpus stays
  pre-OCR'd. This is ad-hoc handling of one user-supplied file.
- **Guardrail:** extracted citations go through the deterministic resolver like any other.
  Nothing is asserted about a document we cannot read cleanly; we say so instead.
- `[UNKNOWN]` Devanagari accuracy in the vision model. Test before committing to it.

### 3.9 Where AI is deliberately NOT used

Stated so the discipline is legible: citation resolution, date extraction, digit-key matching,
graph traversal, supersession-chain computation, lint verdicts, the parity numeric diff, all
counting and all statistics. **Every number in the pitch is computed, never generated.**
Content moderation is also unused — no fit here, and PII in published GRs is out of scope.

---

## 4. What I need from you

### Resolved `[MEASURED]` — working configuration

Verified by live call, 2026-07-26:

| item | value |
| --- | --- |
| endpoint | `POST https://api.groq.com/openai/v1/chat/completions` — OpenAI-compatible |
| reasoning / tools model | `openai/gpt-oss-120b` |
| token limit param | **`max_completion_tokens`**, *not* `max_tokens` |
| reasoning knob | `reasoning_effort: low \| medium \| high` |
| JSON mode | `response_format: {"type": "json_object"}` — works |
| key | `.env`, gitignored. **Exposed in a chat transcript — rotate after the hackathon** |

One transport gotcha, fixed in `ai/client.py`: a default `Python-urllib/x.y` User-Agent is
rejected by Cloudflare in front of the API with `403 error code: 1010` (browser-signature ban).
Any client must send a real User-Agent.

Cost shape for batching: a 7-sentence edge-typing probe at `reasoning_effort=medium` used ~76
prompt + ~45 completion tokens per call, of which ~35 were reasoning tokens. Reasoning tokens
dominate, so `reasoning_effort` is the main cost lever for high-volume work.

**Still needed:**

1. **Speech-to-Text model id** — `gpt-oss-120b` is text-only, so §3.7 dictation is blocked
   without it. Whichever Whisper variant is available, plus whether Marathi (`mr`) is supported.
2. **Vision model id** — §3.8 (judge uploads a GR scan) is blocked without it.
3. **Rate limits** (RPM / TPM) — decides whether extraction over 17,253 GRs runs in one pass or
   needs overnight batching.
4. `[DECIDE]` **A second, smaller/faster text model id** if one is available. Edge typing is
   thousands of calls where latency and cost matter; conflict adjudication is a few dozen calls
   where quality matters. Different models suit them.

**Priority order of roles.** 1 is non-negotiable; 4 and 5 are cuttable.

| # | role | need | why |
| --- | --- | --- | --- |
| 1 | **Multilingual reasoning, JSON out, long context** | **critical** | carries §3.1–3.5. Must genuinely handle Marathi, not just claim it. Longest context available — conflict adjudication feeds two full GRs |
| 2 | **Function calling / tool use** | high | §3.6, the drafting agent. Can be the same model |
| 3 | **Speech to Text with Marathi** | medium | §3.7. Cut if Marathi is weak |
| 4 | **Vision, Devanagari-capable** | medium | §3.8. High demo value, unproven accuracy |
| 5 | **Text to Speech, Marathi voice** | low | accessibility read-back. Only if time remains |

If two reasoning models are available at different sizes, I want both IDs: the larger for
conflict adjudication (few calls, high stakes) and the faster for per-sentence edge typing
(thousands of calls). Cost and latency profiles differ by orders of magnitude.

---

## 5. The offline tension, resolved

`CLAUDE.md` requires the demo to run **fully offline against cached artefacts**. Groq is a cloud
API. That is a real conflict and it is resolved by splitting the two things a demo does:

**Findings are precomputed.** Every AI-derived artefact — typed edges, obligations, conflicts,
terminology clusters — is built in a batch job, verified, and committed under `out/`. On stage
these load from disk. Instant, deterministic, and network-independent. `AI_MODE=strict` makes
this **mechanically enforced**: the client refuses to open a socket, so an accidental live call
fails loudly in rehearsal instead of hanging on stage.

**Interaction is live, with a floor.** Draft Studio, dictation and PDF upload are live calls.
Mitigations: responses cached by content hash so a rehearsed demo is a cache hit and stays
offline; a "recorded run" fallback for each interactive feature; `AIUnavailable` degrades to the
deterministic result with a visible "model unavailable" state rather than an error.

Rehearse the whole thing once with wifi off. Whatever breaks, precompute.

---

## 6. Feature map — the four bullets, done properly

### 6.1 Cross Department Conflict Detection

Currently zero, and it is the problem statement's *first* bullet. Three tiers, increasing in
novelty:

**Tier 1 — Explicit conflict.** Two live GRs, different departments, citing each other, with
contradictory obligations. Findable, valuable, table stakes.

**Tier 2 — Silent conflict.** Two live GRs, different departments, that **never cite each
other**, same subject, contradictory values. Candidates from subject-token + scope overlap; the
model adjudicates; guardrails verify. This is the real institutional pathology — no official can
see across departments, so nobody notices.

**Tier 3 — Latent conflict. The best finding in the project.**

> Higher Education GR B (live) sets a rate *by reference to* Finance GR A. Finance GR A was
> later superseded by GR C, which changed that rate. **GR B is live and depends on a number that
> no longer exists.**

This requires traversing a cross-departmental reference edge *and* a supersession chain. It is
**not discoverable by any manual process** and not by document-level RAG either — it is a
property of the graph, not of any document. If this yields even a handful of real cases, it is
the strongest thing we can put on a slide.

### 6.2 Bilingual Legal Terminology (English)

- Devanagari leak repair — **done**: 75-type closed vocabulary, back-transliterating Class B
  (`Dr. आर.एस.Mali` → `Dr. R.S. Mali`) rather than deleting load-bearing name fragments.
- **Mined bilingual glossary** from 17,253 aligned pairs — a real artefact, not a lookup table
  someone typed.
- **Inconsistency detection**: same Marathi legal term rendered N different ways in English,
  ranked by spread. Directly actionable.
- **Numeric parity** with classification, per `CLAUDE.md` — magnitude error vs table-merge
  artefact vs list-numbering noise. Classify, don't just flag: naive diff flags 99.5%.
- Mandatory caveat wherever this appears: the corpus English is machine translation, so this
  measures **translation** consistency, never divergence between two official texts.

### 6.3 Automated Reference Tracking

Deepest area. Resolver + 14 property tests shipped. Adds: the graph, AI edge typing (§3.1), the
dead-reference audit, supersession chains, and an "as-of" traversal (§6.5). Keeps the honest
scope reporting — unresolvable citations are shown *as* unresolvable, with the reason.

### 6.4 Strict Template Enforcement

The innovation is **not hand-coding the Manual of Office Procedure.** Mine the template from
17,253 GRs — the 136-GR verbatim boilerplate family already found proves the signal is there —
and emit rules with **empirical support counts**:

> `GRL-014` — 97.3% of GRs in this department place a Reference block before the Proposal
> section. Yours does not. *(support: 4,588 / 4,715)*

A rule carrying a measured support count is far more defensible than an asserted one, and it
generalises to departments whose conventions differ. Must handle the displaced-ordinal bug
(`The 1.सदर approval will always be…`) since that is the family being mined.

### 6.5 Extra features

**E1 — Dead-Reference Audit.** *"N GRs in force today cite orders that no longer exist."* The
headline. A finding, not a capability. Keeps the `unverifiable_reference` bucket rigorously
separate: 85+24 citations resolve to nothing, and that is crawl incompleteness, not legal
deadness. Counting them would quadruple the number and make it false.

**E2 — Blast Radius.** Before issuing a draft: what does it break? Every live GR depending on
what you are about to supersede, across departments, with a count. This is the "AI assisted
drafting" of the title and it is only possible with the graph.

**E3 — As-Of Time Machine.** *"What was the rule on 15 March 2021?"* Traverse supersession edges
to a date and show the version in force plus the chain that got there. The thing officials
actually need. Deterministic traversal, AI writes the summary.

**E4 — Trust Ledger.** §7.8. Makes the guardrails visible and quantified.

---

## 7. UI — one page per capability

Offline-first, reading committed artefacts. **FastAPI + vanilla JS, all assets vendored
locally** — no CDN, because no network. Graph rendering via a vendored Cytoscape.js. Bilingual
labels throughout (Marathi primary per rule 1, English beneath); every screen showing a
conclusion also shows its evidence sentence.

### 7.1 The Finding *(landing)*
Not a menu — the headline. Big numbers: GRs indexed, edges, **dead references**, cross-dept
conflicts, hallucinations blocked. Each tile is a link to its evidence. A judge should
understand the project in fifteen seconds without being told.

### 7.2 Graph Explorer
The thesis made visible. Node = GR, edge coloured by type. Click a node: subject, date,
department, in/out edges. Click an edge: **the verbatim Marathi sentence that produced it**,
English beneath, plus its verification badge. Filter by department, date, type. Highlight
supersession chains. Dead-end nodes marked distinctly — a visible dead reference is the whole
pitch in one screenshot.

### 7.3 Conflicts
Three tabs for the tiers of §6.1, latent first because it is the most striking. Detail view:
two GRs side by side, contradictory spans highlighted in both, conflict class, model
explanation, verification badges per gate. A "why do you believe this" expander showing exactly
which gates passed.

### 7.4 Draft Studio
The drafting surface. Marathi editor, dictation button (§3.7), and a live right-hand rail:
template lint with rule codes and line numbers, citations auto-resolved as typed (green =
resolved to a real uid, amber = unresolved, **never silently accepted**), and a live blast-radius
count. "Generate section" invokes the tool-using agent — and every citation it inserts is
traceable to a tool call.

### 7.5 Reference Audit
The dead-reference table. Columns: citing GR, cited order, why it is dead, the supersession that
killed it, evidence. A second, clearly separated tab for `unverifiable_reference` with the crawl
explanation. Separating these two tabs *is* the credibility feature.

### 7.6 Terminology
Mined glossary, searchable. Inconsistency view: one Marathi term, its N English renderings,
frequency, departments, and the aligned sentence pairs. Devanagari-leak repair before/after.

### 7.7 As-Of
Date picker plus topic. Returns the rule in force on that date and the chain, with superseded
versions greyed and dated. A timeline scrubber makes this a genuinely memorable interaction.

### 7.8 Trust Ledger — *the page no other team will have*
Every AI claim, its verdict, and the gate that decided it. Headline: **"the model proposed X
claims; we blocked Y."** Browsable rejections with the fabricated quote next to the real
document. Counts per gate.

This inverts the hardest question in the room. When a judge asks "how do you know your AI isn't
making things up," the answer is a number, a page, and a browsable list of the specific times it
tried.

---

## 8. Build order for the remaining ~2.5 days

Sequenced so something demoable exists at every checkpoint, and nothing late is load-bearing.

**Day 3 (today) — substrate.** Graph over all 4 departments (deterministic, `REFERENCES` only)
→ dead-reference audit → **get the number.** Then wire Groq, smoke-test Marathi comprehension on
20 sentences, and build `verify.py` with G1–G6. *Checkpoint: a real finding, plus a verified AI
edge type.*

**Day 4 — features.** AI edge typing over the corpus (batched, cached, verified) → supersession
chains → latent conflicts → lint engine with mined support counts → terminology mining.
*Checkpoint: all four bullets have a working artefact.*

**Day 5 — make it visible.** UI pages in order 7.1, 7.2, 7.5, 7.3, 7.4, then 7.8, 7.6, 7.7 as
time allows. Rehearse with wifi **off**. Deck last, built from the artefacts.

**Cut list, decided now so it is not agonised over later:** as-amended text consolidation (needs
clause alignment we do not have), TTS, content moderation, and Vision if Devanagari accuracy
disappoints on first test.

---

## 9. Risks

| risk | mitigation |
| --- | --- |
| ~~Marathi quality is poor~~ **RETIRED `[MEASURED]`** | Probed `openai/gpt-oss-120b` on 7 corpus sentences. Reads Marathi legal prose accurately (`पूर्वलक्षी प्रभावाने रद्द करण्यात येत आहे` → "is being cancelled with retrospective effect"), and **passed both regex-trap cases** — read `पुढे चालू` as part of a file name, not an operative verb. All 7 evidence spans verbatim (G1 clean). See §9.1 for the limitation this probe *did* find |
| Rate limits make 17,253-GR extraction infeasible | run AI only where it changes an outcome — sentences already containing a resolved citation, not every sentence. Cache aggressively. Batch overnight |
| Latent conflicts turn out to be zero | it is a *finding* either way, and the tiering means Tier 1/2 still carry §6.1. Never loosen a definition to manufacture a number |
| Live demo network failure | `AI_MODE=strict`, everything precomputed, recorded fallbacks, rehearsed offline |
| Verified-but-wrong claims | the gates bound *fabrication*, not *judgement*. Say so plainly rather than implying the guardrails prove correctness. **Observed in the wild — §9.1** |
| Breadth-first leaves everything shallow | day-3 checkpoint is a real finding, not scaffolding. If day 4 slips, the headline still stands alone |

### 9.1 The limitation the probe found — granularity of cancellation `[MEASURED]`

One of 7 probe sentences cancels **the appointments of committee members made under** a GR dated
23.08.2021. The model returned `SUPERSEDES` on the edge to that GR. That is the wrong granularity:
the 2021 GR is not superseded, its committee composition is amended. Typed as `SUPERSEDES` it
would mark a live GR dead and poison the dead-reference audit, the chains, and blast radius.

**Every gate passes on this error.** The quote is verbatim (G1), the GR exists and resolves (G2),
the type is in the enum (G3), no forward-time violation (G5). This is the concrete demonstration
that G1–G6 bound *fabrication* and not *judgement*, and it should be quoted honestly rather than
buried — a team that can name its own failure mode is more credible than one claiming none.

Three responses, all adopted:

1. **Sharpen the prompt.** Ask explicitly: does the sentence cancel *the order itself*, or
   something *done under* the order (an appointment, a sanction, a payment)? The latter is
   `AMENDS` at most. This distinction is the single highest-value line in the edge-typing prompt.
2. **Add a seventh gate, G7 — scope.** If the cancelled object in the evidence span is a noun
   other than the order itself (`नियुक्त्या` appointments, `मान्यता` approval, `निधी` funds),
   downgrade `SUPERSEDES` → `AMENDS`. Deterministic, checkable, and it catches exactly this class.
3. **Human spot-check on typed edges is no longer optional.** Volume is low enough to read every
   `SUPERSEDES` edge, and it is the one type whose errors propagate into all three downstream
   features.
