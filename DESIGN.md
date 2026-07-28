# DESIGN — steps 3 to 10

What I intend to build, precisely enough to argue with before any of it is written.

`CLAUDE.md` holds the durable rules. `CHECKLIST.md` is the log of what is already done and what
was learned doing it. **This file is forward-looking only**: contracts, algorithms, and the places
where I could be wrong.

## How to read this file

Every factual claim carries its provenance. If a claim has no tag it is a design decision, not a
fact about the corpus.

| tag | meaning |
| --- | --- |
| `[MEASURED]` | I ran it on this corpus. The command is given or is in `CHECKLIST.md`. Trust it. |
| `[ESTIMATE]` | Extrapolated from something measured. The reasoning is shown. Could be off. |
| `[ASSUMPTION]` | Load-bearing belief I have **not** verified. Each one is a place the design breaks if wrong. |
| `[UNKNOWN]` | I do not know and have not tried to find out yet. |
| `[DECIDE]` | Needs your call, not mine. Collected again at the end. |

**Fixture counts do not generalise.** `fixtures/` was deliberately selected for pathologies
(`select_fixtures.py`), so it over-represents heavy citing, supersession and amendment language by
construction. Any rate quoted from 55 fixtures is a rate *on the fixtures*, never a corpus rate.
This is the single easiest way for this project to fool itself.

---

## Where things actually stand

Done and tested: steps 0–2.

| artefact | what it is | provenance |
| --- | --- | --- |
| `data/mahGRs/` | sparse clone, 4 departments | step 0 |
| `data/devanagari_leak_map.json` | 75-type leak vocabulary | step 1 |
| `out/parsed.json` | parser output over fixtures | step 1 |
| `out/resolved.json` | **239 citation rows, 26 resolved** `[MEASURED]` | step 2 |
| `tests/test_resolver_invariants.py` | 14 zero-label property tests, passing `[MEASURED]` | step 2 |

`out/resolved.json` row shape, as actually emitted:

```jsonc
{ "src_uid": "201803071449402308",
  "raw": "शासन निर्णय क्र. मुवाढ-२०१६/(३८/१६)/मशि-१, दिनांक १३.१०.२०१७.",
  "cited_no": "मुवाढ-२०१६/(३८/१६)/मशि-१", "cited_date": "2017-10-13",
  "cited_dept": null, "is_gr": true, "same_no": false,
  "resolved_uid": "201710131542059108", "confidence": 0.97,
  "reason": "exact number + date within ±3d (+0d)", "candidates": ["201710131542059108"] }
```

Note what is **not** in it: no edge type, and no operative sentence beyond the citation itself.
Both are step 3's job, and the second one is harder than it looks — see 3.3.

**Known gaps carried forward.** No `Makefile`, which `CLAUDE.md` requires for every pitch number.
Two `parser.py` defects logged in `CHECKLIST.md` (bare date returned as `decision_no`; decision
number truncated at the first comma). Neither blocks step 3; both degrade the English witness.

---

## Step 3 — Graph

### 3.1 What it consumes and produces

New file `graph.py`. Consumes `out/resolved.json` plus the corpus index. Produces
`out/graph.json`, and that is the only thing steps 4, 5 and 9 read.

```jsonc
{
  "meta": { "built_at": "...", "corpus": "...", "departments": ["..."],
            "window_days": 3, "resolver_version": "..." },
  "nodes": [
    { "uid": "201710131542059108", "date": "2017-10-13", "dept_code": "08",
      "dept": "Higher and Technical Education Department",
      "decision_no": "मुवाढ-२०१६/(३८/१६)/मशि-१", "subject": "...",
      "in_corpus": true }
  ],
  "edges": [
    { "src": "201803071449402308", "dst": "201710131542059108",
      "type": "REFERENCES", "confidence": 0.97,
      "evidence": "शासन निर्णय क्र. मुवाढ-२०१६/(३८/१६)/मशि-१, दिनांक १३.१०.२०१७.",
      "evidence_en": "Government Decision No. Muwad-2016/(38/16)/Mashi-1, dated 13.10.2017.",
      "evidence_kind": "citation | operative_sentence",
      "cue": null, "cue_lang": "mr" }
  ],
  "unresolved": [
    { "src": "...", "cited_date": "...", "cited_no": "...",
      "why": "outside_range | other_dept | series_gap | no_number | not_a_gr",
      "candidates": ["..."] }
  ]
}
```

