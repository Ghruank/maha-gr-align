#!/usr/bin/env python3
"""
Bilingual legal terminology + numeric parity.

    python bilingual.py --parity data/mahGRs/GRs --limit 3000
    python bilingual.py --glossary data/mahGRs/GRs --limit 1200
    python bilingual.py --all data/mahGRs/GRs

Two deliverables for the problem statement's "Bilingual Legal Terminology (English)" bullet.

## The caveat that constrains every claim here

The English side of this corpus is **IndicTrans2 machine translation of the Marathi**, not the
state's own English text. So nothing below measures divergence between two official documents. It
measures **translation fidelity**, and a divergence is a defect in the working English view rather
than a legal contradiction. `CLAUDE.md` requires this said out loud wherever the feature appears,
and the UI repeats it.

That still matters: officials read the English. A grant of ₹1.36 crore rendered as ₹13,600 is a
usable, checkable finding about the corpus everyone actually consults.

## Numeric parity — classify, never merely flag

A naive numeric diff flags 93% of pairs `[MEASURED]` and is therefore useless. Two filters make it
informative:

1. **Only significant numbers.** Tokens with ≥4 significant digits — amounts, years, large counts.
   Small integers are list ordinals, page numbers and clause references; they were 73% of raw
   mismatches and carry no legal weight.
2. **Explain each difference before reporting it.** Classes, in decreasing seriousness:

   * `MAGNITUDE_ERROR` — same significant digits, different scale (`13600000` vs `13600`). A real
     and serious finding: a factor of 1000 repeated down a table column.
   * `TRUNCATED` — the English number is a prefix of the Marathi one (`4450144346` → `4450144`).
   * `TABLE_MERGE` — one Marathi cell arrived as two English tokens (`3318750.00` → `3318` +
     `750.00`). An OCR column-boundary artefact, not a semantic discrepancy.
   * `YEAR_ONLY_IN_MR` — a bare year dropped in translation. Usually harmless.
   * `MISSING_FROM_ENGLISH` — present in Marathi, absent in English, unexplained. The residual.

## Glossary — mined by association, not asserted

There is no word-alignment model here and no hand-written term list, because a hand-written list
is exactly the kind of assertion this project refuses. Instead the same lift test used to validate
the supersession vocabulary: a Marathi term and an English term are associated when they co-occur
across aligned documents far above the English term's base rate.

The valuable output is not the glossary but the **inconsistency**: one Marathi legal term rendered
several different ways in English, which is a concrete, actionable finding about the corpus
officials read.
"""

from __future__ import annotations

import re
import json
import random
import argparse
from pathlib import Path
from collections import Counter, defaultdict

DEV = str.maketrans('०१२३४५६७८९', '0123456789')

MR_WORD = re.compile(r'[ऀ-ॿ]{3,}')
EN_WORD = re.compile(r'[A-Za-z]{4,}')

EN_STOP = {
    'government', 'decision', 'resolution', 'department', 'maharashtra', 'shall', 'this', 'that',
    'with', 'from', 'have', 'been', 'will', 'said', 'above', 'under', 'other', 'such', 'which',
    'they', 'their', 'these', 'those', 'there', 'been', 'also', 'after', 'before', 'accordingly',
    'regarding', 'following', 'thereof', 'hereby', 'letter', 'number', 'date', 'dated', 'mumbai',
    'state', 'order', 'orders', 'circular', 'page', 'annexure', 'sanction', 'given', 'made',
    'shall', 'therefore', 'been', 'being', 'should', 'would', 'about', 'into', 'more', 'than',
    'only', 'over', 'each', 'both', 'same', 'when', 'where', 'while', 'were', 'according',
}
MR_STOP = {
    'शासन', 'निर्णय', 'विभाग', 'महाराष्ट्र', 'क्रमांक', 'दिनांक', 'येथील', 'करण्यात', 'येत',
    'आहे', 'आहेत', 'यांचे', 'यांच्या', 'सदर', 'तसेच', 'संदर्भ', 'वाचा', 'नुसार', 'बाबत',
    'करण्याबाबत', 'खालीलप्रमाणे', 'मंत्रालय', 'प्रत', 'अनुसार', 'असून', 'करून', 'त्यानुसार',
}


