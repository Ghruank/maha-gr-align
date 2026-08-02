# MAHA-GR-ALIGN

AI-assisted Government Resolution drafting, alignment and conflict detection for the
Government of Maharashtra. Built for VJTI AI Hackathon 2026, Problem Area 1.

## How to use this file

**This is a living record, not scripture.** It is a place to write down what has been measured
and decided so it does not have to be rediscovered — so when the code and this file disagree,
the right move is usually to fix the file, not to bend the work around it. Corrections belong
here: several entries below are marked `[MEASURED]` precisely because an earlier claim turned
out to be wrong, and one of them (the PDF round-trip) was wrong for a week.

Two things genuinely are hard constraints, because they are about honesty rather than taste:
never surface a citation that does not resolve to a real uid, and never let a model assert what
can be computed. Everything else is a default to be argued with. The officer owns the rules; a
proposal to change one belongs in this file, not in a negotiation.

## AUTHORITY ORDER (read first)

`documents/Maha-GR-Align_Simple_SRS-updated.pdf` is the **current problem statement and supersedes
this file wherever they disagree.** Added 2026-07-31. `documents/mcs270623075036.pdf` is the
Maharashtra Manual of Office Procedure, 2023 — the template authority it points at (FR-10).

Known supersessions already applied below: build-order step 6 (template rules now come from the
Manual, not from corpus mining) and build-order step 10 (drafting is no longer last — FR-13..FR-16
make it a headline deliverable). The four-bullet scorecard below still holds; the SRS restates it
as FR-1..FR-16 with acceptance criteria, which are reproduced in **SRS requirements** further down.

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
| Cross Department Conflict Detection | graph (3) + conflict detection (7) + `references.py` R11/R12 | **needs a multi-department index.** A single-department resolver rejects cross-dept citations, i.e. does the opposite of this bullet. Now answerable for an unissued draft, not just over the corpus |
| Bilingual Legal Terminology (English) | leak map + parity (8) + **`glossary.py` FR-7/8/9** | the corpus English is machine translation, so claims are about *translation* consistency, never two official texts. The controlled list is the normative half; `bilingual.py` remains the descriptive half |
| Automated Reference Tracking | parser (1) + resolver (2) + graph (3) + `references.py` (FR-1/2/3) | strongest area, and now reachable from a document the officer uploads rather than only from the corpus |
| Strict Template Enforcement | `template.py` (6) — **DONE** | now driven by the Manual of Office Procedure Appendix 10.6, per SRS FR-10; corpus mining is descriptive evidence only |

Note the framing that keeps these coherent rather than four separate demos: **all four bullets are
downstream of one missing artefact — the dependency graph.** Build it and the features fall out;
build the features without it and you get four shallow demos.

## STATUS — what exists right now (read this first)

Last updated **2026-08-02**. The updated SRS HAS now been read; see AUTHORITY ORDER at the top.

Two servers must both be up. `make dev` starts them together, `make doctor` says what is down.
**This matters**: with only one running, every page loads and every API call fails, which reads
as "the OCR is broken" rather than "the backend is down". That mistake cost a debugging cycle.

| layer | file | state |
| --- | --- | --- |
| Parser | `parser.py` | ✅ regex only, no LLM |
| Resolver | `resolver.py` | ✅ multi-department, two-key + digit key |
| Graph | `graph.py` | ✅ **17,283 nodes, 4,815 edges, 1,538 cross-dept**, builds in 10 s |
| AI edge typing | `type_edges.py` + `ai/client.py` | ✅ hosted Groq. **33 SUPERSEDES, 169 AMENDS** |
| Dead-reference audit | `audit.py` | ✅ **24 dead references** (10 rotted, 14 born dead, 2 latent cross-dept) |
| Blast radius | `api.py` `/api/blast/{uid}` | ✅ one Finance circular has **229 live dependents** |
| GR-Lint | `lint.py` | ✅ mined per department, **76.5% of GRs clean** |
| Bilingual | `bilingual.py` | ✅ **335 magnitude errors**, 26 inconsistently-rendered terms |
| Metrics | `metrics.py` | ✅ every pitch number, one command |
| **Local LLM** | `ai/local.py` | ✅ **NEW** Ollama transport, `qwen3.5:2b`, ~9–11 tok/s CPU |
| **Template engine** | `template.py` + `data/gr_template.json` | ✅ **NEW** FR-10/11/12, deterministic |
| **Drafting** | `drafting.py` | ✅ **NEW** questions → draft → refine, all local |
| **Doc export** | `docgen.py` | ✅ **NEW** PDF (WeasyPrint) + DOCX (python-docx), one model |
| **Upload / OCR** | `ocr.py` | ✅ **NEW** text-layer first, EasyOCR (mr+en) fallback |
| **Reference check** | `references.py` | ✅ FR-1/2/3 live on an uploaded document, ~4 ms |
| **Bilingual glossary** | `glossary.py` + `data/glossary.json` | ✅ FR-7/8/9, 31 terms, 19 approved |
| **Clause index** | `embed.py` + `index_clauses.py` | ✅ **NEW** 23,977 clauses, MahaSBERT, 34 MB |
| **Semantic search** | `semantic.py` | ✅ **NEW** FR-4/5/6, exact numpy search, Draft GR |
| **Alignment verdict** | `references._alignment` | ✅ **NEW** aligned / misaligned / partial, computed |
| **Narrative review** | `refreview.py` | ✅ **NEW** local Qwen explains the verdict, 20–40 s |
| **Cited-GR popup** | `corpus.py` + `/api/gr/{uid}` | ✅ **NEW** corpus text + official portal PDF link |
| Portal UI | `web/src/portal/` | ✅ Home · Draft · Verify · Check Graph · Recent GRs — no stubs |
| Legacy dashboard | `web/src/archive/` | ✅ intact at `/archive`, lazy-loaded, **unlinked from the nav** |
| **Corpus screening** | `/api/corpus/recent` | ✅ both checks over the latest N GRs, 170 ms |
| **In-tray / staging** | `staging.py` | ✅ **NEW** upload a GR; later uploads can cite it |
| **Contradiction check** | `conflicts.py` | ✅ **NEW** restated amounts vs the cited order |
| **Graph view** | `web/src/portal/GraphView.tsx` | ✅ **NEW** cites ← GR → cited-by, plain SVG |
| Tests | `tests/` | ✅ **131 passing, zero API calls** |