Three deliberate departures from the `CLAUDE.md` edge contract, all additive:

- `evidence_en` alongside `evidence`. `CLAUDE.md` rule 1 makes Marathi operative, so `evidence`
  is Marathi. But a judge cannot read it. The English is a **display convenience and is labelled
  as such**; it is never what a decision is made from.
- `evidence_kind` records whether the sentence is the citation itself or a separate operative
  sentence, because those carry different weight (3.3).
- `unresolved[]` is kept **in the graph file**, not discarded. Rule 3 says an unresolvable
  citation must be visible as unresolvable. Dropping these would make the graph look complete and
  would quietly delete the step 4 caveat.

`in_corpus` exists because step 4 needs to distinguish "cites an order we do not have" from
"cites an order that was superseded". Conflating those two is the single biggest credibility risk
in this project and 4.3 is about nothing else.

### 3.2 Nodes

One node per GR in the index, not only per GR that appears in an edge. Isolated nodes are a real
finding (a GR nothing cites), and building nodes from edges alone would erase them.

Source of truth: `GRs.json` for `decision_no` and `subject`; uid prefix for `date` per
`CLAUDE.md`. No body parsing needed. `[MEASURED]` 4,718 GRs indexed for HTE.

### 3.3 Edge typing — the part I expect to get wrong first

`REFERENCES` is free: every resolved row is one, and `raw` is already its evidence.

`AMENDS` and `SUPERSEDES` are **not** free, and my earlier assumption that they would be was
wrong. I measured it before writing this.

#### The cue vocabulary, and how it was validated

**I do not read Marathi.** Every gloss below started as model knowledge, which is not evidence. It
was then validated against the corpus, and the validation changed the vocabulary — two entries I
had asserted turned out to be wrong and one I did not have turned out to be real.

The method needs no Marathi on my part: the corpus is **parallel**, so for a candidate token the
question "does this mean cancel?" becomes "do GRs containing it carry English cancellation
language far above its base rate?" `[MEASURED]` over 900 randomly sampled aligned HTE pairs
(`seed=0`). English base rates in that sample: SUPERSEDE 15.6%, AMEND 13.4%, CONTINUE 83.4%.

| token | gloss | GRs | best class | lift | verdict |
| --- | --- | ---: | --- | ---: | --- |
| `रद्द` | cancel / annul | 112 | SUPERSEDE (95%) | ×6.08 | **use** — strongest cue in the corpus |
| `सुधारणा` | amendment | 61 | AMEND (64%) | ×4.76 | **use** |
| `अंशत` | partially | 11 | AMEND (64%) | ×4.73 | **use** |
| `व्यपगत` | lapsed | 15 | SUPERSEDE (67%) | ×4.29 | **use** — see note below |
| `अधिक्रमित` | superseded | 12 | SUPERSEDE (58%) | ×3.75 | use; rare and weaker |
| `शुद्धिपत्रक` | corrigendum | 1 | — | — | too rare to judge; keep, expect ~nothing |
| `पुढे चालू` | continuation | 69 | CONTINUE | ×1.20 | **drop — refuted** |
| `स्थगित` | stayed / suspended | 6 | — | ×1.24 | drop, no lift |
| `खारीज` | rejected | 1 | — | ×0.00 | drop |
| `अधिक्रमून`, `मागे घे`, `निरंतर` | — | 0 | — | — | **absent in 900 GRs; my guesses. dropped** |

Three corrections this forced, each worth keeping visible:

- **`पुढे चालू` is not a cue.** Only 3% of its 69 GRs carry supersession language and 4% carry
  amendment language. And CONTINUE has an **83.4% base rate** — continuation language is in nearly
  every GR, so the whole class is undiscriminating. An earlier draft of this table listed it with a
  count, implying signal it does not have.
- **`अंशत` was reported as 0 and is not 0.** 0/55 fixtures, 11/900 corpus. This is precisely the
  false negative the "fixture counts do not generalise" warning at the top of this file predicts,
  committed two sections after writing that warning. **Cue vocabulary must be measured on the
  corpus, never on `fixtures/`.**
- **`व्यपगत` (lapsed) was missing entirely** and is real at ×4.29. It may be how this corpus
  expresses a GR expiring by its own terms, which is the open `[UNKNOWN]` in §4.2 about whether
  "in force" is overstated. Worth following up there specifically.