# --------------------------------------------------------------------------- numeric parity

def _numbers(text: str) -> Counter:
    """Numeric tokens, normalised hard: Devanagari digits folded, Indian comma grouping removed."""
    t = re.sub(r'(?<=\d),(?=\d)', '', text.translate(DEV))
    return Counter(re.findall(r'\d+(?:\.\d+)?', t))


def _significant(tok: str) -> bool:
    return len(tok.replace('.', '').lstrip('0')) >= 4


def _core(tok: str) -> str:
    return tok.replace('.', '').lstrip('0').rstrip('0')


def classify(tok: str, en_only: list[str]) -> tuple[str, list]:
    """Explain one Marathi-only number, or admit it is unexplained."""
    digits = tok.replace('.', '').lstrip('0')

    mag = [o for o in en_only
           if _core(o) == _core(tok) and o != tok
           and abs(len(o.replace('.', '').lstrip('0')) - len(digits)) >= 2]
    if mag:
        return 'MAGNITUDE_ERROR', mag[:3]

    if len(digits) >= 6:
        for a in en_only:
            for b in en_only:
                if a != b and (a + b).replace('.', '') == tok.replace('.', ''):
                    return 'TABLE_MERGE', [a, b]

    trunc = [o for o in en_only
             if len(o) >= 4 and digits.startswith(o.replace('.', '').lstrip('0'))
             and len(o.replace('.', '')) < len(digits)]
    if trunc:
        return 'TRUNCATED', trunc[:3]

    if re.fullmatch(r'(19|20)\d\d', tok):
        return 'YEAR_ONLY_IN_MR', []

    return 'MISSING_FROM_ENGLISH', en_only[:3]


SEVERITY = {'MAGNITUDE_ERROR': 'ERROR', 'TRUNCATED': 'WARN',
            'MISSING_FROM_ENGLISH': 'WARN', 'TABLE_MERGE': 'INFO',
            'YEAR_ONLY_IN_MR': 'INFO'}


def parity(corpus_root: Path, limit: int = 3000, seed: int = 5) -> dict:
    random.seed(seed)
    files = [f for d in sorted(corpus_root.iterdir()) if d.is_dir()
             for f in sorted(d.glob('*.mr.txt'))]
    samp = random.sample(files, min(limit, len(files)))

    naive = flagged = 0
    cls = Counter()
    findings = []
    for f in samp:
        e = f.with_name(f.name.replace('.mr.', '.en.'))
        if not e.exists():
            continue
        mr = _numbers(f.read_text(encoding='utf-8', errors='ignore'))
        en = _numbers(e.read_text(encoding='utf-8', errors='ignore'))
        if mr != en:
            naive += 1
        mr_only = [k for k in (mr - en) if _significant(k)]
        en_only = [k for k in (en - mr) if _significant(k)]
        if not mr_only:
            continue
        flagged += 1
        for tok in mr_only:
            kind, other = classify(tok, en_only)
            cls[kind] += 1
            if kind in ('MAGNITUDE_ERROR', 'TRUNCATED'):
                findings.append({"uid": f.name.split('.')[0], "kind": kind,
                                 "severity": SEVERITY[kind], "marathi_value": tok,
                                 "english_values": other,
                                 "factor": _factor(tok, other)})
    findings.sort(key=lambda x: (x["kind"] != 'MAGNITUDE_ERROR', -(x["factor"] or 0)))
    return {
        "sampled": len(samp),
        "naive_diff_flags": naive,
        "naive_diff_rate": round(naive / max(len(samp), 1), 4),
        "with_significant_divergence": flagged,
        "significant_divergence_rate": round(flagged / max(len(samp), 1), 4),
        "classes": dict(cls.most_common()),
        "severity_of": SEVERITY,
        "findings": findings[:300],
        "caveat": "The English side is IndicTrans2 machine translation OF the Marathi, not the "
                  "state's own English text. These are translation-fidelity defects in the "
                  "working English view, NOT contradictions between two official documents.",
    }


