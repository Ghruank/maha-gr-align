#!/usr/bin/env python3
"""
Parser v1 — GR text → GR record (schema in CLAUDE.md).

Regex first. Nothing here calls an LLM.

Three rules from CLAUDE.md are load-bearing and are enforced structurally, not by convention:

1. **The date comes from the uid prefix, never from the body.** The body `Date:` line is parsed
   anyway, but only into `_provenance.body_date` so the drift can be measured. It never reaches
   the `date` field.

2. **Never fabricate a citation.** `references[].resolved_uid` is always None here and
   `confidence` always 0.0. Resolution is step 2 and needs a hand-labelled truth set. A parser
   that guessed uids would manufacture a graph out of nothing.

3. **De-leak before parsing.** Devanagari reaches decision numbers (3 in HTE), and the
   displaced-ordinal template fuses list ordinals into sentence bodies. Both corrupt extraction
   if left in place.

Usage:
    python3 parser.py fixtures/ out/parsed.json
"""

import sys, re, json, glob, unicodedata
from pathlib import Path
from datetime import date

from deleak import load_map, deleak, DEVANAGARI, UnmappedToken

# --------------------------------------------------------------------------- structure
PAGE = re.compile(r'^#\s*Page\s+(\d+)\s*$', re.M)

# The document's own number. `select_fixtures.py` looks for "Government Decision No" and finds
# it in 57.3% of HTE. The header actually varies across at least a dozen forms — Decision,
# Resolution, Order, Memorandum, Circular, Corrigendum, Notification… Broadening to
# "Government <word(s)> No" lifts coverage to 96.0%. The `no_decision_no` fixture bucket is
# therefore mostly a false negative of the selection regex, not of the corpus.
DECISION_NO = re.compile(
    r'Government\s+(?P<kind>[A-Za-z][A-Za-z ]{0,25}?)\s*(?:No|NO|Number)\b\s*[.:]?\s*'
    r'(?P<no>[^\n]{3,120})', re.I)
# Letter/memo layout puts the number on a bare line with no "Government" prefix (0.2%).
DECISION_NO_BARE = re.compile(r'^\s*Number\s*[:.\-]+\s*(?P<no>[^\n]{3,120})', re.I | re.M)

# Same story for the date line: `^Date:` anchored hits 75.9%, allowing "The date" and a
# trailing period hits 85.0%. Parsed for measurement only — `date` comes from the uid.
DATE_LINE = re.compile(r'^\s*(?:The\s+)?date\s*[:.\-\s]+(?P<val>[^\n]{4,40})', re.I | re.M)

# `Reference:` labels 53.9% of HTE. `Read:` is the same block under a different translation
# and labels a further 25.6% — together 79.6%. CLAUDE.md records 51.6% and concludes "48% have
# no Reference block"; the real figure is ~20%.
REF_BLOCK = re.compile(r'^\s*(?:Reference[s]?|Read)\s*[:\-]\s*', re.I | re.M)
# Enumerated reference items. Line-anchored `1)` / `(1)` / `1.`, or a mid-line bare `1)`.
# The `(N)` form is NOT accepted mid-line: statutory sub-section references — "Section 40 (1)
# of the Act", "Section 106 (2)" — look identical and were being split as reference items,
# destroying the reference list of any GR that cites a statute.
REF_ITEM = re.compile(r'(?m)^\s*\(?(\d{1,2})[\)\.]\s+|(?<=[\s,;])(\d{1,2})\)\s+')

# A number field ends where the date begins; both sit on one line in the letter layout
# ("Number: - Narrow-2204 / Q.No.91 / VISHI-1 Date: - 18.07.2025").
NO_TAIL = re.compile(r'\s*(?:,\s*)?\b(?:date[ds]?|dt|d)\b\s*[:.\-]?.*$', re.I)

BODY_START = re.compile(
    r'^\s*(?:the\s+Government\s+Order|The\s+Proposal|The\s+Government\'?s?\s+Decision|'
    r'Government\s+Decision\s*:|Refinance\s+Sheet|Approval\s+is\s+being\s+given)', re.I | re.M)

SUBJECT_END = re.compile(r'^\s*(?:The\s+)?Government\s+of\s+Maharashtra', re.I | re.M)
# Letter layout leads with the address block, so the subject sits in an explicit `Subject:` line
# below it rather than above "Government of Maharashtra".
SUBJECT_LINE = re.compile(r'^\s*Subject\s*[:.\-]+\s*(?P<val>[^\n]{5,300})', re.I | re.M)

