# CHECKLIST

Running log of what is actually done. Build order is from `CLAUDE.md`; each layer is
worthless without the one below it.

---

## Step 0 — Corpus pulled ✅ (2026-07-24)

Sparse + partial clone of `orgpedia/mahGRs` (MIT) into `data/mahGRs/`, gitignored so it is
never committed and is not an embedded git repo inside ours.

```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/orgpedia/mahGRs.git
git sparse-checkout set \
  "GRs/Higher_and_Technical_Education_Department" \
  "GRs/General_Administration_Department" \
  "GRs/Finance_Department" \
  "GRs/School_Education_and_Sports_Department"
```

**440 MB on disk. 34,506 text files = 17,253 GRs, bilingual, zero unpaired.**

| department | GRs (text pairs) | metadata entries | date range |
| --- | --- | --- | --- |
| General Administration | 6,278 | 6,298 | 2018-03-16 → 2026-07-22 |
| School Education and Sports | 5,234 | 5,252 | 2018-05-15 → 2026-07-13 |
| Higher and Technical Education | 4,715 | 4,720 | 2017-10-12 → 2026-07-22 |
| Finance | 1,026 | 1,032 | 2021-01-14 → 2026-07-22 |
| **total** | **17,253** | **17,302** | 2017-10-12 → 2026-07-22 |

Verified:
- Every `.pdf.en.txt` has a matching `.pdf.mr.txt` in all four departments. Zero unpaired.
- HTE = 4,715, exactly matching the figure recorded in `CLAUDE.md`. Corpus is the one we profiled.
- Metadata is a strict superset of the text: 49 GRs have metadata but no extracted text
  (image-only PDFs). Zero text files without metadata. Parser must skip those 49, not crash.

### Finding: `GRs.json` is ground truth the build plan did not account for

Each department ships `GRs.json` + `GRs-new.json` (~3.9 MB each) that `CLAUDE.md` never
mentions. Keyed by `<uid>.pdf`:

```jsonc
{
  "url": "https://gr.maharashtra.gov.in/.../201710121514029708.pdf",
  "dept": "Higher and Technical Education Department",
  "text": "Regarding procedures and criteria for New Colleges, ...",   // subject line
  "code": "201710121514029708",                                        // uid
  "date": "12-10-2017",                                                // DD-MM-YYYY
  "order_number": "एनजीसी २०१७/( २२ ९/१७ )/मशि-४",                      // decision no., Devanagari
  "order_type": "शासन निर्णय क्रमांक",
  "num_pages": 11, "size_kb": "3371", "name": "mahtech-1.pdf", "crawl_dir": "05-May-2022"
}
```

Coverage, measured across all four departments:

| field | from `GRs.json` | from OCR text (per CLAUDE.md, HTE) |
| --- | --- | --- |
| date | **100.0%** | 75.9% (`Date:` line) |
| decision / order number | **97.4 – 98.8%** | 66.3% (`Government Decision No.`) |
| subject | 100% | — |

**Why this matters for the resolver (step 2).** The same-date collision trap is the highest-value
correctness problem in the project, and the fix is to match decision number *alongside* date.
This file gives us a near-complete, authoritative `(uid → decision_no, date)` index for the
*target* side of every citation — so resolution degrades from "parse both sides out of OCR" to
"parse only the citing side, look up against a clean index". Do not re-derive dates or decision
numbers from OCR text where this file has them; use OCR only as fallback and cross-check.

Caveats to handle, not yet handled:
- `order_number` is Devanagari-numeral (`२०१७`), citations in body text may be either script.
  Digit-system normalisation is required before any string match.
- ~2% of `order_number` values are null/empty — those fall back to text parsing.
- `GRs.json` vs `GRs-new.json` difference not yet examined.
- Metadata `date` is the portal upload date field; not yet confirmed identical to the `Date:`
  line inside the GR. Needs a sampled cross-check before being trusted as the legal date.

---

## Fixtures built ✅ (2026-07-24)

`select_fixtures.py` run against HTE. **4,715 GRs scored → 52 selected → 104 files in
`fixtures/` (3.7 MB) + `manifest.json`.**

```bash
python3 select_fixtures.py data/mahGRs/GRs/Higher_and_Technical_Education_Department fixtures/
```

Every bucket pool size reproduced the table in `CLAUDE.md` exactly (533 / 8 / 692 / 504 / 2184 /
1135 / 2280 / 1589 / 407 / 476 / 1501). Selection is deterministic and the documented figures
are trustworthy.

Verified: 52 en + 52 mr files on disk, no missing pairs, bucket uids unique and equal to the
`records` map. Manifest is internally consistent.

Naming: the script arrived as `script.py` with an empty `features/` dir alongside it. Renamed to
`select_fixtures.py` writing to `fixtures/`, matching what `CLAUDE.md` documents in both the
prose and the regenerate command, and what the script's own docstring says. Empty `features/`
left in place, unused.

### Finding: the `devanagari_leakage` bucket misses the dominant leak class

Devanagari-in-English leakage across HTE:

| threshold | GRs |
| --- | ---: |
| any Devanagari at all | 441 |
| ≥ 5 chars | 334 |
| **exactly 20 chars** | **136** ← modal cluster |
| `> 20` chars (the bucket filter) | 8 |
| ≥ 100 chars | 0 |

The histogram spikes hard at exactly 20 (136 GRs; next most common are 12 → 76 and 15 → 40).
That cluster is a single systematic MT failure: **IndicTrans2 leaves `सदर` ("the said")
untranslated** — 814 occurrences across those 136 files, plus `अभ` 135 times. It is precisely the
artefact `CLAUDE.md` names in its traps section (`The 1.सदर approval will always be...`).

The bucket's `> 20` filter sits one character above that spike, so it selected the 6 extreme
outliers (78, 55, 40, 35, 23 chars) and **excluded all 136 instances of the most common leak
pattern in the corpus.** A de-leaking routine tuned only against the selected 6 will not
generalise to the case that actually dominates.

Not changed. `CLAUDE.md` forbids silently reshuffling the fixture set mid-project because
`tests/resolver_truth.json` is keyed to these uids. Two options when it is worth acting on:

- lower the threshold to `>= 12` (pool becomes ~300) and regenerate before any truth file exists;
- or leave the fixture set alone and handle `सदर`/`अभ` as a known token-level strip rule in the
  parser, validated against the full 441-GR population rather than the fixtures.