def _factor(tok: str, others: list) -> int | None:
    try:
        a = float(tok)
        for o in others:
            b = float(o)
            if b and a > b and (a / b).is_integer():
                return int(a / b)
    except (ValueError, ZeroDivisionError, TypeError):
        pass
    return None


# --------------------------------------------------------------------------- glossary

def _mr_terms(text: str) -> set:
    return {w for w in MR_WORD.findall(text) if w not in MR_STOP}


def _en_terms(text: str) -> set:
    return {w.lower() for w in EN_WORD.findall(text) if w.lower() not in EN_STOP}


def glossary(corpus_root: Path, limit: int = 1200, seed: int = 9,
             min_docs: int = 12, min_lift: float = 6.0, top_per_term: int = 6,
             max_partners: int = 3) -> dict:
    """Associate Marathi terms with English renderings by document-level lift.

    Not word alignment and not a hand-written list. A pair is kept when the English term appears in
    documents containing the Marathi term far more often than in the corpus at large — the same
    test that validated the supersession vocabulary and rejected `पुढे चालू`.

    Its limits, which the UI states: association is not translation (a term and its close
    collocate both score), and lift is only as good as the sample. It is a lead-generation tool for
    finding inconsistency, not an authoritative dictionary.
    """
    random.seed(seed)
    files = [f for d in sorted(corpus_root.iterdir()) if d.is_dir()
             for f in sorted(d.glob('*.mr.txt'))]
    samp = random.sample(files, min(limit, len(files)))

    docs = []
    mr_df, en_df = Counter(), Counter()
    for f in samp:
        e = f.with_name(f.name.replace('.mr.', '.en.'))
        if not e.exists():
            continue
        m = _mr_terms(f.read_text(encoding='utf-8', errors='ignore'))
        n = _en_terms(e.read_text(encoding='utf-8', errors='ignore'))
        docs.append((m, n))
        mr_df.update(m)
        en_df.update(n)

    N = len(docs)
    mr_keep = {t for t, c in mr_df.items() if c >= min_docs and c <= 0.45 * N}
    en_keep = {t for t, c in en_df.items() if c >= min_docs and c <= 0.45 * N}

    co = defaultdict(Counter)
    for m, n in docs:
        mm = m & mr_keep
        nn = n & en_keep
        for a in mm:
            co[a].update(nn)

    # Pass 1: every pair clearing the lift bar.
    raw: dict[str, list[dict]] = {}
    for mr_t, counts in co.items():
        base_mr = mr_df[mr_t]
        cands = []
        for en_t, c in counts.items():
            if c < min_docs:
                continue
            expected = base_mr * en_df[en_t] / N
            lift = c / expected if expected else 0
            if lift >= min_lift:
                cands.append({"english": en_t, "documents": c, "lift": round(lift, 2),
                              "coverage": round(c / base_mr, 3)})
        if cands:
            raw[mr_t] = cands

    # Pass 2: drop TOPIC MARKERS, keep translations.
    #
    # Lift alone conflates two very different relationships and the first version shipped the
    # wrong one. `तक्रारी` (complaints), `तत्वावर` (on the principle of), `मान्य` (approved),
    # `प्रवेश` (admission) and `शुल्क` (fee) all returned the *same* English cluster —
    # capitation / ragging / usability / learners — because a family of education-regulation GRs
    # contains all of those words together. That is document topic, not translation.
    #
    # The discriminator: **a translation is near-bijective, a topic marker is many-to-many.**
    # An English word that is a high-lift partner of many different Marathi terms is describing
    # the subject matter of a document cluster, not rendering any one term. So count each English
    # term's Marathi partners and drop the promiscuous ones.
    partners = Counter()
    for cands in raw.values():
        for c in cands:
            partners[c["english"]] += 1

    entries, dropped = [], Counter()
    for mr_t, cands in raw.items():
        kept = []
        for c in cands:
            if partners[c["english"]] > max_partners:
                dropped[c["english"]] += 1
                continue
            kept.append({**c, "mr_partners": partners[c["english"]]})
        if kept:
            kept.sort(key=lambda x: -x["lift"])
            entries.append({"marathi": mr_t, "documents": mr_df[mr_t],
                            "renderings": kept[:top_per_term]})

    entries.sort(key=lambda x: -x["documents"])
    inconsistent = [e for e in entries
                    if len([r for r in e["renderings"] if r["coverage"] >= 0.30]) >= 2]
    inconsistent.sort(key=lambda e: -len(e["renderings"]))
    return {
        "sampled_pairs": N,
        "marathi_vocabulary": len(mr_keep),
        "english_vocabulary": len(en_keep),
        "min_documents": min_docs, "min_lift": min_lift,
        "max_marathi_partners_per_english_term": max_partners,
        "topic_markers_dropped": dict(dropped.most_common(25)),
        "terms": entries[:400],
        "inconsistent_terms": inconsistent[:120],
        "method": "document-level lift between Marathi and English terms across aligned pairs",
        "caveat": "Association is not translation: a term and a frequent collocate both score. "
                  "This finds candidates for inconsistent rendering; it is not a dictionary. The "
                  "English side is machine translation of the Marathi.",
    }


