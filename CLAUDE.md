# MAHA-GR-ALIGN

AI-assisted Government Resolution drafting, alignment and conflict detection for the
Government of Maharashtra. Built for VJTI AI Hackathon 2026, Problem Area 1.

## The problem statement, verbatim — this is the scorecard

```
Maha GR Align: AI Assisted GR drafting and alignment
  - Cross Department Conflict Detection
  - Bilingual Legal Terminology (English)
  - Automated Reference Tracking
  - Strict Template Enforcement
Tagline: "streamline government resolution processing"
```

**Judges have a four-item list and will check off four items.** Depth on one bullet does not
substitute for absence on another; 4/4 adequate plausibly beats 1/4 beautiful. Track coverage
honestly and keep breadth ahead of further depth once a bullet is credible.

| bullet | maps to | note |
| --- | --- | --- |
| Cross Department Conflict Detection | graph (3) + conflict detection (7) | **needs a multi-department index.** A single-department resolver rejects cross-dept citations, i.e. does the opposite of this bullet |
| Bilingual Legal Terminology (English) | leak map (done) + parity (8) + mined term glossary | the corpus English is machine translation, so claims are about *translation* consistency, never two official texts |
| Automated Reference Tracking | parser (1) + resolver (2) + graph (3) | strongest area |
| Strict Template Enforcement | GR-Lint (6) | the 136-GR verbatim boilerplate family is the mining seed |

Note the framing that keeps these coherent rather than four separate demos: **all four bullets are
downstream of one missing artefact — the dependency graph.** Build it and the features fall out;
build the features without it and you get four shallow demos.

## STATUS — what exists right now (read this first)

Last updated 2026-07-28. **The deadline was extended**; a fresh evaluation document exists that
has not yet been read into this file.

Everything below is built, tested and committed. `make serve` → http://localhost:8000.

| layer | file | state |
| --- | --- | --- |
| Parser | `parser.py` | ✅ regex only, no LLM |
| Resolver | `resolver.py` | ✅ multi-department, two-key + digit key |
| Graph | `graph.py` | ✅ **17,283 nodes, 4,815 edges, 1,538 cross-dept**, builds in 10 s |
| AI edge typing | `type_edges.py` + `ai/` | ✅ batched, gated, cached. **33 SUPERSEDES, 169 AMENDS** |
| Dead-reference audit | `audit.py` | ✅ **24 dead references** (10 rotted, 14 born dead, **2 latent cross-dept**) |
| Blast radius | `api.py` `/api/blast/{uid}` | ✅ one Finance circular has **229 live dependents** across 3 other departments |
| GR-Lint | `lint.py` | ✅ rules mined per department, **76.5% of GRs clean** |
| Bilingual | `bilingual.py` | ✅ **335 magnitude errors**, 26 inconsistently-rendered terms |
| Metrics | `metrics.py` | ✅ every pitch number, one command |
| API + UI | `api.py`, `web/` | ✅ FastAPI + Vite/React/Cytoscape, 6 pages |
| Tests | `tests/` | ✅ **41 passing, zero API calls** (`conftest.py` forces `AI_MODE=strict`) |

**The demo makes no AI calls.** `api.py` contains no model-calling code at all; every AI output is
precomputed, verified, and committed under `out/` and `out/ai_cache/`. Verified by replaying the
whole typing pass with `AI_MODE=strict` and getting identical results.

Docs: `README.md` (for judges) · `DEMO.md` (3-min script + answers to hard questions) ·
`AI_ARCHITECTURE.md` (the seven gates) · `DESIGN.md` (forward-looking spec) · `CHECKLIST.md`
(what was built and every measurement that corrected an assumption) · `Makefile`.

### Known gaps / next up

1. **The new evaluation document has not been read.** Do that before building anything else — it
   may reassign priorities.
2. **~380 of 718 candidate edges are still untyped**, purely from the token cap. `make type-edges`
   then `make audit` grows the dead-reference count with no code change.
3. **OWED to the user: the precision audit.** ~50 edges, human yes/no, ~15 min. Converts
   `metrics.json`'s `accuracy: UNMEASURED` into a real number. They asked to be reminded.
4. **Obligation-level conflict detection** (step 7) is the one problem-statement bullet only
   partly addressed — cross-departmental *dependency* is done, semantic *contradiction* is not.