Recommend the second — it is additive, keeps the uids stable, and the leak is a closed
vocabulary rather than a parsing problem. Decide before `resolver_truth.json` is written.

---

## Boilerplate leak pinned ✅ (2026-07-24)

Option (2) taken. `pin_boilerplate.py` appends a `template_boilerplate` bucket covering the
136-GR cluster the `devanagari_leakage` bucket structurally excluded. **`fixtures/` is now
55 GRs / 110 files.** The empty `features/` directory was removed.

```bash
python3 pin_boilerplate.py data/mahGRs/GRs/Higher_and_Technical_Education_Department fixtures/
```

The cluster resolves into exactly two token profiles:

| profile | GRs | composition |
| --- | ---: | --- |
| `सदर`×6, `अभ`×1 | 135 | 6×3 + 1×2 = 20 chars — accounts for the histogram spike exactly |
| `सदर`×4, `सदरच`×1, `खर`×2 | 1 | the variant |

Pinned uids — earliest and latest of the dominant profile, plus the sole variant:

| uid | profile | why |
| --- | --- | --- |
| `202407091224447908` | `सदर`×6, `अभ`×1 | earliest instance of the modal case |
| `202607151841599808` | `सदर`×6, `अभ`×1 | latest instance — confirms the leak is still live in 2026 |
| `202603231852133008` | `सदर`×4, `सदरच`×1, `खर`×2 | **the variant, and the important one** |

The variant earns its place: `सदरच` is `सदर` + the `च` suffix. A strip rule written as a naive
substring replace on `सदर` turns it into a dangling `च` rather than removing the token. The
de-leaker must be token-boundary aware, and this fixture is what will catch it if it is not.

All three carry `Date:` and `Government Decision No.` lines, so they exercise the leak in
isolation rather than tangled with missing-field pathologies.

### Additivity verified

- All 52 original bucket lists and record dicts byte-identical, order preserved.
- Exactly one new bucket key. No existing uid moved, was removed, or was re-scored.
- 55 bucket uids, all unique, equal to the `records` map, all 110 files present on disk.
- `total_scored` unchanged at 4,715; `selected` 52 → 55.

`pin_boilerplate.py` initially re-picked fresh uids on every invocation (a second run grew the
set to 57). It now no-ops when the bucket is already present, and verifies the pinned files
still exist rather than silently passing. Confirmed no-op across repeat runs.

---

## Devanagari leak map + de-leaker ✅ (2026-07-24)

`build_leak_map.py` → `data/devanagari_leak_map.json`; `deleak.py` applies it.

```bash
python3 build_leak_map.py data/mahGRs/GRs/Higher_and_Technical_Education_Department data/devanagari_leak_map.json
python3 deleak.py --audit data/mahGRs/GRs/Higher_and_Technical_Education_Department
```

**Acceptance test passes: 441 / 441 leaked GRs de-leak to zero Devanagari, 0 unmapped-token
errors, 0 survivors.** Reproduces CLAUDE.md exactly — 441 GRs, 75 types, 2,109 instances.

The build script asserts exhaustiveness both ways and exits non-zero if the corpus contains an
undeclared token or the map declares one never observed. The vocabulary cannot silently drift.

| class | types | instances | replacement |
| --- | ---: | ---: | --- |
| `marathi_word` | 40 | 1,817 | `""` (English follows the token, so it is redundant) |
| `latin_translit` | 35 | 292 | Latin — never stripped |

### Classification was structural, not eyeballed

Every token was bucketed by the context it appears in, and the two classes separate almost
perfectly — which is *why* a flat lookup table works:

- **ORDINAL** — token follows a displaced list ordinal (`17.अभ Any future situation…`). This is
  the template bug in CLAUDE.md: Marathi `१७. अभ्यास…` became `17.अभ …`, stranding the head of
  the Marathi sentence in front of its own English translation. Redundant → strip.
- **ACRONYM** — token sits in a dotted run (`एम.ई.ड Digital systems`, `आय.आय.ट Guwahati`).
  Latin letters written in Devanagari, inside degrees, institutions, initials, addresses →
  back-transliterate.

De-leaking the ORDINAL class incidentally **fixes the displaced-ordinal parser bug**:
`- 1.सदर No new posts can be created` → `- 1. No new posts can be created`. The ordinal is
recoverable by normal list parsing afterwards.

### Token-boundary matching is load-bearing

Matching is on whole `[ऀ-ॿ]+` runs, never substrings, and an unmapped run raises rather than
passing through. Negative control, iterating the map in frequency order the way a naive
implementation would (`सदर` before `सदरच`):

| implementation | GRs still containing Devanagari |
| --- | ---: |
| naive substring replace, map order | **46** — strands fragments like `च`, `आद`, `ह`, `आ` |
| whole-run lookup (shipped) | **0** |

`If the 9.सदरच purchase…` → naive gives `9.च purchase` (still Devanagari, silently corrupt);
whole-run gives `9. purchase`. Fixture `202603231852133008` is the regression test.

### Correction to CLAUDE.md: Devanagari *does* reach decision numbers

CLAUDE.md flags this as a resolver risk and records "sampling found none." Scanning all 9,211
`Government Decision/Memorandum No.` strings in HTE: **3 contain Devanagari (0.03%)** — rare, but
not zero.

```
Government Memorandum No: E: 721827|र SUYO-2024 / Q.No.04 / VISHI-3
Government Decision No.3611 / Pro. र.56/15/त No.2, D 13/01/2016.
```

`र` is `क्र` (क्रमांक, "number"), `त` is the तांशि/TANSHI section code, `आस` is आस्थापना. These are
mapped as `latin_translit` with real replacements (`Kra`, `Ta`, `Astha`) rather than stripped,
because the resolver keys on this field. **The de-leaker must run before resolution, not after.**
A stripped or mis-substituted character here fails resolution invisibly.

### Limitation: the vocabulary is closed for HTE only

The 75 types are exhaustive for HTE, which is what CLAUDE.md measured and what the acceptance
test covers. Across all four ingested departments it is not closed:

