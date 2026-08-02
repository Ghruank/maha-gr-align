#!/usr/bin/env python3
"""
Cross-document contradiction detection — the problem statement's first bullet, sharpened.

`references.py` answers *does the order this GR cites still stand?* This module answers a
different and harder question: **does this GR agree with the order it cites?** A citation can
resolve perfectly, point at an order in force, and still restate its contents wrongly.

The case it is built for is the one that actually costs money:

    Finance sanctions Rs. 15,00,00,000 for an institution.
    Higher Education, citing that very order, writes "Rs. 10,00,00,000 was sanctioned"
    and releases instalments against the smaller figure.

Both documents are impeccably drafted. Both pass the template check. The citation resolves and
the cited order is in force, so the alignment verdict is clean. Nothing in either document, read
alone, is wrong — the defect exists only in the relationship between them, and no official
holding one of the two can see it.

## Why this is deterministic and not a similarity score

SRS FR-4/5/6 reach for this with embeddings, and semantic similarity is the right tool for
*prose* conflicts. A restated figure is not a prose conflict: it is an integer, quoted from a
named source, that either matches or does not. Computing it settles the question; scoring it
would only estimate an answer we can have exactly. CLAUDE.md rule 4 — facts we can compute are
never generated — applies with full force, so there is no model call in this file.

## What is required before anything is reported

Three things must all hold, and the middle one is what keeps this from being noise:

1. A sentence in the citing document states a monetary amount.
2. **That sentence attributes the amount to a specific cited order** — by reference ordinal
   ("संदर्भ क्रमांक १ येथील"), or by naming the cited order's own file number. An amount merely
   *near* a citation is not an attribution, and treating it as one would flag every GR that
   cites an order and separately sanctions money.
3. The cited order's text is available to us, and states amounts of its own.

If the cited document states no amount at all we say nothing: silence there is our ignorance,
not the drafter's error.
"""

from __future__ import annotations

import re
from typing import Any, Callable

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# `रु. १५,००,००,०००` / `रुपये 15,00,00,000` / `₹ 15.00 कोटी` / `Rs. 15 crore`.
# Requires a DIGIT to open the figure, which is what stops the spelled-out restatement
# `(रुपये पंधरा कोटी फक्त)` from being counted a second time alongside the numeral it glosses.
AMOUNT = re.compile(
    r"(?:रु\.?|रुपये|₹|Rs\.?|INR)\s*([०-९\d][०-९\d,\.]*)\s*"
    r"(कोटी|लाख|हजार|crores?|lakhs?|thousand)?", re.I)

MULT = {"कोटी": 10**7, "crore": 10**7, "crores": 10**7,
        "लाख": 10**5, "lakh": 10**5, "lakhs": 10**5,
        "हजार": 10**3, "thousand": 10**3}

# "संदर्भ क्रमांक १ येथील" — an attribution to the Nth item of this document's own Read block.
REF_ORDINAL = re.compile(r"(?:संदर्भ|वाचा)\s*(?:क्रमांक|क्र)\s*[.:ः]?\s*([०-९\d]{1,2})"
                         r"|reference\s*(?:no\.?|number)?\s*([0-9]{1,2})", re.I)

# How far back from a figure to look for the attribution that governs it.
#
# NOT a sentence split. The obvious `(?<=[।.])\s+` breaks on `रु.` — the abbreviation for rupees
# ends in a period, so the marker `संदर्भ क्रमांक १ येथील` and the figure it introduces land in
# different fragments and nothing is ever compared. A backward window also matches how these
# documents are written: the attribution always precedes the figure.
LOOKBACK = 320
PARA = re.compile(r"\n\s*\n")

# A figure introduced by one of these is a PORTION of the attributed amount, not a restatement
# of it. `... मंजूर झालेल्या रु. १०,००,००,००० इतक्या निधीपैकी पहिला हप्ता म्हणून रु. ५,००,००,०००`
# releases five crore out of ten; the five is not a claim about what the cited order sanctioned,
# and comparing it against that order's total is a false contradiction. Checked in the span
# immediately before the figure, which is where the partitive always sits.
# Kept deliberately short. `भागा` was here and had to go: it matches inside `विभागाच्या`
# ("of the department"), so any sentence naming a department suppressed the finding entirely —
# a false NEGATIVE, and the worst kind, because a check that silently declines looks identical
# to a check that passed. `अंशत:` went too: it means "partially" as in a partial amendment, not
# a part-payment. Only unambiguous part-release markers remain.
PARTITIVE = re.compile(r"पैकी|हप्त|टप्प|out\s+of|instal?ment|tranche|part\s+of", re.I)
PARTITIVE_SPAN = 90


def amounts(text: str) -> list[dict[str, Any]]:
    """Every monetary figure in `text`, normalised to rupees."""
    out: list[dict[str, Any]] = []
    for m in AMOUNT.finditer(text):
        raw_num = m.group(1).translate(DEV_DIGITS).replace(",", "").rstrip(".")
        if not raw_num or not raw_num.replace(".", "").isdigit():
            continue
        try:
            val = float(raw_num)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        val *= MULT.get(unit, 1)
        out.append({"raw": " ".join(m.group(0).split()), "value": int(val),
                    "start": m.start()})
    return out


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _context(text: str, at: int) -> str:
    """The text governing a figure: back to the start of its paragraph, at most LOOKBACK chars.

    Bounded by the paragraph so an attribution in one paragraph cannot be read as governing a
    figure in the next — which is the difference between a finding and a coincidence.
    """
    lo = max(0, at - LOOKBACK)
    window = text[lo:at + 80]
    breaks = list(PARA.finditer(text[lo:at]))
    if breaks:
        window = text[lo + breaks[-1].end():at + 80]
    return window


