#!/usr/bin/env python3
"""
Citation → uid resolution. Step 2 of the build order.

Resolves from the MARATHI side. This is not a stylistic choice, it is the only defensible one
and it is also empirically the better one:

  * Marathi is legally authoritative (CLAUDE.md rule 1).
  * The citation's file number in `.mr.txt` is Devanagari, and `GRs.json`'s `order_number` is
    Devanagari, so matching is an EXACT normalised string comparison. On the English side the
    same number arrives transliterated and unstable — `Masi-1` / `Mashi-1` / `MASHI-1`, and in
    one fixture the section code `विशि` came out `Vishy-1` in one reference and `Special-1` in
    another. No string match survives that.
  * The Marathi reference block is more regular. On fixture 201803071449402308 the Marathi side
    yields 18 reference items where the English parser recovers 10.

## Why this ships without a hand-labelled answer key

`tests/resolver_truth.json` is the authority on accuracy and is hand-labelled (CLAUDE.md).
Nothing here writes to it, and nothing here is a substitute for it. What this module does instead
is refuse to guess, and expose machine-checkable evidence that needs no labels:

  1. **Two independent keys must agree.** A resolution requires the file number to match AND the
     date to land in the window. Number-only is not enough (41.1% of HTE GRs share a number, so
     the number identifies a *file*, not a GR) and date-only is not enough (every GR issued that
     day collides). Agreement of two keys whose failure modes are unrelated is evidence.
  2. **Cross-language agreement.** The same citation is extracted from `.en.txt` independently
     and the two answers compared. Devanagari string matching and Latin token overlap fail in
     uncorrelated ways, so agreement is a real signal — unlike two runs of the same logic.
  3. **Invariants** — see tests/test_resolver_invariants.py. A citation may not resolve to its
     own document, may not resolve forward in time, and may not resolve to a uid absent from the
     corpus. These catch whole classes of bug with zero labels.

The residue that none of this settles is exactly what a human should spend fifteen minutes on:
the cases where the two languages disagree, or where a number matches but no date does.
`--audit` prints that list and nothing else.

Usage:
    python3 resolver.py fixtures/ data/mahGRs/GRs/Higher_and_Technical_Education_Department/ \
        --out out/resolved.json
    python3 resolver.py fixtures/ <corpus> --audit
"""

import re, json, argparse, datetime
from pathlib import Path
from collections import defaultdict

DEV_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

# `वाचा` ("read") is the Marathi reference-block header; `संदर्भ` ("reference") and `पहा`
# ("see") also occur.
MR_REF_HEAD = re.compile(r'(?:वाचा|संदर्भ|पहा)\s*[:ः]')
# Body markers. `शासन आदेश` ("Government Order") is as common as `प्रस्तावना` and its omission
# let the reference region run hundreds of characters into the body, where stray dates live.
MR_BODY_START = re.compile(r'(?:प्रस्तावना|शासन\s*आदेश|शासन\s*निर्णय\s*[:ः])')
# Ordinals: Devanagari digits followed by ')', optionally wrapped as "(२)". Validated in code
# rather than by lookbehind, because the two forms need different context tests and Python
# lookbehind must be fixed-width. A file number contains runs like "(३८/१६)" whose "१६)" is
# indistinguishable from an ordinal in isolation — the same trap parser.py handles for English
# statutory sub-sections. The discriminator is the preceding character: an ordinal follows
# whitespace or a line start, a sub-run follows '/' or a digit.
MR_ORDINAL_RAW = re.compile(r'(\(?)([०-९]{1,2})\)\s')