| scope | GRs | leaked | types | covered by HTE map |
| --- | ---: | ---: | ---: | ---: |
| HTE (mapped) | 4,715 | 441 | 75 | 100% |
| General Administration | 6,278 | 240 | 133 | 81.8% of instances |
| School Education and Sports | 5,234 | 256 | 87 | 78.8% |
| Finance | 1,026 | 89 | 55 | 72.6% |
| **all four** | **17,253** | **1,026 (5.9%)** | **223** | **89.2% of instances** |

148 unmapped types remain corpus-wide, but the long tail is thin: only 19 of them occur ≥5 times
and those cover 56% of the unmapped instances. Top unmapped: `एक` (58), `एलप` (55), `लक` (17),
`है।` (14), `ससप` (14). Extending the map is the same one-pass exercise over the other three
departments — not started, since this instruction scoped to the 75.

Until then `deleak.py` raises `UnmappedToken` on non-HTE input rather than silently emitting
Devanagari, which is the correct failure mode but means it is not yet safe to run corpus-wide.

---

## Parser v1 ✅ (2026-07-24)

`parser.py` — GR text → GR record to the CLAUDE.md schema. Regex only, no LLM.
`parse_report.py` gives per-bucket field coverage, missing-field buckets first.

```bash
python3 parser.py fixtures/ out/parsed.json
python3 parse_report.py fixtures/ out/parsed.json
```

### Fixtures — 55/55

| field | coverage |
| --- | ---: |
| `decision_no` | 55/55 (100%) |
| `subject` | 55/55 (100%) |
| `date` | 55/55 (100%) |
| `references` | 55/55 (100%) |
| `body` | 55/55 (100%) |
| `conditions` | 25/55 (45%) — most GRs genuinely have no numbered list |
| `amounts` | 25/55 (45%) — most GRs genuinely carry no rupee figure |

**All four hard buckets — `no_decision_no`, `no_reference_block`, `no_date_line`,
`template_boilerplate` — are at 100% on the five always-present fields.** Running them first was
the right call: every one of them exposed a real defect, and three of the four turned out to be
mislabelled by the *selection* regex rather than genuinely missing the field.

### Full HTE corpus — batch, 0 crashes, 6 seconds

| field | coverage |
| --- | ---: |
| `date` | 4715/4715 (100.0%) |
| `body` | 4714/4715 (100.0%) |
| `subject` | 4703/4715 (99.7%) |
| `decision_no` | 4652/4715 (98.7%) |
| `references` | 4557/4715 (96.6%) |
| `conditions` | 1178/4715 (25.0%) |
| `amounts` | 1260/4715 (26.7%) |

10,379 references extracted, mean 2.2 per GR. Summary artefact: `out/hte_coverage.json`.
Full records are not committed — 4,715 records including body paragraphs is far too large, and
the run regenerates in 6 seconds.

### Invariants, enforced structurally and asserted in the report

- **`date` is always the uid prefix.** PASS on all 55. The body date is parsed only into
  `_provenance.body_date` so drift is measurable; it cannot reach the `date` field.
- **No fabricated citations.** `resolved_uid` is `None` and `confidence` `0.0` on every
  reference, always. Resolution is step 2 and needs the hand-labelled truth set.
- **De-leak runs before parsing**, so Devanagari cannot reach `decision_no`.

### Four corrections to CLAUDE.md's measured figures

These change what the "missing field" buckets actually mean.

| claim in CLAUDE.md | measured on HTE | why it differs |
| --- | --- | --- |
| `Government Decision No.` present 66.3% | **98.8%** | the header varies — Decision 2254, Resolution 1020, Order 737, Memorandum 207, Circular 142, Corrigendum 43, plus `Number:` instead of `No:` (5.1%). Matching only "Decision" finds 57.3%. |
| enumerated `Reference:` block 51.6% | **79.6%** | `Read:` is the same block under a different translation and labels a further 25.6%. So "48% have no Reference block" is really ~20%. |
| `Date:` line — 5.5% line-anchored / 8.1% unanchored, **78% of those disagree** with the uid | **87.0% parse; 93.9% of those agree** | allowing `The date:` and a trailing period. The 78%-disagree figure comes from unanchored matching, which captures a *cited* date out of the reference block instead of the document's own. |
| `no_decision_no` = 1,589 GRs (34%) | ~4% genuinely lack one | the bucket is mostly a false negative of `select_fixtures.py`'s narrow regex |

The uid remains the date source regardless — 100% coverage with no parsing beats 87% with
parsing. But the body date is far more trustworthy than the doc suggests.

### Empirical drift, which sizes the resolver's date window

Where body date and uid disagree (249 GRs), the gap is small and one-directional — the uid
(publication) usually trails the body (signing) date:

| uid − body, days | +1 | +2 | +3 | −1 | −2 | −3 | +4 | +5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GRs | 126 | 22 | 22 | 21 | 5 | 5 | 5 | 5 |

**This is direct empirical support for CLAUDE.md's ±3-day resolver window** — ±3 captures the
overwhelming majority. `tests/resolver_truth.json` should still be the final arbiter.

### Defects found and fixed while running the hard buckets first

1. **`REF_ITEM` split on statutory sub-sections.** `Section 40 (1) of the Act` and
   `Section 106 (2)` were being parsed as reference-list ordinals, destroying the reference list
   of any GR citing a statute. The `(N)` form is now rejected mid-line; only line-anchored
   ordinals and bare mid-line `N)` are accepted.
2. **Reference zone stopped at the date line.** ~20% of GRs label no reference block, and their
   citations sit *after* the date line as bare lines (`Letter from the Governor's Office dated
   June 7, 2016.`) carrying a date but no order word — position is the only signal. The zone now
   runs from the top of page 1 to the body marker.
3. **Conditions required the run to start at `1.`** OCR loses the first ordinal often enough
   that this dropped whole lists — fixture `202208251443425308` runs 2..6 with no `1.` anywhere.
   Now takes the longest ascending run regardless of start, minimum length 3.
4. **Dates swallowed into number fields.** `NGC 2017 / (29/17) / Masi-D. 15.09.2017` and
   `Narrow-2204 / Q.No.91 / VISHI-1 Date: - 18.07.2025` kept the date inside the key, which
   would break resolver matching. Trimmed by `_clean_no()`.
5. **Letter-layout GRs have no subject above "Government of Maharashtra"** — it sits in an
   explicit `Subject:` line below the address block. Added as a fallback.

