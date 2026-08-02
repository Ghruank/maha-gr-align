#!/usr/bin/env python3
"""
Plain-language review of whether a GR still aligns with the orders it cites.

## The line this file walks

CLAUDE.md rule 4: *the model proposes, the corpus verifies.* Facts we can compute are never
generated. So the model here is **not** asked "is this GR aligned with its citations?" — that
question is already answered, deterministically, by `references.check`, off graph edges that
carry the sentence which produced them.

What the model is asked for is the paragraph an officer would otherwise have to assemble in
their head: given these computed findings, what does a desk officer do about them, and in what
order. Explanation, not adjudication.

Two structural consequences, both enforced in code below rather than asked for in the prompt:

1. **The model is given the findings, never the raw citations.** It cannot reach a different
   verdict from ours because it is never shown the evidence a verdict would rest on — only the
   verdicts themselves. A model that "decides" a citation resolved is a model that can
   hallucinate a citation, which rule 3 forbids outright.
2. **It is never shown an order number, and may not write one.** See below.

## The identifier rule, and why it is this blunt `[MEASURED 2026-08-02]`

The first version of this file handed the model the findings verbatim — file numbers and all —
and whitelisted the 18-digit uids it was allowed to repeat. Qwen3.5-2B promptly produced:

    ... citation number मइवाधो-२०ॲ३५/प्र.क्र.२५/तां.क्र.४ (2021) at line 11 ...

Two fabrications in one clause. `२०ॲ३५` is not a number in any script — the model corrupted a
Devanagari file number it had been shown — and line 11 holds nothing of the sort. The uid
whitelist caught neither, because neither is a uid. It also invented lines 43 and 45 in an
eight-citation document, and advised the officer to "issue a formal notice of supersession",
which is not a thing.

So the rule is now mechanical and severe, in two halves:

* **The prompt contains no order numbers, no dates and no line numbers.** Citations are
  identified to the model only as `[1]`, `[2]`. It cannot corrupt an identifier it never saw.
* **Any sentence containing a digit outside `[n]` is discarded whole**, along with anything
  containing `/`. Not repaired — discarded. A mangled identifier reads exactly as authoritative
  as a correct one and no officer can tell them apart, so the only safe move is to drop the
  sentence and say how many were dropped.

The deterministic summary is computed regardless and returned alongside as `computed`, so the UI
can always show something true. If the model is unavailable that summary IS the review, flagged
`degraded`. "Ollama is not running" is a legitimate thing to display. A fabricated citation is
not.
"""

from __future__ import annotations

import re
from typing import Any

from ai import local

UID = re.compile(r"\b\d{18}\b")

SYSTEM = (
    "You advise desk officers in the Government of Maharashtra on Government Resolutions. "
    "You are given the RESULT of an automated citation check already performed against the "
    "official archive. Explain what those results mean for the officer and what to do about "
    "them. You never dispute the check and never claim on your own authority that a reference "
    "does or does not exist.\n"
    "ABSOLUTE RULE: refer to a citation ONLY by its bracketed number, exactly as [1] or [2]. "
    "Never write an order number, a file number, a date, a year or a line number. Any sentence "
    "containing a digit outside the brackets will be deleted before the officer sees it.\n"
    "Write plain administrative prose. No preamble, no headings, no bullet lists."
)

# Severity is decided by `references.py`; restating it here would let the two drift.
# Worded so the model cannot paraphrase a coverage limit into a missing reference. Observed:
# handed "is a court order, which the GR archive does not hold", Qwen3.5-2B wrote "citation [2]
# is absent from the archive" — collapsing the exact distinction this system exists to keep.
# Only ONE gloss below contains the word "missing", and it is the only one that means it.
_VERDICT_GLOSS = {
    "verified": "CONFIRMED present in the archive",
    "not_in_archive": "MISSING: it should be in the archive and is not — a defect to fix",
    "ambiguous": "matched more than one archived order, so no match was asserted",
    "unverifiable": "NOT CHECKED because the citation gives no usable file number — this is "
                    "about how the citation was written, it is not a missing document",
    "other_dept": "NOT CHECKED because it belongs to a department outside this archive — "
                  "the document is fine, our coverage is limited",
    "outside_range": "NOT CHECKED because it predates the archive — the document is fine, "
                     "our coverage is limited",
    "out_of_scope": "NOT CHECKED because it is a court order, Act or letter, which a GR "
                    "archive never contains — the document is fine, this is normal and "
                    "expected, and it is NOT a missing reference",
}