# A captured "file number" is rejected if it looks like anything but one. Without this, the
# tail of the header word `वाचा` and whole date strings were being captured as numbers.
MR_NO_REJECT = re.compile(r'वाचा|संदर्भ|दिनांक|दिनाक|^\s*दि\s*[.:]')
# "समक्रमांक" = "of the same number" — a citation to another GR in the citing document's OWN
# file. Resolvable, but only by inheriting the citing GR's number rather than reading one out
# of the citation text, which is why it looked like a failure before.
MR_SAME_NO = re.compile(r'समक्रमांक|सम\s*क्रमांक')
# Date marker: `दिनांक` in full, `दिनाक` (OCR drops the anusvara), or the abbreviation `दि`.
# `दि` is a common syllable, so it is only accepted when digits follow — that guard is what
# keeps it from firing inside ordinary words.
MR_DATEMARK = r'(?:दिनांक|दिनाक|दि)\s*[.:ः]?\s*'
MR_DATE = re.compile(MR_DATEMARK + r'([०-९]{1,2})\s*[.\-/]\s*([०-९]{1,2})\s*[.\-/]\s*([०-९]{2,4})')
# The file number sits between a "क्र"-family marker and the date.
MR_NO = re.compile(r'(?:क्रमांक|क्र)\s*[.:ः]?\s*(.{4,90}?)(?=\s*,?\s*' + MR_DATEMARK + r'[०-९])', re.S)
MR_GR_WORD = re.compile(r'शासन\s*(?:निर्णय|परिपत्रक|शुद्धिपत्रक|आदेश|पूरक\s*पत्र)')

# Spelled-out Marathi months. `MR_DATE` accepts only `दि.०७.०३.२०१८`, but a large minority of
# citations write `दिनांक ०९ जुलै, २०२६` — MEASURED on 600 corpus GRs, 730 of 1,625 date-bearing
# reference items (45%) were dropped for this reason alone, and it was the ONLY reason any of
# them were dropped. Supporting it is the difference between extracting half the citations in a
# वाचा block and extracting nearly all of them.
#
# Months are matched on their SKELETON — consonants with every matra and virama removed —
# because a PDF text layer returns `एप्रिल` as `एिप्रल` with the matras in visual order. The
# twelve skeletons stay distinct from one another.
MR_MONTHS = ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
             "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]


def skeleton(s: str) -> str:
    """A Devanagari word with its combining marks stripped. Matra-order independent."""
    import unicodedata
    return ''.join(c for c in s if unicodedata.category(c) not in ('Mn', 'Mc'))


MONTH_BY_SKELETON = {skeleton(m): i + 1 for i, m in enumerate(MR_MONTHS)}
MR_DATE_WORD = re.compile(
    MR_DATEMARK + r'([०-९]{1,2})\s*([ऀ-ॿ]{2,14}?)\s*,?\s*([०-९]{4})')

# Department names as they appear in Marathi citations. A citation naming a department other
# than the indexed one cannot resolve against a single-department index — that is the ~53%
# cross-departmental population, and it must be labelled unresolved rather than forced.
MR_DEPTS = {
    'वित्त विभाग': 'Finance',
    'सामान्य प्रशासन विभाग': 'General Administration',
    'शालेय शिक्षण': 'School Education',
    'उच्च व तंत्र शिक्षण विभाग': 'Higher and Technical Education',
    'उच्च व तंत्रशिक्षण विभाग': 'Higher and Technical Education',
    'महसूल': 'Revenue',
    'गृह विभाग': 'Home',
    'नियोजन विभाग': 'Planning',
    'विधी व न्याय': 'Law and Judiciary',
    'ग्रामविकास': 'Rural Development',
    'नगर विकास': 'Urban Development',
    'सार्वजनिक बांधकाम': 'Public Works',
    'आदिवासी विकास': 'Tribal Development',
    'सामाजिक न्याय': 'Social Justice',
    'वैद्यकीय शिक्षण': 'Medical Education',
    'कौशल्य विकास': 'Skill Development',
    'जलसंपदा': 'Water Resources',
    'कृषी': 'Agriculture',
    'उद्योग': 'Industries',
}


def norm_no(s: str | None) -> str:
    """Normalised file number: alphanumerics only, Devanagari digits folded to ASCII.

    Both sides of the comparison are Devanagari, so letters are preserved and compared
    directly — this is an exact match, not a heuristic."""
    return re.sub(r'[^0-9a-zA-Zऀ-ॿ]', '', (s or '').translate(DEV_DIGITS)).lower()