Conditions extraction is sequence-aware because the template family fuses ordinals into
sentence bodies (`The 1. approval will always be…`, `…capacity for the 3. course…`), so ordinals
cannot be found by anchoring to line start. `displaced_ordinals` flags 676 GRs corpus-wide.

### Known limitations, not yet addressed

- `references[].decision_no` is extracted verbatim and not normalised — the resolver will need
  to fold digit systems and punctuation before matching.
- 158 GRs corpus-wide yield no references at all; not yet verified whether that is correct
  (a GR citing nothing is legitimate) or a parse failure.
- `header_variant:In Context` and `header_variant:Refinery` look like over-matches of the broad
  header regex; harmless for extraction but worth tightening.
- Only the English side is parsed. `lang` is recorded as `"en"`. Marathi is authoritative and
  no legal question should be resolved from these records alone.

---

## Labelling tool rebuilt ✅ (2026-07-25)

`label_citations.py` v2. Step 2 (resolver) is blocked on `tests/resolver_truth.json`, which must
be hand-labelled — the tool exists to make that fast, and it does not decide anything.

```bash
python3 label_citations.py fixtures/ data/mahGRs/GRs/Higher_and_Technical_Education_Department/ \
    --out tests/resolver_truth.json --n 15
```

Three defects in v1, each of which would have cost real time per row or produced a wrong key:

1. **Citations came from a local regex that only matched `Reference:`.** 25.6% of HTE labels the
   block `Read:` instead, so those GRs fell through to a whole-document scan and emitted run-on
   blobs spanning three citations — carrying the text of one and the date of another. It also
   de-duplicated on date, so a GR citing six orders yielded one item. Now delegates to
   `parser.parse()`, which already handles `Read:`, rejects statutory sub-sections and splits
   enumerated items. Fixture `201803071449402308` went from 1 garbled item to **10 clean ones**;
   the fixture-wide citation count rose 218 → 252.
2. **Candidate identifiers were OCR-only.** Displayed numbers like
   `wledge Corporation Limited" to General Administration Department.` — visibly truncated
   garbage, against which the overlap ranking is meaningless. Now unions `GRs.json`
   `order_number` (4,660/4,715) with the OCR header (4,641/4,715) and shows both, so a Marathi
   reader can verify against the authoritative Devanagari string directly.
3. **Only date-window candidates were offered.** See the finding below — this one hid correct
   answers entirely.

Also flags citations naming another department (`** cites Finance Department — not in this index,
probably n **`). ~53% of HTE citations leave HTE, and the v1 "outside range" check only tested
dates, so a Finance GR dated inside the range looked resolvable. These sort last.

### Finding: `order_number` is a file number, not a GR identifier — 41.1% collide

This is a correction to `CLAUDE.md`'s central resolver claim, now written up there in full under
**Same-number collision**. Measured on HTE:

| | |
| --- | ---: |
| GRs with an `order_number` | 4,662 |
| distinct `order_number` values | 3,326 |
| **GRs sharing a number with ≥1 other GR** | **1,916 (41.1%)** |
| worst single number | 41 GRs |

A departmental file accumulates decisions over years. Fixture `201803071449402308` cites **six**
GRs under `Muwad-2016/(38/16)/Masi-1` spanning Apr 2016 → Jan 2018, and carries that number
itself. So "match the decision number alongside the date" is necessary but not sufficient — both
keys collide, and **retrieval needs two paths**: the ±3-day window *and* every GR sharing the
number at any date. That series' members sit at −95d, +252d, +416d and +1331d from one cited
date; a window-only tool cannot see them.

**Matching is on the digit signature, not the string.** `order_number` is 97.6% Devanagari
(`मुवाढ-२०१६/( ३८/१६ )/मशि-१`) while citations are transliterated Latin
(`Muwad-2016/(38/16)/Mashi-1`), so no string match connects them — and transliteration is
unstable for the same file anyway (`Masi-1` / `Mashi-1` / `MASHI-1`). Ordered digit runs are
script- and transliteration-independent: both sides reduce to `('2016','38','16','1')`.
2,647 of 3,252 signatures are unique, so retrieval stays tight. Signatures with <2 runs are
rejected as insufficiently discriminative.

### Truth-file ids are content-addressed, not positional

v1 keyed rows `<uid>#<index into the reference list>`. `parser.py`'s reference extraction will
keep improving, and any added or split item would silently re-point every existing label — on the
one artefact in this project that cannot be regenerated. Ids are now
`<uid>#<cited_date>#<6-char hash of date + digit signature>`, which survives parser changes.
Verified: 252 fixture citations → 251 distinct ids, resume across runs works, and the single
collapse is correct (`विशि` rendered `Vishy-1` in one reference and `Special-1` in another, same
date and signature — one cited order, one label).

### Finding: the corpus has gaps inside its own range and department

That `Muwad` citation is dated 16.01.2018 — inside the corpus range, inside HTE — yet no member
of the series carries that date (nearest 2017-10-13 and 2018-09-25). The cited GR is not in the
crawl. `unresolved` is therefore the *correct* answer for some citations that look resolvable,
which means the resolver must be scored on finding the **right** target, not on finding one.
A recall-only metric would reward fabrication and violate rule 3.

---

## Step 2 — Resolver ✅ (2026-07-26)

`resolver.py` + `tests/test_resolver_invariants.py` (14 tests, all passing).

```bash
python resolver.py fixtures/ data/mahGRs/GRs/Higher_and_Technical_Education_Department/ \
    --out out/resolved.json            # add --audit for the human-adjudication list
python -m pytest tests/test_resolver_invariants.py -q
```

**Built without waiting on hand-labels.** Labelling was treated as the blocker for a day and it
was not one — it gates the *accuracy number*, nothing else. See "Validating without labels" in
CLAUDE.md. `tests/resolver_truth.json` still does not exist and nothing in this step wrote to it.

### Resolves from the Marathi side

Rule 1 says Marathi is authoritative, so extraction reads `.mr.txt` and matches Devanagari file
numbers against `GRs.json` `order_number` — crawled portal metadata, independent of our OCR text
pipeline. The English side is then used only as a *witness*, never as the substrate.

Getting Marathi extraction to parity took four fixes; the first attempt found 95 citations against
English's 252, and a header-token census on the fixtures explained all of the gap:

