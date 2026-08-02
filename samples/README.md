# Sample GRs for the Verify GR page

## The demo pair — use these two

Same department, same form, opposite answers. Upload one, then the other.

| | file | verdict the page shows |
|---|---|---|
| **A** | `demo-A-citations-aligned.pdf` | **Aligned with the orders it cites** — 15 citations, 9 resolve, every one of them still in force |
| **B** | `demo-B-citations-not-aligned.pdf` | **NOT aligned with the orders it cites** — 2 citations, and the one that resolves was superseded |

Both are real General Administration resolutions. **B is the one to linger on:** it cites
exactly one Government Resolution, that order was cancelled on 21.07.2026, and nothing in
either document says so. Click **View this GR** on the citation and the popup shows the
superseding order, plus a link to the original signed PDF on `gr.maharashtra.gov.in`.

B's second citation is a Bombay High Court order. It comes back *not checked — a GR archive
never holds court orders*, in grey, not red. That distinction is the point: **only A's and B's
red items are defects.** Everything grey is a limit of our coverage, not of the document.

The demo flow:

1. Upload → the GR appears, editable.
2. **See citations** → the list, each with its department and verdict.
3. The **alignment verdict** sits at the top. It is computed from the dependency graph; no
   model is consulted for it.
4. **Write a plain-language review** → the on-premise model puts the findings into prose.
   Takes 20–40 s on this box. It explains the verdict; it never decides it.
5. **View this GR** on any resolved citation → the cited order, its supersession chain, and the
   official PDF link.

## The contradiction pair — C and D

**These two are written by me, not drawn from the corpus.** Every other file here is a real
Government Resolution; C and D are constructed to stage one specific failure, and nothing in the
corpus does it as cleanly.

| | file | |
|---|---|---|
| **C** | `demo-C-finance-15-crore.pdf` | Finance sanctions **Rs. 15,00,00,000** to VJTI for infrastructure |
| **D** | `demo-D-hte-10-crore.pdf` | Higher Education, **citing C**, says **Rs. 10,00,00,000** was sanctioned |

Upload C first on **Recent GRs -> Upload GR**: template compliant, citations aligned, terminology
clean, no conflicts. Then upload D. Same clean sheet on all three checks — and a red
**Rs. 5,00,00,000 understated** against it.

The point: both documents are impeccably drafted, D's citation resolves, and the order it cites
is in force. **Nothing in either document, read alone, is wrong.** The defect exists only in the
relationship between them, and no official holding one of the two can see it.

Hover the badge for the computed comparison and the on-premise model's note (~20 s).

Both are Marathi and both follow Appendix 10.6 in full — budget head `2203-00-800-01`, Finance
concurrence, Governor's order line, signature, distribution list. The `.mr.txt` source sits
beside each PDF if you want to change the figures.

---

## The full set

Drop any of these on **Verify GR** (`/verify`) and open the **Citations** tab.

Six are real Government Resolutions from the `orgpedia/mahGRs` corpus, re-typeset as PDFs
because the crawl ships text, not the original scans. Two are constructed, and say so.

Every figure below was measured by extracting from the **finished PDF** — not from the source
text — so this is what the page will actually show you. Re-measure with:

```bash
make refcheck FILE=<path to a .txt>          # source text
python -c "import ocr,references as X; ..."  # or upload the PDF and read the panel
```

| # | file | what it is for | citations | verified | errors | codes |
|---|------|----------------|----------:|---------:|-------:|-------|
| 01 | `01-cross-department-conflict.pdf` | **The headline.** A General Administration GR standing on a Finance order Finance has since replaced | 8 | 1 | 6 | R01 R06 R09 **R11** |
| 02 | `02-all-references-sound.pdf` | The green case at scale — nothing broken, and one cross-departmental dependency worth knowing about | 15 | 9 | **0** | R08 R09 R10 |
| 03 | `03-many-verdicts.pdf` | Most verdict types in one document, including an ambiguous match | 11 | 1 | 3 | R01 **R02** R05 R06 R08 R09 |
| 04 | `04-cancels-a-load-bearing-order.pdf` | Cancels an order four other GRs still stand on — blast radius before the damage | 5 | 1 | 1 | R01 R03 R06 R07 R09 **R12** |
| 05 | `05-mostly-outside-the-archive.pdf` | **The honesty split.** 18 citations, 12 of them predating the crawl | 18 | 1 | 5 | R01 R08 |
| 06 | `06-cites-an-amended-order.pdf` | Cites an order still in force but amended since | 9 | 4 | 5 | R01 **R03** |
| 07 | `07-every-verdict-english.pdf` | *Constructed.* All seven verdicts and nine finding codes in one English GR | 8 | 3 | 2 | R01 R03 R06 R07 R08 R09 R10 **R11 R12** |
| 08 | `08-draft-before-issue.pdf` | *Constructed.* An unissued draft cancelling a circular **229 live GRs** depend on, across three departments | 3 | 1 | 1 | R01 R09 **R12** |