# --------------------------------------------------------------------------- citations
MONTHS = ('january february march april may june july august september october november december'
          .split())
MONTH_RE = '|'.join(MONTHS) + '|' + '|'.join(m[:3] for m in MONTHS)

DATE_NUM = re.compile(r'\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b')
DATE_TXT = re.compile(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_RE})[a-z]*\.?,?\s+(\d{{4}})\b', re.I)
DATE_TXT2 = re.compile(rf'\b({MONTH_RE})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b', re.I)

# A citation is a reference to another order. Requires an order word AND a date nearby.
CITE_ORDER = re.compile(
    r'Government\s+(?:Decision|Resolution|Order|Memorandum|Circular|Ordinance|Corrigendum|'
    r'Notification)', re.I)
# The cited order's own number, e.g. "No. NGC-2017/ (208/17)/ Mashi-4"
CITE_NO = re.compile(r'\bNo[.:]?\s*([A-Za-z0-9][^\s,;]*(?:[ /\-][^\s,;]+){0,6})')

# --------------------------------------------------------------------------- amounts
# Indian grouping: 33,54,00,000. Also bare digits, and lakh/crore multipliers.
AMOUNT = re.compile(
    r'(?:Rs\.?|₹|INR)\s*([0-9][0-9,]*(?:\.\d{1,2})?)\s*(lakhs?|crores?|thousand)?', re.I)
AMOUNT_WORD = re.compile(r'\b([0-9][0-9,]*(?:\.\d{1,2})?)\s+(lakhs?|crores?)\b', re.I)
MULT = {'lakh': 100000, 'lakhs': 100000, 'crore': 10000000, 'crores': 10000000,
        'thousand': 1000}


def _norm(s: str) -> str:
    return ' '.join(s.split()).strip(' .,;:-')


def _clean_no(s: str | None) -> str | None:
    """Trim a trailing date off a number field. `NGC 2017 / (29/17) / Masi-D. 15.09.2017`
    is a number plus a date, and keeping the date in the key breaks resolver matching."""
    if not s:
        return None
    return _norm(NO_TAIL.sub('', s)) or None


def _mkdate(d, m, y) -> str | None:
    d, m, y = int(d), int(m), int(y)
    if y < 100:
        y += 2000 if y < 60 else 1900
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def find_dates(text: str) -> list[str]:
    """Every date in `text`, ISO, in order of appearance. Ambiguity is resolved DD/MM
    because these are Indian government orders — never MM/DD."""
    out = []
    for m in DATE_NUM.finditer(text):
        iso = _mkdate(*m.groups())
        if iso:
            out.append(iso)
    for m in DATE_TXT.finditer(text):
        d, mon, y = m.groups()
        iso = _mkdate(d, MONTHS.index(next(x for x in MONTHS if x.startswith(mon.lower()))) + 1, y)
        if iso:
            out.append(iso)
    for m in DATE_TXT2.finditer(text):
        mon, d, y = m.groups()
        iso = _mkdate(d, MONTHS.index(next(x for x in MONTHS if x.startswith(mon.lower()))) + 1, y)
        if iso:
            out.append(iso)
    return out


def parse_amounts(text: str) -> list[dict]:
    seen, out = set(), []
    for rx in (AMOUNT, AMOUNT_WORD):
        for m in rx.finditer(text):
            raw, unit = m.group(1), (m.group(2) or '').lower()
            digits = raw.replace(',', '')
            if not digits or digits.startswith('.'):
                continue
            try:
                val = float(digits)
            except ValueError:
                continue
            val *= MULT.get(unit.rstrip('s') + ('s' if unit.endswith('s') else ''), 1) \
                if unit in MULT else (MULT.get(unit, 1))
            key = (raw, unit)
            if key in seen:
                continue
            seen.add(key)
            out.append({"raw": m.group(0).strip(), "value": int(val), "currency": "INR"})
    return out


def split_pages(text: str) -> list[tuple[int, str]]:
    """[(page_no, page_text)]. Text before any marker is page 1."""
    marks = list(PAGE.finditer(text))
    if not marks:
        return [(1, text)]
    out = []
    if marks[0].start() > 0 and text[:marks[0].start()].strip():
        out.append((1, text[:marks[0].start()]))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((int(m.group(1)), text[m.end():end]))
    return out