| fix | why |
| --- | --- |
| `दि.` accepted, not just `दिनांक` | `दि.` is the **dominant** date marker; anchoring on `दिनांक` alone lost most citations |
| `दिनाक` accepted | anusvara dropped by OCR — a real, frequent variant |
| `पहा` added as a third header word | alongside `वाचा` / `संदर्भ` |
| `शासन आदेश` added to body-start markers | missing, so reference regions ran ~700 chars into the body and swallowed prose |

Final: **239 citations from 55 fixtures.**

### `समक्रमांक` — citations with no number of their own

`समक्रमांक` ("of the same number") cites another GR **in the citing document's own file**, so the
number is not in the citation text at all. Inheriting the citing GR's `order_number` resolves
these; without it they look permanently unresolvable. +3 resolutions.

### The key is the digits, concatenated

Replaced the tuple-of-digit-runs "digit signature" with a concatenated `digit_key`, because
**Marathi OCR inserts spaces inside Devanagari digit runs**: `( १२ ९/१३ )` → `2013|12|9|13|2`
where English `(129/13)` → `2013|129|13|2`. A tuple comparison calls those different files.
Concatenated, both are `201312913`.

Measured the cost before committing to it: 3,252 → 3,240 distinct keys over 4,645 numbered GRs,
in-group rate 43.0% → 43.3%. Inspected all 12 merged keys — every one is a spacing variant of the
same number, i.e. a merge that *should* happen. `label_citations.py` now imports `digit_key` from
`resolver.py` instead of defining its own, so the two cannot drift.

### The honest denominator (`scope_report`)

A raw resolution rate is misleading in both directions and the flattering direction is the gameable
one. Four exclusive, exhaustive buckets, printed by the same command that writes the artefact:

| bucket | n | why it cannot resolve |
| --- | ---: | --- |
| `not_a_gr` | 87 | citation is a letter / email / notification / minutes — there is no GR to find |
| `other_dept` | 26 | names a department this index does not contain; widening the corpus fixes it |
| `outside_range` | 85 | cited date outside the crawl (index covers 2017-10-12 → 2026-07-22) |
| `in_scope` | 41 | a GR, in HTE, inside the window — **the resolver's to get right** |

**In-scope: 26/41 = 63.4%.** Over all 239 it would read 10.9%; both numbers alone mislead, which
is why the breakdown is what gets quoted. Two tests keep the buckets exclusive and exhaustive and
assert no resolution lands in a bucket declared unresolvable.

Of the 15 in-scope misses, 24 rows corpus-wide are "number matched an N-GR series but no member
within ±3d" — these are `--audit` output, and per the in-range-gap finding above the correct answer
for most is genuinely `unresolved`. Nearest siblings sit +70d, −185d, −465d, +569d away. Snapping
to them would fabricate citations.

### Cross-language agreement — the only independent witness

The Marathi path does exact Devanagari matching against portal metadata; the English path sees
IndicTrans2 transliteration with unstable section codes. **Uncorrelated failure modes**, so
agreement is evidence rather than self-consistency. 11 comparable rows, **0 contradictions**,
10 of 11 exact key equality.

Two relaxations, each earned by inspecting the case that forced it rather than by loosening until
green:

1. **Skip English `decision_no` that is only the cited date restated.** `parser.py` sometimes
   returns e.g. `'22.02.2018'` as a reference's decision number. Such a row carries nothing the
   resolver did not already use — it can neither confirm nor contradict. *(Logged as a parser
   defect below.)*
2. **Containment in either direction, not equality.** `संकीर्ण-२०१६/प्र.क्र.२६२/१६/विशि-१`
   (`2016262161`) arrived in English as `262/16/ VC-1, 2016/ No. 262/16/ VC-1` — IndicTrans2
   reordered the components and `parser.py`'s capture stopped at the first comma, yielding
   `262161` with the year run stranded. Dropping digits is transcription loss; *substituting* them
   means a different file, and containment still rejects that. Verified it stays discriminating:
   a mean of **3.6 GRs out of 4,718** are compatible with a given English key, i.e. it excludes
   99.92% of the corpus.

Rejected the alternative of keying off the reference's full raw English text — measured 11 failures
against `decision_no`'s 1, because the raw is mostly empty of numbers or contains only date
fragments.

### New parser defect found (not yet fixed)

`parser.py` sometimes returns a bare date as a reference's `decision_no` (e.g. `'22.02.2018'` for a
reference dated 2018-02-22) — a partial regression of defect 4 above. Also truncates a decision
number at the first comma, which loses a component when IndicTrans2 reorders the number. Neither
affects the resolver, which reads Marathi; both degrade the English witness.

---

## Step 3 — Graph ✅ (2026-07-26)

`graph.py` + `tests/test_graph_invariants.py` (15 tests). Full suite: **29 passing.**

```bash
python graph.py data/mahGRs/GRs --out out/graph.json     # 10 seconds, all 4 departments
python -m pytest tests/ -q
```

**All four departments indexed.** `resolver.load_index` now takes many corpus dirs and
`resolve` takes `in_index` (the set of departments actually present) instead of `own_dept`. A
citation naming another department is now only unresolvable when that department is *genuinely
absent from the index* — previously any cross-department citation was rejected outright, which
is the exact opposite of the problem statement's first bullet. `DEPT_BY_CODE` maps the uid's
trailing 2-digit code: `05` Finance, `07` GAD, `08` HTE, `21` School Education (verified unique).

Added a third key, available only in the multi-department index: **when a citation names its
department, candidates are restricted to that department** — but only when that does not
eliminate every candidate, so a mislabelled department degrades instead of destroying a good
match. This is what stops the wider index from costing precision.

### Result over the full corpus `[MEASURED]`

| | |
| --- | ---: |
| nodes (GRs indexed) | **17,283** |
| documents scanned | 17,253 |
| citations extracted | **27,948** |
| edges (resolved) | **4,815** (17.2%) |
| **cross-departmental edges** | **1,538** (31.9% of edges) |
| unresolved, all labelled | 23,133 |
| nodes touched by an edge | 3,798 (22.0%) |
| runtime | **10 s** |

### Finding: Finance is the structural chokepoint

**96.7% of all cross-departmental edges point into Finance** (1,488 of 1,538). Every other
department's spending decisions hang off Finance appropriation and fund-distribution orders.