def digit_key(s: str | None) -> str:
    """All digits, in order, concatenated — script-independent AND segmentation-independent.

    Fallback for when letters cannot be compared (one side transliterated). Deliberately NOT a
    tuple of digit runs: Marathi OCR inserts spaces inside Devanagari digit runs, so the same
    number arrives as `( १२ ९/१३ )` on one side and `(129/13)` on the other. Run tuples make
    those look different — ('2013','12','9','13','2') vs ('2013','129','13','2') — while the
    concatenation is identical. Measured on HTE, concatenating costs almost no discrimination
    (3,252 → 3,240 distinct keys over 4,645 GRs) and the only 12 keys it merges are precisely
    these spacing variants. Needs >=4 digits to be worth retrieving on."""
    k = ''.join(re.findall(r'\d+', (s or '').translate(DEV_DIGITS)))
    return k if len(k) >= 4 else ''


def uid_date(uid: str) -> datetime.date:
    return datetime.date(int(uid[0:4]), int(uid[4:6]), int(uid[6:8]))


def _mkdate(d, m, y):
    d, m, y = int(d.translate(DEV_DIGITS)), int(m.translate(DEV_DIGITS)), int(y.translate(DEV_DIGITS))
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def mr_reference_span(text: str) -> tuple[int, int] | None:
    """(start, end) of the वाचा / संदर्भ block, or None when the document labels none."""
    h = MR_REF_HEAD.search(text)
    if not h:
        return None
    b = MR_BODY_START.search(text, h.end())
    return h.end(), (b.start() if b else min(len(text), h.end() + 4000))


def mr_reference_items(text: str) -> list[tuple[int, str]]:
    """[(offset_into_text, item_text)] for the reference block. [] when there is no block.

    Offsets are returned rather than discarded because a *draft* checker must be able to tell an
    officer which line a bad citation is on (SRS FR-3), and recovering the offset afterwards by
    searching for the item fails — items are whitespace-normalised downstream.
    """
    span = mr_reference_span(text)
    if not span:
        return []
    base, end = span
    region = text[base:end]

    def is_ordinal(m):
        """True for a list ordinal, False for a sub-run inside a file number."""
        start = m.start()
        prev = region[start - 1] if start else '\n'
        if m.group(1):                      # "(२)" — the '(' must itself follow whitespace
            return prev.isspace() or start == 0
        return not (prev in '/(' or '०' <= prev <= '९')

    marks = [m for m in MR_ORDINAL_RAW.finditer(region) if is_ordinal(m)]
    if marks:
        spans = [(m.end(), marks[i + 1].start() if i + 1 < len(marks) else len(region))
                 for i, m in enumerate(marks)]
    else:
        spans, at = [], 0
        for line in region.split('\n'):
            if line.strip():
                spans.append((at, at + len(line)))
            at += len(line) + 1
    return [(base + s, region[s:e]) for s, e in spans]


def _cited_date(raw: str):
    """The date a citation names, numeric or spelled out. None when neither form is present."""
    dm = MR_DATE.search(raw)
    if dm:
        d = _mkdate(*dm.groups())
        if d:
            return d
    for m in MR_DATE_WORD.finditer(raw):
        mon = MONTH_BY_SKELETON.get(skeleton(m.group(2)))
        if not mon:
            continue
        try:
            return datetime.date(int(m.group(3).translate(DEV_DIGITS)), mon,
                                 int(m.group(1).translate(DEV_DIGITS)))
        except ValueError:
            continue
    return None


def mr_citation(raw: str) -> dict | None:
    """One citation record from one reference item, or None if the item is not a citation.

    Split out of `extract_mr_citations` so that `references.py` can parse a draft — which has no
    uid, and often no वाचा block — under exactly the rules the corpus was parsed under. Two
    definitions of "what a citation looks like" would drift, and the graph and the draft checker
    would then disagree about the same sentence.
    """
    raw = ' '.join(raw.split())
    if len(raw) < 12:
        return None
    d = _cited_date(raw)
    if not d:
        return None
    nm = MR_NO.search(raw)
    no = ' '.join(nm.group(1).split()) if nm else None
    if no and (MR_NO_REJECT.search(no) or not re.search(r'[०-९]', no)):
        no = None                       # captured noise, not a file number
    dept = next((v for k, v in MR_DEPTS.items() if k in raw), None)
    return {
        "raw": raw[:400],
        "cited_no": no,
        "cited_date": d.isoformat(),
        "cited_dept": dept,
        "is_gr": bool(MR_GR_WORD.search(raw)),
        "same_no": bool(MR_SAME_NO.search(raw)),
    }