def parse_references(header: str, ref_zone: str, body: str) -> tuple[list[dict], str]:
    """Returns (references, how). A reference is only emitted if it carries a date or a
    number — a bare mention of 'Government Decision' with neither is not a citation.

    `ref_zone` is the span between the header fields and the start of the body. ~20% of GRs
    label no reference block at all, but the citations still sit in that span as bare lines
    ("Letter from the Governor's Office dated June 7, 2016."). Those carry a date but no order
    word, so position is the only signal that they are citations — which is why the zone is
    passed in rather than reusing the header."""
    blk = REF_BLOCK.search(header)
    if blk:
        region, how = header[blk.end():], "reference_block"
    else:
        region, how = ref_zone, "header_scan"

    items, nums = [], list(REF_ITEM.finditer(region))
    if nums:
        # Enumerated. Split on the ordinals, keeping ascending runs only.
        for i, m in enumerate(nums):
            end = nums[i + 1].start() if i + 1 < len(nums) else len(region)
            items.append(region[m.end():end])
    else:
        items = [l for l in region.split('\n') if l.strip()]

    refs = []
    for raw in items:
        raw = _norm(raw)
        if len(raw) < 12:
            continue
        dates = find_dates(raw)
        no = CITE_NO.search(raw)
        if not dates and not no:
            continue
        if not CITE_ORDER.search(raw) and not dates:
            continue
        refs.append({
            "raw": raw,
            "decision_no": _clean_no(no.group(1)) if no else None,
            "date": dates[0] if dates else None,
            # Resolution is step 2 and needs the hand-labelled truth set. Never guessed here.
            "resolved_uid": None,
            "confidence": 0.0,
        })

    if not refs:
        # Last resort: inline citations in the body (`no_reference_block` bucket).
        for m in CITE_ORDER.finditer(body):
            window = body[m.start():m.start() + 220]
            dates = find_dates(window)
            if not dates:
                continue
            no = CITE_NO.search(window)
            refs.append({
                "raw": _norm(window.split('.')[0][:200]),
                "decision_no": _clean_no(no.group(1)) if no else None,
                "date": dates[0],
                "resolved_uid": None,
                "confidence": 0.0,
            })
        if refs:
            how = "inline_body"

    # de-duplicate on (decision_no, date)
    seen, out = set(), []
    for r in refs:
        k = (r["decision_no"], r["date"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out, how


def parse_conditions(body: str) -> tuple[list[dict], bool]:
    """Numbered conditions, sequence-aware.

    The template-boilerplate family fuses the ordinal into the sentence body — CLAUDE.md's
    displaced-ordinal bug. After de-leaking, `१. सदर मान्यता` reads `The 1. approval ...`, and
    deeper in, `... capacity for the 3. course ...`. So ordinals cannot be found by anchoring
    to line start; they must be tracked as an ascending sequence wherever they appear.

    Returns (conditions, displaced) where `displaced` marks the template family.
    """
    marks = []
    for m in re.finditer(r'(?<![\d.])(\d{1,2})\.\s', body):
        marks.append((int(m.group(1)), m.start(), m.end()))
    if not marks:
        return [], False

    # Longest ascending run, step +1. The run is NOT required to start at 1: OCR loses the
    # first ordinal often enough that demanding it drops whole condition lists (fixture
    # 202208251443425308 runs 2..6 with no `1.` anywhere in the document).
    runs, cur = [], []
    for n, st, e in marks:
        if cur and n == cur[-1][0] + 1:
            cur.append((n, st, e))
        else:
            if cur:
                runs.append(cur)
            cur = [(n, st, e)]
    if cur:
        runs.append(cur)
    # Prefer the longest run; on a tie prefer the one starting lowest, then earliest.
    best = max(runs, key=lambda r: (len(r), -r[0][0], -r[0][1]), default=[])
    if len(best) < 3:
        return [], False

    conds, displaced = [], False
    for i, (n, s, e) in enumerate(best):
        end = best[i + 1][1] if i + 1 < len(best) else min(len(body), e + 600)
        text = _norm(body[e:end])
        line_start = body.rfind('\n', 0, s) + 1
        if body[line_start:s].strip():          # something precedes the ordinal on its line
            displaced = True
        if text:
            conds.append({"n": n, "text": text})
    return conds, displaced


def parse(text: str, uid: str, lang: str = "en", dept: str | None = None,
          table: dict | None = None) -> dict:
    artifacts = []

    if lang == "en":
        if DEVANAGARI.search(text):
            artifacts.append("devanagari_in_en_translation")
            try:
                text = deleak(text, table if table is not None else load_map())
                artifacts.append("deleaked")
            except UnmappedToken:
                artifacts.append("deleak_failed_unmapped_token")

    pages = split_pages(text)
    page1 = pages[0][1] if pages else text

    # --- date: uid prefix is authoritative. Body date parsed for measurement only.
    iso = f"{uid[0:4]}-{uid[4:6]}-{uid[6:8]}"
    dl = DATE_LINE.search(page1)
    body_dates = find_dates(dl.group('val')) if dl else []
    body_date = body_dates[0] if body_dates else None
    if body_date and body_date != iso:
        artifacts.append("body_date_disagrees_with_uid")
    if not dl:
        artifacts.append("no_date_line")

    # --- subject: everything above "Government of Maharashtra"
    se = SUBJECT_END.search(page1)
    subject = _norm(re.sub(r'^#\s*Page\s+\d+\s*$', '', page1[:se.start()] if se else page1[:400],
                           flags=re.M).replace('\n', ' ')) or None
    sl = SUBJECT_LINE.search(page1)
    if sl and (not subject or len(subject) < 15):
        subject = _norm(sl.group('val'))
        artifacts.append("subject_via:subject_line")

    # --- decision_no
    dn = DECISION_NO.search(page1)
    if dn:
        decision_no, kind = _clean_no(dn.group('no')), _norm(dn.group('kind')).title()
    else:
        dn = DECISION_NO_BARE.search(page1)
        decision_no, kind = (_clean_no(dn.group('no')), "Bare Number") if dn else (None, None)
    if not dn:
        artifacts.append("no_decision_no")
    elif kind != "Bare Number" and not re.search(r'Decision', dn.group('kind'), re.I):
        artifacts.append(f"header_variant:{kind}")

    # --- header zone / body split
    bs = BODY_START.search(page1)
    anchor = max([m.end() for m in
                  [dn, dl, REF_BLOCK.search(page1)] if m] or [0])
    hdr_end = bs.start() if bs and bs.start() > anchor else anchor
    header = page1[:hdr_end]
    # Reference zone: from the last header field to the body marker. Bounded so a GR with no
    # body marker does not swallow the whole document.
    ref_zone = page1[:(bs.start() if bs else min(len(page1), anchor + 2500))]
    body_text = text[text.find(page1) + hdr_end:] if hdr_end else text

    refs, how = parse_references(header, ref_zone, body_text)
    if how != "reference_block":
        artifacts.append(f"references_via:{how}")
    if not refs:
        artifacts.append("no_references_found")

    # --- body paragraphs, page-tagged
    body = []
    n = 0
    for pno, ptext in pages:
        for para in ptext.split('\n'):
            para = _norm(para)
            if len(para) < 3:
                continue
            if body and pno == 1 and text.find(para) < hdr_end:
                continue
            n += 1
            body.append({"para_no": n, "text": para, "page": pno})

    conds, displaced = parse_conditions(body_text)
    if displaced:
        artifacts.append("displaced_ordinals")

    return {
        "uid": uid,
        "dept_code": uid[-2:],
        "dept": dept,
        "decision_no": decision_no,
        "date": iso,
        "subject": subject,
        "references": refs,
        "body": body,
        "conditions": conds,
        "amounts": parse_amounts(text),
        "lang": lang,
        "artifacts": artifacts,
        "_provenance": {
            "date": "uid_prefix",
            "body_date": body_date,
            "decision_no_header": kind,
            "references": how,
            "n_pages": len(pages),
        },
    }


def main(src_dir: str, out_path: str):
    src = Path(src_dir)
    table = load_map()
    recs = {}
    for f in sorted(src.glob("*.en.txt")):
        uid = f.name.split('.')[0]
        recs[uid] = parse(f.read_text(encoding='utf-8', errors='ignore'), uid,
                          lang="en", dept="Higher and Technical Education Department",
                          table=table)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"parsed {len(recs)} GRs -> {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out/parsed.json")