5. STT and vision models are wired in `ai/client.py` but **never tested**.

### Operational facts that cost time to learn

- Groq's daily token cap is **per ORGANISATION, not per key** — new API keys do not reset it.
- Groq needs `max_completion_tokens`, not `max_tokens`; a default `Python-urllib` User-Agent is
  rejected by Cloudflare with `403 error code: 1010`.
- **60% of tokens were prompt tokens** before batching. Batch, don't loop.
- `pkill -f 'uvicorn api:app'` **matches the shell running it** — use `pkill -f "uvi[c]orn"`.
- Running `make graph` alone resets `graph.json` to REFERENCES-only and the audit then finds
  nothing. Re-run `make type-edges` (needs quota) or restore from git.

## The thesis (read this before writing any code)

A Government Resolution is **not a document, it is a node in a legal dependency graph.**
Every GR amends, supersedes, references, or silently contradicts prior GRs. Maharashtra has
issued lakhs of them since 1960 and there is no machine-readable representation of that graph
anywhere.

Everything we build follows from that reframing. If a proposed feature does not depend on the
graph, it is probably the commodity submission every other team is building — deprioritise it.

## Non-negotiable domain rules

1. **Marathi is authoritative.** The `.mr.txt` files are the legally operative text. English is
   a derived working view. Never resolve a legal question from the English side alone.
2. **The English text is machine translation and it leaks.** Expect Devanagari fragments inside
   English output (e.g. `The 1.सदर approval will always be...`, where `सदर` = "the said").
   Strip/flag these; never present them as clean output.
3. **Never fabricate a citation.** Every GR reference surfaced to a user must resolve to a real
   uid in the corpus, or be explicitly labelled `unresolved / outside corpus`. A hallucinated
   legal citation is a total credibility failure in this domain.
4. **The model proposes, the corpus verifies.** Nothing a model asserts reaches a user until a
   deterministic gate has checked it against the corpus — see `AI_ARCHITECTURE.md` for the six
   gates and `ai/verify.py` for the implementation. Corollaries, all binding:

   - **Facts we can compute are never generated.** Citation resolution, dates, digit-key
     matching, graph traversal, supersession chains, lint verdicts, and *every number in the
     pitch* are computed. A model may explain a finding; it may not be the reason we believe it.
   - **AI goes where determinism provably fails**, and the measurement that proves it gets
     recorded. Edge typing qualifies: cue-word matching hits 28% co-occurrence and false-positives
     on file numbers (`वित्तीय सुधारणा-१` = "Financial Reforms-1"), which is a semantic
     distinction regex cannot make.
   - **Temperature 0, cached, committed.** Reproducibility is a requirement. `AI_MODE=strict`
     forbids the client from opening a socket, so the demo is offline by construction.
   - **Rejections are published, not swallowed.** A blocked hallucination is a finding about the
     system and belongs in the Trust Ledger with the gate that caught it.
   - **Degrade, never fake.** If a model is unavailable or its output fails a gate, show the
     deterministic result and say the model did not contribute. "The model was unavailable" is a
     legitimate state to display.

   An earlier version of this rule read "LLMs are used only for obligation extraction and draft
   text generation." That was too narrow — it ruled out the places AI is genuinely needed and,
   at an AI hackathon, understated the work. The intent (never let a model assert what we could
   compute) is preserved above and is now mechanical rather than a matter of restraint.
5. **No Marathi term enters the codebase on an assistant's say-so.** Claude does not read Marathi.
   A gloss from model knowledge is a hypothesis, not evidence, and a wrong one fails *silently* —
   the code runs, the edges are typed, the graph is confidently wrong. Every Marathi token used as
   a signal must first be validated against the corpus and its result recorded:

   Take a random sample of aligned `.mr` / `.en` pairs (900 is enough), and ask whether GRs
   containing the token carry the corresponding English cue class **far above that class's base
   rate in the same sample**. Keep tokens with a strong lift, drop the rest, and write the lift
   next to the token so a later reader can see what it rests on. `DESIGN.md` §3.3 is the worked
   example: it confirmed `रद्द` (×6.08) and `सुधारणा` (×4.76), **refuted** `पुढे चालू` (×1.20,
   because CONTINUE has an 83.4% base rate and discriminates nothing), and surfaced `व्यपगत`,
   which was missing from the hand-written list entirely.

   Two failure modes this rule exists to catch. **Measure on the corpus, never on `fixtures/`** —
   `अंशत` reads 0/55 on fixtures and 11/900 on the corpus, so fixtures produce false negatives for
   vocabulary work by construction. And **a 0 count is ambiguous**: it means either "absent from
   the corpus" or "wrong word", and those must not be reported as the same thing.

   Its limit, which must be stated wherever the result is used: the English side is machine
   translation *of that same Marathi*, so this validates the translator's reading, not ground
   truth. It is not an independent witness the way the resolver's cross-language check is. Where a
   human Marathi reader is available, a shortlist confirmation takes minutes and is worth asking
   for.

