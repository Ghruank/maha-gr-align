#!/usr/bin/env python3
"""
Reference Parser Module — SRS FR-1, FR-2, FR-3.

    FR-1  extract every cited GR, circular and court order from a draft preamble
    FR-2  verify whether each cited document exists in the mahGRs archive
    FR-3  highlight missing or incorrect references

plus the problem statement's first bullet — *detect conflicts with other departments' existing
policies* — which is the same walk one hop further: resolve the citation, then ask the dependency
graph what has happened to the order since.

## Why this file exists rather than a route in api.py

Every layer needed for this was already built and none of them were reachable from a document an
officer uploads. `parser.py` and `resolver.py` read *corpus files* keyed by uid; `graph.py` runs
as a batch job. A draft has no uid, is not in the corpus, and must be answered in milliseconds.
This module is the adapter, and it adds no new detection logic of its own: citation shapes come
from `resolver.mr_citation` / `parser`, resolution from `resolver.resolve`, and every verdict
about supersession from edges `graph.py` already committed.

## Two rules from CLAUDE.md do most of the design work here

**Never fabricate a citation (rule 3).** The tempting product is "12 references, 12 verified".
The honest one distinguishes *five* reasons a citation does not resolve, only one of which is a
defect in the draft:

    not_in_archive  a departmental order, in range, that the archive does not contain — the
                    finding. Either the reference is wrong or the order was never published.
    outside_range   cited before 2017-10-12 or after the crawl ends. The archive cannot have it,
                    so its absence says nothing about the draft.
    other_dept      names a department outside the four indexed.
    out_of_scope    a court order, an Act, a letter. The GR archive does not hold these and never
                    will; reporting them missing would be a lie about our own coverage.
    unverifiable    the citation carries no file number. Date alone cannot identify a GR — the
                    same-date collision trap — so we abstain rather than guess.

Collapsing those five into "missing" would roughly quadruple the red count and make it false.

**The model proposes, the corpus verifies (rule 4).** There is no model call in this file and
there will not be one. Whether a cited order was superseded is settled by an edge carrying the
verbatim Marathi sentence that produced it. Every finding below can be traced to a uid, a date
and a sentence.

## What "conflicts with other departments' policies" resolves to, concretely

Three computable things, all cross-departmental, none visible from reading either document:

  R11  the draft cites another department's order which *that department* has since replaced.
       This is `audit.py`'s LATENT finding evaluated for one unissued draft.
  R12  the draft cancels or amends an order that other departments still stand on. Blast radius,
       run before the damage instead of after it.
  R10  a plain cross-departmental dependency — not a defect, but the thing an officer drafting
       inside one department has no way to see.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from typing import Any

import parser as P
import resolver as R

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# --------------------------------------------------------------------------- what is cited
#
# FR-1 names three things: GRs, circulars and court orders. They are not interchangeable — the
# archive holds the first two and cannot hold the third — so the type has to be decided before
# the verdict, or a High Court order gets reported as a missing GR.
#
# Ordered, first match wins. `court` leads because a court order is described with आदेश/"order"
# and would otherwise be swallowed by the departmental-order pattern below it. `act` follows for
# the same reason.
KINDS: list[tuple[str, str, dict[str, str]]] = [
    ("court", r"न्यायालय|न्यायाधिकरण|खंडपीठ|याचिका|रिट|"
              r"High\s+Court|Supreme\s+Court|Tribunal|Writ\s+Petition|\bW\.?\s?P\.?\s*(?:No|\()|"
              r"\bSLP\b|Civil\s+Application|Hon'?ble",
     {"en": "Court order", "mr": "न्यायालयीन आदेश"}),
    ("act", r"अधिनियम|विधेयक|कायदा|\bAct,?\s+\d{4}|\bAct\b|\bOrdinance\b",
     {"en": "Act or statute", "mr": "अधिनियम"}),
    ("corrigendum", r"शुद्धिपत्रक|शुध्दीपत्रक|Corrigendum|Errat",
     {"en": "Corrigendum", "mr": "शुद्धिपत्रक"}),
    ("circular", r"परिपत्रक|Circular",
     {"en": "Circular", "mr": "परिपत्रक"}),
    ("notification", r"अधिसूचना|Notification|Gazette|राजपत्र",
     {"en": "Notification", "mr": "अधिसूचना"}),
    ("gr", r"शासन\s*निर्णय|Government\s+(?:Resolution|Decision)",
     {"en": "Government Resolution", "mr": "शासन निर्णय"}),
    ("order", r"शासन\s*आदेश|Government\s+Order|आदेश",
     {"en": "Government order", "mr": "शासन आदेश"}),
    ("letter", r"\bपत्र\b|ई-?मेल|अर्ध\s*शासकीय|\bLetter\b|e-?mail|\bD\.?O\.?\s",
     {"en": "Letter", "mr": "पत्र"}),
    ("minutes", r"बैठक|इतिवृत्त|Minutes|Proceedings",
     {"en": "Minutes of a meeting", "mr": "बैठकीचे इतिवृत्त"}),
]
KIND_LABELS = {k: lab for k, _, lab in KINDS}
KIND_LABELS["unknown"] = {"en": "Unclassified reference", "mr": "अवर्गीकृत संदर्भ"}

# What the mahGRs archive actually contains: orders published on the departmental GR portal.
# A court order, an Act or a departmental letter is not in it and never was, so "not found"
# is a statement about our coverage, not about the draft.
IN_ARCHIVE = {"gr", "circular", "corrigendum", "notification", "order", "unknown"}

# Marathi supersession / amendment cues. Imported rather than re-declared so the draft checker
# and the corpus edge typer cannot disagree about what a cancellation sentence looks like.
CUE = re.compile(r"रद्द|अधिक्रमित|अधिक्रमून|व्यपगत|सुधारणा|अंशत")
CUE_EN = re.compile(r"cancel|supersede|repeal|rescind|withdraw|in\s+supersession", re.I)

# Department names as they appear in ENGLISH text, mapped to the same canonical vocabulary
# `resolver.MR_DEPTS` and `resolver.DEPT_BY_CODE` use. Without this the English path can never
# tell a cross-departmental citation from an internal one.
EN_DEPTS: dict[str, str] = {
    r"Finance\s+Department": "Finance",
    r"General\s+Administration\s+Department": "General Administration",
    r"Higher\s+and\s+Technical\s+Education": "Higher and Technical Education",
    r"School\s+Education(\s+and\s+Sports)?\s+Department": "School Education",
    r"Revenue\s+Department": "Revenue",
    r"Home\s+Department": "Home",
    r"Planning\s+Department": "Planning",
    r"Law\s+and\s+Judiciary": "Law and Judiciary",
    r"Rural\s+Development": "Rural Development",
    r"Urban\s+Development": "Urban Development",
    r"Public\s+Works": "Public Works",
    r"Tribal\s+Development": "Tribal Development",
    r"Social\s+Justice": "Social Justice",
    r"Medical\s+Education": "Medical Education",
    r"Skill\s+Development": "Skill Development",
    r"Water\s+Resources": "Water Resources",
    r"Agriculture\s+Department": "Agriculture",
    r"Industries\s+Department": "Industries",
}

# The document's OWN file number, needed for `समक्रमांक` ("of the same number") citations — a
# reference to another decision in this very file. In the corpus the resolver inherits it from
# GRs.json; a draft is not in GRs.json, so it must be read off the header.
OWN_NO = re.compile(
    r"(?:शासन\s*)?(?:निर्णय|परिपत्रक|आदेश|ज्ञापन)\s*क्रमांक\s*[:ः.\-–]?\s*(?P<mr>[^\n]{4,120})"
    r"|(?:Government\s+)?(?:Resolution|Circular|Order|Decision)\s+No\.?\s*[:\-–]?\s*"
    r"(?P<en>[^\n]{4,120})", re.I)

# The document's own date, off the header line. Both numeric and spelled-out Marathi forms:
# the Manual's own specimen writes "दिनांक : ७ मार्च, २०१८", and reading only digits would miss
# it on the very form we enforce.
OWN_DATE_NUM = re.compile(
    r"(?:दिनांक|दिनाक|^\s*Date)\s*[:ः.\-–\s]*"
    r"([०-९\d]{1,2})\s*[.\-/]\s*([०-९\d]{1,2})\s*[.\-/]\s*([०-९\d]{2,4})", re.M)
MR_MONTHS = ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
             "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]
# The month is captured as a bare Devanagari run and matched on its SKELETON — the consonants,
# with every matra and virama removed — rather than compared literally.
#
# Because a PDF text layer routinely hands back the same word with its matras in visual order:
# `एप्रिल` (April) arrives as `एिप्रल`, and a literal alternation matches neither the header nor
# anything else, so the document's own date silently becomes "today". Stripping combining marks
# maps both spellings to `एपरल`, and the twelve skeletons stay distinct from one another.
_MARKS = None


def _skeleton(s: str) -> str:
    global _MARKS
    if _MARKS is None:
        import unicodedata
        _MARKS = unicodedata.category
    return "".join(c for c in s if _MARKS(c) not in ("Mn", "Mc"))


MONTH_BY_SKELETON = {_skeleton(m): i + 1 for i, m in enumerate(MR_MONTHS)}
OWN_DATE_MR = re.compile(
    r"(?:दिनांक|दिनाक)\s*[:ः.\-–\s]*([०-९\d]{1,2})\s*([ऀ-ॿ]{2,14}?)\s*,?\s*"
    r"([०-९\d]{4})")


def classify(raw: str) -> str:
    for name, pat, _ in KINDS:
        if re.search(pat, raw, re.I):
            return name
    return "unknown"


# --------------------------------------------------------------------------- the archive

class Archive:
    """Read-only view of `out/graph.json`, shaped for live citation checking.

    The resolution index is built from the graph's own nodes rather than re-read from the
    corpus's GRs.json files. That is deliberate on two counts: the API already holds the graph in
    memory, and it guarantees that anything a citation resolves to is a node whose supersession
    status we can immediately answer. An index that could resolve to a uid the graph does not
    contain would produce "verified" citations with no status — the worst of both.
    """

    def __init__(self, graph: dict):
        self.nodes: dict[str, dict] = {n["uid"]: n for n in graph.get("nodes", [])}

        by_date: dict[datetime.date, list[str]] = defaultdict(list)
        by_no: dict[str, list[str]] = defaultdict(list)
        by_key: dict[str, list[str]] = defaultdict(list)
        meta: dict[str, dict] = {}
        for uid, n in self.nodes.items():
            d = R.uid_date(uid)
            no = n.get("decision_no") or ""
            meta[uid] = {"date": d, "no": no, "subject": n.get("subject") or "",
                         "dept": n.get("dept"), "dept_code": n.get("dept_code"),
                         "dept_full": n.get("dept")}
            by_date[d].append(uid)
            if R.norm_no(no):
                by_no[R.norm_no(no)].append(uid)
            if R.digit_key(no):
                by_key[R.digit_key(no)].append(uid)
        self.idx = (by_date, by_no, by_key, meta)
        self.in_index = {m["dept"] for m in meta.values() if m.get("dept")}

        dates = [m["date"] for m in meta.values()]
        self.covers = (min(dates), max(dates)) if dates else (None, None)

        # Supersession / amendment, target -> the edges that did it. Evidence travels with them,
        # because a claim that an order was cancelled must be able to show the sentence.
        self.killed_by: dict[str, list[dict]] = defaultdict(list)
        self.amended_by: dict[str, list[dict]] = defaultdict(list)
        self.in_edges: dict[str, list[dict]] = defaultdict(list)
        for e in graph.get("edges", []):
            self.in_edges[e["dst"]].append(e)
            if e["type"] == "SUPERSEDES":
                self.killed_by[e["dst"]].append(e)
            elif e["type"] == "AMENDS":
                self.amended_by[e["dst"]].append(e)

    @property
    def available(self) -> bool:
        return bool(self.nodes)

    def add(self, uid: str, node: dict) -> None:
        """Insert one GR into the live indexes — for documents not yet in the corpus.

        A GR pending issue is invisible to every check in this project until it is crawled,
        which is exactly backwards: the moment it matters most is *before* it is published. So
        an uploaded draft is registered here and thereafter resolves like any archived order,
        including from a second draft that cites it.

        The date range widens with it. Without that, a draft dated next month would have its own
        citations rejected as `outside_range` by the coverage test, which is a statement about
        the crawl and not about a document we are holding in memory.
        """
        by_date, by_no, by_key, meta = self.idx
        d = R.uid_date(uid)
        self.nodes[uid] = node
        no = node.get("decision_no") or ""
        meta[uid] = {"date": d, "no": no, "subject": node.get("subject") or "",
                     "dept": node.get("dept"), "dept_code": node.get("dept_code"),
                     "dept_full": node.get("dept")}
        by_date[d].append(uid)
        if R.norm_no(no):
            by_no[R.norm_no(no)].append(uid)
        if R.digit_key(no):
            by_key[R.digit_key(no)].append(uid)
        if node.get("dept"):
            self.in_index.add(node["dept"])
        lo, hi = self.covers
        self.covers = (min(lo, d) if lo else d, max(hi, d) if hi else d)

    def drop(self, uid: str) -> None:
        """Remove a staged GR again. The corpus is never touched by this path."""
        by_date, by_no, by_key, meta = self.idx
        node = self.nodes.pop(uid, None)
        m = meta.pop(uid, None)
        if not m:
            return
        for bucket, key in ((by_date, m["date"]), (by_no, R.norm_no(m["no"])),
                            (by_key, R.digit_key(m["no"]))):
            if key and uid in bucket.get(key, []):
                bucket[key].remove(uid)
        del node

    def brief(self, uid: str) -> dict:
        n = self.nodes.get(uid, {})
        return {"uid": uid, "date": n.get("date"), "dept": n.get("dept"),
                "decision_no": n.get("decision_no"), "subject": n.get("subject"),
                "in_degree": n.get("in_degree", 0)}

    def _edge_brief(self, e: dict) -> dict:
        return {**self.brief(e["src"]),
                "evidence": e.get("cue") or e.get("evidence"),
                "evidence_en": e.get("evidence_en"),
                "confidence": e.get("confidence")}

    def status(self, uid: str) -> dict:
        """What has happened to this order since it was issued."""
        killers = [self._edge_brief(e) for e in self.killed_by.get(uid, [])]
        amenders = [self._edge_brief(e) for e in self.amended_by.get(uid, [])]
        return {
            "in_force": not killers,
            "superseded_by": sorted(killers, key=lambda x: x["date"] or ""),
            "amended_by": sorted(amenders, key=lambda x: x["date"] or ""),
            "cited_by_count": len(self.in_edges.get(uid, [])),
        }

    def dependents(self, uid: str, depth: int = 3) -> dict:
        """Transitive live dependents, by department. The blast radius of cancelling `uid`.

        Same walk as `/api/blast/{uid}`, run here for a citation in an unissued draft. Already
        superseded dependents are excluded from the headline — they cannot break twice.
        """
        superseded = set(self.killed_by)
        seen, frontier = {uid}, {uid}
        for _ in range(depth):
            nxt = set()
            for u in frontier:
                for e in self.in_edges.get(u, []):
                    if e["src"] not in seen:
                        seen.add(e["src"])
                        nxt.add(e["src"])
            if not nxt:
                break
            frontier = nxt
        live = (seen - {uid}) - superseded
        depts = Counter(self.nodes[u]["dept"] for u in live if u in self.nodes)
        return {
            "live": len(live),
            "total": len(seen) - 1,
            "departments": dict(depts.most_common()),
            "sample": [self.brief(u) for u in
                       sorted(live, key=lambda x: -self.nodes[x]["in_degree"])[:8]],
        }


# --------------------------------------------------------------------------- extraction (FR-1)

def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# A `क्र`-family marker. Used to re-anchor number capture in body prose — see `_tighten_no`.
MR_NO_MARK = re.compile(r"(?:क्रमांक|क्र)\s*[.:ः]?\s*")


def _tighten_no(raw: str) -> str | None:
    """The file number nearest the date, when a body sentence contains several `क्र` markers.

    `resolver.MR_NO` captures from the FIRST marker up to the date, which is right for a
    reference-block item — those are split one per ordinal, so there is only one marker. Operative
    body prose is different:

        संदर्भ क्रमांक १ येथील शासन परिपत्रक, वित्त विभाग, क्रमांक अर्थसं-२०२५/प्र.क्र.४४/अर्थ-३,
        दिनांक ०७.०४.२०२५ याद्वारे रद्द करण्यात येत आहे.

    "the circular at reference no. 1" opens with a marker of its own, so the capture runs from
    `क्रमांक १` and swallows the whole clause. The resulting digit key matches nothing, and the
    one sentence that carries the cancellation language — the sentence the whole cross-department
    conflict check hangs on — silently fails to resolve.

    Anchoring on the LAST marker before the date fixes it. Applied to body candidates only:
    `resolver.py` stays byte-identical on the corpus, so the graph and this checker cannot drift
    on any citation the graph itself parsed.
    """
    best = None
    for mk in MR_NO_MARK.finditer(raw):
        m = R.MR_NO.match(raw, mk.start())
        if m:
            best = m
    if not best:
        return None
    no = " ".join(best.group(1).split())
    if R.MR_NO_REJECT.search(no) or not re.search(r"[०-९]", no):
        return None
    return no


def _mr_body_candidates(text: str, skip: tuple[int, int] | None) -> list[tuple[int, str]]:
    """Citation-shaped sentences OUTSIDE the वाचा block.

    ~20% of real GRs label no reference block at all and cite inline, and a drafting officer
    routinely names an order in the operative paragraph as well as in the preamble. Restricting
    FR-1 to the preamble would miss exactly the citations that carry the cancellation language.

    Gated harder than the reference block is, because ordinary prose is full of dates: a sentence
    qualifies only if it also names an order type, carries a क्रमांक, or carries cancellation
    language. That last clause is not optional — a page break or a wrapped line routinely leaves
    `… दिनांक ०७.०४.२०२५ याद्वारे रद्द करण्यात येत आहे.` on a fragment of its own, with the file
    number stranded above it. Drop that fragment and the one sentence the whole blast-radius
    check depends on never reaches the resolver.
    """
    out: list[tuple[int, str]] = []
    at = 0
    for chunk in re.split(r"(?<=[।\n])", text):
        start, at = at, at + len(chunk)
        # Overlap, not containment. The वाचा block's span begins mid-line — just after the
        # `वाचा :` marker — so the line holding the first reference item starts BEFORE the span
        # and a containment test lets it through, re-reading the first citation as a body
        # sentence and listing every document's opening reference twice.
        if skip and start < skip[1] and at > skip[0]:
            continue
        s = chunk.strip()
        if len(s) < 20 or not R.MR_DATE.search(s):
            continue
        if not (R.MR_GR_WORD.search(s) or "क्रमांक" in s or re.search(KINDS[0][1], s)
                or CUE.search(s)):
            continue
        out.append((start, s))
    return out


def _en_items(text: str) -> list[tuple[int, str]]:
    """[(offset, item)] from the English side.

    Reuses `parser.py`'s reference-block regexes rather than restating them — including the
    hard-won rule that a mid-line `(1)` is NOT a list ordinal, because "Section 40 (1) of the
    Act" looks identical and splitting on it destroys the reference list of any GR citing a
    statute.

    The line scan below is not a fallback for odd documents, it is the main path: IndicTrans2
    frequently drops the `वाचा :` label altogether, so the English rendering of a GR with a
    perfectly good reference block arrives as bare lines. Fixture 201803071449402308 is exactly
    that — eighteen references, no header word anywhere.
    """
    out: list[tuple[int, str]] = []
    blk = P.REF_BLOCK.search(text)
    covered = (0, 0)
    if blk:
        body = P.BODY_START.search(text, blk.end())
        end = body.start() if body else min(len(text), blk.end() + 4000)
        region, base = text[blk.end():end], blk.end()
        covered = (blk.end(), end)
        marks = list(P.REF_ITEM.finditer(region))
        if marks:
            for i, m in enumerate(marks):
                stop = marks[i + 1].start() if i + 1 < len(marks) else len(region)
                out.append((base + m.end(), region[m.end():stop]))
        else:
            at = 0
            for line in region.split("\n"):
                if line.strip():
                    out.append((base + at, line))
                at += len(line) + 1

    at = 0
    for line in text.split("\n"):
        start, at = at, at + len(line) + 1
        if covered[0] <= start < covered[1] or not line.strip():
            continue
        # The cue clause matters as much as the order words: an operative sentence wraps, and the
        # fragment carrying "is hereby cancelled" often holds the date while the file number sits
        # on the line above. Such a fragment resolves by merging onto the citation that already
        # gave that date — see the by-date merge in `extract`.
        if P.CITE_ORDER.search(line) or P.CITE_NO.search(line) or CUE_EN.search(line):
            out.append((start, line))
    return out


def _en_citation(raw: str) -> dict | None:
    """One citation record from an English reference item, in `resolver`'s shape.

    English resolution runs on the digit key alone. The archive's `order_number` is 97.6%
    Devanagari while an English citation carries a transliterated file number — `Masi-1` /
    `Mashi-1` / `MASHI-1` for one file — so no string comparison can ever connect them. Digits
    survive both transliteration and script (`resolver.digit_key`). Marathi remains the
    authoritative side; this path exists because officers upload English drafts, not because it
    is the better evidence.
    """
    raw = " ".join(raw.split())
    if len(raw) < 12:
        return None
    dates = P.find_dates(raw)
    if not dates:
        return None
    no = P.CITE_NO.search(raw)
    cited_no = P._clean_no(no.group(1)) if no else None
    if cited_no and not re.search(r"\d", cited_no):
        cited_no = None
    dept = next((v for pat, v in EN_DEPTS.items() if re.search(pat, raw, re.I)), None)
    return {
        "raw": raw[:400],
        "cited_no": cited_no,
        "cited_date": dates[0],
        "cited_dept": dept,
        "is_gr": bool(P.CITE_ORDER.search(raw)),
        "same_no": False,
    }


def extract(text: str, lang: str = "mr") -> tuple[list[dict], str]:
    """FR-1 — every cited order in the document. Returns (citations, side_used).

    Falls back to the other language when the chosen side yields nothing, because `lang` is
    guessed from the script mix of a scanned page and a bilingual GR can be misread. Which side
    actually produced the citations is returned, never assumed.
    """
    pend = _preamble_end(text)

    def run(side: str) -> list[dict]:
        rows: list[dict] = []
        # `prose` marks items caught by scanning running text rather than lifted out of an
        # enumerated reference list. It governs number re-anchoring, not the zone label — a
        # reference block with no `वाचा` header is prose to the scanner and preamble to a reader.
        if side == "mr":
            items = [(o, s, False) for o, s in R.mr_reference_items(text)]
            items += [(o, s, True) for o, s in
                      _mr_body_candidates(text, R.mr_reference_span(text))]
            make = R.mr_citation
        else:
            items = [(o, s, True) for o, s in _en_items(text)]
            make = _en_citation
        for offset, item, prose in items:
            c = make(item)
            if not c:
                continue
            if side == "mr" and prose:
                c["cited_no"] = _tighten_no(c["raw"]) or c["cited_no"]
            rows.append({**c, "zone": "preamble" if offset < pend else "body",
                         "line": _line_of(text, offset), "side": side,
                         "kind": classify(c["raw"]),
                         "cue": bool(CUE.search(c["raw"]) or CUE_EN.search(c["raw"]))})
        return rows

    primary = "mr" if lang == "mr" else "en"
    rows = run(primary)
    side = primary
    if not rows:
        rows = run("en" if primary == "mr" else "mr")
        side = "en" if primary == "mr" else "mr"

    # One legal fact deserves one row. The same order is routinely cited in the preamble and
    # again in the operative paragraph; keep the preamble copy — it carries the fuller text —
    # but remember that the body mentioned it, because that is where cancellation language lives.
    seen: dict[tuple, dict] = {}
    by_date: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: (x["zone"] != "preamble", x["line"])):
        k = (R.digit_key(r["cited_no"]) or (r["cited_no"] or ""), r["cited_date"])
        prior = seen.get(k)
        # A body sentence naming a date but no number, when the preamble already cites an order
        # on that date, is the operative reference to that same order — "the GR dated 03.02.2022"
        # written after the reference block already gave its number. Kept as a separate row it
        # produced a spurious "cannot be verified" against an order we had in fact just verified.
        if prior is None and r["zone"] == "body" and not R.digit_key(r["cited_no"]):
            prior = by_date.get(r["cited_date"])
        if prior is not None:
            prior["also_at_lines"].append(r["line"])
            prior["cue"] = prior["cue"] or r["cue"]
            continue
        row = {**r, "also_at_lines": []}
        seen[k] = row
        by_date.setdefault(r["cited_date"], row)
    return sorted(seen.values(), key=lambda x: x["line"]), side


# --------------------------------------------------------------------------- document header

# The document's OWN number line, which must not be mistaken for a citation when bounding the
# header. The letter layout puts number and date on one line, so "has a number and a date" alone
# would cut the header above the very field we are looking for.
#
# Deliberately NOT `Government Resolution No.` — that is the form a *citation* takes as well
# ("Government Resolution No. 1004/… dated 04.10.2004"), and skipping it let the first citation
# back inside the header, which is the bug this whole function exists to prevent. What is safe
# here is anchored at line start: a citation is preceded by its list ordinal.
_OWN_HEADER_LINE = re.compile(
    r"^\s*Number\s*[:.\-]|^\s*(?:शासन\s*)?(?:निर्णय|परिपत्रक|आदेश|ज्ञापन)\s*क्रमांक", re.I)


def _header(text: str) -> str:
    """Everything above the first citation.

    Every header field must be read from here and nowhere else. Below the वाचा line each cited
    order carries its own number, date and department, and a scan of "the first 25 lines" picks
    those up instead — measured on fixture 201803071449402308, whose own date is 07.03.2018 and
    whose first numeric date is 04.10.2004, belonging to its first citation. The misread is not
    cosmetic: the document's date sets the horizon for "a GR cannot cite an order issued after
    it", so a 2004 header date silently rejects every real citation in the document.

    Bounded by whichever comes first of the labelled reference block and the first
    citation-shaped line, because the label is frequently absent — IndicTrans2 drops `वाचा :`
    outright, and ~20% of Marathi GRs never had one.
    """
    ends = []
    span = R.mr_reference_span(text)
    if span:
        ends.append(span[0])
    blk = P.REF_BLOCK.search(text)
    if blk:
        ends.append(blk.start())

    at = 0
    for n, line in enumerate(text.split("\n")):
        start, at = at, at + len(line) + 1
        if n < 2 or _OWN_HEADER_LINE.match(line):
            continue
        has_date = bool(P.find_dates(line) or R.MR_DATE.search(line))
        names_order = bool(P.CITE_ORDER.search(line) or R.MR_GR_WORD.search(line)
                           or P.CITE_NO.search(line) or "क्रमांक" in line or "क्र." in line)
        if has_date and names_order:
            ends.append(start)
            break

    return text[:min(ends)] if ends else text[:1500]


def _preamble_end(text: str) -> int:
    """Where the recitals stop and the operative part begins.

    Used to label each citation `preamble` or `body` by POSITION rather than by which regex
    caught it. FR-1 asks specifically for the citations in the preamble, and a document whose
    reference block carries no label would otherwise report every one of its references as a
    body mention and draw a warning for a preamble that is in fact perfectly populated.
    """
    for m in (R.MR_BODY_START.search(text), P.BODY_START.search(text)):
        if m:
            return m.start()
    span = R.mr_reference_span(text)
    if span:
        return span[1]
    blk = P.REF_BLOCK.search(text)
    if blk:
        return min(len(text), blk.end() + 4000)
    return len(_header(text))


def doc_date(text: str) -> tuple[datetime.date | None, str]:
    """The document's own date, and where it came from.

    Matters for more than bookkeeping: it decides whether a cited order was *already* dead when
    the document was issued (a drafting error at the time) or died afterwards (silent decay) —
    `audit.py`'s BORN_DEAD / ROTTED split. Unparseable degrades to today, which for a draft is
    the correct assumption anyway.
    """
    head = _header(text)
    m = OWN_DATE_NUM.search(head)
    if m:
        try:
            d, mo, y = (int(g.translate(DEV_DIGITS)) for g in m.groups())
            y += 2000 if y < 100 else 0
            return datetime.date(y, mo, d), "date line"
        except ValueError:
            pass
    for m in OWN_DATE_MR.finditer(head):
        mon = MONTH_BY_SKELETON.get(_skeleton(m.group(2)))
        if not mon:
            continue
        try:
            d = int(m.group(1).translate(DEV_DIGITS))
            y = int(m.group(3).translate(DEV_DIGITS))
            return datetime.date(y, mon, d), "date line"
        except ValueError:
            continue
    # Spelled-out English ("Date of release: March 7, 2018"). Scanned bottom-up and preferring a
    # line that says so, because the Manual puts the document's date last in the header block —
    # `find_dates` returns numeric matches before textual ones regardless of position, so taking
    # its first answer picks up whatever sits highest on the page instead.
    lines = head.splitlines()
    for want_label in (True, False):
        for line in reversed(lines):
            if want_label and not re.search(r"दिनांक|दिनाक|\bDate\b", line, re.I):
                continue
            found = P.find_dates(line)
            if found:
                return datetime.date.fromisoformat(found[0]), "date line"
    return None, "not stated — today assumed"


def doc_dept(text: str) -> str | None:
    """The issuing department, read off the header.

    Scanned only above the reference block: below it, every cited order names *its* department
    and the first match would be somebody else's.
    """
    head = _header(text)
    for k, v in R.MR_DEPTS.items():
        if k in head:
            return v
    for pat, v in EN_DEPTS.items():
        if re.search(pat, head, re.I):
            return v
    return None


def doc_number(text: str) -> str | None:
    m = OWN_NO.search(_header(text))
    if not m:
        return None
    no = m.group("mr") or m.group("en") or ""
    no = re.split(r"\s*(?:दिनांक|दिनाक|\bDate\b)", no)[0]
    return " ".join(no.split()) or None


# --------------------------------------------------------------------------- verdicts (FR-2)

VERDICTS = {
    "verified":       {"en": "Found in the archive", "mr": "संग्रहात आढळले"},
    "ambiguous":      {"en": "Several archive entries match", "mr": "एकाहून अधिक नोंदी जुळतात"},
    "not_in_archive": {"en": "Not found in the archive", "mr": "संग्रहात आढळले नाही"},
    "unverifiable":   {"en": "Cannot be verified", "mr": "पडताळणी अशक्य"},
    "other_dept":     {"en": "Department not indexed", "mr": "विभाग निर्देशांकात नाही"},
    "outside_range":  {"en": "Outside the archive's date range", "mr": "संग्रह कालावधीबाहेर"},
    "out_of_scope":   {"en": "Not a document the GR archive holds", "mr": "शासन निर्णय संग्रहाबाहेर"},
}


def _verdict(cit: dict, res: dict, arc: Archive) -> tuple[str, str]:
    """(verdict, why). The five ways of not finding something are kept apart on purpose — see
    the module docstring. Only `not_in_archive` is a defect in the draft."""
    if cit["kind"] not in IN_ARCHIVE:
        label = KIND_LABELS[cit["kind"]]["en"]
        return "out_of_scope", (
            f"{label}s are not published in the mahGRs Government Resolution archive, so this "
            f"reference cannot be checked against it. Its absence is a limit of our coverage, "
            f"not a defect in the draft.")
    if res["resolved_uid"]:
        return "verified", res["reason"]

    reason = res["reason"]
    if "outside this index" in reason:
        return "other_dept", (
            f"{reason}. The archive indexes {len(arc.in_index)} departments "
            f"({', '.join(sorted(arc.in_index))}); this citation names another one.")

    lo, hi = arc.covers
    cd = datetime.date.fromisoformat(cit["cited_date"])
    if lo and not (lo <= cd <= hi):
        return "outside_range", (
            f"Cited {cd.isoformat()}, but the archive covers {lo.isoformat()} to "
            f"{hi.isoformat()}. Absence here says nothing about whether the order exists.")
    if "ambiguous" in reason:
        return "ambiguous", reason
    if "no file number" in reason:
        return "unverifiable", (
            "This citation gives a date but no file number. A date alone cannot identify an "
            "order — every GR issued that day would match — so no resolution is offered.")
    # A "number" with no digit key is not a file number we can match in EITHER script: the exact
    # Devanagari comparison has already failed by this point, and `digit_key` is the only other
    # route. Observed on body prose — `संदर्भ क्र. १६ येथील शासन निर्णयान्वये` is "the GR at
    # reference no. 16", a pointer into this document's own list, not a file number at all.
    # Reporting that as a missing archive entry would be a fabricated defect.
    if not R.digit_key(cit["cited_no"]):
        return "unverifiable", (
            f"No usable file number could be read from this reference "
            f"(“{cit['cited_no']}”). It may be a pointer into the document's own list "
            f"rather than an order number. Date alone cannot identify an order.")
    return "not_in_archive", reason


# --------------------------------------------------------------------------- findings (FR-3)

GRAPH_AUTHORITY = "Dependency graph, out/graph.json — edge carries the sentence that produced it"


def _finding(code, severity, message, i=None, authority="SRS FR-2", **extra):
    return {"code": code, "severity": severity, "message": message,
            "citation": i, "authority": authority, **extra}


def check(text: str, lang: str = "mr", arc: Archive | None = None,
          window: int = 3) -> dict[str, Any]:
    """FR-1 + FR-2 + FR-3 over one document. Deterministic; no model is consulted."""
    if arc is None or not arc.available:
        return {"available": False,
                "hint": "run: python graph.py data/mahGRs/GRs --out out/graph.json"}

    citations, side = extract(text, lang)
    dept = doc_dept(text)
    own_no = doc_number(text)
    ddate, ddate_src = doc_date(text)
    effective_date = ddate or datetime.date.today()

    # `resolve` needs a citing uid: to exclude self-citation, and to reject a citation of an
    # order issued after the citing document. A draft has none, so one is synthesised from the
    # document's own date. The trailing zeroes cannot collide with a real uid — no GR is uploaded
    # at 00:00:00 under department code 00.
    src_uid = effective_date.strftime("%Y%m%d") + "0" * 10

    rows: list[dict] = []
    findings: list[dict] = []

    for i, c in enumerate(citations, 1):      # 1-based: `citation` on a finding is the row's `n`
        cit = dict(c)
        # `समक्रमांक` — "of the same number" — cites another decision in this very file. In the
        # corpus the number is inherited from GRs.json; a draft is not in GRs.json, so it comes
        # off the header instead.
        if cit.get("same_no") and not cit["cited_no"] and own_no:
            cit["cited_no"] = own_no
            cit["number_inherited"] = True

        res = R.resolve(cit, src_uid, arc.idx, window, in_index=arc.in_index)
        verdict, why = _verdict(cit, res, arc)

        row: dict[str, Any] = {
            "n": i, **{k: cit[k] for k in
                           ("raw", "cited_no", "cited_date", "cited_dept", "kind", "zone",
                            "line", "cue")},
            "also_at_lines": cit.get("also_at_lines", []),
            "number_inherited": cit.get("number_inherited", False),
            "kind_label": KIND_LABELS[cit["kind"]],
            "verdict": verdict, "verdict_label": VERDICTS[verdict], "why": why,
            "side": cit["side"],
            "match": None, "status": None, "candidates": [],
        }

        if verdict == "verified":
            uid = res["resolved_uid"]
            row["match"] = arc.brief(uid)
            row["confidence"] = res["confidence"]
            st = arc.status(uid)
            row["status"] = st
            tgt = arc.nodes[uid]
            row["cross_dept"] = bool(dept and tgt.get("dept") and tgt["dept"] != dept)
            drift = (R.uid_date(uid) - datetime.date.fromisoformat(cit["cited_date"])).days
            row["date_drift_days"] = drift
            findings.extend(_alignment_findings(i, row, arc, dept, effective_date))
        else:
            row["candidates"] = [arc.brief(u) for u in res.get("candidates", [])[:5]]
            findings.append(_unresolved_finding(i, row))

        rows.append(row)

    findings.extend(_document_findings(rows, citations, text))

    counts = Counter(r["verdict"] for r in rows)
    sev = Counter(f["severity"] for f in findings)
    cross = [r for r in rows if r.get("cross_dept")]
    return {
        "available": True,
        "document": {
            "department": dept,
            "decision_no": own_no,
            "date": effective_date.isoformat(),
            "date_source": ddate_src,
            "side_parsed": side,
            "lang": lang,
        },
        "archive": {
            "grs": len(arc.nodes),
            "departments": sorted(arc.in_index),
            "covers": [arc.covers[0].isoformat(), arc.covers[1].isoformat()],
        },
        "summary": {
            "citations": len(rows),
            "verified": counts["verified"],
            "not_in_archive": counts["not_in_archive"],
            "unverifiable": counts["unverifiable"] + counts["ambiguous"],
            "out_of_scope": counts["out_of_scope"] + counts["other_dept"]
                            + counts["outside_range"],
            "superseded": sum(1 for r in rows if r["status"]
                              and not r["status"]["in_force"]),
            "amended": sum(1 for r in rows if r["status"]
                           and r["status"]["amended_by"] and r["status"]["in_force"]),
            "cross_department": len(cross),
            "by_verdict": dict(counts),
            "by_kind": dict(Counter(r["kind"] for r in rows)),
        },
        "counts": {"error": sev["error"], "warning": sev["warning"],
                   "advisory": sev["advisory"]},
        "alignment": _alignment(rows, findings),
        "clean": sev["error"] == 0,
        "citations": rows,
        "findings": sorted(findings,
                           key=lambda f: ({"error": 0, "warning": 1, "advisory": 2}[f["severity"]],
                                          f["citation"] if f["citation"] is not None else 99)),
        "definitions": {
            "verified": "the cited file number and date both match one GR in the archive",
            "not_in_archive": "a departmental order, inside the archive's range, that the "
                              "archive does not contain — either the reference is wrong or the "
                              "order was never published",
            "out_of_scope": "court orders, Acts and letters are not held in the GR archive; "
                            "their absence is a limit of our coverage, not a defect",
            "in_force": "no incoming SUPERSEDES edge within the indexed departments — an upper "
                        "bound, so every finding here is conservative",
        },
    }


ALIGNMENT = {
    "aligned":    {"en": "Aligned with the orders it cites",
                   "mr": "संदर्भित आदेशांशी सुसंगत"},
    "misaligned": {"en": "NOT aligned with the orders it cites",
                   "mr": "संदर्भित आदेशांशी विसंगत"},
    "partial":    {"en": "Aligned, with points to check",
                   "mr": "सुसंगत, परंतु तपासण्याजोगे मुद्दे"},
    "unverified": {"en": "Could not be established",
                   "mr": "निश्चित करता आले नाही"},
}


def _alignment(rows: list[dict], findings: list[dict]) -> dict[str, Any]:
    """Does this document still stand on what it cites? Computed, never generated.

    This is the headline an officer reads first, so it is settled by counting graph facts rather
    than by asking a model — CLAUDE.md rule 4, and a 2B model measurably gets it wrong: given the
    findings and left to infer the verdict, Qwen3.5-2B called a document whose citations had been
    superseded "valid because the cited references are either unverified or superseded".

    Four states, in decreasing order of certainty:

      misaligned  something it stands on has been superseded, or an order it cites is not in the
                  archive at all. Either way the document rests on something that is not there.
      partial     everything found is in force, but an order has been amended since, or a
                  citation could not be checked. Nothing is broken; something needs a look.
      aligned     every citation that COULD be checked resolved, and every one of those orders
                  is in force today.
      unverified  nothing could be checked — no citations, or none of them checkable. Saying
                  "aligned" here would be a claim we have not earned.
    """
    checkable = [r for r in rows if r["verdict"] in ("verified", "not_in_archive", "ambiguous")]
    verified = [r for r in rows if r["verdict"] == "verified"]
    dead = [r for r in verified if r["status"] and not r["status"]["in_force"]]
    amended = [r for r in verified if r["status"] and r["status"]["in_force"]
               and r["status"]["amended_by"]]
    missing = [r for r in rows if r["verdict"] == "not_in_archive"]
    unsure = [r for r in rows if r["verdict"] in ("unverifiable", "ambiguous")]
    cancels = [f for f in findings if f["code"] == "R12"]

    reasons: list[str] = []
    if dead:
        reasons.append(f"{len(dead)} cited order(s) have been superseded and no longer stand.")
    if missing:
        reasons.append(f"{len(missing)} cited order(s) are not in the archive, though they fall "
                       f"inside its coverage.")
    if amended:
        reasons.append(f"{len(amended)} cited order(s) are in force but have been amended since.")
    if unsure:
        reasons.append(f"{len(unsure)} citation(s) could not be checked.")
    if cancels:
        reasons.append(f"This document cancels or amends an order other GRs still depend on.")
    if verified and not dead and not missing:
        reasons.append(f"All {len(verified)} order(s) that could be resolved are in force today.")

    if dead or missing:
        verdict = "misaligned"
    elif not checkable and not verified:
        verdict = "unverified"
    elif amended or unsure or cancels:
        verdict = "partial"
    else:
        verdict = "aligned"

    return {
        "verdict": verdict,
        "label": ALIGNMENT[verdict],
        "reasons": reasons,
        "counts": {"verified": len(verified), "superseded": len(dead), "amended": len(amended),
                   "missing": len(missing), "unchecked": len(unsure)},
        "basis": "computed from the dependency graph — no model is consulted for this verdict",
    }


def _unresolved_finding(i: int, row: dict) -> dict:
    """FR-3. Severity is the whole point: only one of these is the draft's fault."""
    v = row["verdict"]
    where = f"line {row['line']}"
    if v == "not_in_archive":
        return _finding(
            "R01", "error",
            f"The order cited at {where} — {row['cited_no'] or 'no file number'}, dated "
            f"{row['cited_date']} — is not in the archive. Check the file number and the date "
            f"before this GR is issued; a citation that does not resolve cannot be relied on.",
            i, "SRS FR-2 / FR-3")
    if v == "ambiguous":
        return _finding("R05", "warning",
                        f"{row['why']} ({where}). The citation does not distinguish between "
                        f"them, so no reference is asserted.", i, "SRS FR-2")
    if v == "unverifiable":
        return _finding("R06", "warning",
                        f"The reference at {where} cannot be verified. {row['why']} "
                        f"Give the order's full file number so it can be checked.",
                        i, "SRS FR-1")
    if v == "other_dept":
        return _finding("R07", "advisory", f"{row['why']} ({where})", i, "SRS FR-2")
    if v == "outside_range":
        return _finding("R08", "advisory", f"{row['why']} ({where})", i, "SRS FR-2")
    return _finding("R09", "advisory", f"{row['why']} ({where})", i, "SRS FR-2")