Highest in-degree nodes are all Finance budget orders — **209 GRs cite a single Finance circular
of 07.04.2025** (`अर्थसं-२०२५/प्र.क्र.४४/अर्थ-३`, "Fund Release 2025-26"). This is the blast-radius
story with a real number: supersede one Finance appropriation order and hundreds of downstream
GRs across departments are affected.

### The in-degree was verified, not assumed

`CLAUDE.md` warns that a naive date-only resolver produced five GRs falsely tied at in-degree
292, so in-degree 209 needed checking before being believed. Verified: all 209 citing edges carry
the same digit key (`2025443`) *and* the same cited date, and every evidence sentence explicitly
names that Finance circular. **Ten GRs in the corpus share that file number; only one carries
that date** — the two-key mechanism selected the right series member out of ten.

It also caught the digit key earning its keep in production. Two citations of the *same* order:

```
अर्थसं-२०२५/प्र.क्र.४४/अर्थ-३           → exact number match
अर्थसं-२०२५/प्र.क्र.४४/अर्थसंकल्प-३    → digit key match   ("Arth-3" vs "Arthsankalp-3")
```

One department abbreviates the section code, another spells it out. String matching gets the
first and silently misses the second.

### Bug caught by the new tests: 20-digit uids

`test_every_edge_endpoint_is_a_node` failed on first run. **19 of 17,253 filenames carry a
20-digit uid instead of 18** — upstream corpus artefacts, absent from `GRs.json`, so they have no
metadata and cannot be nodes. `load_index` already filtered them; `graph.py` globbed filenames
without the same check, producing edges whose `src` was not a node. A 20-digit uid also makes the
trailing department code meaningless. Now skipped and **counted** as
`stats.skipped_malformed_uid` — 0.1% caught and reported beats 0.1% silently missing.

### The test that matters most

`test_every_edge_evidence_is_verbatim` samples 400 edges and asserts the evidence sentence
actually occurs in the citing document's Marathi text (whitespace-normalised, nothing else).
This is what turns "every edge carries evidence" from a slogan into a mechanically enforced
property. An edge whose evidence is not in the source document is fabricated.

### Honest note on the resolution rate

17.2% over all 27,948 citations, and that number alone is misleading in the usual direction.
Unresolved breakdown: 7,072 `date_only_insufficient` (date matched, no number agreement — a
*correct refusal*, this is the same-date collision trap), 6,775 `no_number` (citation carries no
file number at all), 4,013 `number_absent`, 2,824 `series_gap` (number matched a real series but
no member in the window → cited GR absent from the crawl), 2,012 `other_dept`, 437 `ambiguous`.
Per `CLAUDE.md`, `series_gap` and friends are **unverifiable, not dead** — they must never be
counted as dead references.

---

## AI layer — propose / verify / degrade ✅ (2026-07-26 → 27)

`ai/client.py` (transport, cache-first), `ai/verify.py` (gates G1–G7), `type_edges.py` (edge
typing). Full spec in `AI_ARCHITECTURE.md`. **Rule 4 in `CLAUDE.md` was rewritten**: it previously
forbade most of this, which was defensible engineering and wrong for an AI hackathon.

### Working Groq configuration `[MEASURED]`