### The two pages that are built

**Draft GR** (`/draft`) — left settings panel, right editable preview.
prompt → AI asks clarifying questions (text + multiple choice) → answers → AI drafts into the
template → refine by prompt, or edit the preview directly → verify → download PDF/DOCX.
Version history tags every entry Template / AI / Officer with restore buttons (FR-15).

**The invariant that must not be broken:** the preview is the single source of truth. Every
refine sends the CURRENT preview text, hand edits included. If AI output were kept separately
and merged later, a hand edit could be silently reverted — in a legal document that is a
correctness failure, not a UX wrinkle.

**FR-14, added 2026-08-02.** A refinement is now HELD as a proposal and shown beside the current
text as a line-level diff, with a before/after compliance count, until the officer accepts or
discards. This does not weaken the invariant — the request still sends the current preview, and
the proposal is a whole-document replacement that is never *merged*. A merge is what could
revert a hand edit; an accept-or-discard cannot. It also strengthens FR-15: an accepted
suggestion is an explicit human decision with a timestamp, and a DISCARDED one is recorded too.

**Verify GR** (`/verify`) — upload a PDF or scan, extract, then run THREE checks in one pass,
shown on tabs that each carry their own count:

- **Template** — the SAME `template.verify` the drafting page runs. One rule engine for both
  pages, so a GR cannot pass on one and fail on the other.
- **References** (`references.py`, added 2026-08-02) — SRS FR-1/2/3. Every cited GR, circular
  and court order is extracted, resolved against the graph's own 17,283-node index, and checked
  against what has happened to it since.
- **Terminology** (`glossary.py`, added 2026-08-02) — SRS FR-7/8/9. See below.

All three re-run on "Re-check", because a corrected OCR file number changes which orders
resolve and a corrected term changes the terminology result.

**A GR can be perfectly formed, rest on an order cancelled two years ago, and call it by a name
the Manual does not use.** Three separate answers; none substitutes for another.

Nine finding codes, and the severities are the design:

| | | |
| --- | --- | --- |
| R01 | **error** | cited order is in range, in an indexed department, and NOT in the archive |
| R02 / R11 | **error** | cites a superseded order — R11 when the supersession was another department's |
| R03 | warning | cited order is in force but has been amended since |
| R12 | warning | this draft cancels an order others still stand on — blast radius, before the damage |
| R05 / R06 | warning | ambiguous, or no file number to verify against |
| R07 / R08 / R09 | advisory | department not indexed · date outside coverage · court order or Act |
| R10 | advisory | a plain cross-departmental dependency |
| R13 / R00 | warning / advisory | citations only in the body · no citations at all |

**The five ways of not finding something are never merged**, and this is the whole honesty
argument (rule 3). Only R01 is a defect in the document; `outside_range`, `other_dept` and
`out_of_scope` are facts about *our coverage*. Collapsing them would roughly quadruple the red
count and make it false — measured on fixture 201803071449402308, 5 genuine misses against 12
citations that predate the crawl. The UI colours them grey for the same reason.

`references.py` calls no model and a test enforces it. Every supersession claim ships with the
verbatim Marathi sentence off the graph edge that produced it.

**`samples/` holds ten PDFs to test this page with**, with a README giving the measured result
for each. All are real corpus GRs re-typeset with `export_pdf.py` (XeLaTeX) — **not**
`docgen.py`, whose text layer is unusable for Marathi, see the correction below.

**The demo pair is `demo-A-citations-aligned.pdf` and `demo-B-citations-not-aligned.pdf`.**
Same department, same form, opposite verdicts: A resolves nine orders and every one is in
force; B cites one order and it was cancelled in July 2026. B's other citation is a High Court
order, which comes back *not checked* in grey — the distinction the whole design protects.

### Three additions the officer asked for on 2026-08-02

**The alignment verdict is COMPUTED, not generated** (`references._alignment`). Four states:
`misaligned` (something it stands on was superseded, or is absent from the archive),
`partial` (all found orders in force, but one was amended or a citation could not be checked),
`aligned`, `unverified` (nothing checkable — saying "aligned" there is a claim we have not
earned). This was originally left to the model and that was wrong twice over: rule 4 forbids
generating a computable fact, and Qwen3.5-2B, handed the findings and asked to judge, wrote
*"the resolution remains valid because the cited references are either unverified or
superseded"* about a document whose citations had been superseded. Handing the model the
verdict and asking it to explain fixed the prose immediately.

**`refreview.py` writes the narrative, under two mechanical gates.** The prompt contains no
order number, no date, no uid and no line number — the model cannot corrupt an identifier it
never saw. And any sentence containing a digit outside `[n]`, or a `/`, is **discarded whole**,
never repaired, because a mangled file number reads exactly as authoritative as a correct one.
Both gates exist because the first version produced
`मइवाधो-२०ॲ३५/प्र.क्र.२५/तां.क्र.४` — a corrupted file number and an invented line 43 — which a
uid whitelist could not catch. `tests/test_refreview.py` pins both halves.

**A court order must never be paraphrased as "missing".** Given "the archive does not hold
court orders", the model wrote "citation [2] is absent from the archive", collapsing the exact
distinction the five verdicts exist to keep. Fixed in the glosses handed to it: only
`not_in_archive` may contain the word MISSING, and `out_of_scope` says "NOT a missing
reference" in as many words. A test asserts that.

### Semantic conflict detection — FR-4/5/6 (added 2026-08-02)