## Data: verified facts, do not re-derive

Source: `https://github.com/orgpedia/mahGRs` (MIT licence, credit it in the README and the deck).
96,617 GRs across 33 departments. Every GR has a Marathi original **and** an English translation
(OCR + paragraph detection + table detection + IndicTrans2). **The OCR problem is already solved
— do not build an OCR pipeline.**

Pull with a partial + sparse clone, never a full clone:

```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/orgpedia/mahGRs.git
cd mahGRs
git sparse-checkout set \
  "GRs/Higher_and_Technical_Education_Department" \
  "GRs/General_Administration_Department" \
  "GRs/Finance_Department" \
  "GRs/School_Education_and_Sports_Department"
```

Filenames are `<uid>.pdf.<lang>.txt`. The uid encodes `YYYYMMDD` + upload time + a 2-digit
department code (`08` = Higher & Technical Education).

Measured on the HTE department (4,715 GRs, Oct 2017 – Jun 2026, 107 MB):

| signal | coverage |
| --- | --- |
| bilingual pairs, zero unpaired | 4,715 / 4,715 |
| explicit `Date:` line | see **Dates** below — the 75.9% figure was wrong |
| `Government Decision No.` present | 66.3% |
| enumerated `Reference:` block | 51.6% |
| cites a prior dated order | 49.0% |
| supersession language (cancel / repeal / withdraw / rescind) | 14.7% (692 GRs) |
| amendment language (amend / partially / in continuation) | 10.7% (504 GRs) |

Typical GR skeleton, in order: subject line, issuing authority, `Government of Maharashtra`,
department name, `Government Decision No. <no>`, Mantralaya address, `Date: - DD.MM.YYYY`,
`Reference: - 1) ... 2) ...`, `The Proposal: -`, `The Government's Decisions:`, numbered
conditions, signatory block.

## Known traps

**Same-date collision.** Resolving citations by date alone links every GR issued that day. A
naive date-only resolver produced 19,840 edges with five different GRs falsely tied at in-degree
292. **The resolver must match the decision-number string alongside the date.** This is the
single highest-value correctness problem in the project.

**Same-number collision — the mirror trap. Neither key is sufficient alone.**
`order_number` / `Government Decision No.` is a **departmental file number, not a unique GR
identifier.** Measured on HTE: 4,662 GRs carry one but only 3,326 are distinct — **41.1% of GRs
share their number with at least one other GR**, worst case 41 GRs on a single number. A file
accumulates decisions over years, so fixture `201803071449402308` cites *six* GRs under
`Muwad-2016/(38/16)/Masi-1` spanning Apr 2016 → Jan 2018, and carries that same number itself.

Consequences for the resolver, all load-bearing:

- Date alone collides, number alone collides. **The key is the pair**, and candidate retrieval
  must run *both* paths — the ±3-day window *and* every GR sharing the number at any date —
  because a series member routinely sits far outside the window (observed for one citation's
  siblings: −95d, +252d, +416d, +1331d).
- **Match numbers on their digit key, not their string.** Metadata `order_number` is 97.6%
  Devanagari while citations in the English text are transliterated Latin, so no string match can
  ever connect them. Digits are script- and transliteration-independent:
  `Muwad-2016/(38/16)/Mashi-1` and `मुवाढ-२०१६/( ३८/१६ )/मशि-१` both reduce to `201638161`.
  Canonical implementation is `resolver.digit_key()`; `label_citations.py` imports it rather than
  defining its own, so the tool and the resolver cannot drift on what "same file number" means.
