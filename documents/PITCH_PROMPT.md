# Prompt for Claude Design — MAHA-GR-ALIGN presentation

Copy everything below the line into Claude Design.

---

Build a presentation deck for a hackathon submission. Audience: government officials and
technical judges at the VJTI AI Hackathon 2026. Tone: confident, evidence-led, government-formal
but not stiff. **Lead every section with a finding or a number, never with a feature list.**

Design direction: a Government of Maharashtra digital-service look. Deep teal and indigo with
gold rules, white body slides, generous whitespace, tabular numerals for statistics. Devanagari
appears in several slides — use a font that renders it correctly (Noto Serif Devanagari). No
stock photography, no clip art. Charts should be clean and labelled, not decorative.

Roughly 18–22 slides. Follow the section order below exactly; it is the required submission
structure.

---

## 1. Title

**MAHA-GR-ALIGN** — AI-Assisted Drafting and Legal Alignment System for Maharashtra Government
Resolutions. VJTI AI Hackathon 2026, Problem Area 1.

Tagline to feature: *"A Government Resolution is not a document. It is a node in a legal
dependency graph."*

## 2. Problem statement

The official problem statement asks for four things:

1. Cross-department conflict detection
2. Bilingual legal terminology (Marathi–English)
3. Automated reference tracking
4. Strict template enforcement

Frame the underlying problem this way: Maharashtra has issued lakhs of Government Resolutions
since 1960. Every one amends, supersedes, or depends on earlier ones. **That dependency graph
has never existed in machine-readable form**, so no officer can answer basic questions —
does the order I am citing still stand? has another department already decided this? what breaks
if I cancel this?

Include this as the motivating example on its own slide:

> A General Administration resolution, **in force today**, cites a Finance Department order on
> vehicle price limits. Finance replaced that order in February 2024. **Neither document mentions
> the other.** Finding it requires a cross-departmental citation *and* a supersession chain — it
> is a property of the graph, not of any document. We found **24** such dead references.

## 3. Proposed solution

A web portal with five pages that sits between the desk officer and the GR archive:

| Page | What it does |
|---|---|
| **Draft GR** | Compose against the Manual's form; AI drafts and refines; semantic check against other departments |
| **Verify GR** | Upload a PDF or scan; three independent checks — template, citations, terminology |
| **Check Graph** | Look up any GR: what it cites, what cites it, which of those still stand |
| **Recent GRs** | Screen recent resolutions in bulk; upload drafts to a pre-issue in-tray |
| **Archive** | Original analytical dashboard, retained |

The organising principle, stated as a slide: **facts are computed, never generated.** A language
model may explain a finding; it is never the reason the system believes one.

## 4. System architecture

Five layers — draw as a clean vertical or left-to-right stack:

1. **Data** — mahGRs corpus → text → embeddings; EasyOCR fallback for scans
2. **NLP engine** — MahaSBERT (Marathi embeddings), IndicTrans2 (translation), Qwen3.5-2B (generation), all on-premise CPU
3. **Vector search** — exact NumPy inner product over a 23,977 × 768 matrix
4. **Compliance rules** — JSON schemas: Manual of Office Procedure structure + controlled glossary
5. **Frontend** — React + Vite dashboard, bilingual

Also draw the **document pipeline** as a flow:

```
upload → text layer or OCR → header parse → citation extraction → resolve against 17,283-node index
                                                                → template check
                                                                → glossary check
                                                                → contradiction check
```

Emphasise: **nothing leaves the machine.** Ollama on localhost, models on disk, graph and index
as local artefacts. Demonstrated by running the whole demo with the wifi off.

## 5. Technologies used

Present as a clear table, grouped. **Every item below must be named** — the submission requires
explicit acknowledgement of external resources.

**Dataset (external, credited)**
- **orgpedia/mahGRs** — https://github.com/orgpedia/mahGRs — MIT licence. 96,617 Government
  Resolutions across 33 departments, Marathi original + English machine translation. We ingested
  4 departments = **17,283 GRs**, October 2017 – July 2026.
- **Maharashtra Manual of Office Procedures, 2023** — the template authority. Appendix 10.6 is the
  specimen form for a Government Resolution.
- **gr.maharashtra.gov.in** — official portal; every archived GR links back to its signed PDF.

**Pre-trained models (external, credited, all run locally)**
- **`l3cube-pune/marathi-sentence-similarity-sbert`** (MahaSBERT) — 768-dim Marathi sentence embeddings
- **`BAAI/bge-base-en-v1.5`** — English sentence embeddings
- **`ai4bharat/indictrans2-indic-en-dist-200M`** and **`indictrans2-en-indic-dist-200M`** — translation
- **`qwen3.5:2b`** via **Ollama** — drafting, summarisation, narrative explanation
- **EasyOCR** (Marathi + English) — scanned-document OCR