`embed.py` → `index_clauses.py` → `semantic.py`, on the **Draft GR** page as a second tab beside
the template check. 23,977 operative clauses from 6,000 GRs, MahaSBERT, 768-dim, 34 MB.

**Read this before claiming anything about it `[MEASURED 2026-08-02]`:**

    उक्त शासन निर्णय याद्वारे रद्द करण्यात येत आहे.        (a cancellation)
      vs a differently-worded cancellation                 0.406
      vs सदर शासन निर्णयात अंशत: सुधारणा (an AMENDMENT)     0.467   ← HIGHER
      vs an unrelated sports clause                        0.167

**Topic separates cleanly; the legal ACT does not.** The model ranks an amendment above a second
cancellation, so this index can answer *"has another department written about this?"* and
absolutely cannot answer *"does it contradict me?"* Every hit is labelled a candidate for
review, the score is shown raw next to the threshold that produced it, and the word "conflict"
never appears without "potential". That is also precisely what FR-6 asks for.

**This supersedes the 0.802 note elsewhere in this file.** That figure came from a different
sentence pair. Do not quote it as evidence that MahaSBERT separates supersession from amendment
— measured here on a fair triple, it does not.

Design decisions, each with a reason:

- **Two indexes, never one translated space** (decided 2026-07-31, still right). Embedding
  IndicTrans2 output and comparing it to Marathi would measure the translator.
- **Only the operative section is indexed.** The header and `वाचा` block are near-identical
  corpus-wide; indexing them makes every GR the nearest neighbour of every other. The
  distribution list and the website boilerplate are excluded for the same reason — `प्रति, १)
  संचालक, तंत्र शिक्षण संचालनालय…` appears near-verbatim in thousands of documents.
- **Other departments only.** Within a department the officer already knows the standing orders.
  The invisible failure is Higher Education writing what School Education settled two years ago.
- **numpy, not FAISS.** Neither FAISS nor hnswlib is installed and neither is needed: 23,977 ×
  768 is one matmul, a few milliseconds, and exact — so the score shown is the real cosine, not
  an approximation. One less thing to install on an SDC box.
- **float16 on disk** — 68 MB → 34 MB, and the vectors are L2-normalised so every component is
  in [-1, 1] where float16 has ~3 decimal digits. Scores are displayed to two.
- **Behind a button.** Embedding the draft is ~11 clauses/second on this CPU; re-running it on
  every keystroke would be unusable.

`make index` rebuilds it: ~35 minutes, and NOT part of `make all`. The output is committed.

### Contradiction detection — `conflicts.py` + `staging.py` (added 2026-08-02)

`references.py` answers *does the order this GR cites still stand?* This answers a harder one:
**does this GR agree with it?** The case it is built for:

> Finance sanctions Rs. 15,00,00,000 for an institution. Higher Education, citing that very
> order, writes "Rs. 10,00,00,000 was sanctioned" and releases instalments against the smaller
> figure.

Both documents pass the template check. The citation resolves and the cited order is in force,
so the alignment verdict is clean. **Nothing in either document, read alone, is wrong** — the
defect exists only between them. `samples/demo-C-finance-15-crore.pdf` and
`samples/demo-D-hte-10-crore.pdf` are exactly this, and are the demo.

**Deterministic, not a similarity score.** SRS FR-4/5/6 reach for this with embeddings, and
that is right for *prose* conflicts. A restated figure is not prose: it is an integer, quoted
from a named source, that either matches or does not. Rule 4 applies at full strength, so there
is no model call in `conflicts.py`; the model only writes the hover note, and is handed the
three figures with every other number scrubbed from its output.

**Staging is what makes it possible before issue.** Every check reads `out/graph.json`, the
*published* record, so a GR pending issue is invisible to all of it — exactly backwards. An
upload is registered in the live index (`Archive.add`) and thereafter resolves like any archived
order, so a second draft can cite it. Staged records live in `out/staging.json`, are marked
`staged: true` everywhere, and never touch the graph: if an upload could quietly join the
archive, "verified against the official archive" would stop being true.

Three restraints, without which this is a false-positive generator:

- **Only a figure explicitly attributed to a cited order is compared** — by reference ordinal
  (`संदर्भ क्रमांक १ येथील`) or by the cited order's own file number in the same span. A GR that
  cites an order *and separately* sanctions money is the normal case, not a contradiction.
- **A part-release is not a restatement.** `... रु. १५,००,००,००० इतक्या निधीपैकी पहिला हप्ता
  म्हणून रु. ५,००,००,०००` releases five crore out of fifteen.
- **Silence when the cited order cannot be read.** Our ignorance is not the drafter's error.

Two bugs worth remembering, both false NEGATIVES — the dangerous kind, because a check that
silently declines looks exactly like a check that passed:

- **`भागा` in the partitive list matched inside `विभागाच्या`** ("of the department"), so any
  sentence naming a department suppressed the finding. The real demo document escaped only
  because its department name happened to sit outside the 90-character window.
- **Sentence-splitting on `(?<=[।.])\s+` breaks on `रु.`** — the rupee abbreviation ends in a
  period, so the attribution and the figure it introduces landed in different fragments and
  nothing was ever compared. Replaced with a paragraph-bounded backward window, which also
  matches how these documents are written: the attribution always precedes the figure.

### Terminology — FR-7/8/9 (`glossary.py`, `data/glossary.json`, added 2026-08-02)

**A descriptive glossary and a normative one are different objects, and only the second one
satisfies FR-7.** `bilingual.py` mines the corpus and reports how terms *are* translated; FR-7
asks how a term *must* be translated, and no amount of mining answers that because the corpus is
the thing being judged. The measurement that settles it:

> Across 2,500 corpus documents, **"Government Decision" appears in 1,861 and "Government
> Resolution" in 1,021** — and the Manual of Office Procedures uses "Government Resolution" six
> times and "Government Decision" not once. **The dominant machine-translated rendering is the
> non-standard one.** A glossary derived from the corpus would have enshrined the error.