- **Concatenate the digits; do not keep them as a tuple of runs.** Marathi OCR inserts spaces
  inside Devanagari digit runs, so run boundaries are an OCR artefact while the digit sequence is
  not: `( १२ ९/१३ )` segments as `2013|12|9|13|2` where the English `(129/13)` segments as
  `2013|129|13|2`, and a tuple comparison calls those different files. Concatenated, both are
  `201312913`. The cost of concatenating is 12 keys out of 3,252 — measured, and all 12 are
  exactly these spacing variants, i.e. merges that *should* happen. 3,240 distinct keys over
  4,645 numbered GRs, so it still retrieves tightly.
- Transliteration is unstable across GRs for the *same* file (`Masi-1` / `Mashi-1` / `MASHI-1`) —
  a second, independent reason string matching fails.

**The corpus has in-range, in-department gaps.** The `Muwad` citation above is dated 16.01.2018,
inside the corpus range and inside HTE, yet no member of that file series carries that date —
nearest are 2017-10-13 and 2018-09-25. The cited GR is simply not in the crawl. So
`unresolved` is the *correct* label for some citations that look perfectly resolvable, and a
resolver scored on "did it find something" rather than "did it find the right thing" will reward
fabrication. This is what rule 3 exists for.

**Citations leaving the corpus.** ~53% of dated citations in HTE point outside HTE's own range.
That is not a bug — cross-departmental references are the point of the problem statement. Widen
the corpus rather than suppressing them, and label genuinely unresolvable ones honestly.

**Bilingual parity false positives.** A naive numeric diff between `.en` and `.mr` flags 99.5%
of pairs, almost all tokenisation noise (`1983,` vs `1983`, trailing periods, lakh-crore comma
grouping, Devanagari numerals). Normalise hard — strip punctuation, unify digit systems, collapse
comma grouping — before flagging anything. Real divergences exist and are the whole point
(one sampled pair had `33,54,00,000` present in Marathi and absent in English); they are
worthless if buried under noise.

## Interface contracts — fix these before parallel work begins

Every module reads and writes these shapes. Do not change one without changing all consumers.

```jsonc
// GR record — output of the parser
{
  "uid": "202606091837205608",
  "dept_code": "08",
  "dept": "Higher and Technical Education Department",
  "decision_no": "1681439-HTED - 14025/08/2026 - MHT (TE-5)",
  "date": "2026-06-09",
  "subject": "...",
  "references": [ { "raw": "...", "decision_no": "...", "date": "2026-05-08",
                    "resolved_uid": "2026...", "confidence": 0.93 } ],
  "body": [ { "para_no": 1, "text": "...", "page": 1 } ],
  "conditions": [ { "n": 1, "text": "..." } ],
  "amounts": [ { "raw": "33,54,00,000", "value": 335400000, "currency": "INR" } ],
  "lang": "mr",
  "artifacts": [ "devanagari_in_en_translation" ]
}

// Graph edge
{ "src": "<uid>", "dst": "<uid>", "type": "REFERENCES|AMENDS|SUPERSEDES",
  "evidence": "verbatim sentence that justified this edge", "confidence": 0.87 }

// Obligation record — input to conflict detection
{ "uid": "<uid>", "actor": "...", "action": "...", "condition": "...",
  "amount": 335400000, "effective_from": "2026-07-01", "scope": ["..."] }
```

Every edge carries `evidence`. If we cannot show the judge the sentence that produced an edge,
the edge does not ship.

## Fixtures — `select_fixtures.py` and `fixtures/`

### What it is

`fixtures/` is a 52-GR working set (104 files, Marathi + English) mined out of the 4,715-GR
HTE corpus by `select_fixtures.py`. **All parser, resolver, graph and lint development iterates
against `fixtures/`.** Full-corpus runs are batch jobs, never interactive work.

Do not read the full corpus into context. It is 107 MB of text for one department and roughly
400 MB across the four we ingest. Loading it wastes the session and teaches you nothing that
the fixtures do not.

### How fixtures were chosen

They were not hand-picked. The script defines the **pathologies the parser must survive**,
scores every GR in the corpus against each one, and takes the worst offenders. Selection is
therefore deterministic and reproducible — rerunning the script on the same corpus yields the
same 52 files.

Each bucket is `(name, filter, sort key, count)`. A GR already selected for one bucket is
skipped for later buckets, so the set is de-duplicated and every file earns its place.