# --------------------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", metavar="CORPUS_ROOT")
    ap.add_argument("--glossary", metavar="CORPUS_ROOT")
    ap.add_argument("--all", metavar="CORPUS_ROOT")
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--out", default="out/bilingual.json")
    a = ap.parse_args()

    root = a.parity or a.glossary or a.all
    if not root:
        ap.error("one of --parity / --glossary / --all is required")
    root = Path(root)
    result = {}

    if a.parity or a.all:
        p = parity(root, a.limit)
        result["parity"] = p
        print("=" * 74)
        print("NUMERIC PARITY")
        print("=" * 74)
        print(f"  pairs sampled                    : {p['sampled']:,}")
        print(f"  naive numeric diff would flag    : {p['naive_diff_flags']:,} "
              f"({p['naive_diff_rate']*100:.1f}%)  ← useless")
        print(f"  significant divergence           : {p['with_significant_divergence']:,} "
              f"({p['significant_divergence_rate']*100:.1f}%)")
        print("\n  classified Marathi-only numbers:")
        for k, v in p["classes"].items():
            print(f"    {v:6,}  [{SEVERITY[k]:5s}]  {k}")
        mags = [f for f in p["findings"] if f["kind"] == 'MAGNITUDE_ERROR']
        print(f"\n  MAGNITUDE ERRORS — the serious class ({len(mags)} shown):")
        for f in mags[:8]:
            print(f"    {f['uid']}  Marathi {f['marathi_value']:>16s}  vs English "
                  f"{', '.join(f['english_values']):<16s}"
                  + (f"  factor ×{f['factor']:,}" if f["factor"] else ""))

    if a.glossary or a.all:
        g = glossary(root, min(a.limit, 1200))
        result["glossary"] = g
        print("\n" + "=" * 74)
        print("BILINGUAL GLOSSARY (mined by association)")
        print("=" * 74)
        print(f"  aligned pairs                    : {g['sampled_pairs']:,}")
        print(f"  Marathi / English vocabulary     : {g['marathi_vocabulary']:,} / "
              f"{g['english_vocabulary']:,}")
        print(f"  terms with a confident rendering : {len(g['terms']):,}")
        print(f"  INCONSISTENTLY rendered terms    : {len(g['inconsistent_terms']):,}")
        print("\n  most inconsistently rendered:")
        for e in g["inconsistent_terms"][:10]:
            rs = ", ".join(f"{r['english']} ({r['coverage']*100:.0f}%)"
                           for r in e["renderings"][:5])
            print(f"    {e['marathi']:<18s} in {e['documents']:4d} docs →  {rs}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