So authority comes from outside the corpus. `documents/mcs270623075036.pdf` turns out to be **in
English** (0 Devanagari characters in 225k), which makes it directly usable as the term
authority — Appendix 10.6 is headed FORM OF GOVERNMENT RESOLUTION. 31 terms, 19 `approved: true`
citing the Manual or SRS FR-11, 12 proposed from my own judgement and marked so. Hand-authored
in `build_glossary.py`; `make glossary` only re-measures the evidence counts, so re-running never
overwrites a human decision.

Two gates keep it from producing nonsense, and both were built after seeing it misfire:

- **`strict`** gates whether FR-9 offers a replacement. `रद्द` (cancelled), `अधिक्रमित`
  (superseded) and `व्यपगत` (lapsed) do different things to an order, so "cancelled" in an
  English GR may be a perfectly correct rendering of `रद्द`. Those entries report the ambiguity
  and withhold the suggestion. **FR-9 declining to guess is the requirement working.**
- **A variant is only listed when its presence is probably a mis-rendering of *this* term.**
  Dropped during construction: "Chief Secretary" (a real, different office — मुख्य सचिव),
  "Allowance" (correctly renders भत्ता), "Reference" (correctly renders संदर्भ), "in this
  regard" (ordinary prose), "the Government of Maharashtra" (correct outside the masthead).
  Every one of these was a false positive in a first run.

**`\b` is mandatory in the matcher and its absence was a real bug.** Without it "Re" matched
inside "Regarding"/"Reference"/"Resolution" and scored 2,497 of 2,500 documents; "Fund" matched
inside "Funds"; "Memo" inside "Memorandum". `glossary.phrase()` is the single definition, and
`build_glossary.py` imports it so the recorded evidence and the live findings cannot disagree.
Safe here because every term matched this way is Latin — the `\b`-after-Devanagari trap applies
to the Marathi side, which uses a plain substring test.

**The two languages are asked different questions.** English is the derived view and the only
side where a rendering can be wrong. Marathi is authoritative, so instead of correcting it the
panel lists the terms present with the English each must take — which is what an officer
preparing the English version actually needs.

### The archived dashboard was UNLINKED on 2026-08-02 — not deleted

`web/src/archive/` is intact and `/archive` still resolves. What was removed is every **link**
to it: the navigation pill and the footer entry, plus the now-unused `nav.archive` string.

The distinction matters and was corrected mid-change: deleting the source also removed cytoscape
and stranded four API routes. Keeping it costs nothing, because the route is lazily loaded — the
486 kB chunk is never downloaded unless somebody types the URL. So it stays available for a
question during the demo without putting a superseded interface in front of anyone.

**Do not link it back into the chrome.** Every page it offered has been superseded: Reference
Audit by Verify GR's Citations tab, Graph Explorer by Check Graph, Trust Ledger and GR-Lint by
the finding panels. The one thing with no home in the portal is the **bilingual parity view**
(335 magnitude errors, 26 inconsistently-rendered terms). It is still served by `/api/bilingual`,
still reproducible with `make bilingual`, and still quoted in the deck; if it deserves a screen
it belongs as a tab on Verify GR beside Terminology, not as a resurrected dashboard.

### Recent GRs (`/recent`, added 2026-08-02) — and the template bug it exposed

The most recent N GRs, each screened on BOTH questions: does it follow the Manual's form, and
does it still stand on what it cites. 170 ms for 15 rows, `lru_cache`d per uid.

Building it forced a correction to `template.py` that had been silently wrong all along.
**Measured on 400 random corpus GRs, 0.2% were template-compliant.** A column reading ✗ on
every row is not a finding, it is a broken measurement, and three separate causes were mixed
into it:

1. **`verify()` detected the document type and then ignored it.** `detect_doc_type` has always
   returned circular / memorandum / notification / resolution, and the Manual gives each its own
   specimen form (10.4, 10.5, 10.7, 10.6) — but every document was checked against the
   Resolution section list regardless. `DETECT["resolution"]` matched only `शासन निर्णय`, so the
   operative section read as MISSING on every memorandum and corrigendum in the corpus. In a
   400-GR sample that is 111 circulars, 31 memoranda and 13 notifications judged by the wrong
   form. Fixed: the operative-section pattern now accepts ज्ञापन / परिपत्रक / शुद्धिपत्रक / आदेश,
   and for a non-resolution only the sections common to every form (`UNIVERSAL`) may error.
2. **The subject detector required a `विषय :-` label.** Real GRs put the subject as a bare line
   above `महाराष्ट्र शासन` — which is how `parser.py` has always read it. The label-anchored
   pattern reported it missing on 388 of 400 while the mined profile puts it at 93% present, so
   the 97% failure was the pattern's fault. `_unlabelled_subject` fixes it, and refuses a bare
   label so a blank skeleton still fails.
3. **The signature block and Governor's order line are images.** Nothing to fix; they must not
   be enforced on an already-issued document.

Hence `verify(text, lang, mode=...)`, one rule engine and two questions:

* **`draft`** — the full Appendix 10.6 form, unchanged, still 0.2% on the corpus. What FR-10/11/12
  require of a document *we* are about to produce, and the only mode the drafting page uses.
* **`issued`** — for a GR read back through OCR. A required section is downgraded to advisory
  when its mined `corpus_rate` is below `ISSUED_FLOOR` (0.5), or when the Manual gives this
  document type a form we have not encoded. Both reasons are reported per finding.

Result on the same 400 GRs: **45.0% compliant under `issued`**, and the residue is real — no
discernible operative section or resolution number in the extracted text. A column that
discriminates. `relaxed[]` on the response names every section that was not counted and why,
so nothing is quietly forgiven.

### Check Graph (`/graph`, added 2026-08-02)