**The limit of this validation, stated because it is easy to oversell.** The English side is
IndicTrans2's machine translation *of the same Marathi*. So agreement confirms **the translator's
reading** of a token, not ground truth. It is far stronger than an unverified gloss — a
purpose-built Marathi system, consistent across 112 documents for `रद्द` — but it is *not* an
independent witness in the sense the resolver's cross-language check is, where the two sides have
genuinely uncorrelated failure modes. It is the same caveat `CLAUDE.md` attaches to parity
checking, and it applies to every Marathi term in this project.

`[DECIDE]` **A native Marathi reader should sanity-check the six-token shortlist.** Unlike
`resolver_truth.json` this is not a labelling task — it is confirming six words mean roughly what
the table says, which is minutes. It is the cheapest correction available to the component most
likely to be wrong.

**Standing rule for this project: no Marathi token enters the codebase on my say-so.** Any new
term gets the alignment test above, on the corpus, with its lift recorded, before it is used.

`[MEASURED]` and this is the finding that matters: of **40 cue-bearing sentences across 22
fixtures, only 11 (28%) also contain a citation** — and inspecting those 11 shows the cue is
often not a verb at all:

```
११) ... पत्र क्र.५(३)/आस्थायीपदे/पुढे चालू/ २०१७/३८९, दिनांक १९.०८.२०१७
                            └─ "पुढे चालू" is inside a FILE NUMBER
१२ (भाग-२)/२००४/वित्तीय सुधारणा-१ दिनांक ०४.१०.२००४
                    └─ "वित्तीय सुधारणा-१" = "Financial Reforms-1", a SECTION CODE
```

Two consequences, both design-level:

1. **A cue word anywhere in the document must never type an edge.** A GR that cancels one order
   and cites nine others would emit nine `SUPERSEDES` edges. Cue and citation must co-occur in
   the same sentence, and the sentence must be the evidence.
2. **The cue vocabulary needs a reject list before it needs more entries.** `सुधारणा` and
   `पुढे चालू` both occur inside identifier strings. The existing `MR_NO_REJECT` pattern in
   `resolver.py` is the precedent: reject inside a number region first, then match.

So step 3 ships edge typing in this order, and **stops** at whichever rung the evidence supports:

- **3a.** `REFERENCES` for all 26 resolved rows. Deterministic, no cue needed. This is the graph.
- **3b.** `SUPERSEDES` / `AMENDS` only where a cue and a resolved citation share a sentence **and**
  the cue is not inside an identifier. Typed edge carries the cue and the full sentence.
- **3c.** Everything else stays `REFERENCES`. An untyped edge is honest; a wrongly-typed one
  corrupts steps 4, 5 and 9 simultaneously, because all three read edge *type*.

`[ASSUMPTION]` I can sentence-split Marathi well enough for 3b by splitting on danda `।`,
newline, and `. ` followed by whitespace. My probe used exactly that and it did not obviously
mangle anything, but I did not check it properly. If it turns out unreliable, 3b's precision
collapses and the fallback is paragraph-scoped co-occurrence, which is weaker.

`[UNKNOWN]` What fraction of the full HTE corpus gets a typed edge. `CLAUDE.md` records 14.7%
supersession and 10.7% amendment language **on the English side, document-level** — that is
presence of a cue *somewhere*, not attributable typing, so it is an upper bound and probably a
loose one. Given the 28% co-occurrence figure, `[ESTIMATE]` real typed-edge yield is single-digit
percent of GRs. I would rather find that out and report it than promise it.

### 3.4 How step 3 is tested

Same zero-label approach as step 2, in `tests/test_graph_invariants.py`:

- every edge's `src` and `dst` exist in `nodes`
- no self-edges; no edge pointing forward in time beyond the ±3d publication-drift window
- every edge has non-empty `evidence`, and that evidence string **actually occurs** in the source
  GR's Marathi text — this is the test that makes the "every edge carries evidence" promise real
  rather than decorative
- every typed (`AMENDS`/`SUPERSEDES`) edge has a non-null `cue`, and that cue occurs inside its
  own evidence sentence
- edge count + `unresolved` count equals the input row count: nothing silently vanishes
- rebuilding gives byte-identical output (rule 4)

`[DECIDE]` Whether to hand-check the typed edges once. There will be few enough of them
(`[ESTIMATE]` under 20 on fixtures) that you could eyeball every one in ten minutes, and unlike
`resolver_truth.json` this is not a labelling task — it is reading a sentence and saying yes or
no. It is the cheapest available guard on the highest-risk component.