Measured pool sizes on HTE (this is what the corpus actually looks like — trust these over
intuition):

| bucket | what it stresses | pool | taken |
| --- | --- | ---: | ---: |
| `many_references` | reference-block parsing, ≥5 enumerated items (max seen: 19) | 533 | 5 |
| `devanagari_leakage` | Devanagari surviving into the English translation | 8 | 6 |
| `supersession` | cancel / repeal / rescind / withdraw language → `SUPERSEDES` edges | 692 | 6 |
| `amendment` | amend / partially / in continuation → `AMENDS` edges | 504 | 5 |
| `numeric_divergence` | normalised numeric token mismatch between `.mr` and `.en` | 2,184 | 6 |
| `no_date_line` | no line-anchored `Date:` — in practice the body date is unusable everywhere, see **Dates** | 1,135 | 4 |
| `no_reference_block` | 48% have no `Reference:` block; citations appear inline in the body | 2,280 | 4 |
| `no_decision_no` | no `Government Decision No.` string to key on | 1,589 | 3 |
| `very_long` | ≥6 pages, multi-page tables, page-break artefacts | 407 | 4 |
| `heavily_citing` | ≥3 distinct dated citations → dense graph neighbourhoods | 476 | 5 |
| `clean_baseline` | all fields present, minimal noise — the happy path | 1,501 | 4 |

The three "missing field" buckets are the important ones. A parser built only against
well-formed GRs will silently drop a quarter to a half of the corpus.

### `manifest.json`

Written into `fixtures/`. Contains `source`, `total_scored`, `selected`, a `buckets` map of
bucket name → list of uids, and a `records` map of uid → its full computed score dict
(`n_refs`, `n_citations`, `devanagari_leak_ratio`, `has_date_line`, `has_decision_no`,
`has_ref_block`, `supersedes`, `amends`, `n_pages`, `len_en`, `numeric_divergence`,
`divergent_en_only`, `divergent_mr_only`).

When a test fails, look up the uid in `manifest.json` to see which pathology it was selected
for. That tells you what the failure means.

### The rule that must not be broken

**Fixtures are inputs. They are not ground truth.**

The resolver's expected outputs — which uid each citation actually resolves to — are
hand-labelled by a human in `tests/resolver_truth.json`. Do not generate, extend, "correct",
or infer entries in that file. If code and answer key are both machine-produced, passing tests
prove only self-consistency, and the graph will be confidently wrong.

If `tests/resolver_truth.json` lacks a case you want covered, say so and stop. Do not add it.

### Validating without labels — what labelling does and does not gate

Hand-labelling is **required for one thing only: an accuracy number.** It does *not* gate building
the resolver, and treating it as a blocker stalls the build for no benefit. `tests/resolver_truth.json`
being absent is not a reason to stop; it is a reason to not claim a percentage.

What runs instead is `tests/test_resolver_invariants.py` — 14 property tests that need no answer
key because they assert facts that hold whatever the right uid turns out to be: a GR cannot cite
itself, cannot cite an order issued after it, a resolved uid must exist in the corpus, no
resolution may rest on a date alone, ambiguity must abstain rather than pick, a number matching a
series with no member in the window must stay unresolved, and the same input must give the same
output. These make whole classes of bug impossible. They cannot tell you the resolver is *right*.

The strongest of them is **cross-language agreement**, and it is worth understanding why it counts
as evidence rather than as a second run of the same logic. The Marathi path matches Devanagari file
numbers against crawled portal metadata; the English path sees IndicTrans2 output with
transliterated, unstable section codes. **Their failure modes are uncorrelated.** So where both
sides see the same cited date, the English digit key must not contradict the resolved target's
number. Abstention on either side is fine — contradiction is a bug. Compare with *containment in
either direction*, not equality: IndicTrans2 reorders number components and `parser.py`'s capture
stops at the first comma, so the English key is sometimes a truncation. Dropping digits is
transcription loss; substituting them means a different file, which containment still rejects. It
stays discriminating — a mean of 3.6 GRs out of 4,718 are compatible with a given English key.