Search box on the left — accepts an 18-digit uid, a Devanagari file number, or words from the
subject, because an officer holding a paper GR has the file number and not the portal id. The
view is **three columns: what this GR cites · the GR · what cites it.**

Deliberately NOT a force layout, and not cytoscape, though the archived dashboard uses both.
The question this page answers is directional, and a cose layout places nodes by attraction so
direction survives only in the arrowheads — unreadable on a projector. Columns also make the
picture deterministic, which a demo needs and a force layout does not give. It keeps cytoscape
at all — the portal ships no graph library.

**A superseded neighbour is drawn red and dashed**, which needed `src_in_force` / `dst_in_force`
added to `Store.edge_out` in `api.py`. Without them a client showing a neighbourhood would have
to fetch every neighbour separately to discover that the order in front of it was cancelled —
i.e. the one thing the view exists to reveal would have been the one thing it did not show.

Unresolved citations are listed in the sidebar, never drawn. A GR that cites five orders we
could not verify must not look like a GR that cites nothing.

**The popup behind a citation offers two different things** (`corpus.py`). The corpus text works
offline and is OCR of the scan; the **official PDF on `gr.maharashtra.gov.in`** is the signed
instrument and needs the network. `GRs.json` carries a `url` for every crawled GR — that field
was unused until now and is the single most persuasive thing we can show a sceptic. Both are
labelled for what they are.

### Local model roster — `data/models.json`, `make models` / `make models-check`

All six present. Machine has **no GPU** (Intel UHD only), 12 cores, 15 GB RAM.

| role | model | measured |
| --- | --- | --- |
| LLM | `qwen3.5:2b` (ollama) | 9–11 tok/s; questions ~26–35 s, draft ~28 s |
| Translation | `ai4bharat/indictrans2-{indic-en,en-indic}-dist-200M` | 2.0 s / 2 sentences, beam 5 |
| Marathi embeddings | `l3cube-pune/marathi-sentence-similarity-sbert` | 768-dim, 43 sent/s |
| Marathi alt | `l3cube-pune/marathi-sentence-bert-nli` | downloaded, unused |
| English embeddings | `BAAI/bge-base-en-v1.5` | 768-dim |

MahaSBERT-STS separates cleanly on real Marathi: two differently-worded cancellations score
**0.802**, against 0.313 unrelated and 0.343 amendment. That is the evidence FR-4/FR-5 will work.

**Nothing is indexed yet.** The embedding models are downloaded and benchmarked; no vector
index over the corpus exists. That is the next big build.

### Known gaps / next up

1. ~~FR-4/5/6 semantic conflict detection is not built.~~ **Built 2026-08-02.** 23,977 clauses
   from 6,000 GRs, MahaSBERT, on the Draft GR page. See **Semantic conflict detection** below —
   and read the measurement there before claiming anything about it.
2. ~~The `/references` and `/analysis` tabs are stubs.~~ **Both removed 2026-08-02** at the
   officer's request. Citation checking lives on Verify GR, where the document raising the
   question is already on screen; `/graph` (**Check Graph**) replaced AI Analysis and is real.
   What is still unbuilt is a *corpus-wide* browser — everything today is one document or one
   node at a time.
3. ~~FR-7/8/9 controlled bilingual glossary does not exist.~~ **Built 2026-08-02** —
   `data/glossary.json` (31 terms, 19 approved) + `glossary.py`, on the Verify page's
   Terminology tab. `bilingual.py` still does the numeric-parity work and is unchanged; the two
   are different objects and the distinction is the point, see below.
4. **Groq → local migration is half done.** `ai/local.py` serves drafting; `type_edges.py` still
   uses hosted Groq and the committed 33/169 edges came from it. Decided 2026-07-31:
   **re-type with Qwen locally but KEEP the Groq output to compare**, so the migration becomes a
   measurable agreement rate rather than a silent swap. Qwen 2B may well be worse — measure.
5. ~~OWED: the precision audit.~~ **DONE 2026-08-02 — but by Claude, not a human.** The officer
   had no time and explicitly instructed me to adjudicate it myself, overriding the rule below.
   **48/50 (96%)** on a sample deliberately weighted towards the hard paths; zero demonstrably
   wrong, two I could not confirm either way and counted as errors. See
   `out/precision_audit.json` and **AI-adjudicated precision** further down. `metrics.json`
   now carries the figure with `provenance: ai-adjudicated`, and that label must travel with it.
6. **~380 of 718 candidate edges are still untyped** from the old token cap.
7. STT and vision models are wired in `ai/client.py` but **never tested**.

### SRS requirements — the current scorecard

From `documents/Maha-GR-Align_Simple_SRS-updated.pdf`. ✅ built · ◐ partial · ✗ not started.

| | requirement | state |
| --- | --- | --- |
| FR-1..3 | extract + verify + highlight citations | ✅ `references.py`, live on Verify GR |
| FR-4..6 | clause embeddings, vector search, similarity score | ✅ `semantic.py`, Draft GR |
| FR-7..9 | controlled bilingual glossary, flag, suggest | ✅ `glossary.py`, Terminology tab |
| FR-10..12 | Manual of Office Procedure structure, mandatory sections, warn | ✅ `template.py` |
| FR-13 | upload or type a draft | ✅ both pages |
| FR-14 | side-by-side text, AI suggestions, validation | ✅ `SuggestionDiff.tsx`, accept/discard |
| FR-15 | audit trail of AI suggestions and human edits | ✅ version history |
| FR-16 | export PDF / DOCX | ✅ `docgen.py` |
| NFR-1 | 30 s for reference + conflict check | ◐ drafting 28–35 s, OCR 18.5 s warm |
| NFR-2 | nothing leaves the on-premise box | ✅ ollama on localhost, no hosted calls on these paths |
| NFR-5 | full Marathi + English Unicode | ✅ fonts vendored, see below |
| NFR-6 | every AI suggestion shows its source or rule | ◐ template findings cite the Manual; drafting does not yet |