def extract_mr_citations(text: str) -> list[dict]:
    """Reference items from the Marathi side, one record per citation."""
    out = []
    for _, item in mr_reference_items(text):
        c = mr_citation(item)
        if c:
            out.append(c)
    return out


def scope_report(rows: list[dict], idx) -> dict:
    """The honest denominator.

    A raw resolution rate over every extracted citation is a misleading number in both
    directions, and the misleading version is the flattering one to game: a resolver that
    guessed would score higher on it. Most citations in this corpus CANNOT resolve against a
    single-department index, for reasons that are structural rather than failures of the code:

      * `not_a_gr`      — the citation is a letter, email, notification or minutes, not a GR.
                          There is no GR to find.
      * `other_dept`    — names a department this index does not contain. ~53% of HTE citations
                          leave HTE; widening the corpus fixes these, the resolver cannot.
      * `outside_range` — cited date predates the crawl (HTE begins Oct 2017) or postdates it.
      * `in_scope`      — a GR, in this department, inside the crawl window. Only these are
                          the resolver's to get right, and only this rate is worth quoting.

    Bucketing is ordered and exclusive, so the four counts sum to the total. Reported by the
    same command that writes the artefact, so the number in the deck cannot drift from the code.
    """
    meta = idx[3]
    dates = [m["date"] for m in meta.values()]
    lo, hi = min(dates), max(dates)

    buckets = {"not_a_gr": [], "other_dept": [], "outside_range": [], "in_scope": []}
    for r in rows:
        cd = datetime.date.fromisoformat(r["cited_date"])
        if not r["is_gr"]:
            buckets["not_a_gr"].append(r)
        elif "outside this index" in r["reason"]:
            buckets["other_dept"].append(r)
        elif not (lo <= cd <= hi):
            buckets["outside_range"].append(r)
        else:
            buckets["in_scope"].append(r)

    print(f"\nscope (index covers {lo} → {hi}):")
    for k in ("not_a_gr", "other_dept", "outside_range", "in_scope"):
        print(f"  {len(buckets[k]):4d}  {k}")

    ins = buckets["in_scope"]
    hit = [r for r in ins if r["resolved_uid"]]
    print(f"\nin-scope resolution: {len(hit)}/{len(ins)} "
          f"({100*len(hit)/max(1,len(ins)):.1f}%)")
    stray = [r for r in rows if r["resolved_uid"] and r not in ins]
    if stray:
        print(f"  note: {len(stray)} resolutions landed outside in_scope — check the bucketing")
    return {k: len(v) for k, v in buckets.items()}


DEPT_BY_CODE = {'05': 'Finance', '07': 'General Administration',
                '08': 'Higher and Technical Education', '21': 'School Education'}


def dept_of(uid: str) -> str | None:
    """Department from the uid's trailing 2-digit code. Verified unique per department across the
    four cloned corpora (05/07/08/21), so no directory bookkeeping is needed downstream."""
    return DEPT_BY_CODE.get(uid[-2:])


def load_index(corpus_dirs):
    """(uid -> date/number/dept) index for the target side, from each department's GRs.json.
    Devanagari, and crawled portal metadata rather than OCR — independent of our text pipeline.

    Accepts one path or many. **Indexing all four departments is what makes cross-departmental
    resolution possible at all**: with a single-department index, a citation naming another
    department can only ever be rejected, which is the opposite of the problem statement's first
    requirement. The set of indexed departments is returned so `resolve` can distinguish "cites
    elsewhere, we have it" from "cites elsewhere, genuinely outside our corpus".
    """
    if isinstance(corpus_dirs, (str, Path)):
        corpus_dirs = [corpus_dirs]
    by_date, by_no, by_key, meta = defaultdict(list), defaultdict(list), defaultdict(list), {}
    for corpus_dir in corpus_dirs:
        md = json.loads((Path(corpus_dir) / "GRs.json").read_text(encoding='utf-8'))
        for k, v in md.items():
            uid = k.split('.')[0]
            if not re.fullmatch(r'\d{18}', uid) or uid in meta:
                continue
            no = (v.get('order_number') or '').strip()
            d = uid_date(uid)
            meta[uid] = {"date": d, "no": no, "subject": (v.get('text') or '').strip(),
                         "dept": dept_of(uid), "dept_code": uid[-2:],
                         "dept_full": (v.get('dept') or '').strip()}
            by_date[d].append(uid)
            if norm_no(no):
                by_no[norm_no(no)].append(uid)
            if digit_key(no):
                by_key[digit_key(no)].append(uid)
    return by_date, by_no, by_key, meta