def _alignment_findings(i: int, row: dict, arc: Archive, dept: str | None,
                        on: datetime.date) -> list[dict]:
    """Does the draft still align with what it cites? Everything here comes off a graph edge."""
    out: list[dict] = []
    st, m = row["status"], row["match"]
    where = f"line {row['line']}"

    for k in st["superseded_by"]:
        kd = datetime.date.fromisoformat(k["date"]) if k["date"] else None
        # audit.py's BORN_DEAD / ROTTED split, evaluated for this one document. For an unissued
        # draft `on` is today, so every existing supersession reads BORN_DEAD — which is exactly
        # right: the officer is about to cite an order that already does not stand.
        born_dead = bool(kd and kd <= on)
        when = ("was already superseded" if born_dead
                else "has been superseded since this document was dated")
        cross = bool(dept and k["dept"] and k["dept"] != dept)
        out.append(_finding(
            "R11" if cross else "R02", "error",
            f"The GR cited at {where} ({m['uid']}, {m['date']}) {when} — by {k['uid']} of "
            f"{k['date']}"
            + (f", issued by the {k['dept']} Department" if cross else "")
            + ". "
            + ("Citing an order that no longer stands leaves this GR resting on nothing."
               if born_dead else
               "The citation was correct when written and has decayed since.")
            + (" Neither department can see this from either document alone — it needs a "
               "cross-departmental citation and a supersession chain." if cross else ""),
            i, GRAPH_AUTHORITY, evidence=k.get("evidence"), related=k["uid"],
            kind="BORN_DEAD" if born_dead else "ROTTED"))

    if st["in_force"]:
        for a in st["amended_by"]:
            out.append(_finding(
                "R03", "warning",
                f"The GR cited at {where} ({m['uid']}) is still in force but was amended by "
                f"{a['uid']} of {a['date']}. Cite the amendment too, or say which text is "
                f"intended.",
                i, GRAPH_AUTHORITY, evidence=a.get("evidence"), related=a["uid"]))

    if row.get("cross_dept") and not any(f["code"] == "R11" for f in out):
        out.append(_finding(
            "R10", "advisory",
            f"{where} depends on an order of the {m['dept']} Department. It is in force today; "
            f"if that department replaces it, this GR decays silently.",
            i, GRAPH_AUTHORITY, related=m["uid"]))

    # The draft proposes to cancel or amend this order. What else is standing on it?
    if row["cue"]:
        dep = arc.dependents(m["uid"])
        others = {k: v for k, v in dep["departments"].items() if k != dept}
        if dep["live"]:
            out.append(_finding(
                "R12", "warning",
                f"This draft carries cancellation or amendment language against {m['uid']} "
                f"({m['date']}), which {dep['live']} GRs still in force depend on"
                + (f", across {len(others)} other department(s): "
                   f"{', '.join(sorted(others))}" if others else "")
                + ". Those citations become dead references the day this GR is issued.",
                i, GRAPH_AUTHORITY, related=m["uid"], blast=dep))
    return out


def _document_findings(rows: list[dict], citations: list[dict], text: str) -> list[dict]:
    out: list[dict] = []
    if not rows:
        out.append(_finding(
            "R00", "advisory",
            "No citations were found. A 'वाचा' / 'Read' block appears in 47.9% of real GRs, so "
            "citing nothing is normal — but if this GR rests on an earlier order, name it.",
            None, "SRS FR-1"))
        return out

    if not any(r["zone"] == "preamble" for r in rows):
        out.append(_finding(
            "R13", "warning",
            "Every citation found sits in the body; the preamble names none. FR-1 expects the "
            "orders a GR rests on to be listed in the 'वाचा' / 'Read' block.",
            None, "SRS FR-1"))
    return out


# --------------------------------------------------------------------------- cli

def _load_archive(path: str = "out/graph.json") -> Archive:
    import json
    from pathlib import Path
    return Archive(json.loads(Path(path).read_text(encoding="utf-8")))


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    lang = sys.argv[2] if len(sys.argv) > 2 else "mr"
    if lang not in ("mr", "en"):
        raise SystemExit(f"language must be 'mr' or 'en', got {lang!r}")
    body = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    print(json.dumps(check(body, lang, _load_archive()), ensure_ascii=False, indent=2))