Acceptance criteria still unmeasured: ≥80% citation extraction, conflict flagged above a
similarity threshold, glossary mismatch highlighting.

### Operational facts that cost time to learn

**Local model stack** (added 2026-07-31, when the project moved off hosted Groq to on-prem):

- **`HF_HUB_DISABLE_XET=1` is required.** With `hf_xet` 1.5.2 active, HuggingFace downloads of
  the IndicTrans2 repos **stall silently at a fixed byte count** — no error, no timeout, the
  process just sits there. Two restarts hung identically; disabling Xet fixed it immediately.
- **IndicTrans2 repos are gated.** A human must accept the licence on each model page while
  signed in, then authenticate. Cannot be scripted.
- `transformers` is pinned to **exactly 4.53.3**, for two independent reasons. 5.x moved
  `tokenization_utils.PreTrainedTokenizerBase`, so IndicTransToolkit will not import. And
  IndicTrans2's own `trust_remote_code` modeling file still uses the legacy tuple KV-cache
  (`past_key_values[0][0].shape[2]`); 4.57 hands it a Cache object and generation dies with
  `AttributeError: 'NoneType' object has no attribute 'shape'`. Newer transformers works only
  with `use_cache=False`, which is **2.4× slower** (4.8 s vs 2.0 s, same output).
- **`torchvision` must come from the CPU index**, matching torch. The PyPI wheel is built
  against a different torch ABI and EasyOCR dies at import with
  `operator torchvision::nms does not exist`. `uv pip install --torch-backend=cpu torchvision`.
  `uv` will report the PyPI one as already satisfied — force with `--reinstall-package`.
- `sentencepiece` is required by the IndicTrans2 tokenizer and is **not** pulled in as a
  transitive dependency. Missing it fails at tokenizer load, not at install.
- `IndicTransToolkit` publishes **no cp314 wheel**; pip builds it from sdist (~100 s, needs a C
  compiler). A State Data Centre box without build tools needs a pre-built wheel vendored.
- Install torch from the **CPU index** (`--torch-backend=cpu`). The default wheel pulls ~3 GB of
  CUDA libraries that are dead weight — the target box has no NVIDIA GPU.
- **Qwen3.5 thinks by default.** `think: false` is mandatory: one classification with thinking on
  burned 500 tokens and 54 s without emitting an answer, against a 30 s NFR.
- `snapshot_download(local_files_only=True)` is **wrong in both directions** as a presence check —
  it succeeds on the empty directory a failed download leaves behind, and raises when a snapshot
  is merely incomplete against the manifest. `fetch_models.py` scans for weight bytes instead.
- `pkill -f fetch_models.py` **kills the shell running it** — same trap as the uvicorn one below.
  Use `pkill -f "fetch_model[s].py"`. **The bracket trick is not enough on its own**: if the same
  command line also contains the literal word (e.g. a `nohup … uvicorn …` in the same compound
  command), pgrep still matches the shell. Put the kill in a SEPARATE call from the start.
- **Long-lived `while pgrep -f foo` wait loops never exit**, because the loop's own command line
  contains `foo`. Four of them spun for an hour before being noticed. Same bracket fix.

**Fonts, scripts and documents** (added 2026-08-01):

- **No Devanagari font is installed on the target box.** `fc-list :lang=mr` returns only
  FreeSans/FreeSerif, whose conjunct shaping is poor. Noto Serif + Noto Serif Devanagari are
  **vendored in `web/public/fonts/`** (OFL, one superfamily, shared metrics) and referenced by
  path, never by family name. Assume nothing is installed.
- **`\b` does not work after Devanagari.** `वाचा` ends in U+093E, a combining mark that Python's
  `re` classes as a NON-word character, so `\b` after it never matches. A section-boundary regex
  ending in `\b` silently matched nothing and let a completely blank template verify as fully
  compliant. Anchor on the separator instead. `tests/test_template.py` pins this.
- **A `<textarea>` does not print its content.** The browser clips it to the visible box, so
  `window.print()` produced truncated PDFs. Irrelevant now that export is server-side, but the
  mirrored `.pk-printable` node remains as the Ctrl+P fallback.
- **XeLaTeX writes Devanagari text layers in VISUAL order** — `विषय` extracts as `िवषय`. This is
  why `docgen.py` (WeasyPrint) replaced `export_pdf.py` (XeLaTeX). `ocr.py` still carries the
  repair for foreign PDFs that do the same thing — and that repair **cannot be idempotent** for
  the reph case (logical `कर्म` is character-identical to the visual reordering), so it runs only
  behind `looks_visual_order()`.
- **CORRECTION `[MEASURED 2026-08-02]`: a docgen-exported Marathi PDF does NOT round-trip.** An
  earlier version of the bullet above claimed WeasyPrint "emits logical order, so an exported GR
  round-trips back through Verify." It does not. Exporting a draft and re-uploading it yields
  `वाचा` → `विाचा`, `दिनांक` → `दनां क`, `निर्णय` → `नणर्षाय`: i-matras duplicated or dropped,
  rakar rendered as `रि`, spaces inserted mid-word. This is **not** the visual-order problem, so
  `looks_visual_order()` correctly declines to fire and the repair does not help. `pdftotext`
  produces the identical mangling, which locates the fault in the PDF's glyph→Unicode mapping,
  not in `ocr.py`. Consequences: the Marathi export/re-verify loop is broken (0 citations found),
  and **`force_ocr` is the workaround** — EasyOCR over the rendered page recovers the text at
  ~0.57 confidence, enough that citations extract and classify, though file numbers degrade far
  enough that resolution honestly abstains. The English export is unaffected and round-trips.
  Not yet diagnosed further; suspect the vendored Noto ToUnicode CMap.
- **In OOXML, Devanagari is a complex script.** Setting `w:ascii`/`w:hAnsi` is not enough — Word
  ignores the font for Marathi runs unless `w:cs` is set too.
