# MAHA-GR-ALIGN

**AI-assisted Government Resolution drafting, alignment and conflict detection for the Government
of Maharashtra.** VJTI AI Hackathon 2026, Problem Area 1.

> We built a dependency graph over **17,283 Government Resolutions** across four departments, and
> found **Government Resolutions still in force that cite orders which no longer exist** — including
> two General Administration approvals depending on a Finance policy that Finance itself replaced.
>
> Nobody in either department can see that. It is a property of the graph, not of any document.

---

## The reframing everything follows from

A Government Resolution is the instrument through which Maharashtra exercises executive power. It
is not a memo — it *is* the decision. Two properties make GRs hard, and they compound:

- **They are incremental, never self-contained.** A GR almost never states a complete rule; it
  modifies earlier ones. To know the rule actually in force you must reconstruct a chain.
- **They are permanent and never garbage-collected.** Lakhs since 1960. A GR stays in force until
  something explicitly supersedes it — and supersession is expressed in Marathi prose,
  inconsistently, sometimes not at all. There is no expiry field and no "superseded by" pointer.

So officials cannot answer "what is the rule right now", departments contradict each other without
knowing, and new GRs cite orders that died years ago.

> **A Government Resolution is not a document. It is a node in a legal dependency graph.**

Once you accept that, the problem statement's four requirements stop being four products and
become one missing artefact plus four views of it. **That artefact does not exist anywhere** — the
documents are public, the relationships between them are not.

---

## What it does

| Problem-statement requirement | What we built |
| --- | --- |
| **Automated Reference Tracking** | Citation resolver + 17,283-node dependency graph, 4,815 edges, each carrying the verbatim Marathi sentence that produced it |
| **Cross Department Conflict Detection** | 1,538 cross-departmental dependency edges; dead-reference audit finds live GRs depending on replaced orders from *other* departments |
| **Strict Template Enforcement** | GR-Lint, with rules **mined from the corpus** and carrying empirical support counts — not transcribed from the Manual of Office Procedure |
| **Bilingual Legal Terminology** | Numeric parity (335 magnitude errors found) + a mined Marathi↔English glossary flagging inconsistently rendered legal terms |
| *(and, for the "drafting" in the title)* | **Blast radius** — before you supersede a GR, see everything that depends on it. One Finance circular has **229 live dependents across three other departments** |

---

## Headline numbers

