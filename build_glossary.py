#!/usr/bin/env python3
"""
Seed the controlled bilingual glossary — SRS FR-7.

    python build_glossary.py --corpus data/mahGRs/GRs --out data/glossary.json

## What "controlled" means, and why this file is not a miner

`bilingual.py` builds a DESCRIPTIVE glossary: it mines the corpus and reports how terms are
actually translated. FR-7 asks for a NORMATIVE one — how a term MUST be translated — and no
amount of mining produces that, because the corpus is the thing being judged. A list derived
from the corpus could only ever say "the common rendering is correct", which is precisely the
question at issue: measured below, the commonest English rendering of `शासन निर्णय` is
"Government Decision", used in 68.4% of documents, and it is **not the Manual's term**.

So authority comes from outside the corpus:

* **`documents/mcs270623075036.pdf`** — the Maharashtra Manual of Office Procedures, 2023, which
  is in English and whose Appendix 10.6 is headed FORM OF GOVERNMENT RESOLUTION. Terms it uses
  are marked `approved: true` and cite it. It says "Government Resolution" six times and
  "Government Decision" zero times.
* **SRS FR-11**, for the two terms the Manual words differently from the requirement
  (`Budget Head`).
* **Everything else** is seeded from the corpus's dominant rendering and marked
  `approved: false` — a PROPOSAL for a human to accept or correct. Nothing unapproved is ever
  enforced. This is the same rule the rest of the project runs on: evidence proposes, a person
  decides, and only then is it normative.

## Two traps this table is built to avoid

**Different ranks are not variants of each other.** "Deputy Secretary" appears in 10.6% of the
corpus and "Under Secretary" in 6.2%, but these are distinct offices — suggesting one for the
other would corrupt a signature block. They get separate entries with separate Marathi.

**Different legal acts are not variants of each other.** `रद्द` (cancelled), `अधिक्रमित`
(superseded), `मागे घेणे` (withdrawn) and `व्यपगत` (lapsed) do different things to an order.
Flagging English "cancelled" and suggesting "superseded" would be wrong whenever the Marathi
said `रद्द`. Those entries are marked `strict: false`, which makes the checker report the
ambiguity instead of proposing a replacement it cannot justify from one side of the document.
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import re
from pathlib import Path

MANUAL = "Maharashtra Manual of Office Procedures, 2023"

# Imported, not redefined: the counts recorded as evidence and the findings raised at runtime
# must come from the same notion of "does this term occur in this document".
from glossary import phrase                                              # noqa: E402

# Non-standard MARATHI spellings of a source term. Only where both forms genuinely occur in the
# corpus — `template.py` already has to accept both of these.
MR_VARIANTS: dict[str, list[str]] = {
    "corrigendum": ["शुध्दीपत्रक"],
}

# (id, marathi, approved english, [wrong english renderings], authority, approved, strict, note)
SEED: list[tuple] = [
    # --- instrument types. The Manual names these directly in Appendices 10.4-10.7.
    ("resolution", "शासन निर्णय", "Government Resolution",
     ["Government Decision", "Government Order", "Govt. Resolution", "Government Ruling"],
     f"{MANUAL}, Appendix 10.6 (FORM OF GOVERNMENT RESOLUTION)", True, True,
     "The Manual uses 'Government Resolution' throughout and never 'Government Decision'."),
    ("circular", "शासन परिपत्रक", "Government Circular",
     ["Government Letter", "Govt Circular", "Circular Letter"],
     f"{MANUAL}, Appendix 10.5", True, True, ""),
    ("memorandum", "शासन ज्ञापन", "Government Memorandum",
     ["Government Memo", "Office Memo"],
     f"{MANUAL}, Appendix 10.4", True, True, ""),
    ("notification", "अधिसूचना", "Notification",
     ["Announcement", "Public Notice"],
     f"{MANUAL}, Appendix 10.7 (FORM OF GOVERNMENT NOTIFICATION)", True, True, ""),
    ("corrigendum", "शुद्धिपत्रक", "Corrigendum",
     ["Errata", "Erratum", "Purification Letter", "Correction Letter"],
     "Corpus dominant rendering; the Manual gives no form for a corrigendum", False, True,
     "Not in the Manual. 'Purification Letter' is a literal machine translation of "
     "शुद्धिपत्रक and is not English legal usage."),
    ("order", "शासन आदेश", "Government Order",
     ["Government Instruction", "State Order"],
     "Corpus dominant rendering", False, True, ""),

    # --- section headers of the Resolution form, verbatim from Appendix 10.6.
    ("subject", "विषय", "Subject", ["Topic", "Sub."],
     f"{MANUAL}, Appendix 10.6", True, True,
     "'Regarding' is deliberately NOT listed: it opens legitimate subject lines rather than "
     "standing in for the label."),
    ("read", "वाचा", "Read", ["Readable", "Perused"],
     f"{MANUAL}, Appendix 10.6 ('Read.-')", True, False,
     "'Reference' is NOT listed as a wrong rendering: it is the correct rendering of संदर्भ, "
     "which has its own entry, and the English alone cannot tell the two apart."),
    ("reference", "संदर्भ", "Reference", ["Contextual Note"],
     "Corpus dominant rendering", False, False,
     "'Regard' is NOT listed: 'in this regard' is ordinary English prose, not a rendering of "
     "the label."),
    ("preamble", "प्रस्तावना", "Preamble", ["Introduction", "Foreword", "Background"],
     f"{MANUAL}, FR-11 (Background -> Reference -> Resolution)", True, True, ""),
    ("govt", "महाराष्ट्र शासन", "Government of Maharashtra",
     ["Maharashtra Government", "Govt. of Maharashtra", "Maharashtra State Government"],
     f"{MANUAL}, Appendix 10.6 (GOVERNMENT OF MAHARASHTRA)", True, True,
     "The article is not listed as a variant: 'the Government of Maharashtra' is correct in "
     "running prose and wrong only in the masthead, which this check cannot tell apart."),
    ("mantralaya", "मंत्रालय", "Mantralaya", ["Ministry", "Secretariat", "Ministry Building"],
     f"{MANUAL}, Appendix 10.6", True, True,
     "A place name, not a common noun. 'Ministry' is a mistranslation."),
    ("governor_line", "राज्यपाल यांच्या आदेशानुसार व नावाने",
     "By order and in the name of the Governor of Maharashtra",
     ["By order of the Governor", "On behalf of the Governor",
      "As per the order and in the name of the Governor"],
     f"{MANUAL}, Appendix 10.6", True, True, ""),

    # --- offices. Distinct ranks; never suggested for one another.
    ("under_secy", "अवर सचिव", "Under Secretary", ["Sub Secretary", "Junior Secretary"],
     f"{MANUAL}, Appendix 10.6 (Under Secretary to the Government of Maharashtra)", True, True,
     "A distinct rank. Never interchangeable with Deputy or Principal Secretary."),
    ("deputy_secy", "उप सचिव", "Deputy Secretary", ["Vice Secretary", "Assistant Secretary"],
     MANUAL, True, True, "A distinct rank."),
    ("principal_secy", "प्रधान सचिव", "Principal Secretary", ["Main Secretary"],
     MANUAL, True, True,
     "'Chief Secretary' is deliberately NOT listed as a variant: it is a real and different "
     "office (मुख्य सचिव), so flagging it would be wrong far more often than right."),
    ("addl_chief_secy", "अपर मुख्य सचिव", "Additional Chief Secretary",
     ["Extra Chief Secretary"], MANUAL, True, True, ""),

    # --- money. FR-11 fixes 'Budget Head'; the Manual words the line differently.
    ("budget_head", "लेखाशीर्ष", "Budget Head",
     ["Account Head", "Accounting Head", "head of account", "Ledger Head"],
     "SRS FR-11 (budget head, e.g. 2054-00-101-02)", True, True,
     "The Manual's form says 'The expenditure should be debited to-'; FR-11 names the field "
     "'Budget Head'. The corpus overwhelmingly writes 'head of account'."),
    ("finance_concurrence", "वित्त विभागाची सहमती", "concurrence of the Finance Department",
     ["Finance Department consent", "approval of the Finance Department",
      "agreement of the Finance Department"],
     f"{MANUAL}, Appendix 10.6", True, True, ""),
    ("grant", "अनुदान", "Grant-in-aid", ["Donation", "Gratuity"],
     "Corpus dominant rendering", False, False,
     "'Allowance' is NOT listed: it is the correct rendering of भत्ता. 'Subsidy' is a distinct "
     "instrument. Non-strict, so no replacement is proposed."),
    ("funds", "निधी", "Funds", ["Monies"],
     "Corpus dominant rendering", False, False,
     "'Fund' singular is number agreement, not a terminology defect, and is not listed."),

    # --- the supersession vocabulary. Distinct legal acts: never suggested for one another.
    ("supersede", "अधिक्रमित", "Superseded", ["Overridden", "Overruled"],
     "Corpus dominant rendering", False, False,
     "Distinct from रद्द (cancelled) and मागे घेणे (withdrawn). Reported without a suggestion "
     "because the English alone cannot tell which Marathi term it renders."),
    ("cancel", "रद्द", "Cancelled", ["Nullified", "Annulled"],
     "Corpus dominant rendering", False, False,
     "Distinct from अधिक्रमित (superseded)."),
    ("withdraw", "मागे घेण्यात", "Withdrawn", ["Taken back", "Retracted"],
     "Corpus dominant rendering", False, False, ""),
    ("lapse", "व्यपगत", "Lapsed", ["Elapsed"],
     "Corpus dominant rendering", False, False,
     "'Expired' is NOT listed: a scheme legitimately expires by its own terms."),
    ("amend", "सुधारणा", "Amendment", ["Improvement", "Betterment"],
     "Corpus dominant rendering", False, False,
     "सुधारणा also means 'reform' in ordinary usage and appears inside file NAMES "
     "(वित्तीय सुधारणा-१ = 'Financial Reforms-1'), so a rendering here is not always a defect."),
    ("partially", "अंशत:", "Partially", ["Partly", "In part"],
     "Corpus dominant rendering", False, False, ""),

    # --- misc high-frequency
    ("said", "सदर", "The said", ["The prevailing", "The aforementioned said"],
     "Corpus dominant rendering", False, True,
     "The single commonest Devanagari token surviving into the English translation "
     "(1,529 instances across 319 HTE GRs). Qwen3.5-2B renders it 'the prevailing belief'."),
    ("dept", "विभाग", "Department", ["Ministry Department"],
     f"{MANUAL}, Appendix 10.6", True, False,
     "'Section' and 'Wing' are NOT listed: they render कलम and शाखा respectively."),
    ("number", "क्रमांक", "No.", ["Serial Number"],
     f"{MANUAL}, Appendix 10.6 ('Resolution No.')", True, False,
     "'Number' spelled out is not a defect; only a serial-number reading is."),
    ("distribution", "प्रति", "To", ["Recipients", "Distribution List"],
     f"{MANUAL}, Appendix 10.6", True, False,
     "'Copy to' is legitimate for प्रत and is not listed."),
]


def measure(corpus_root: Path, limit: int, seed: int = 4) -> dict[str, dict[str, int]]:
    """How often each rendering actually occurs, in documents. The evidence, not the rule."""
    random.seed(seed)
    en_files = glob.glob(str(corpus_root / "*" / "*.en.txt"))
    mr_files = glob.glob(str(corpus_root / "*" / "*.mr.txt"))
    random.shuffle(en_files)
    random.shuffle(mr_files)
    en_files, mr_files = en_files[:limit], mr_files[:limit]

    counts: dict[str, dict[str, int]] = {}
    for tid, mr, en, variants, *_ in SEED:
        counts[tid] = {"_en_docs": 0, "_mr_docs": 0}
        for v in [en] + list(variants):
            counts[tid][v] = 0

    for p in en_files:
        try:
            t = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for tid, mr, en, variants, *_ in SEED:
            for v in [en] + list(variants):
                if phrase(v).search(t):
                    counts[tid][v] += 1
    for p in mr_files:
        try:
            t = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for tid, mr, *_ in SEED:
            if mr in t:
                counts[tid]["_mr_docs"] += 1

    for tid in counts:
        counts[tid]["_en_docs"] = len(en_files)
    return counts


def build(corpus_root: Path | None, limit: int) -> dict:
    counts = measure(corpus_root, limit) if corpus_root else {}
    terms = []
    for tid, mr, en, variants, authority, approved, strict, note in SEED:
        c = counts.get(tid, {})
        terms.append({
            "id": tid,
            "mr": mr,
            "en": en,
            "variants_en": list(variants),
            "variants_mr": MR_VARIANTS.get(tid, []),
            "authority": authority,
            "approved": approved,
            # `strict` gates whether a replacement may be SUGGESTED. A non-strict term is
            # reported with its ambiguity and no proposed fix (FR-9 declines rather than guesses).
            "strict": strict,
            "note": note,
            "evidence": {
                "documents_sampled": c.get("_en_docs", 0),
                "approved_used_in": c.get(en, 0),
                "variants_used_in": {v: c.get(v, 0) for v in variants if c.get(v, 0)},
                "marathi_term_in": c.get("_mr_docs", 0),
            },
        })
    return {
        "_source": {
            "normative": MANUAL + " (documents/mcs270623075036.pdf) and SRS FR-11",
            "proposed_from": "dominant rendering in the orgpedia/mahGRs corpus",
            "rule": "Only entries with approved=true are enforced. Everything else is a "
                    "proposal awaiting a human decision and is reported as advisory.",
            "built_by": "build_glossary.py",
        },
        "terms": terms,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/mahGRs/GRs")
    ap.add_argument("--out", default="data/glossary.json")
    ap.add_argument("--limit", type=int, default=2500)
    a = ap.parse_args()

    root = Path(a.corpus)
    g = build(root if root.is_dir() else None, a.limit)
    Path(a.out).write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")

    approved = sum(t["approved"] for t in g["terms"])
    print(f"{len(g['terms'])} terms — {approved} approved (enforced), "
          f"{len(g['terms']) - approved} proposed (advisory)")
    print(f"wrote {a.out}\n")
    print("terms whose APPROVED rendering is not the corpus's dominant one:")
    for t in g["terms"]:
        ev = t["evidence"]
        worse = {v: n for v, n in ev["variants_used_in"].items() if n > ev["approved_used_in"]}
        if worse:
            top = max(worse.items(), key=lambda x: x[1])
            print(f"  {t['mr']:<18} approved '{t['en']}' in {ev['approved_used_in']:5d} docs, "
                  f"but '{top[0]}' in {top[1]:5d}")


if __name__ == "__main__":
    main()