def indexed_depts(idx) -> set:
    """Department names present in the index, in the vocabulary `MR_DEPTS` maps citations to."""
    return {m["dept"] for m in idx[3].values() if m.get("dept")}


def resolve(cit: dict, src_uid: str, idx, window: int = 3, own_dept: str | None = None,
            in_index: set | None = None) -> dict:
    """Resolve one citation. Refuses rather than guesses.

    The rule that does the work: a file number identifies a FILE, and a file accumulates
    decisions over years, so the number narrows to a series and the DATE selects the member.
    If the number matches but no member lands in the date window, the cited member is not in the
    corpus — that is `unresolved`, never the nearest sibling. Silently snapping to a sibling
    would fabricate a citation, which rule 3 forbids and which is the failure mode most likely
    to survive undetected into the graph.
    """
    by_date, by_no, by_key, meta = idx
    cd = datetime.date.fromisoformat(cit["cited_date"])
    src_d = uid_date(src_uid)

    # A citation naming another department is only unresolvable if that department is genuinely
    # absent from the index. `in_index` is the multi-department path and takes precedence;
    # `own_dept` is the legacy single-department behaviour, kept so existing callers and the
    # fixture-scale tests keep working unchanged.
    cited_dept = cit["cited_dept"]
    if cited_dept:
        if in_index is not None:
            if cited_dept not in in_index:
                return {"resolved_uid": None, "confidence": 0.0,
                        "reason": f"cites {cited_dept} Department, outside this index",
                        "candidates": []}
        elif own_dept and cited_dept != own_dept:
            return {"resolved_uid": None, "confidence": 0.0,
                    "reason": f"cites {cited_dept} Department, outside this index",
                    "candidates": []}

    # `समक्रमांक` ("of the same number") cites another GR in the citing document's own file, so
    # the number comes from the citing GR's metadata rather than from the citation text.
    cited_no, inherited = cit["cited_no"], False
    if cit.get("same_no") and not cited_no and src_uid in meta:
        cited_no, inherited = meta[src_uid]["no"], True

    # --- number-led retrieval: exact normalised string, then script-independent digit key
    series, how_no = [], None
    if cited_no:
        series = [u for u in by_no.get(norm_no(cited_no), []) if u != src_uid]
        how_no = "exact number" if series else None
        if not series and digit_key(cited_no):
            series = [u for u in by_key.get(digit_key(cited_no), []) if u != src_uid]
            how_no = "digit key" if series else None
    if inherited and how_no:
        how_no += " (समक्रमांक, inherited from citing GR)"

    # --- date-led retrieval
    window_uids = [u for delta in range(-window, window + 1)
                   for u in by_date.get(cd + datetime.timedelta(days=delta), [])
                   if u != src_uid]

    def forward(u):
        """A GR cannot cite an order issued after it. Publication drift makes a few days of
        slack legitimate; beyond that the match is impossible, not merely unlikely."""
        return uid_date(u) > src_d + datetime.timedelta(days=window)

    # --- both keys agree: the only high-confidence outcome
    hits = [u for u in series if u in set(window_uids) and not forward(u)]

    # A third key, available only in the multi-department index: when the citation names its
    # department, the target must be in that department. This is what stops a wider index from
    # costing precision — a file number and date that collide across departments would otherwise
    # turn a clean single-department resolution into an ambiguity. Applied only when it does not
    # eliminate every candidate, so a mislabelled department degrades to the old behaviour
    # instead of destroying a good match.
    if cited_dept and in_index is not None and len(hits) > 1:
        same_dept = [u for u in hits if meta.get(u, {}).get("dept") == cited_dept]
        if same_dept:
            hits = same_dept
    if len(hits) == 1:
        u = hits[0]
        return {"resolved_uid": u, "confidence": 0.97 if uid_date(u) == cd else 0.90,
                "reason": f"{how_no} + date within ±{window}d ({(uid_date(u)-cd).days:+d}d)",
                "candidates": hits}
    if len(hits) > 1:
        return {"resolved_uid": None, "confidence": 0.0,
                "reason": f"ambiguous: {len(hits)} GRs match number and date",
                "candidates": hits}

    # --- number matched a series but no member is in the window: the cited member is absent
    if series:
        near = sorted(((uid_date(u) - cd).days, u) for u in series)
        return {"resolved_uid": None, "confidence": 0.0,
                "reason": f"file number matches a {len(series)}-GR series but no member within "
                          f"±{window}d (nearest {near[0][0]:+d}d) — cited GR absent from corpus",
                "candidates": [u for _, u in near[:5]]}

    # --- date only. Never resolved: same-date collision is the documented trap.
    # The two causes are distinguished because they mean different things: a citation carrying no
    # number is an extraction gap on our side, while a number that matches nothing in the corpus
    # is evidence the target is genuinely absent.
    why = ("no file number in citation" if not cited_no
           else "file number matches no GR in corpus")
    live = [u for u in window_uids if not forward(u)]
    if not live:
        return {"resolved_uid": None, "confidence": 0.0,
                "reason": f"no candidate within date window; {why}", "candidates": []}
    return {"resolved_uid": None, "confidence": 0.0,
            "reason": f"date-only match ({len(live)} candidates); {why}",
            "candidates": live[:5]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures"); ap.add_argument("corpus")
    ap.add_argument("--out"); ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--dept", default="Higher and Technical Education")
    ap.add_argument("--audit", action="store_true",
                    help="print only the cases a human should adjudicate")
    a = ap.parse_args()

    corpus_dir = Path(a.corpus)
    idx = load_index(corpus_dir)
    print(f"indexed {len(idx[3])} GRs from GRs.json")

    rows = []
    for f in sorted(Path(a.fixtures).glob("*.mr.txt")):
        uid = f.name.split('.')[0]
        text = f.read_text(encoding='utf-8', errors='ignore')
        for c in extract_mr_citations(text):
            r = resolve(c, uid, idx, a.window, a.dept)
            rows.append({"src_uid": uid, **c, **r})

    res = [r for r in rows if r["resolved_uid"]]
    print(f"\n{len(rows)} citations extracted from the Marathi side")
    print(f"  resolved   : {len(res)} ({100*len(res)/max(1,len(rows)):.1f}%)")
    print(f"  unresolved : {len(rows)-len(res)}")
    print("\nreasons:")
    tally = defaultdict(int)
    for r in rows:
        tally[re.sub(r'\d+', 'N', r["reason"]).split('(')[0].strip()] += 1
    for k, n in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {k}")

    scope_report(rows, idx)

    if a.audit:
        print("\n" + "=" * 78)
        print("FOR HUMAN ADJUDICATION — number matched a series but no member in the window.")
        print("These are the only cases where the two keys disagree. Everything else is either")
        print("settled by both keys agreeing, or unresolvable for a stated structural reason.")
        print("=" * 78)
        n = 0
        for r in rows:
            if "series but no member" not in r["reason"]:
                continue
            n += 1
            print(f"\n[{n}] {r['src_uid']} cites {r['cited_date']}  no. {r['cited_no']}")
            print(f"    {r['reason']}")
            for u in r["candidates"]:
                print(f"      {u}  {uid_date(u)}  {idx[3][u]['subject'][:60]}")
        print(f"\n{n} cases. Everything else needed no judgement call.")

    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\nwrote {len(rows)} rows → {a.out}")


if __name__ == "__main__":
    main()