The honest way to report the resolver until labels exist: quote the **scope breakdown**, not a
resolution rate. `resolver.py` prints it (`scope_report`), and two tests keep the buckets exclusive
and exhaustive so the denominator cannot be gamed. Measured on the 55 fixtures, 239 Marathi
citations: 87 `not_a_gr` (letters, emails, notifications — there is no GR to find), 26
`other_dept`, 85 `outside_range`, **41 `in_scope`, of which 26 resolve (63.4%)**. A rate over all
239 would read 10.9% and would be just as wrong in the other direction. Never quote a bare
resolution rate; a resolver that guessed would score better on it, which is exactly the incentive
rule 3 exists to remove.

### Interpreting `numeric_divergence`

The score is a normalised token diff (Devanagari digits folded to ASCII, comma grouping and
trailing punctuation stripped). Normalisation matters: the naive version flags 99.5% of pairs,
the normalised version flags 46%. Among what remains there are at least three distinct classes,
and the parity checker must classify rather than merely flag:

- **Magnitude errors** — e.g. `100000` in English against `100000000` in Marathi, a factor of
  1000 repeated down a table column. Potentially a real, serious finding.
- **Table-cell merge artefacts** — e.g. Marathi `15682183.00` appearing as English `15682` and
  `183.00`. An OCR column-boundary artefact, not a semantic discrepancy. Suppress these.
- **List-numbering noise** — sequential small integers present on one side only. Suppress.

Caveat that constrains the feature's claim: the English side of this corpus is **machine
translation of the Marathi**, not the state's own English text. So divergences measure
translation fidelity, not drift between two official documents. Do not overstate this in output
or in the pitch unless official bilingual pairs are confirmed to exist.

### Regenerating

```bash
python select_fixtures.py GRs/<Department_Name> fixtures/
```

Fixtures are committed to the repo. Regenerate only when the corpus changes or a new pathology
is discovered; do not silently reshuffle the set mid-project, because the labelled resolver
truth file is keyed to these uids.

## Dates — take them from the uid, never from the body

**The uid filename prefix is the authoritative GR date.** Present for 100% of GRs, no parsing
required: `YYYYMMDD` at the start of the uid.

The `Date:` string in the body is **not usable**:

- Anchored to line start, only 261 / 4,715 GRs (5.5%) yield a parseable date.
- Unanchored across the first 1,800 chars, 382 / 4,715 (8.1%) — and **78% of those disagree with
  the uid prefix**, because the pattern captures a *cited* date out of the reference block rather
  than the document's own date. Observed: a 2026 GR whose first body `Date:` parses to 21.10.2011.

An earlier version of this file reported "explicit `Date:` line — 75.9%". That measured *a line
beginning with the word "Date"*, not *a parseable GR date*. Do not use that figure.

A parser that trusts the body date will silently misdate hundreds of GRs, and every graph edge
derived from them will be wrong.

**Caveat that shapes the resolver.** The uid prefix is the portal *publication* date and can
drift from the signing date that another GR cites. So **resolve citations against a ± day window
(default ±3), not an exact date match**, and rank candidates inside that window by identifier-token
overlap between the citation text and the candidate's own decision number.
`tests/resolver_truth.json` will tell you empirically how large the real drift is — inspect the
`[+Nd]` distribution once it is labelled.

## Devanagari leakage — verified, closed vocabulary

Measured across all 4,715 HTE GRs: **441 GRs (9.4%) contain Devanagari in the `.en` translation.
There are only 75 distinct token types in the whole corpus, 2,109 instances total, and the top 9
types cover 90% of instances.** This is a lookup-table problem, not a parsing problem. Do not
build a general de-leaking model.

Validate any de-leak routine against the **full 441-GR leak population**, not against the
`devanagari_leakage` fixtures — that bucket filters on `>20` chars and so captures only 8 extreme
outliers, missing the dominant pattern entirely by construction.

### Two classes, handled differently

**Class A — untranslated Marathi words.** Strip or translate.

| token | instances | files | meaning |
| --- | ---: | ---: | --- |
| `सदर` | 1,529 | 319 | "the said" |
| `सदरह` | 10 | 10 | "the aforesaid" |

**Class B — Latin letters transliterated into Devanagari.** **Back-transliterate to Latin. Never
strip.** These sit inside person names, degree names, institution names and addresses, all of
which are load-bearing for obligation extraction and blast radius.