def _facts(report: dict[str, Any]) -> str:
    """The findings, flattened for the prompt — with every identifier stripped out.

    No file numbers, no dates, no uids, no line numbers. The model gets the shape of the problem
    and nothing it could corrupt into a plausible-looking citation.
    """
    lines: list[str] = []
    doc = report.get("document", {})
    lines.append(f"DOCUMENT: a Government Resolution of the "
                 f"{doc.get('department') or 'issuing'} Department.")

    # The verdict is HANDED to the model, never left for it to infer. Given only the findings,
    # Qwen3.5-2B concluded "the resolution remains valid because the cited references are either
    # unverified or superseded" — on a document whose citations had in fact been superseded.
    # Stating the conclusion up front is what turns the task from judgement into phrasing.
    al = report.get("alignment", {})
    if al:
        lines.append(f"\nESTABLISHED CONCLUSION, which you must accept and explain, never "
                     f"contradict: this document is {al['label']['en'].upper()}.")
        for r in al.get("reasons", []):
            lines.append(f"  - {r}")

    lines.append("\nCITATIONS, each with the result of the archive check:")
    for c in report.get("citations", []):
        bits = [f"[{c['n']}] a {c['kind_label']['en'].lower()}",
                _VERDICT_GLOSS.get(c["verdict"], c["verdict"])]
        m, st = c.get("match"), c.get("status")
        if m:
            bits.append(f"issued by the {m['dept']} Department")
            if c.get("cross_dept"):
                bits.append("which is NOT this document's own department")
            if st and not st["in_force"]:
                bits.append("and it HAS SINCE BEEN SUPERSEDED by a later order")
            elif st and st["amended_by"]:
                bits.append("still in force but AMENDED by a later order")
            else:
                bits.append("still in force")
        lines.append("  " + "; ".join(bits) + ".")

    sev = {"error": [], "warning": [], "advisory": []}
    for f in report.get("findings", []):
        n = f.get("citation")
        sev[f["severity"]].append(f"[{n}]" if n else "the document as a whole")
    if sev["error"]:
        lines.append(f"\nMUST BE FIXED BEFORE ISSUE: {', '.join(sev['error'])}.")
    if sev["warning"]:
        lines.append(f"SHOULD BE LOOKED AT: {', '.join(sev['warning'])}.")
    if sev["advisory"]:
        lines.append(f"NOT JUDGED, outside what the archive holds: "
                     f"{', '.join(sev['advisory'])}.")
    return "\n".join(lines)


# A sentence may carry digits only inside a citation marker. Anything else — a year, a file
# number, a line number — is the model reaching for an identifier it was not given.
_MARKER = re.compile(r"\[\s*\d{1,3}\s*\]")
_DIGIT = re.compile(r"[0-9०-९]")
_SENTENCE = re.compile(r"(?<=[.!?।])\s+")


def _scrub(text: str, n_citations: int) -> tuple[str, int]:
    """Drop whole sentences that reach for an identifier. Returns (text, sentences dropped).

    Discarding rather than repairing is deliberate: a corrupted file number reads exactly as
    authoritative as a correct one, so half-fixing it is worse than losing the sentence.
    """
    kept, dropped = [], 0
    for s in _SENTENCE.split(text.strip()):
        if not s.strip():
            continue
        bare = _MARKER.sub("", s)
        if _DIGIT.search(bare) or "/" in bare:
            dropped += 1
            continue
        # A marker pointing past the end of the citation list is equally invented.
        if any(int(m.strip("[] ")) > n_citations or int(m.strip("[] ")) < 1
               for m in _MARKER.findall(s)):
            dropped += 1
            continue
        kept.append(s.strip())
    return " ".join(kept), dropped


def _deterministic(report: dict[str, Any]) -> str:
    """The review we can always give, with no model at all. Also the fallback when it is down."""
    s = report.get("summary", {})
    al = report.get("alignment", {})
    if not s.get("citations"):
        return ("This document cites no orders that the checker could identify. If it rests on "
                "an earlier resolution, name it in the 'वाचा' / 'Read' block.")
    parts = [f"{al.get('label', {}).get('en', 'Checked')}."]
    parts.extend(al.get("reasons", []))
    if s.get("out_of_scope"):
        parts.append(f"{s['out_of_scope']} citation(s) fall outside what the archive holds and "
                     f"were not judged.")
    return " ".join(parts)


