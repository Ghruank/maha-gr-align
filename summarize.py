#!/usr/bin/env python3
"""
Plain-English summary of an uploaded Government Resolution.

This is a **real generative task** and the only one in the project where the model is producing
content rather than explaining a computed finding. A GR is several pages of formal Marathi and
an officer from another department wants to know, in four sentences, what it does. Nothing can
compute that. So the model writes it — and the guard rails move accordingly.

## What is still not generated

The skeleton is handed over, not invented. Department, date, resolution number, subject line and
every monetary figure are extracted deterministically and given to the model as FACTS. It is
writing prose around a frame it did not build, which is the same division of labour as
`drafting.py`: the model fills, the code lays out.

## The gate, and why it is narrower than elsewhere

`refreview.py` discards any sentence containing a digit it was not given. That is right there,
because those outputs are *about* identifiers. A summary is different: its whole value is
telling you the resolution sanctions fifteen crore, and a rule that strips figures would strip
the point.

So the gate is targeted at what is actually dangerous in a summary:

* **A money figure that is not in the source.** Whitelisted from `conflicts.amounts()`, including
  the crore/lakh reading of each — `१५,००,००,०००` legitimately becomes "15 crore", so both the
  full figure and 15 are allowed.
* **An 18-digit uid**, which a summary has no business containing at all.
* **A four-digit year that is not in the source.**

Small numbers — clause counts, "two institutions" — pass. A sentence that breaks the rule is
discarded whole and counted, never repaired: a wrong rupee figure in a summary of a sanction
order is the single most damaging thing this page could print.

## Marathi in, English out

`CLAUDE.md` records that Qwen3.5-2B mistranslates legal Marathi — `सदर मान्यता` came out as
"the prevailing belief" against a correct "the said approval". That is a real limit and it is
why translation proper goes through IndicTrans2 elsewhere in this project. A *summary* is more
forgiving than a translation because it is not asked to be faithful clause by clause, but the
limit has not gone away, and the UI says the summary is a reading aid rather than a translation.
"""

from __future__ import annotations

import re
from typing import Any

import conflicts as _conflicts
from ai import local

UID = re.compile(r"\b\d{18}\b")
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SENT = re.compile(r"(?<=[.!?])\s+")

# Enough of the document to summarise without overflowing a 2B model's useful attention. The
# operative part of a GR is at the top; tables and distribution lists at the bottom add tokens
# and no meaning.
MAX_CHARS = 6000

SYSTEM = (
    "You summarise Government Resolutions of the Government of Maharashtra for officers who do "
    "not read Marathi. You are given the document and a set of FACTS extracted from it. "
    "Write only what the document says. Never state a rupee figure, a year or a resolution "
    "number that is not in the facts or the document — a sentence containing one will be "
    "deleted before the officer sees it. If the document does not say something, omit it "
    "rather than guessing. Plain administrative English, no headings, no bullet lists."
)


def _facts(text: str, header: dict[str, Any]) -> tuple[str, set[str]]:
    """The deterministic frame, and the numbers the model is permitted to use."""
    money = _conflicts.amounts(text)
    allowed: set[str] = {""}
    for a in money:
        v = a["value"]
        allowed.add(str(v))
        for scale in (10**7, 10**5, 10**3):
            if v >= scale:
                allowed.add(f"{v / scale:g}")
                allowed.add(f"{v / scale:.2f}")
        allowed.add(str(v)[:2])
    for y in re.findall(r"\b(19|20)\d{2}\b", text.translate(_conflicts.DEV_DIGITS)):
        allowed.add(y)
    allowed |= {m.group(0) for m in _NUM.finditer(
        text.translate(_conflicts.DEV_DIGITS))}

    lines = [
        f"DEPARTMENT: {header.get('department') or 'not stated'}",
        f"DATE: {header.get('date') or 'not stated'}",
        f"RESOLUTION NUMBER: {header.get('decision_no') or 'not stated'}",
    ]
    if money:
        lines.append("AMOUNTS STATED IN THIS DOCUMENT: "
                     + "; ".join(_conflicts._fmt(a["value"]) for a in money[:6]))
    else:
        lines.append("AMOUNTS: this document states no monetary figure.")
    if header.get("citations"):
        lines.append(f"IT CITES {header['citations']} earlier order(s).")
    return "\n".join(lines), allowed


def _norm(tok: str) -> str:
    t = tok.replace(",", "").rstrip(".")
    return t


def _scrub(text: str, allowed: set[str]) -> tuple[str, int]:
    """Drop sentences carrying a figure the document does not contain."""
    kept, dropped = [], 0
    for s in _SENT.split(text.strip()):
        if not s.strip():
            continue
        if UID.search(s):
            dropped += 1
            continue
        bad = False
        for m in _NUM.finditer(s):
            raw = _norm(m.group(0))
            digits = raw.replace(".", "")
            # Small numbers are clause counts and the like; they carry no risk.
            if len(digits) < 4 and not re.search(
                    r"(?:crore|lakh|rs\.?|rupee)", s[max(0, m.start() - 14):m.end() + 14], re.I):
                continue
            if raw not in allowed and raw.rstrip("0").rstrip(".") not in allowed:
                bad = True
                break
        if bad:
            dropped += 1
            continue
        kept.append(s.strip())
    return " ".join(kept), dropped


def summarize(text: str, header: dict[str, Any], sentences: int = 4) -> dict[str, Any]:
    """English summary of a GR. Never raises — the model being down is a displayable state."""
    body = text.strip()
    truncated = len(body) > MAX_CHARS
    facts, allowed = _facts(body, header)

    prompt = (
        f"FACTS EXTRACTED FROM THIS DOCUMENT:\n{facts}\n\n"
        f"THE DOCUMENT:\n{body[:MAX_CHARS]}\n\n"
        f"Write {sentences} sentences of plain English telling an officer what this Government "
        f"Resolution does: what is being sanctioned or directed, who it applies to, any amount "
        f"of money, and what earlier orders it rests on. Use only figures that appear above.")

    try:
        out, stats = local.generate(prompt, system=SYSTEM, max_tokens=330, temperature=0.0)
    except local.LocalAIUnavailable as exc:
        return {"available": False, "summary": None, "degraded": True, "local": False,
                "dropped": 0, "stats": {}, "truncated": truncated,
                "note": f"The on-premise model is not reachable, so no summary was written: "
                        f"{exc}"}

    out = re.sub(r"^\s*(#+|\*+|\-|\d+\.)\s*", "", out.strip(), flags=re.M)
    out, dropped = _scrub(out, allowed)
    if len(out) < 60:
        return {"available": False, "summary": None, "degraded": True, "local": True,
                "dropped": dropped, "stats": stats, "truncated": truncated,
                "note": "The model's summary did not survive the figure check and has been "
                        "withheld. A summary with a wrong rupee figure is worse than none."}

    return {
        "available": True, "summary": out, "degraded": False, "local": True,
        "dropped": dropped, "stats": stats, "truncated": truncated,
        "note": ("Written by the on-premise model from the document text. A reading aid, not a "
                 "translation — the Marathi remains the legally operative text. Figures are "
                 "checked against the document and a sentence quoting any other number is "
                 "discarded."
                 + (f" {dropped} sentence(s) were discarded." if dropped else "")
                 + (" Only the first 6,000 characters were read." if truncated else "")),
    }
