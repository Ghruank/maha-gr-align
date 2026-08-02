#!/usr/bin/env python3
"""
Controlled bilingual terminology — SRS FR-7, FR-8, FR-9.

    FR-7  maintain a controlled Marathi-English legal glossary
    FR-8  flag any term that does not match the approved glossary
    FR-9  suggest the correct standard term when a mismatch is found

The list itself is `data/glossary.json`, seeded by `build_glossary.py` and meant to be edited by
hand. This module only reads it and applies it. No model is involved and none will be: whether a
document writes "Government Decision" where the Manual says "Government Resolution" is a fact a
string comparison settles.

## Why a term can be wrong at all, given the Marathi is authoritative

Every GR has one legally operative Marathi text and an English rendering derived from it. A legal
term is a handle for a defined thing, so if `शासन निर्णय` comes out as "Government Resolution"
in one document and "Government Decision" in the next, an officer searching the English for
everything affecting their file silently misses half of it. Nothing was mistranslated exactly;
the terminology simply was not held fixed.

Measured on 2,500 corpus documents: **"Government Decision" appears in 1,861 of them and
"Government Resolution" in 1,021** — and the Manual of Office Procedures uses "Government
Resolution" six times and "Government Decision" not once. The dominant rendering is the
non-standard one, which is exactly the condition FR-8 exists to detect and which no amount of
mining the corpus could have told us.

## Two gates that keep this from producing nonsense

**`approved`** — only entries with external authority (the Manual, or SRS FR-11) are enforced as
warnings. Everything else is one person's judgement, is reported as advisory, and says so.

**`strict`** — a replacement is SUGGESTED only where one can be justified from a single side of
the document. `रद्द` (cancelled), `अधिक्रमित` (superseded) and `व्यपगत` (lapsed) do different
things to an order, so seeing "cancelled" in an English GR is not evidence of a mis-rendering —
it may be a perfectly correct rendering of `रद्द`. Those entries report the ambiguity and
withhold the suggestion. FR-9 declining to guess is the requirement working, not failing.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
GLOSSARY = ROOT / "data" / "glossary.json"

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


@lru_cache(maxsize=256)
def phrase(term: str) -> re.Pattern:
    """Whole-phrase matcher for a Latin term.

    `\\b` is mandatory, and its absence was a real measurement bug while seeding: without it
    "Re" matched inside "Regarding", "Reference" and "Resolution" and scored 2,497 of 2,500
    documents; "Fund" matched inside "Funds"; "Memo" inside "Memorandum". Safe here because
    everything matched this way is Latin — CLAUDE.md's warning that `\\b` fails after Devanagari
    applies to the Marathi side, which is compared with a plain substring test instead.

    Interior whitespace is relaxed to `\\s+` so a line break inside "Government  Resolution"
    does not hide it.
    """
    return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in term.split()) + r"\b", re.I)


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    if not GLOSSARY.exists():
        return {"_source": {}, "terms": []}
    return json.loads(GLOSSARY.read_text(encoding="utf-8"))


def available() -> tuple[bool, str]:
    g = load()
    n = len(g["terms"])
    if not n:
        return False, "data/glossary.json is missing (run: python build_glossary.py)"
    ok = sum(t["approved"] for t in g["terms"])
    return True, f"{n} terms, {ok} approved"


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _first_line(lines: list[str], pat: re.Pattern) -> int | None:
    for i, line in enumerate(lines, 1):
        if pat.search(line):
            return i
    return None


def _mr_line(lines: list[str], needle: str) -> int | None:
    for i, line in enumerate(lines, 1):
        if needle in line:
            return i
    return None


def check(text: str, lang: str = "mr") -> dict[str, Any]:
    """FR-8 + FR-9 over one document.

    The two languages are asked different questions, because they are different objects:

    * **English** — the derived view, and the only side where a rendering can be *wrong*. Every
      non-approved variant found is reported, with the approved term where one can be justified.
    * **Marathi** — the authoritative source. There is nothing here to correct against an English
      glossary, so instead the terms present are listed with the English each one MUST take, which
      is what an officer preparing the English version actually needs. Non-standard Marathi
      spellings are flagged where the list records them.
    """
    g = load()
    if not g["terms"]:
        return {"available": False,
                "hint": "run: python build_glossary.py --out data/glossary.json"}

    lines = _lines(text)
    findings: list[dict[str, Any]] = []
    present: list[dict[str, Any]] = []

    for t in g["terms"]:
        approved_pat = phrase(t["en"])
        uses_approved = bool(approved_pat.search(text))
        mr_here = t["mr"] in text

        # --- FR-8, English side: a rendering that is not the approved one.
        for variant in t.get("variants_en", []):
            pat = phrase(variant)
            hits = pat.findall(text)
            if not hits:
                continue
            line = _first_line(lines, pat)
            findings.append({
                "code": "G01" if t["approved"] else "G02",
                "term_id": t["id"],
                "mr": t["mr"],
                "found": variant,
                "occurrences": len(hits),
                "line": line,
                "approved": t["en"],
                # FR-9. Withheld where the English alone cannot establish which Marathi term is
                # being rendered — see the module docstring.
                "suggestion": t["en"] if t["strict"] else None,
                "severity": "warning" if t["approved"] else "advisory",
                "authority": t["authority"],
                "note": t["note"],
                "also_uses_approved": uses_approved,
                "message": _message(t, variant, len(hits), uses_approved),
            })

        # --- FR-8, Marathi side: a non-standard spelling of the source term.
        for variant in t.get("variants_mr", []):
            if variant not in text:
                continue
            findings.append({
                "code": "G03",
                "term_id": t["id"], "mr": t["mr"], "found": variant,
                "occurrences": text.count(variant),
                "line": _mr_line(lines, variant),
                "approved": t["mr"],
                "suggestion": t["mr"],
                "severity": "advisory",
                "authority": t["authority"], "note": t["note"],
                "also_uses_approved": mr_here,
                "message": f"Spelled '{variant}'. The glossary's form of this term is "
                           f"'{t['mr']}'. Both occur in the corpus; only one should be used "
                           f"within a document.",
            })

        if mr_here or uses_approved:
            present.append({
                "id": t["id"], "mr": t["mr"], "en": t["en"],
                "approved": t["approved"], "authority": t["authority"],
                "in_marathi": mr_here, "in_english": uses_approved,
            })

    sev = {"warning": 0, "advisory": 0}
    for f in findings:
        sev[f["severity"]] += 1

    return {
        "available": True,
        "lang": lang,
        "script": "mr" if DEVANAGARI.search(text) else "en",
        "glossary": {
            "terms": len(g["terms"]),
            "approved": sum(t["approved"] for t in g["terms"]),
            "source": g["_source"],
        },
        "terms_present": sorted(present, key=lambda x: x["id"]),
        "findings": sorted(findings, key=lambda f: (f["severity"] != "warning",
                                                    -f["occurrences"])),
        "counts": {"warning": sev["warning"], "advisory": sev["advisory"],
                   "total": len(findings)},
        "clean": sev["warning"] == 0,
    }


def _message(t: dict, variant: str, n: int, also_approved: bool) -> str:
    times = "once" if n == 1 else f"{n} times"
    head = f"'{variant}' is used {times}."
    if not t["strict"]:
        return (f"{head} The glossary's term for {t['mr']} is '{t['en']}', but '{variant}' may "
                f"legitimately render a different Marathi term, so no replacement is proposed — "
                f"check the Marathi.")
    body = f" The approved term for {t['mr']} is '{t['en']}'."
    if also_approved:
        body += (" Both forms appear in this document, so the same thing is being called two "
                 "different names.")
    if not t["approved"]:
        body += " This entry is a proposal and has not been approved."
    return head + body


def suggest(term: str) -> dict[str, Any] | None:
    """FR-9 on its own: the approved rendering for a single term, in either direction."""
    for t in load()["terms"]:
        if phrase(t["en"]).fullmatch(term.strip()) or t["mr"] == term.strip():
            return t
        if any(phrase(v).fullmatch(term.strip()) for v in t.get("variants_en", [])):
            return t
    return None


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    lang = sys.argv[2] if len(sys.argv) > 2 else "mr"
    body = sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")
    print(json.dumps(check(body, lang), ensure_ascii=False, indent=2))