def review(report: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    """Narrative review of a `references.check` result. Never raises on model failure."""
    base = _deterministic(report)
    n = len(report.get("citations", []))
    if not report.get("available"):
        return {"review": base, "computed": base, "degraded": True, "local": False,
                "note": "The reference archive is not loaded.", "stats": {}, "dropped": 0}

    want = "Marathi (Devanagari)" if lang == "mr" else "English"
    verdict = report.get("alignment", {}).get("label", {}).get("en", "")
    prompt = (
        f"{_facts(report)}\n\n"
        f"Write exactly three sentences in {want} for the officer handling this file. "
        f"First: restate the established conclusion — the document is {verdict.lower()} — and "
        f"why. "
        f"Second: which citations need action and what action. "
        f"Third: which were NOT CHECKED and why that is a limit of the archive, not a defect "
        f"in the document. Never describe a NOT CHECKED citation as missing or absent. "
        f"Refer to citations only as [1], [2]. Write no numbers of any other kind.")

    try:
        # 260 tokens is roughly 26 s on this box at the measured 10 tok/s. Three sentences is
        # also the length at which a 2B model stops padding and starts inventing.
        text, stats = local.generate(prompt, system=SYSTEM, max_tokens=260, temperature=0.0)
    except local.LocalAIUnavailable as exc:
        return {"review": base, "computed": base, "degraded": True, "local": False,
                "note": f"The local model did not contribute: {exc}",
                "stats": {}, "dropped": 0}

    text = re.sub(r"^\s*(#+|\*+|\-)\s*", "", text.strip(), flags=re.M)
    text, dropped = _scrub(text, n)
    if len(text) < 40:
        return {"review": base, "computed": base, "degraded": True, "local": True,
                "note": ("The local model returned nothing that survived the identifier check, "
                         "so the computed summary is shown instead."),
                "stats": stats, "dropped": dropped}

    return {
        "review": text,
        "computed": base,
        "degraded": False,
        "local": True,
        "dropped": dropped,
        "note": ("Written by the on-premise model from the results of the deterministic check. "
                 "It explains the findings; it does not produce them, and it is not shown any "
                 "order number it could misquote."
                 + (f" {dropped} sentence(s) were discarded for containing an identifier the "
                    f"model was not given." if dropped else "")),
        "stats": stats,
    }


# --------------------------------------------------------------------------------------
# Conflict explanation — the hover on a detected contradiction.
#
# Same discipline as `review` above and the same reason: the contradiction is COMPUTED by
# `conflicts.py` from two documents, and the model is only asked what it means for the officer.
# One difference — here the figures ARE the content, so they cannot be withheld from the prompt.
# They are whitelisted instead: any number in the output that is not one of the three we supplied
# is a number the model invented, and the sentence carrying it is discarded.
# --------------------------------------------------------------------------------------

CONFLICT_SYSTEM = (
    "You advise desk officers in the Government of Maharashtra. An automated check has compared "
    "a draft Government Resolution against the order it cites and found that the two state "
    "different amounts of money. Explain what this means and what the officer must do. "
    "You never dispute the check. Use ONLY the figures given to you — any sentence containing a "
    "figure that was not supplied will be deleted before the officer sees it. "
    "Two or three sentences of plain administrative prose. No headings, no lists."
)

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(s: str) -> set[str]:
    """Digit groups, comma- and decimal-insensitive, so 15,00,00,000 == 150000000."""
    return {m.group(0).replace(",", "").rstrip(".").rstrip("0").rstrip(".") or "0"
            for m in _NUM.finditer(s)}


def _scrub_numeric(text: str, allowed: set[str]) -> tuple[str, int]:
    """Drop sentences carrying a figure that was not supplied. Returns (text, dropped)."""
    kept, dropped = [], 0
    for s in _SENTENCE.split(text.strip()):
        if not s.strip():
            continue
        if _numbers_in(s) - allowed:
            dropped += 1
            continue
        kept.append(s.strip())
    return " ".join(kept), dropped


def explain_conflict(conflict: dict[str, Any], citing: dict[str, Any],
                     lang: str = "en") -> dict[str, Any]:
    """Plain-language note on one amount contradiction. Never raises on model failure."""
    base = conflict["message"]
    t = conflict["target"]
    claimed, actual = conflict["claimed"], conflict["actual"]
    allowed = (_numbers_in(claimed["display"]) | _numbers_in(actual["display"])
               | _numbers_in(conflict["delta_display"]) | {"", "0"})

    want = "Marathi (Devanagari)" if lang == "mr" else "English"
    prompt = (
        f"A draft Government Resolution of the {citing.get('dept') or 'issuing'} Department "
        f"cites an order of the {t.get('dept')} Department.\n"
        f"The draft says that order sanctioned {claimed['display']}.\n"
        f"That order actually states {actual['display']}.\n"
        f"The gap is {conflict['delta_display']}.\n"
        f"The draft is "
        f"{'understating' if conflict['delta'] < 0 else 'overstating'} the sanction.\n\n"
        f"Write two or three sentences in {want}: what has gone wrong, which of the two "
        f"documents governs, and what the officer should do before this draft is issued. "
        f"Use only the three figures above.")

    try:
        text, stats = local.generate(prompt, system=CONFLICT_SYSTEM, max_tokens=240,
                                     temperature=0.0)
    except local.LocalAIUnavailable as exc:
        return {"explanation": base, "computed": base, "degraded": True, "local": False,
                "dropped": 0, "stats": {},
                "note": f"The local model did not contribute: {exc}"}

    text = re.sub(r"^\s*(#+|\*+|\-)\s*", "", text.strip(), flags=re.M)
    text, dropped = _scrub_numeric(text, allowed)
    if len(text) < 40:
        return {"explanation": base, "computed": base, "degraded": True, "local": True,
                "dropped": dropped, "stats": stats,
                "note": "The local model returned nothing that survived the figure check, so "
                        "the computed finding is shown instead."}
    return {
        "explanation": text, "computed": base, "degraded": False, "local": True,
        "dropped": dropped, "stats": stats,
        "note": ("Written by the on-premise model from the computed comparison. The figures are "
                 "the check's, not the model's — a sentence containing any other number is "
                 "discarded."
                 + (f" {dropped} sentence(s) were discarded." if dropped else "")),
    }
