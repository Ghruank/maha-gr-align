#!/usr/bin/env python3
"""
Template Enforcement Engine — SRS FR-10, FR-11, FR-12.

The structure enforced here comes from the **Maharashtra Manual of Office Procedure, 2023,
Appendix 10.6** (`documents/mcs270623075036.pdf`), declared in `data/gr_template.json`.

This module contains **no model calls and never will.** Whether a draft carries a signature
block is a fact about the text; a model that "decides" it is a model that can be wrong about
something a regex settles. The LLM writes prose, this file judges structure.

Two design points that came out of measuring the corpus rather than assuming:

* **Conditional sections are conditional.** The budget head and Finance concurrence apply only
  to GRs that sanction expenditure — 16.3% of the corpus. Marking them universally mandatory
  would fail five drafts in six for no reason.
* **Budget heads are matched on digits, not on separators.** SRS FR-11 writes the head as
  `2054-00-101-02`, but the corpus OCR renders them space-separated (`2075 0113`, `2204 1981`),
  and Marathi GRs use Devanagari digits. A hyphen-anchored regex finds ZERO budget heads in
  1,500 real GRs. Same trap as `resolver.digit_key()` — normalise, then compare.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
TEMPLATE = json.loads((ROOT / "data" / "gr_template.json").read_text())

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Detection patterns per section. Marathi first — it is the legally operative text — with the
# English translation accepted alongside so a bilingual draft lints in either language.
DETECT: dict[str, str] = {
    "subject":             r"^\s*विषय\s*[:\-–]|^\s*Subject\s*[:\-–]",
    "govt":                r"महाराष्ट्र शासन|GOVERNMENT OF MAHARASHTRA",
    # Trailing punctuation is normal: the corpus writes "वित्त विभाग," with a comma.
    "department":          r"विभाग\s*[,.:;]?\s*$|Department\s*[,.:;]?\s*$",
    # "शासन" is often absent — real headers read "परिपत्रक क्रमांक :" or "आदेश क्रमांक".
    "resolution_no":       r"(शासन\s*)?(निर्णय|परिपत्रक|आदेश|ज्ञापन)\s*क्रमांक|"
                           r"(Government\s+)?(Resolution|Circular|Order)\s+No",
    "address":             r"मंत्रालय|Mantralaya",
    "date":                r"दिनांक|^\s*Date\s*[:\-]",
    "read":                r"वाचा\s*[:\-–]|^\s*Read\s*[:\-–]|^\s*संदर्भ\s*[:\-–]",
    "preamble":            r"प्रस्तावना|^\s*Preamble",
    # The OPERATIVE section header. Its wording follows the document type: a memorandum opens
    # its operative part with `शासन ज्ञापन :-`, a corrigendum with `शासन शुद्धीपत्रक :-`. Anchoring
    # this on `शासन निर्णय` alone reported the operative section missing on every memorandum and
    # corrigendum in the corpus — 47% of a 400-GR sample — which is not a defect in those
    # documents but a defect in this pattern. `क्रमांक` cannot follow, or the resolution NUMBER
    # line would match as the section header.
    "resolution":          r"शासन\s*(?:निर्णय|ज्ञापन|परिपत्रक|शुद्धिपत्रक|शुध्दीपत्रक|आदेश)"
                           r"\s*[:\-–]|"
                           r"^\s*शासन\s*(?:निर्णय|ज्ञापन|परिपत्रक|शुद्धिपत्रक|शुध्दीपत्रक|आदेश)"
                           r"\s*$|"
                           r"^\s*(?:परिपत्रक|ज्ञापन)\s*$|"
                           r"^\s*Resolution\s*[:\-–]|^\s*Resolution\s*$|"
                           r"^\s*(?:Memorandum|Circular|Corrigendum)\s*[:\-–]",
    "expenditure":         r"लेखाशीर्ष|खर्च.{0,40}(खाती|टाकण्यात)|debited to|budget head",
    "finance_concurrence": r"वित्त विभाग.{0,60}(सहमती|संमती|अनौपचारिक)|concurrence of the Finance",
    "governor_order":      r"राज्यपाल.{0,40}आदेशानुसार|आदेशानुसार व नावाने|"
                           r"[Bb]y order and in the name of the Governor",
    "signature":           r"(अवर|उप|प्रधान|कक्ष)?\s*सचिव|Under Secretary|Deputy Secretary|"
                           r"Principal Secretary",
    "distribution":        r"^\s*प्रति\s*[,:\-]?|^\s*To\s*[,:]",
    "website":             r"maharashtra\.gov\.in",
}

# Budget head: four-digit major head then three more groups, any separator, either digit system.
BUDGET_HEAD = re.compile(r"\b\d{4}\s*[-–\s]\s*\d{2}\s*[-–\s]\s*\d{3}\s*[-–\s]\s*\d{2}\b")

# Does this draft actually sanction money? Gates the conditional sections.
FINANCIAL = re.compile(
    r"निधी|अनुदान|रक्कम|खर्च|तरतूद|रुपये|₹|लेखाशीर्ष|"
    r"sanction.{0,30}(expenditure|amount|grant)|budget|funds?\b|Rs\.?\s*\d",
    re.I,
)


@dataclass
class Finding:
    code: str
    section: str
    label: str
    severity: str          # "error" | "warning" | "advisory"
    message: str
    line: int | None       # 1-indexed, None when the section is absent entirely
    authority: str


def _sections() -> list[dict[str, Any]]:
    return TEMPLATE["sections"]


# The Manual gives DIFFERENT specimen forms per communication type — Circular is Appendix 10.5,
# Resolution 10.6, Notification 10.7. Judging a circular against the resolution form produces
# confident nonsense, so say what the document is before saying whether it conforms.
DOC_TYPES = [
    ("circular",     r"परिपत्रक", "Appendix 10.5"),
    ("notification", r"अधिसूचना", "Appendix 10.7"),
    ("memorandum",   r"ज्ञापन|शुध्दीपत्रक|शुद्धिपत्रक", "Appendix 10.4"),
    ("resolution",   r"शासन निर्णय", "Appendix 10.6"),
]


def detect_doc_type(text: str) -> tuple[str, str]:
    """(type, manual appendix). Resolution is the default and the only one we draft."""
    head = "\n".join(text.splitlines()[:12])
    for name, pat, appendix in DOC_TYPES:
        if re.search(pat, head):
            return name, appendix
    return "resolution", "Appendix 10.6"


def has_financial_sanction(text: str) -> bool:
    """Whether the conditional financial sections apply to this draft."""
    return bool(FINANCIAL.search(text))


def find_budget_heads(text: str) -> list[str]:
    """Budget heads, separator- and script-independent. See module docstring."""
    return BUDGET_HEAD.findall(text.translate(DEV_DIGITS))


# Sections written as a label followed by content ("विषय :- X", or "प्रस्तावना :-" then a
# paragraph). For these, finding the label is NOT enough — the blank skeleton contains every
# label, so a label-only match reported an empty template as fully present. Content is required.
# Deliberately NOT department/signature/distribution: those lines ARE the content
# ("वित्त विभाग," is the department, "अवर सचिव" is the signature), so requiring something
# after a separator wrongly reports them missing.
LABELLED = {"subject", "resolution_no", "date", "read", "preamble", "resolution"}

# Any line matching one of these starts a new section, so it bounds the previous one's content.
#
# NO `\b` ANYWHERE IN THIS PATTERN. Devanagari words routinely end in a combining vowel sign —
# `वाचा` ends in U+093E — which Python's `re` classifies as a NON-word character. `\b` after it
# therefore never matches, and an earlier version of this regex silently failed on every
# Marathi label, letting a blank template read as filled. Anchor on the separator instead.
_ANY_LABEL = re.compile(
    r"^\s*(विषय|वाचा|संदर्भ|प्रस्तावना|प्रति|दिनांक|"
    r"शासन\s*(?:निर्णय|ज्ञापन|परिपत्रक|शुद्धिपत्रक|शुध्दीपत्रक|आदेश)|"
    r"Subject|Read|Preamble|Resolution|Memorandum|Corrigendum|To|Date)\s*[:\-–]"
    # Fixed boilerplate lines also bound a section — otherwise an empty Resolution swallows
    # the website line that follows it and reports itself as filled.
    r"|^\s*(महाराष्ट्र शासन|मंत्रालय|मादाम कामा|सदर शासन निर्णय|महाराष्ट्राचे राज्यपाल|"
    r"GOVERNMENT OF MAHARASHTRA|Mantralaya|Madam Cama|This Government Resolution|By order)"
)


def _section_has_content(lines: list[str], idx: int) -> bool:
    """Is there real text for the section whose label is on line `idx` (0-based)?

    Content may sit after the separator on the same line, or on following lines up to the next
    section label. Blank underscores are content — the officer left a deliberate gap.
    """
    line = lines[idx]
    # The separator is ":-" in this form, so consume the RUN of separator characters. Splitting
    # on a single one left "-" behind, which read as content and passed a blank template.
    after = re.split(r"\s*[:\-–]+\s*", line, maxsplit=1)
    if len(after) > 1 and after[1].strip():
        return True
    for nxt in lines[idx + 1:]:
        if not nxt.strip():
            continue
        if _ANY_LABEL.match(nxt):
            return False
        return True
    return False


# Below this measured corpus presence, a section cannot be an ERROR on an already-issued GR:
# enforcing it would flag the majority of genuine documents. See `verify(mode=...)`.
ISSUED_FLOOR = 0.5

# Sections common to every specimen form in the Manual — a memorandum, a circular and a
# notification all carry these. `data/gr_template.json` encodes Appendix 10.6, the RESOLUTION
# form, and only that one; the Manual gives 10.4 for memoranda, 10.5 for circulars and 10.7 for
# notifications, and those have their own section lists which we have not mined.
#
# So when the document is not a resolution, only the universal sections may raise an error.
# `प्रस्तावना` is the clearest case: a corrigendum has no preamble and is not defective for
# lacking one, but Appendix 10.6 marks it required and it was failing 46% of the corpus.
UNIVERSAL = {"subject", "govt", "department", "resolution_no", "address", "date", "resolution"}


def _unlabelled_subject(lines: list[str]) -> int | None:
    """The subject line when the draft carries no `विषय :-` label.

    Real GRs overwhelmingly do not use the label — the subject is simply the text sitting above
    `महाराष्ट्र शासन`, which is how `parser.py` has always read it. A label-anchored detector
    reported the subject missing on 388 of 400 corpus GRs while the mined profile puts it at 93%
    present, so the 97% failure was this pattern's fault and not the corpus's.

    A bare label with no content must NOT satisfy this, or a blank skeleton reads as filled.
    """
    for i, line in enumerate(lines):
        if not re.search(DETECT["govt"], line):
            continue
        for j in range(i - 1, -1, -1):
            cand = lines[j].strip()
            if not cand:
                continue
            if _ANY_LABEL.match(lines[j]) or len(cand) < 8:
                return None
            return j + 1
        return None
    return None


def verify(text: str, lang: str = "mr", mode: str = "draft") -> dict[str, Any]:
    """Check a document against the Manual's form. Deterministic, offline, no model.

    Two modes, because the same rules answer two different questions:

    * ``draft`` — the full Appendix 10.6 form. What SRS FR-10/11/12 require of a document we are
      about to produce, and the only mode the drafting page uses.
    * ``issued`` — for an already-issued GR read back through OCR. Sections the crawl provably
      cannot see are downgraded from error to advisory, with the measured rate attached.

    The downgrade is data-driven, not a fudge: `corpus_rate` in `data/gr_template.json` is mined
    from 1,500 real GRs, and a required section present in under half of them is one whose
    absence says more about the scan than about the document. The signature block (30.4%) and
    "By order and in the name of the Governor" (2.2%) are IMAGES in the original PDFs, so OCR
    never emits them — CLAUDE.md records that GRs with complete text extraction score the same
    as those with empty trailing pages. Enforcing them on issued GRs would fail 97% of a valid
    corpus, which is a broken measurement rather than a finding.
    """
    lines = text.splitlines()
    financial = has_financial_sanction(text)
    doc_type, appendix = detect_doc_type(text)
    issued = mode == "issued"
    findings: list[Finding] = []
    present: dict[str, bool] = {}
    relaxed: list[str] = []

    for sec in _sections():
        sid = sec["id"]
        pat = DETECT.get(sid)
        hit_line = None
        if pat:
            for i, line in enumerate(lines, 1):
                if not re.search(pat, line, re.M):
                    continue
                # A label with nothing under it is not a filled section.
                if sid in LABELLED and not _section_has_content(lines, i - 1):
                    continue
                hit_line = i
                break
        if hit_line is None and sid == "subject":
            hit_line = _unlabelled_subject(lines)
        found = hit_line is not None
        present[sid] = found
        if found:
            continue

        # Absent. Is that a defect?
        conditional = sec.get("conditional_on") == "has_financial_sanction"
        if conditional and not financial:
            continue                                  # correctly absent
        if sec["required"] or (conditional and financial):
            severity = "error"
        else:
            severity = "advisory"
            if sid == "read":
                severity = "warning"

        why_relaxed = None
        if issued and severity == "error":
            if sec.get("corpus_rate", 1.0) < ISSUED_FLOOR:
                why_relaxed = "ocr"
            elif doc_type != "resolution" and sid not in UNIVERSAL:
                why_relaxed = "doc_type"
        if why_relaxed:
            severity = "advisory"
            relaxed.append(sid)

        findings.append(Finding(
            code=sec["code"],
            section=sid,
            label=sec["label"].get(lang, sec["label"]["en"]),
            severity=severity,
            message=(_missing_message(sec, lang, conditional and financial) if not why_relaxed
                     else _relaxed_message(sec, lang, why_relaxed, doc_type, appendix)),
            line=None,
            authority=sec.get("mop") or "Manual of Office Procedure, Appendix 10.6",
        ))

    findings.extend(_ordering_findings(text, lang))
    findings.extend(_budget_findings(text, lang, financial))

    errors = sum(f.severity == "error" for f in findings)
    return {
        "lang": lang,
        "mode": mode,
        "relaxed": relaxed,
        "doc_type": doc_type,
        "manual_appendix": appendix,
        "financial_sanction_detected": financial,
        "sections_present": present,
        "sections_required": [s["id"] for s in _sections() if s["required"]],
        "findings": [asdict(f) for f in findings],
        "counts": {
            "error": errors,
            "warning": sum(f.severity == "warning" for f in findings),
            "advisory": sum(f.severity == "advisory" for f in findings),
        },
        "compliant": errors == 0,
    }


def _missing_message(sec: dict, lang: str, because_financial: bool) -> str:
    label = sec["label"].get(lang, sec["label"]["en"])
    if because_financial:
        return (f"'{label}' is missing. This draft sanctions expenditure, which makes the "
                f"section mandatory (SRS FR-11; Manual 9.5(6)).")
    if sec["required"]:
        return f"'{label}' is missing. The Manual's Appendix 10.6 form requires it."
    return f"'{label}' is absent. Present in {sec['corpus_rate']:.0%} of real GRs."


def _relaxed_message(sec: dict, lang: str, why: str, doc_type: str, appendix: str) -> str:
    label = sec["label"].get(lang, sec["label"]["en"])
    if why == "doc_type":
        return (f"'{label}' is absent. This document is a {doc_type}, which the Manual gives its "
                f"own form for ({appendix}); the section list enforced here is Appendix 10.6, the "
                f"Resolution form. Not treated as a defect.")
    return (f"'{label}' is not present in the extracted text. The Manual requires it on a draft, "
            f"but it appears in only {sec['corpus_rate']:.1%} of real GRs because it is an image "
            f"in the signed PDF that OCR cannot read — so its absence here is not treated as a "
            f"defect in this already-issued document.")


def _ordering_findings(text: str, lang: str) -> list[Finding]:
    """The Manual fixes an order. FR-11 names Background -> Reference -> Resolution."""
    out: list[Finding] = []
    lines = text.splitlines()
    pos: dict[str, int] = {}
    for sid in ("read", "preamble", "resolution", "governor_order", "signature"):
        pat = DETECT.get(sid)
        for i, line in enumerate(lines, 1):
            if pat and re.search(pat, line, re.M):
                pos[sid] = i
                break

    def check(a: str, b: str, msg: str, code: str) -> None:
        if a in pos and b in pos and pos[a] > pos[b]:
            out.append(Finding(code, b, b, "error", msg, pos[b],
                               "Manual of Office Procedure, Appendix 10.6 (section order)"))

    check("preamble", "resolution",
          "The Resolution appears before the Preamble. FR-11 fixes the order "
          "Background -> Reference -> Resolution.", "T20")
    check("read", "preamble",
          "The Preamble appears before the 'Read' block. References are cited first.", "T21")
    # Correct order is the Governor's order line FIRST, then the signature. check(a, b) fires
    # when a sits after b, so this must be ("governor_order", "signature") — the other way
    # round flags every correctly-ordered draft.
    check("governor_order", "signature",
          "The signature appears before 'By order and in the name of the Governor'. "
          "The Manual's form puts the Governor's order line above the signature.", "T22")
    return out


def _budget_findings(text: str, lang: str, financial: bool) -> list[Finding]:
    if not financial:
        return []
    heads = find_budget_heads(text)
    if heads:
        return []
    if not re.search(DETECT["expenditure"], text):
        return []
    return [Finding(
        "T30", "expenditure", "Budget head", "warning",
        "This draft sanctions expenditure and names an account head, but no budget head in "
        "the form 2054-00-101-02 was found (SRS FR-11).",
        None, "SRS FR-11",
    )]


def render_skeleton(lang: str = "mr", values: dict[str, str] | None = None) -> str:
    """Blank (or partially filled) template — what the preview starts from."""
    values = values or {}
    out = []
    for line in TEMPLATE["skeleton"][lang]:
        def sub(m: re.Match) -> str:
            return values.get(m.group(1), "")
        out.append(re.sub(r"\{(\w+)\}", sub, line))
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    lang = sys.argv[2] if len(sys.argv) > 2 else "mr"
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        body = Path(sys.argv[1]).read_text()
    else:
        body = sys.stdin.read()
    print(json.dumps(verify(body, lang), ensure_ascii=False, indent=2))