**Third-party API (used once, historically — state this honestly)**
- **Groq** hosted inference, used only for the one-off supersession edge-typing pass that produced
  the 33 SUPERSEDES and 169 AMENDS edges. All runtime inference is local.

**Frameworks and libraries**
- Backend: Python, FastAPI, Uvicorn, NumPy, PyTorch (CPU), transformers, sentence-transformers, sentencepiece
- Documents: WeasyPrint (PDF), python-docx (DOCX), XeLaTeX
- Frontend: React 19, TypeScript, Vite 8, React Router 7, Cytoscape (archive view)
- Testing: pytest — 131 tests, zero network calls
- Fonts: Noto Serif / Sans Devanagari (SIL OFL), vendored

## 6. Implementation

### 6a. Requirements delivered — all 16

Show as a compact table with green ticks:

| | Requirement | Status |
|---|---|---|
| FR-1–3 | Extract, verify and highlight citations | Delivered |
| FR-4–6 | Clause embeddings, vector search, similarity score + source link | Delivered |
| FR-7–9 | Controlled bilingual glossary, flag, suggest | Delivered |
| FR-10–12 | Manual of Office Procedure structure enforcement | Delivered |
| FR-13–16 | Web dashboard, side-by-side review, audit trail, PDF/DOCX export | Delivered |

### 6b. Features beyond the specification

Give these their own slide — they are the differentiators:

- **Cross-document contradiction detection.** When a draft restates a figure from an order it
  cites, the system compares it against what that order actually says. Demonstrated: Finance
  sanctions **₹15,00,00,000**; Higher Education, citing that exact order, writes
  **₹10,00,00,000**. Both documents pass every other check. The defect exists only *between* them.
- **Blast radius.** Before issuing a GR that cancels an order, see how many resolutions still in
  force depend on it, and in which departments. One Finance circular has **229 live dependents**
  across three departments.
- **Pre-issue in-tray.** Upload drafts before they are published; a later draft can cite an
  earlier one, so an inter-departmental conflict is visible while *both* are still drafts.
- **Dependency graph explorer.** Search by GR number, Devanagari file number, or subject.
- **Dead-reference audit** across the whole corpus.
- **Cited-GR popup** with the supersession chain and a link to the signed PDF on the Government's
  own site.

### 6c. Validation and guardrails

**This deserves two slides. It is the most distinctive engineering in the project.**

Frame it as: *the system is built so that a wrong answer is structurally hard to produce.*

1. **No model call in the checkers.** The citation checker, template engine, contradiction check
   and glossary contain no LLM call at all — and automated tests assert the absence of the
   imports that would allow one.
2. **Verdicts are computed, then handed to the model to phrase.** Asked to judge for itself, the
   local model concluded a document "remains valid because the cited references are either
   unverified or superseded" — about a document whose citations *had* been superseded.
3. **Identifiers are withheld from prompts.** The model never sees an order number, date or line
   number; citations are given to it only as `[1]`, `[2]`. It cannot corrupt what it never saw.
4. **Sentences containing unexpected digits are discarded whole**, not repaired — a mangled file
   number reads exactly as authoritative as a correct one.
5. **Summaries are gated on figures.** Every monetary amount is extracted deterministically and
   whitelisted; a sentence quoting any other figure is removed.
6. **Five distinct reasons for a citation not resolving, never merged** — only one is a defect in
   the document. Court orders and Acts are reported as outside what a GR archive holds, never as
   missing. Merging them would roughly quadruple the error count and make it false.
7. **Abstention is a first-class outcome.** Ambiguity abstains rather than guessing. A date with
   no file number yields no resolution — every GR issued that day would match.
8. **Evidence travels with every claim.** Every graph edge carries the verbatim Marathi sentence
   that produced it, shown wherever the edge justifies a finding.
9. **Degradation is visible, never silent.** "The model was unavailable" is a state the interface
   displays; a fabricated answer is not.

## 7. Results / demonstration

### Statistics — give this a full slide, well laid out

**Scale**
- 17,283 GRs indexed · 4 departments · Oct 2017 – Jul 2026
- 4,815 resolved citation links · **1,538 cross-departmental**
- 23,977 clauses vectorised (21,018 searchable after boilerplate masking)
- 31-term controlled bilingual glossary
- 131 automated tests, zero network calls