- LibreOffice was considered for PDF/DOCX and rejected: ~1 GB and a root install on the SDC box.
  WeasyPrint + python-docx build against Pango/HarfBuzz/Cairo, already present, no root.

**Hosted Groq** (retained only for the planned local-vs-hosted comparison):

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
     matching, graph traversal, supersession chains, lint verdicts, **template compliance**, and
     *every number in the pitch* are computed. A model may explain a finding; it may not be the
     reason we believe it. `template.py` contains no model call and a test enforces that: whether
     a draft carries a signature block is a fact a regex settles, and a model that "decides" it
     is a model that can be wrong about something checkable.
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

**AMENDED 2026-08-02 by the officer.** He had no time for the audit and instructed me to do it
myself: *"it doesnt matter anymore that an ai is making it and an ai itself is testing. just do
it please."* That decision is his to make and it is recorded here rather than argued with. What
follows still stands for any FUTURE answer key, and the one that now exists is labelled
`ai-adjudicated` everywhere it appears so nobody mistakes it for the thing described below.

**Fixtures are inputs. They are not ground truth.**

The resolver's expected outputs — which uid each citation actually resolves to — are
hand-labelled by a human in `tests/resolver_truth.json`. Do not generate, extend, "correct",
or infer entries in that file. If code and answer key are both machine-produced, passing tests
prove only self-consistency, and the graph will be confidently wrong.

If `tests/resolver_truth.json` lacks a case you want covered, say so and stop. Do not add it.

### AI-adjudicated precision — 48/50, and exactly what it is worth

Run 2026-08-02. `audit_precision.py` builds the evidence packets; the labels and reasoning are
in `out/precision_audit.json`; `make precision` rebuilds the packets but never the labels.

**The honest framing.** Auditor and author are the same model, so shared blind spots cannot be
ruled out and this is NOT equivalent to human ground truth. Two things were done to make it
worth more than a rubber stamp:

* **Adjudicated against the target's CRAWLED PORTAL METADATA** (`GRs.json` order_number,
  subject, date) rather than against our OCR text. That metadata comes from a different pipeline
  than the one the resolver reads, so agreement is not automatic.
* **Every other GR sharing the file number was shown in the packet**, so "it picked a plausible
  document when a better one existed" was checkable — the failure a confirmation pass misses.

**The sample is deliberately skewed to the hard paths and therefore UNDERSTATES precision.**
Quote per stratum:

| stratum | | note |
| --- | --- | --- |
| digit key | 14/14 | includes one where OCR read `संकोर्ण` for `संकीर्ण` — letters disagreed, digits carried it |
| cross-department | 12/12 | turned out to be the EASY case: Finance appropriation circulars have clean numbers |
| `समक्रमांक` inherited | 6/6 | expected to be weakest, is strongest — the claim is self-verifying, since the target's number must equal the citing GR's |
| exact number | 10/10 | |
| **date-drifted** | **6/8** | **the only stratum with deductions** |
| **total** | **48/50** | 0 demonstrably wrong, 2 unconfirmable, counted as errors |

**The one real finding, and it is actionable.** Both deductions sit at the edge of the ±3-day
window inside a *dense* same-number series — cases where several GRs on that file number exist
within days of the cited date and the resolver took the nearest. In one the drift ran the wrong
way entirely (target published three days BEFORE the date cited), which publication lag cannot
explain. Either the citation's date is wrong or the cited member is absent from the crawl and
the edge should not exist.

**Only 18 edges in the whole graph (0.37%) share that profile** — `|drift| >= 2` and two or more
same-number GRs within 30 days. **88.6% of all 4,815 edges have an EXACT date match** and are
not exposed to it at all. Abstaining on those 18, or marking them low-confidence, would cost
almost nothing and would close the only hole this audit could find. Not yet done.

**Recall was not audited**, and the run surfaced a real gap: a citation naming two dates
(`दि.०३/५/२०१८ व दि.१६/५/२०१८`) produces only one edge, even when both targets are in the corpus.

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
6. **GR-Lint** — numbered rule codes, line numbers, auto-fix suggestions.

   **SUPERSEDED 2026-07-31 by the updated SRS** (`documents/Maha-GR-Align_Simple_SRS-updated.pdf`).
   This step used to read "mined empirically from the corpus skeleton, *not* hand-copied from the
   Manual of Office Procedure". SRS **FR-10** says the opposite — enforce the structure defined in
   the Manual — and the SRS wins. The Manual is in `documents/mcs270623075036.pdf`; the specimen
   GR form is **Appendix 10.6** (`pdftotext` line ~3487).

   The two sources answer different questions and both are still needed:

   - **The Manual is normative** — what a draft we generate MUST contain. Enforce it on drafts.
   - **The corpus is descriptive** — what real GRs look like. Use it for parsing and detection,
     and to avoid flagging history as broken. Measured on 1,500 random Marathi GRs:
     `महाराष्ट्र शासन` 99.8%, `मंत्रालय` 99.6%, `शासन निर्णय क्रमांक` 68.8%, `वाचा` block 47.9%,
     signature block **30.4%**, "By order and in the name of the Governor" **2.2%**.
   - So **a rule requiring a signature block would flag ~70% of the real corpus.** Checked whether
     that was OCR truncation — it is not: GRs with complete text extraction show 30.4% and those
     with empty trailing pages 32.3%, statistically the same. The blocks are images, not text.
     Enforce the signature on *drafts*; never use its corpus absence as evidence of a defect.
7. **Obligation extraction** (LLM) → **structured conflict detection.**
8. **Bilingual parity checker.**
9. **Blast radius** — what a draft breaks, before it is issued.
10. ~~**Drafting UI.**~~ **DONE, and no longer last.** SRS FR-13..FR-16 make drafting a headline
    deliverable, not a garnish. Built 2026-07-31/08-01: `drafting.py` (local Qwen),
    `template.py` (deterministic check), `docgen.py` (PDF + DOCX), `ocr.py` (upload), and the
    portal pages `web/src/portal/pages/{DraftGR,VerifyGR}.tsx`.