| token | → | seen in |
| --- | --- | --- |
| `एस` | S | `Dr. आर.एस.Mali` → `Dr. R.S. Mali` |
| `एम` | M | `एम.एसस` → `M.Sc` |
| `एल` | L | `B.Co म.एल.एल.ब C` → `B.Com` / `LL.B` |
| `आय` | I | `आय.आर.ट S.S.` → `I.R.T.` |
| `एच` | H | `Old एम.एच.ब D Colony` → `M.H.B. Colony` |
| `आर` `एन` `ए` `ई` `बी` `सी` `डी` `टी` `के` `पी` | R N A E B C D T K P | acronyms, initials |

The full 75-type vocabulary is finite and enumerable — build the mapping table once,
exhaustively, and commit it as `data/devanagari_leak_map.json`.

**Resolver risk to check explicitly:** confirm no Devanagari survives inside any
`Government Decision No.` string. Sampling found none, but the resolver keys on that field and a
silent letter substitution there fails resolution invisibly rather than loudly.

## Parser bug: displaced ordinals in numbered conditions

136 HTE GRs share one boilerplate terms-and-conditions block, identifiable by an exact leak
signature of 20 chars (`6 × सदर` + `1 × अभ`). In that template the list ordinal is fused into the
sentence body:

```
The 1.सदर approval will always be on a non-grant basis.
```

Marathi `१. सदर मान्यता` became `The 1.सदर ...`. **`conditions[]` extraction will mis-index every
numbered condition in this template family** unless it handles ordinals displaced into the body
text. It is a template, so expect the same family across the other three departments.

**Correction `[MEASURED]` — this is an ENGLISH-side artefact, not a defect in the Marathi.** In
Marathi, `१. सदर पदे …` opening a line is correct numbering. Measured on 700 sampled HTE pairs:
**46 English documents carry the fused ordinal against 13 Marathi ones**, and across all four
departments the English side dominates everywhere. A checker aimed at the Marathi flags 52% of the
corpus and is simply wrong.

"Fused" also needs defining precisely, because the obvious regex does not work: an ordinal is fused
only when **running text precedes it on the same line**. Allowing a preceding `.` plus a newline to
count as "non-whitespace before" matches every legitimate `…आहे.\n1. सदर`. See
`lint.find_fused_ordinal`, and `tests/test_lint.py` pins both halves of this as regressions.

Fixtures for this are pinned under the `template_boilerplate` bucket. It is also the best
starting point for GR-Lint's empirical template mining, since 136 documents share a verbatim
structure.

## Build order

Strictly sequential — each layer is worthless without the one below it.

0. Corpus pulled (done)
1. **Parser** — GR text → GR record. Regex first, LLM only for what regex misses.
2. **Resolver** — citation → uid, matching decision number *and* date. Built; resolves from the
   Marathi side (rule 1). Iterate against `tests/test_resolver_invariants.py`, never against vibes.
   Hand-labelled truth is still required for the *accuracy claim* — see **Validating without
   labels** below for exactly what each buys and what it does not.
3. **Graph** — nodes + typed edges, every edge carrying evidence.
4. **Dead-reference audit** — GRs in force today that cite superseded or withdrawn orders.
   *This is the demo money shot. Get a real number out of it early.*
5. **Supersession chains + consolidated "as-amended" text.**
6. **GR-Lint** — template rules mined empirically from the corpus skeleton, not hand-copied from
   the Manual of Office Procedure. Numbered rule codes, line numbers, auto-fix suggestions.
7. **Obligation extraction** (LLM) → **structured conflict detection.**
8. **Bilingual parity checker.**
9. **Blast radius** — what a draft breaks, before it is issued.
10. **Drafting UI.**

## Working conventions

- Iterate on `fixtures/` (50 hand-picked GRs incl. known-messy ones), never on the full corpus.
  Full-corpus runs are batch jobs, committed as artefacts under `out/`.
- Cache every expensive derivation to disk. Nothing gets recomputed during a live demo.
- The demo must run **fully offline against cached artefacts.** Government judges care about
  on-prem; a live API call that times out on stage loses the hackathon.
- Any number that appears in the pitch must be reproducible by a single command in `Makefile`.

## Pitch framing

Ingestion is the commodity layer and we credit it openly. The delta is the graph and everything
computed on it. Lead the demo with a **finding**, not a capability: "we ran this over four
departments and found N GRs currently in force that cite orders which no longer exist."
Capabilities are copyable. Findings are not.