**Accuracy**
- Citation extraction: **98.9%** (3,461 of 3,501 across 906 GRs) — acceptance threshold was 80%
- Resolver precision: **48 / 50** on a sample weighted towards the hard cases
- 88.6% of citation links have an exact date match
- Template compliance measurable at **45.0%** across 400 real GRs under the issued-document rule set

**Performance** (all on CPU, no GPU)
- All four deterministic checks on one GR: **10 ms** — against a 30-second requirement
- Semantic search: 0.6 s · Bulk screening of 15 GRs: 170 ms

**Findings across the corpus**
- **24 dead references** — 10 decayed after issue, 14 issued already dead, 2 latent cross-departmental
- **229 live dependents** on a single Finance circular
- **335 magnitude errors** in the English translation (e.g. a factor-of-1000 slip down a table column)
- **26 legal terms** rendered inconsistently in English

**The terminology finding — worth its own callout box**
> Across 2,500 corpus documents, **"Government Decision" appears 1,861 times** and
> **"Government Resolution" 1,021 times**. The Maharashtra Manual of Office Procedures uses
> "Government Resolution" **six times and "Government Decision" not once**.
> The dominant machine-translated rendering is the non-standard one — which no amount of mining
> the corpus could reveal. It needs a *controlled* list.

### Demonstration flow (one slide, as numbered steps)

1. Upload an issued GR → **NOT aligned**: it cites an order cancelled in 2024
2. Upload the Finance draft (₹15 crore) → clean on all four checks
3. Upload the Higher Education draft (₹10 crore, citing it) → **₹5,00,00,000 understated**
4. Look up a Finance circular in the graph → **209 GRs depend on it**
5. Refine a draft → suggestion shown side by side, accept or discard

## 8. Challenges

Present as problem → what we measured → what we did. These are real and specific; they are the
best evidence of depth in the whole deck.

| Challenge | Measured | Resolution |
|---|---|---|
| **Same-date collision** | Matching citations by date alone produced 19,840 links, averaging 44 candidates each, peaking at 380 | Match on file number **and** date |
| **Same-number collision** | A "Government Decision No." is a *file* number, not unique — **41.1%** of GRs share theirs | Number narrows to a series; the date selects the member |
| **Two scripts** | Archive numbers are Devanagari; citations arrive transliterated (`Masi-1` / `Mashi-1` / `MASHI-1`) | A digit key that is script- and transliteration-independent |
| **Devanagari regex traps** | `\b` fails after Devanagari (`वाचा` ends in a combining mark), silently passing a blank template | Anchor on separators, never word boundaries |
| **Visual-order PDF text** | `एप्रिल` extracts as `एिप्रल`, matras reordered | Match month names on a matra-stripped skeleton |
| **Spelled-out dates** | Citation extraction stuck at **51.7%** — every `दिनांक ०९ जुलै, २०२६` was dropped | Added spelled-month parsing → **98.9%** |
| **Boilerplate dominating search** | Finance-concurrence clauses matched everything at 0.87–0.91, burying real hits | Mask 12% of clauses as procedural furniture |
| **Wrong template for the document type** | Memoranda and corrigenda judged against the Resolution form; only **0.2%** of real GRs scored compliant | Per-type rules + an issued-document rule set → **45.0%** |
| **No GPU** | 11 clauses/second; the index took ~3 hours to build | Batch offline; commit the artefact so the demo is instant |

Add one honest slide on **model limitations**, which strengthens credibility:
> The 2-billion-parameter local model separates *topic* well but not the legal *act* — it scores
> an amendment higher against a cancellation (0.47) than a second cancellation (0.41). So the
> semantic module surfaces **candidates for review**, and the officer decides. The requirement
> asks for *potential* conflicts, which is exactly what we deliver.

## 9. Future work

- Extend from 4 departments to all 33 — every cross-department figure today is a lower bound
- Re-generate supersession edge typing with the local model to remove the last hosted dependency
- Expand the controlled glossary with review by a legal-terminology expert
- Usability trial with practising desk officers
- Measure recall alongside precision
- Fine-tune an Indic model on the corpus (currently all models are off-the-shelf)
- Integrate directly with the GR portal so checks run at the point of issue

## 10. Closing slide

> Four departments today. The same pipeline runs over all 96,617 Government Resolutions — the
> graph builds in ten seconds. Every check takes 10 milliseconds, and the entire system runs on
> one laptop with the network switched off.

Credits slide: orgpedia/mahGRs (MIT), AI4Bharat IndicTrans2, L3Cube MahaSBERT, BAAI BGE, Qwen via
Ollama, EasyOCR, and the Maharashtra Manual of Office Procedures, 2023. State that all
third-party resources are open-source or publicly available and used within their licences, and
that the system implementation is the team's own work.