**Remaining order, as of 2026-08-01:** step 7 (obligation extraction → conflict detection, which
is FR-4/5/6 and needs the vector index) is the biggest open item, then wiring the Check
References and AI Analysis tabs onto data that already exists.

## The drafting / verification stack — how the new pieces fit

Added 2026-07-31 → 2026-08-01. Read this before touching any of these files.

```
   officer types a prompt
           │
   drafting.py ──── ai/local.py ──── ollama :11434 (qwen3.5:2b)   ← the ONLY model call
           │                                                          on this path
           │ returns FIELD VALUES as JSON, never a whole document
           ▼
   template.py  render_skeleton()   ← lays fields into the Manual's form
           │
           ▼
   preview (plain text, editable)  ◄── ocr.py, for the upload path
           │
           ├─ template.py    verify()   ← DETERMINISTIC. no model, ever.
           ├─ references.py  check()    ← DETERMINISTIC. reads out/graph.json, ~4 ms
           │      └── resolver.resolve() + the graph's SUPERSEDES / AMENDS edges
           └─ docgen.py      to_pdf() / to_docx()
```

**`references.py` adds no detection logic of its own.** Citation shapes come from
`resolver.mr_citation` and `parser.py`, resolution from `resolver.resolve`, supersession from
edges `graph.py` already committed. It is an adapter, and that is the point: the corpus path and
the draft path cannot disagree about what a citation is or where it resolves to.

**Its index is built from the graph's nodes, not re-read from GRs.json.** So anything a citation
resolves to is by construction a node whose supersession status we can answer. An index that
could resolve to a uid the graph does not contain would hand back "verified" with no status.

Three traps it cost time to find, all pinned in `tests/test_references.py`:

- **Read header fields above the first citation, never "the first 25 lines".** Below the वाचा
  line every cited order carries its own number, date and department. On fixture
  201803071449402308 the document's date is 07.03.2018 and the first numeric date in the file is
  04.10.2004, belonging to citation 1. This is not cosmetic — the document's date is the horizon
  for "a GR cannot cite an order issued after it", so the 2004 misread silently rejected every
  real citation in the document.
- **In body prose, anchor the file number on the LAST `क्र` marker before the date.**
  `resolver.MR_NO` captures from the first one, which is right for a reference-block item (they
  are split one per ordinal) and wrong for `संदर्भ क्रमांक १ येथील … क्रमांक अर्थसं-२०२५/… दिनांक …`,
  where it swallows the whole clause. That sentence is the one carrying the cancellation
  language, so losing it loses the entire cross-department conflict check. Applied to body
  candidates only — `resolver.py` stays byte-identical on the corpus.
- **`संदर्भ क्र. १६` is a pointer into the document's own reference list, not a file number.**
  Read as one it resolves to nothing and reports as a missing archive entry — a fabricated
  defect. A "number" with no `digit_key` is unverifiable, not missing.

**The model fills fields; it never writes the form.** Asking a 2B model to reproduce a legal
template verbatim on every call is how the template drifts. `drafting.DRAFT_FIELDS` is a
whitelist — anything outside it is dropped, because a model may not invent a new section of a
Government Resolution.

**One rule engine, three consumers.** `template.DETECT` is used by `verify()` (is the section
present), by `docgen.parse()` (how should this line be aligned), and by the Verify page. A
second notion of "this line is the Subject" would drift within a week.

**Layout is data, not code.** `data/gr_template.json` holds section order (Manual Appendix 10.6),
mandatory-ness, corpus rates, and per-section `align`. The officer chose 2026-08-01: subject
right, Government title / department / Mantralaya address centred, everything else left.
Changing alignment is a JSON edit and both PDF and DOCX follow — they cannot disagree.

Note the open question there: that alignment interrupts the centred masthead, because the
resolution number and date sit left between centred lines. Real corpus GRs centre the whole
header block. The officer was shown both and kept theirs. **Do not "fix" this unasked.**

**Conditional sections are conditional.** Budget head and Finance concurrence apply only to GRs
sanctioning expenditure — 16.3% of the corpus. Universal enforcement would fail five drafts in
six. `template.has_financial_sanction()` gates them.

**Extraction reports its provenance.** `ocr.extract()` tries the PDF's own text layer FIRST and
only OCRs when there is none — OCR over a document you can already read exactly introduces
errors rather than removing them. The response always carries `method`, and the UI shows text
layer in green and OCR in amber with a confidence figure, because those warrant different trust.

**Degradation is visible, never silent.** If ollama is down, `/api/draft/questions` returns a
fixed questionnaire flagged `degraded: true` and the UI says so. "The model was unavailable" is
a legitimate state to display; a fabricated answer is not.

### Qwen3.5-2B — what it can and cannot do here

Measured, so nobody re-learns it:

- **`think: false` is mandatory.** One classification with thinking on burned 500 tokens and
  54 s without emitting an answer.
- **It copies few-shot examples verbatim.** Given a JSON example with real content it returned
  that content as its "questions". Given angle-bracket placeholders it emitted literal
  `<option>` tags. Schema in CAPITALS plus `_strip_markup()` was what finally worked.
- **It mistranslates legal Marathi**: `सदर मान्यता` → "the prevailing belief" (correct: "the
  said approval"). This is the measured reason translation goes through IndicTrans2, not the LLM.
- **On a naive zero-shot prompt it misclassified an explicit `रद्द करण्यात येत आहेत` sentence**
  as REFERENCES in Marathi and AMENDS in English. It fails in BOTH languages, so this is a
  prompt/scale limit, not a Marathi gap. It is NOT a fair test against `type_edges.py`'s tuned
  prompt — re-measure with that before concluding anything about the Groq→local swap.

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