| item | value |
| --- | --- |
| endpoint | `POST https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible) |
| text / tools model | `openai/gpt-oss-120b` |
| STT / vision | `whisper-large-v3-turbo` / `qwen/qwen3.6-27b` — **wired but untested** |
| token param | **`max_completion_tokens`**, not `max_tokens` |
| extra knob | `reasoning_effort: low \| medium \| high` |

Three transport gotchas, each cost real time:

1. **Cloudflare rejects `Python-urllib`** with `403 error code: 1010` (browser-signature ban).
   Any client must send a real `User-Agent`.
2. **Two different 429s.** TPM (per-minute) is waitable — the body states "try again in 7.17s".
   TPD (per-**day**) is not: it says "try again in 9m20s", and honouring that six times per call
   hangs a job for hours. The client now distinguishes them and fails fast on TPD.
3. **The daily cap is per ORGANISATION, not per key.** Three different API keys all reported
   `org_01jjyvv85bfg7v64cbvcxwjmbz` and shared one exhausted 200,000-token pool. Generating new
   keys does nothing.

### Token economics — the binding constraint on this project `[MEASURED]`

Over 231 single-sentence calls: mean 1,484 tokens/call, **60% of all tokens were prompt**, and 83%
of completion tokens were reasoning. The ~836-token system prompt was re-sent identically 702
times. A full pass cost ~1,042K tokens against a 200K/day cap — the instructions alone were more
than half of it.

- **Fixed by batching** (`--batch`, default 8): rules sent once per batch, ~30% total saving. Not
  10×, because reasoning tokens are per-decision and do not shrink.
- **`reasoning_effort="low"` tested and rejected** — it flipped a verdict on the first sample. A
  cheaper wrong answer is not a saving in a legal graph.
- **A malformed or short batch falls back to one call per sentence**, so batching can never
  silently lose an edge.

### Edge typing result

Deterministic pre-filter does the heavy lifting — the model only ever sees a cue-bearing sentence
that is already linked to a resolved citation by one of three **exact** linkers: the sentence
repeats the cited date (141), names `संदर्भ क्र. N` (32), or the document has exactly one resolved
citation (545, added to recover 726 stranded cue sentences). Never fuzzy: a mislinked edge means a
correctly-typed sentence attached to the wrong GR, which no downstream gate can catch.

718 candidate edges (14.9%), of which 231 calls completed before the quota died →
**25 SUPERSEDES, 93 AMENDS**, 230 VERIFIED / 3 FLAGGED. **471 calls still unrun.**

### What the gates actually caught

- **G1 caught the model corrupting Marathi.** It quoted `अधिकरणित करुन` where the source reads
  `अधिक्रमित करुन` — it mistyped a Devanagari word while copying. Classification was right, the
  evidence was fabricated. The cue now falls back to the verbatim extracted sentence.
- **G7 had a false positive I introduced.** I listed `आदेश` ("order") as a *subordinate* object, so
  `संदर्भाधीन दिनांक ०८.०१.२०२० रोजीचे आदेश रद्द करण्यात येत आहेत` ("the orders dated 08.01.2020
  are cancelled") was demoted to AMENDS. **A Government Resolution *is* an order.** Fixed with an
  explicit `ORDER_ITSELF` set, and exact matching instead of substring — `पद` ("post") is a
  substring of `पदभरती` ("recruitment"). Had this not been fixed, the marquee latent finding below
  would not exist.
- **A third trap found in the data:** `सुधारणा करण्याचे शासनाच्या विचाराधीन होते` — "amendment was
  under consideration". Deliberative mood in the Proposal section states intent, not a decision.

Both gate bugs were **judgement** errors that every gate passed. This is the concrete evidence for
`AI_ARCHITECTURE.md` §9.1: the gates bound fabrication, not judgement. Human spot-checking of
SUPERSEDES is therefore not optional.

### Reproducibility proven

Re-ran the entire typing pass with `AI_MODE=strict` (client physically refuses to open a socket)
and got byte-identical results from committed cache. `tests/conftest.py` forces that mode, so the
**test suite cannot spend a token** — a cache miss raises instead of billing.

---

## Step 4 — Dead-reference audit ✅ (2026-07-27)

`audit.py` → `out/audit.json`. **21 dead references**: 8 ROTTED, 13 BORN_DEAD, **2 latent
cross-departmental**.

Definitions are choices, not data, and the UI shows them beside the number. "In force" := no
incoming SUPERSEDES edge — an *upper* bound on in-force, so the count is conservative: supersession
from outside the four departments, expiry by a GR's own terms, and silent supersession are all
invisible and would only increase it.

### The finding the project was built to produce

> Finance issued a **Government E-Vehicle Price Limit Policy** on 03.02.2022. **Finance replaced it
> itself** on 02.02.2024 with a broader vehicle price-limit policy. Two **General Administration**
> GRs approving vehicle purchases — 13.10.2022 and 24.11.2023 — are still in force and depend on
> the replaced policy.

Evidence: `७. यापूर्वी निर्गमित करण्यात आलेले वाहनांच्या किंमत मर्यादेबाबतचे आदेश अधिक्रमित करुन`
("By superseding the previously issued orders regarding vehicle price limits"). All six gates pass.

**Neither department can see this.** GAD does not track Finance's supersessions; Finance does not
know who relies on its policy. It requires traversing a cross-departmental reference edge *and* a
supersession chain — a property of the graph, not of any document.

Honest scope: both latent cases cite the *same* Finance order, so it is one dead policy affecting
two approvals. Only 5 distinct dead orders lie behind all 21 findings, 13 of them behind one
(the MNLU Aurangabad construction approval).

### Two bugs caught by inspection

- **Duplicate findings.** The same citation often appears in both the reference block and the body,
  giving duplicate `src→dst` edges. One legal fact must be one finding, or the headline inflates on
  a formatting artefact. Deduplicated on `(citing, target, killer)`.
- **Self-supersession.** A GR that cancels an order almost always cites it too, producing both a
  REFERENCES and a SUPERSEDES edge for the same pair; the REFERENCES half must not be read as that
  GR citing a dead order.

`unverifiable` (21,121 citations) is kept in a **separate section with its own warning**. Counting
those as dead would multiply the headline and make it false — they are crawl gaps, not deaths.

---

## Metrics — `metrics.py` ✅ (2026-07-26)

```bash
python metrics.py --graph out/graph.json --out out/metrics.json    # 8 s
```

Answers "what can I show a judge" without a labelled answer key. **It computes no accuracy figure
and says so**: `accuracy.status = "UNMEASURED"`.

| metric | value | note |
| --- | --- | --- |
| **ablation — date alone** | **100% ambiguous**, mean 44.2 candidates, worst 380 | measures the *corpus*, so unfalsifiable |
| ablation — number alone | 60.2% ambiguous, 29.1% unique | |
| cross-language agreement | **94.34%** over 3,462 comparable edges | a **lower bound** — see below |
| evidence groundedness | **100%** of 600 sampled edges | verbatim in source |
| invariant violations | **0** over 4,815 edges | |

The 196 residual cross-language disagreements are dominated by **English-side** damage, not
resolver error: `भाग-१` renders as "Part-**I**" (the digit becomes a Roman numeral and vanishes),
and the translation sometimes replaces the file number with the date outright. Hence "lower bound".

Field deliberately named `resolution_rate_pct_DO_NOT_QUOTE_ALONE` — 17.2% is mostly *correct
refusals*, and a resolver that guessed would score higher on it.

### Independent plausibility adjudication (subagent, 2026-07-27)

Sampled 60 edges and judged **semantic plausibility** — deliberately not number+date, which would
be circular. Result: **60/60 plausible, 0 implausible, 0 model calls**. Its own caveat is the
important one and is accepted: this cannot catch the resolver picking the **wrong same-topic
sibling** (e.g. the wrong year of a recurring annual scheme), which is the failure mode `CLAUDE.md`
worries about most. Reassuring about *relatedness*, silent about *correct instance*. Written to
`out/independent_adjudication.json`; `tests/resolver_truth.json` was never touched.

---

## Step 6 — GR-Lint ✅ (2026-07-27)

`lint.py` + `data/template_profile.json` + `tests/test_lint.py`.

```bash
python lint.py --mine data/mahGRs/GRs --profile data/template_profile.json
python lint.py --audit-corpus data/mahGRs/GRs --limit 2000
```

**Rules are mined, not transcribed**, and presence varies enormously by department `[MEASURED]`
over ~700 sampled GRs each:

| marker | Finance | GAD | HTE | School Ed |
| --- | ---: | ---: | ---: | ---: |
| `प्रस्तावना` (preamble) | 43% | **31%** | 67% | **78%** |
| `शासन निर्णय :` header | 37% | 32% | 69% | 61% |
| `वाचा` (read) | 40% | 37% | 33% | 61% |

A hand-written rule requiring a `प्रस्तावना` would flag **69% of General Administration's lawful
output as defective**. Severity comes from the data: ≥99% support → ERROR, 90–99% → WARN, below
that → no rule at all.

### Two bugs, both instructive

1. **`1. सदर पदे…` is normal Marathi formatting, not the displaced-ordinal defect.** My regex let a
   preceding `.` plus newline satisfy "non-whitespace before", flagging it in **52%** of GRs. The
   defect is an **English-side translation artefact** — measured 46/700 in HTE English vs 13 in
   Marathi. `CLAUDE.md`'s parser-bug section has been corrected accordingly.
2. **One canonical section order was wrong.** Sorting markers by mean position and demanding that
   total order produced **2,910 violations over 2,000 GRs**. Measured pairwise, 18 orderings hold
   in ≥95% of documents containing both markers, but **18 pairs are free variation** —
   `order_number` before `date_line` is only 75%, before `mantralaya` 74%. Only reliable pairs are
   enforced; the free-variation list is published alongside, and *that list is the evidence the
   rules were measured*.

Result: **1.2% clean → 76.5% clean**, 23 ERRORs over 2,000 GRs. `tests/test_lint.py` pins both
regressions plus an anti-crying-wolf assertion (≥60% of a mined corpus must pass its own linter).

---

## Step 8 — Bilingual terminology + parity ✅ (2026-07-27)

`bilingual.py` → `out/bilingual.json`.

### Numeric parity — the strong half

| | |
| --- | ---: |
| pairs sampled | 3,000 |
| a naive numeric diff would flag | **92%** — useless |
| significant divergence (≥4 significant digits) | **34.3%** |
| **MAGNITUDE_ERROR** | **335** |
| TRUNCATED / MISSING / TABLE_MERGE / YEAR_ONLY | 247 / 798 / 32 / 896 |

Worst case **×100,000**: `17567000000` in Marathi against `175670` in English. Many at exactly
×1,000 — the pathology `CLAUDE.md` predicted. Every divergence is **classified before being
reported**; small integers (73% of raw mismatches — list ordinals, page numbers) are excluded as
carrying no legal weight.

### Glossary — and a mistake worth keeping recorded

The first version returned 120 "inconsistently rendered" terms and **most were nonsense**:
`तक्रारी`, `प्रवेश` and `शुल्क` all mapped to the same English cluster (capitation / ragging /
usability), because one family of education-regulation GRs contains all those words together. Lift
was measuring **document topic, not translation**.

Fixed by a property rather than a threshold: **a translation is near-bijective; a topic marker is
many-to-many.** An English word that is a high-lift partner of many different Marathi terms is
describing subject matter, not rendering any one term. 120 → **26**, and the survivors are real:

- `लिपिक` (clerk) → typist 59%, typewriter 37%, clerks 26% — one post title, three job titles
- `लघुलेखक` (stenographer) → **writer 86%, story 43%** — a genuine mistranslation
- `पुरस्कार` (award) → puraskar 44%, gaurav 39%, awards 69% — transliterated *and* translated

~40% noise remains (`नांदेड` → jalna/latur is district names co-occurring), so it is presented as
**lead generation for a human terminologist, not a dictionary**. The caveat travels with it
everywhere: the English side is machine translation *of the Marathi*, so this measures translation
fidelity, never divergence between two official texts.

---

## UI + API ✅ (2026-07-27)

`api.py` (FastAPI, read-only over cached artefacts) + `web/` (Vite + React + TypeScript,
Cytoscape). **Spring Boot was considered and rejected**: the entire graph engine is Python, so it
would have meant either rewriting the resolver in Java or adding a pointless bridge layer.

```bash
.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000     # serves web/dist at /
cd web && npm run build
```

Six pages: **The Finding** (leads with the dead-reference count, not a feature list, and carries an
explicit "Accuracy: Unmeasured" tile) · **Graph Explorer** (superseded GRs drawn hollow with a
dashed red outline — an arrow into one *is* a dead reference; click an edge for its verbatim
Marathi and per-gate results) · **Reference Audit** (unverifiable citations in a *separate* tab) ·
**GR-Lint** (rules beside the free-variation list) · **Bilingual Terms** · **Trust Ledger**.

Design rules: the 25 MB graph is **never shipped whole** (bounded neighbourhoods, capped at 130
nodes — the top hub has in-degree 209); every route returning an edge returns its evidence; a
missing artefact yields `available: false` rather than a 500.

---

## Next

### ⚠ OWED — precision audit (deferred by Ghruank 2026-07-26, explicitly asked to be reminded)

~50 resolved edges, human yes/no against the Marathi evidence + target's number/date. ~15 min.
Converts `metrics.json`'s `accuracy: UNMEASURED` into a real headline number, which is the one
gap a judge can poke. **Do this before the deck is written.** Precision-only sampling is much
cheaper than `tests/resolver_truth.json` and is a separate artefact — do not merge them, and do
not machine-generate either.

Everything else is measured label-free and reproducible via `python metrics.py`:
ablation (date alone: **100% ambiguous**, mean 44.2 candidates, worst 380), cross-language
agreement **94.34%** over 3,462 comparable edges (a *lower bound* — the 196 residuals are
dominated by English-side damage: `भाग-१` → "Part-**I**" loses the digit, and the translation
sometimes replaces the file number with the date), **0** invariant violations over 4,815 edges,
**100%** evidence groundedness on 600 sampled edges.

**`DESIGN.md` is the forward-looking spec for steps 3–10** — contracts, algorithms, provenance
tags on every claim, and the open decisions. Read that before implementing any of the below.

One finding from writing it that changes step 3's design, recorded here because it is measured:
**cue words cannot type edges document-wide.** Of 40 cue-bearing Marathi sentences across 22
fixtures, only 11 (28%) also contain a citation, and inspecting those shows `सुधारणा` and
`पुढे चालू` occurring *inside file numbers and section codes* (`वित्तीय सुधारणा-१` =
"Financial Reforms-1"). Cue and citation must share a sentence, and the cue must be rejected
inside identifier strings first — `MR_NO_REJECT` in `resolver.py` is the precedent.

1. **Step 3 — graph.** Nodes + typed `REFERENCES` / `AMENDS` / `SUPERSEDES` edges from
   `out/resolved.json`, every edge carrying its verbatim evidence sentence. Supersession and
   amendment language is already measured (14.7% / 10.7% of HTE) and fixtures exist for both.
2. **Widen to the other three departments.** 26 in-scope citations is thin for a demo, and
   `other_dept` (26) + `outside_range` (85) both shrink as the index grows. This is a batch run,
   not new code — the largest single gain available.
3. **Hand-label `tests/resolver_truth.json`** — ~15 rows, `label_citations.py --n 15`. Human-only,
   must not be machine-generated or extended. Buys the accuracy number for the deck. Not blocking
   anything; do it when there is a spare 20 minutes.