## Where to look first

**Start with 01.** It is the finding that no official in either department can see today: a
General Administration GR from October 2022 cites the Finance Department's e-vehicle price
order of 03.02.2022, and Finance replaced that order on 02.02.2024. Neither document mentions
the other. Finding it needs a cross-departmental citation *and* a supersession chain, which is
a property of the graph rather than of either GR. The panel shows the superseding order and the
verbatim Marathi sentence that cancelled it.

**Then 05, to see what the checker refuses to claim.** Eighteen citations, five genuinely
missing, and twelve that simply predate the archive (which begins 2017-10-12). Those twelve are
grey, not red. Calling them missing would quadruple the error count and would be false — the
archive's limits are not the document's defects. Same reason court orders in 01, 03 and 07 come
back "not a document the GR archive holds" rather than "not found".

**Then 02, so the green case is not a mystery.** Fifteen citations, nine resolved, no errors —
and one advisory flagging that this GR depends on another department's order which, if that
department replaces it, will decay silently.

## What the codes mean

| | | |
|---|---|---|
| R01 | error | cited order is in range, in an indexed department, and **not in the archive** |
| R02 / R11 | error | cites a **superseded** order — R11 when another department did the superseding |
| R03 | warning | cited order is in force but has been **amended** since |
| R12 | warning | this draft **cancels** an order others still stand on — blast radius |
| R05 / R06 | warning | ambiguous match · no file number to verify against |
| R07 / R08 / R09 | advisory | department not indexed · date outside coverage · court order or Act |
| R10 | advisory | a plain cross-departmental dependency |

Only R01 and R02/R11 are defects in the document. Everything else is either a limit of our
coverage or a limit of how the citation was written.

## Provenance

| # | source |
|---|--------|
| A | `202202281129025007` — General Administration, 2022-02-28 (same as 02) |
| B | `202404301225429207` — General Administration, 2024-04-30 |
| 01 | `202210131707040707` — General Administration, 2022-10-13 |
| 02 | `202202281129025007` — General Administration, 2022-02-28 |
| 03 | `202107151614232807` — General Administration, 2021-07-15 |
| 04 | `202409241659558208` — Higher and Technical Education, 2024-09-24 |
| 05 | `201803071449402308` — Higher and Technical Education, 2018-03-07 (also a repo fixture) |
| 06 | `202112061601473707` — General Administration, 2021-12-06 |
| 07 | constructed, English, cites real archived orders |
| 08 | constructed, Marathi draft, cites real archived orders |

Corpus: [`orgpedia/mahGRs`](https://github.com/orgpedia/mahGRs) (MIT licence).

## Expect template errors on every real GR. They are not bugs

Open the **Template** tab on any of these and you will see five or six red items — missing
Subject label, missing signature block, missing "By order and in the name of the Governor",
missing distribution list. That is measured and expected, for three separate reasons:

* **The signature block is an image in the original scan**, so OCR never produced it. Across
  1,500 random corpus GRs a signature block appears in **30.4%** and the Governor's order line
  in **2.2%** — and GRs with complete text extraction score the same as those with empty
  trailing pages, so this is not truncation. `CLAUDE.md` records the measurement.
* **The subject is usually a bare first line**, not a `विषय :-` label, so the label-anchored
  detector does not fire.
* **Budget head and Finance concurrence become mandatory** the moment a draft mentions money,
  which a great many resolutions do in passing.

The template engine enforces the Manual of Office Procedure on **drafts we generate** — that is
what FR-10/11/12 ask for. Running it against a decade of already-issued, OCR'd resolutions is a
different question, and its answer is mostly "the crawl could not see the bottom of the page".
The **Citations** tab is the one to judge these samples by.

## Two caveats about the PDFs themselves

**These were typeset by us, not downloaded from the GR portal.** The crawl publishes OCR'd text,
not the original scans, so the PDFs were rendered from that text with `export_pdf.py` (XeLaTeX).
The *content* is a real GR; the typography is not the original's.

**XeLaTeX writes some Devanagari clusters in visual order**, so a few words in the extracted
text read oddly (`परिपत्रक` → `पिरपत्रक`). File numbers and dates — which is what resolution keys
on — come through intact, which is why the findings above hold. It does cost a little: sample 01
picks up one extra "cannot be verified" against its source text, and one candidate GR was
dropped from this set because the mangling destroyed its reference block entirely.

`docgen.py` (WeasyPrint), the exporter the Draft page uses, is **worse** for this and was not
used here: its text layer drops i-matras inside ligature clusters, so `निर्णय` extracts as
`नणर्षाय` and a re-uploaded Marathi export yields zero citations. Measured 2026-08-02; recorded
in `CLAUDE.md`. If you want to test the scan path instead, tick **Force OCR** on any of these —
EasyOCR reads the rendered page at ~0.57 confidence, enough to extract and classify citations,
though file numbers degrade far enough that resolution honestly abstains.