def _fmt(v: int) -> str:
    """Indian grouping, then a crore/lakh gloss — officials read the gloss, not the digits."""
    s = str(v)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
        s = f"{head},{tail}"
    if v >= 10**7:
        return f"Rs. {s} ({v / 10**7:.2f} crore)"
    if v >= 10**5:
        return f"Rs. {s} ({v / 10**5:.2f} lakh)"
    return f"Rs. {s}"


def check(text: str, ref_report: dict[str, Any],
          text_of: Callable[[str], str | None]) -> dict[str, Any]:
    """Contradictions between this document and the orders it cites. No model is consulted."""
    citations = [c for c in ref_report.get("citations", []) if c.get("match")]
    if not citations:
        return {"available": True, "conflicts": [], "checked": 0,
                "note": "No citation resolved to an archived order, so there was nothing to "
                        "compare this document against."}

    # Cited-order amounts are fetched once per target, not per sentence.
    target_amounts: dict[str, list[dict]] = {}
    for c in citations:
        uid = c["match"]["uid"]
        if uid in target_amounts:
            continue
        body = text_of(uid)
        target_amounts[uid] = amounts(body) if body else []

    by_ordinal = {c["n"]: c for c in citations}
    conflicts: list[dict[str, Any]] = []
    checked = 0

    seen: set[tuple] = set()
    for a in amounts(text):
        context = _context(text, a["start"])
        target = _attributed_to(context, by_ordinal, citations)
        if not target:
            continue
        uid = target["match"]["uid"]
        theirs = target_amounts.get(uid) or []
        if not theirs:
            continue                    # we cannot read the cited order; say nothing

        checked += 1
        their_values = {x["value"] for x in theirs}
        if a["value"] in their_values:
            continue
        # Measured on the raw text immediately BEFORE the figure. Not on `context`, which runs
        # 80 characters past it — taking the tail of that window looks at the wrong side of the
        # number and the rule silently never fires.
        if PARTITIVE.search(text[max(0, a["start"] - PARTITIVE_SPAN):a["start"]]):
            continue                    # a part-release, not a restatement
        # The same figure is routinely restated in the preamble and again in the operative
        # paragraph. One discrepancy, one finding.
        fp = (target["n"], a["value"])
        if fp in seen:
            continue
        seen.add(fp)
        nearest = min(theirs, key=lambda x: abs(x["value"] - a["value"]))
        conflicts.append({
            "code": "X01",
            "kind": "amount_mismatch",
            "severity": "error",
            "citation": target["n"],
            "line": _line_of(text, a["start"]),
            "sentence": " ".join(context.split())[-320:],
            "claimed": {"raw": a["raw"], "value": a["value"], "display": _fmt(a["value"])},
            "actual": {"raw": nearest["raw"], "value": nearest["value"],
                       "display": _fmt(nearest["value"])},
            "all_actual": [{"value": x["value"], "display": _fmt(x["value"])}
                           for x in theirs[:6]],
            "delta": a["value"] - nearest["value"],
            "delta_display": _fmt(abs(a["value"] - nearest["value"])),
            "target": target["match"],
            "cross_dept": bool(target.get("cross_dept")),
            "message": _message(target, a, nearest),
            "authority": "Computed by comparing the figure this document attributes to the "
                         "cited order against the figure that order actually states.",
        })

    return {
        "available": True,
        "conflicts": conflicts,
        "checked": checked,
        "note": ("Only amounts this document explicitly attributes to a cited order are "
                 "compared. A figure that merely sits near a citation is not an attribution."),
    }


def _attributed_to(sentence: str, by_ordinal: dict[int, dict],
                   citations: list[dict]) -> dict | None:
    """Which cited order, if any, this sentence credits its figure to.

    Deliberately strict. Returning a target on weak evidence would turn every GR that both cites
    an order and sanctions money into a false contradiction.
    """
    m = REF_ORDINAL.search(sentence)
    if m:
        raw = (m.group(1) or m.group(2) or "").translate(DEV_DIGITS)
        if raw.isdigit() and int(raw) in by_ordinal:
            return by_ordinal[int(raw)]

    # Or the cited order's own file number appears in this very sentence.
    from resolver import digit_key
    for c in citations:
        key = digit_key(c.get("cited_no"))
        if key and key == digit_key(sentence):
            return c
        if c.get("cited_no") and c["cited_no"] in sentence:
            return c
    return None


def _message(target: dict, claimed: dict, actual: dict) -> str:
    m = target["match"]
    where = f"{m['uid']} ({m['dept']}, {m['date']})"
    direction = "more than" if claimed["value"] > actual["value"] else "less than"
    gap = abs(claimed["value"] - actual["value"])
    return (f"This document attributes {_fmt(claimed['value'])} to the order it cites at "
            f"[{target['n']}], but {where} states {_fmt(actual['value'])} — "
            f"{_fmt(gap)} {direction} the figure sanctioned. One of the two is wrong, and "
            f"releasing funds against the smaller figure would under-pay by that amount.")