---

## Step 4 — Dead-reference audit (the demo)

### 4.1 The claim I want to be able to make

> "We ran this over N departments and found **M GRs currently in force that cite orders which no
> longer exist.**"

Everything in 4.2 and 4.3 exists to make that sentence survive a hostile question from someone
who has worked in Mantralaya for twenty years.

### 4.2 Operational definitions

Neither "in force" nor "no longer exists" is in the data. Both are definitions I am choosing, and
the demo must show the definition next to the number.

**In force** := the GR has no incoming `SUPERSEDES` edge.

That is a *lower bound on deadness and an upper bound on in-force*. It misses: GRs superseded by
an order outside the corpus; GRs that expired by their own terms (a scheme "valid up to
31.03.2020"); GRs superseded silently, with no supersession language. `[UNKNOWN]` how common
self-expiring GRs are — worth measuring, because if it is common, "in force" is materially
overstated and I would rather weaken the wording than defend it on stage.

**No longer exists** := the cited target has an incoming `SUPERSEDES` edge whose source is dated
**after** the citing GR was issued.

The `after` is the whole point. Two different situations:

| situation | what it means | is it a finding? |
| --- | --- | --- |
| G cites T; T superseded **after** G issued | G was correct when written and has silently rotted | **Yes — this is the finding** |
| G cites T; T superseded **before** G issued | G cited a dead order on day one — a drafting error | Yes, but a different, rarer, stronger claim |

I will compute and report both, separately, because they say different things and merging them
would blur the headline.

### 4.3 The trap I will not walk into

There is a much larger and much more tempting population: citations that resolve to **nothing**.
`[MEASURED]` on fixtures: 85 `outside_range`, 24 series-gap, 11 with no file number.

**These are not dead references and must never be counted as such.** `CLAUDE.md` records the
in-range gap finding: a citation dated 16.01.2018, inside HTE and inside the crawl window, whose
target is simply not in the crawl. The honest explanation for almost all 85+24 is **corpus
incompleteness, not legal deadness.**

Counting them would roughly quadruple the headline number and make it false. They get their own
clearly-labelled bucket, `unverifiable_reference`, and the demo says so out loud. The scope
report in `resolver.py` is the precedent for this and step 4 reuses that discipline.

`[ASSUMPTION]` that judges respect a smaller honest number over a bigger soft one. I think this
is right for government judges specifically, and `CLAUDE.md`'s pitch framing already commits to
leading with a finding. If you disagree, say so now — it changes what step 4 optimises for.

### 4.4 The scale problem, stated plainly

`[MEASURED]` The fixtures yield 26 resolved edges. **You cannot build a headline on 26 edges.**
`SUPERSEDES` edges will be a small fraction of those, so the fixture-scale audit will very
plausibly find **zero** dead references. That is not a bug and it is not a reason to loosen the
definitions.

`[ESTIMATE]` Full HTE: `CLAUDE.md` records 49.0% of GRs citing a prior dated order. Fixtures
average 4.3 citations each but are enriched for citing, so assume ~1.5 citations per GR
corpus-wide → **~7,000 citations over 4,715 GRs**. Across all four departments `[ESTIMATE]`
~25,000 citations over 17,253 GRs. Both numbers are extrapolations and I will replace them with
`[MEASURED]` ones the first time the batch runs.

Widening also *directly* shrinks the two biggest unresolvable buckets: `other_dept` (26 on
fixtures, all Finance / GAD / Home / PWD / Social Justice / Revenue — `[MEASURED]`) and part of
`outside_range`. This is why the full run is not optional polish; it is what makes step 4 have a
number at all.

**Therefore step 3 must be written to run over the whole corpus from the start**, not over
fixtures with a "scale it later" note. Fixtures stay the development loop per `CLAUDE.md`; the
batch run is committed under `out/`.

`[UNKNOWN]` runtime of a full four-department run. Reading ~400 MB of Marathi text plus regex
extraction — `[ESTIMATE]` minutes, not hours, and it is a one-time cached job, so even an hour
would be acceptable. Not worth optimising before it has run once.

---

## Steps 5–10 — shape only

These are real but less pinned down, and I would rather commit to detail after step 4 produces a
number, because that number decides what is worth building.

### Step 5 — Supersession chains, "as-amended" text

Walk `SUPERSEDES`/`AMENDS` edges transitively to get, for any GR, the chain that led to the
version in force. `[ASSUMPTION]` the chains are shallow — most supersession is one hop.
`[UNKNOWN]` whether cycles occur; if they do it is a **finding**, not a bug to paper over, and it
gets reported. Consolidated "as-amended" text is the genuinely hard part because it needs to know
*which clause* an amendment replaces, and I do not have clause-level alignment. `[DECIDE]`
whether to attempt real text consolidation or ship a side-by-side chain view, which is far
cheaper and nearly as convincing in a demo.

### Step 6 — GR-Lint

Template rules mined from the corpus skeleton, **not** copied from the Manual of Office
Procedure. The 136-GR boilerplate family in `CLAUDE.md` is the mining seed: 136 documents sharing
verbatim structure is a template definition handed to us. Numbered rule codes, line numbers,
auto-fix suggestions. Must handle the displaced-ordinal bug (`The 1.सदर approval...`) since that
is exactly the family being mined.

### Step 7 — Obligations → conflict detection

The first place an LLM is allowed (`CLAUDE.md` rule 4), and only for extraction into the
`obligation` contract. Conflict detection over the extracted structure stays deterministic:
same actor + overlapping scope + overlapping effective window + contradictory amount or
condition. `[ASSUMPTION]` the interesting conflicts are numeric (two live GRs setting different
rates for the same thing), because those are checkable without semantics. `[DECIDE]` which local
model, given the offline-demo constraint — a cloud call cannot be in the demo path at all.

### Step 8 — Bilingual parity

Already scoped in `CLAUDE.md`: normalise hard, then **classify** rather than flag — magnitude
error vs table-merge artefact vs list-numbering noise. Carries a mandatory caveat: the English
side is machine translation, so this measures translation fidelity, not divergence between two
official texts. Do not overstate it.

### Step 9 — Blast radius

Given draft text, extract its citations, resolve them, and report what the draft touches: which
in-force GRs cite the orders this draft supersedes. Reuses steps 2–5 wholesale; almost no new
logic. This is the feature that makes the graph feel like a tool rather than an analysis.

### Step 10 — Drafting UI

Thin. Offline, cached artefacts only. Its job is to make steps 4 and 9 legible in ninety seconds.
`[DECIDE]` form factor.

---

## Cross-cutting, before or alongside step 3

1. **`Makefile`.** `CLAUDE.md` requires every pitch number reproducible by one command. Does not
   exist. Should exist before there are numbers worth quoting, not after.
2. **Corpus widening.** Batch run of steps 1–3 over all four departments. No new code.
3. **Offline check.** Confirm the demo path touches no network. Cheap to verify, fatal to skip.

---

## Open questions for you

Collected `[DECIDE]` items. Nothing here blocks me from starting step 3a — I will proceed on the
stated defaults if you would rather answer later.

0. **Get a Marathi reader to confirm the six-token cue shortlist** (§3.3). Minutes, not a labelling
   task, and it guards the component most likely to be wrong. *Default if you say nothing: I
   proceed on the measured lifts, which are strong for `रद्द` and `सुधारणा` and thinner for the
   rest.*
1. **Hand-check the typed `AMENDS`/`SUPERSEDES` edges once?** `[ESTIMATE]` under 20 on fixtures,
   ~10 minutes of reading sentences. Not labelling — no truth file involved. It guards the
   component most likely to be wrong and most damaging when it is. *Default if you say nothing:
   I build 3b, print every typed edge with its sentence, and you glance at the list.*
2. **Smaller honest number vs bigger soft number for the step 4 headline.** I have designed for
   the former and I think it is right for government judges. Says so explicitly because it is a
   pitch decision, not an engineering one.
3. **Step 5: real "as-amended" text consolidation, or a side-by-side chain view?** Cost differs by
   roughly a day. *Default: chain view.*
4. **Step 7 local model choice**, given the demo cannot make a network call.
5. **Step 10 form factor.**

## What I will say on stage about limits

Writing these down now so they cannot quietly disappear later:

- "In force" means no supersession edge **in our corpus**. Orders superseded from outside it, or
  expired by their own terms, are counted as live.
- The English text is machine translation. Every legal conclusion is drawn from the Marathi.
- Unresolvable citations are reported as unresolvable, and most of them reflect gaps in the public
  crawl rather than anything wrong with the GRs.
- Edge typing is conservative: an edge we cannot type from a cue in the same sentence stays a
  plain reference.