Every figure below is regenerable — see [Reproducing everything](#reproducing-everything).

| | |
| --- | ---: |
| Government Resolutions indexed | **17,283** |
| Departments | 4 |
| Citations extracted from Marathi | **27,948** |
| Dependency edges resolved | **4,815** |
| — of which cross-departmental | **1,538** (31.9%) |
| **Dead references (GRs in force citing cancelled orders)** | **24** |
| Numeric magnitude errors in the English translation | **335** |
| Template violations over 2,000 GRs | 23 errors, 576 warnings |
| Full graph build time | **10 seconds** |
| Tests (zero API calls, zero labels) | **41 passing** |

---

## The finding, in full

**Finance** issued a *Government E-Vehicle Price Limit Policy* on 03.02.2022.
**Finance replaced it itself** on 02.02.2024 with a broader vehicle price-limit policy.

Two **General Administration** GRs approving vehicle purchases — 13.10.2022 and 24.11.2023 — are
still in force and depend on the replaced policy.

The evidence, verbatim from the Marathi:

```
७. यापूर्वी निर्गमित करण्यात आलेले वाहनांच्या किंमत मर्यादेबाबतचे आदेश अधिक्रमित करुन
   "By superseding the previously issued orders regarding vehicle price limits…"
```

Finding this requires traversing a **cross-departmental reference edge** *and* a **supersession
chain**. GAD does not track Finance's supersessions; Finance does not know who relies on its
policy. No amount of reading either document reveals it.

---

## How we avoid making things up

A hallucinated legal citation is not a bug in this domain — it is a credibility death sentence.
Two mechanisms, both enforced in code.

### 1. Every edge carries its evidence

If we cannot show the sentence that produced an edge, the edge does not ship. This is
mechanically tested, not promised: `test_every_edge_evidence_is_verbatim` samples edges and asserts
the evidence string occurs in the citing document's Marathi text. **100% of 600 sampled edges pass.**

### 2. The model proposes, the corpus verifies

AI is used only where determinism *provably* failed — and we measured the failure first. Cue-word
matching cannot type edges: only 28% of cue-bearing sentences contain a citation, and the cue is
often not a verb at all (`वित्तीय सुधारणा-१` is a file named "Financial Reforms-1").

So a model reads the sentence, and seven deterministic gates decide whether its answer may be
shown:

| gate | enforces |
| --- | --- |
| G1 grounding | every quoted span occurs verbatim in the source document |
| G2 referential | every GR id exists; targets come from our resolver, never the model |
| G3 vocabulary | relationship types come from a closed set |
| G4 numeric | asserted numbers occur in the source, digits normalised across scripts |
| G5 temporal | nothing supersedes an order issued after it |
| G6 determinism | temperature 0, cached; a disagreeing re-run downgrades the claim |
| G7 scope | cancelling something done *under* an order is an amendment, not a supersession |

**The gates caught the model corrupting Marathi**: it quoted `अधिकरणित करुन` where the document
reads `अधिक्रमित करुन` — right classification, fabricated evidence. The Trust Ledger page shows
every such catch, side by side with what the document actually says.

**What the gates do not bound: judgement.** A model can quote a real sentence from a real GR and
still draw the wrong conclusion. We observed that too, and say so rather than implying the
guardrails prove correctness.

---

## What we deliberately do not claim

- **Accuracy is unmeasured.** It needs a human-labelled answer key, which does not exist yet, so
  `out/metrics.json` reports `UNMEASURED` rather than a number we did not earn.
- **21,121 citations could not be resolved**, and they are reported as unverifiable in their own
  section — not as dead references. Almost all reflect gaps in the public crawl. Counting them
  would multiply the headline and make it false.
- **"In force" means "no supersession edge in our four departments."** Orders superseded from
  outside, or expired by their own terms, are counted as live. The figure is conservative.
- **The English text is machine translation.** Every legal conclusion is drawn from the Marathi.
  Bilingual findings measure translation fidelity, never divergence between two official texts.

### What we show instead of accuracy

| metric | value | why it is meaningful without labels |
| --- | --- | --- |
| **Ablation: date alone** | **100% ambiguous** — mean 44.2 candidates, worst 380 | measures the *corpus*, not our code, so it cannot be argued with |
| Ablation: file number alone | 60.2% ambiguous | a file number is not a unique GR identifier |
| Cross-language agreement | **94.34%** over 3,462 edges | the Marathi and English pipelines fail in uncorrelated ways |
| Evidence groundedness | **100%** of 600 sampled | |
| Structural violations | **0** over 4,815 edges | no self-citation, nothing pointing forward in time |

**Date alone cannot resolve a single one of 4,815 citations in this corpus.** That is the technical
heart of the project: `Government Decision No.` is a *departmental file number*, not a unique
identifier — 41% of GRs share theirs — so neither key works alone. The resolver matches on the
pair, using a script-independent digit key (`Muwad-2016/(38/16)/Mashi-1` and
`मुवाढ-२०१६/( ३८/१६ )/मशि-१` both reduce to `201638161`).

---

## Running it

```bash
# 1. corpus (sparse clone, ~400 MB of text, four departments)
git clone --filter=blob:none --sparse --depth 1 \
    https://github.com/orgpedia/mahGRs.git data/mahGRs
cd data/mahGRs && git sparse-checkout set \
    GRs/Higher_and_Technical_Education_Department \
    GRs/General_Administration_Department \
    GRs/Finance_Department \
    GRs/School_Education_and_Sports_Department && cd ../..

# 2. environment
uv venv && uv pip install --python .venv/bin/python fastapi 'uvicorn[standard]' pytest
cp .env.example .env          # add your Groq key; optional, only for rebuilding AI artefacts

# 3. everything
make all                      # build all artefacts (~30 s, no network needed)
make serve                    # http://localhost:8000
```

**The demo runs fully offline.** All AI responses are cached and committed; `AI_MODE=strict` makes
the client physically refuse to open a socket, so a dead conference wifi cannot break the
presentation. The test suite runs in that mode too — **it cannot spend an API token.**

### Reproducing everything

```bash
make graph      # 17,283 nodes, 4,815 edges         (10 s)
make audit      # the dead-reference finding
make metrics    # every number quoted above
make lint       # mined template rules
make bilingual  # numeric parity + glossary
make test       # 41 tests, zero API calls
```

---

## The interface

Six pages, all reading cached artefacts:

1. **The Finding** — leads with a finding, not a feature list
2. **Graph Explorer** — superseded GRs are drawn hollow in dashed red; an arrow into one *is* a dead
   reference. Click any edge for its verbatim Marathi and per-gate verification
3. **Reference Audit** — every dead reference with both proving sentences; unverifiable citations in
   a separate tab
4. **GR-Lint** — mined rules shown *beside* the 18 orderings we deliberately do not enforce
5. **Bilingual Terms** — magnitude errors and inconsistently rendered legal terminology
6. **Trust Ledger** — what the model proposed, what the gates blocked, and why

---

## Architecture

```
data/mahGRs/          corpus (sparse clone, not committed)
parser.py             GR text → structured record      deterministic
resolver.py           citation → uid                   deterministic
graph.py              → out/graph.json                 deterministic
type_edges.py         REFERENCES → AMENDS/SUPERSEDES   AI + gates
audit.py              → out/audit.json                 deterministic
lint.py               mined template rules             deterministic
bilingual.py          parity + glossary                deterministic
metrics.py            every quoted number              deterministic
ai/client.py          Groq transport, cache-first, offline-capable
ai/verify.py          gates G1–G7 — no model is ever called from this file
api.py                FastAPI over the cached artefacts
web/                  Vite + React + Cytoscape
```

Design docs: `CLAUDE.md` (domain rules), `AI_ARCHITECTURE.md` (the verification contract),
`DESIGN.md` (forward-looking spec), `CHECKLIST.md` (what was built and what was learned the hard
way, including every measurement that corrected an assumption).

---

## Credits

Corpus: **[orgpedia/mahGRs](https://github.com/orgpedia/mahGRs)** (MIT) — 96,617 Government
Resolutions with OCR, paragraph and table detection, and IndicTrans2 translation. That ingestion
work is theirs and it is excellent; we did not rebuild it. **The graph, and everything computed on
it, is ours.**
