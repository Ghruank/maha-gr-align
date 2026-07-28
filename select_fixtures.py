#!/usr/bin/env python3
"""
Mine a fixture set out of the GR corpus.

We do not hand-pick fixtures. We define the *pathologies* the parser has to survive,
score every GR against each one, and take the worst offenders. Human effort then goes
into verifying ~50 files instead of reading 17,000.

Usage:
    python select_fixtures.py GRs/Higher_and_Technical_Education_Department fixtures/
"""

import sys, re, json, glob, shutil, unicodedata
from pathlib import Path
from collections import defaultdict

DEVANAGARI = re.compile(r'[\u0900-\u097F]')
RE_REF_ITEM = re.compile(r'\n?\s*\d{1,2}\)')
RE_REF_BLOCK = re.compile(r'Reference\s*:(.{0,2000})', re.I | re.S)
RE_DATE_LINE = re.compile(r'^Date\s*:', re.I | re.M)
RE_DEC_NO = re.compile(r'Government\s+Decision\s+No', re.I)
RE_SUPERSEDE = re.compile(r'\b(supersed|cancel|repeal|rescind|withdraw|revoke)', re.I)
RE_AMEND = re.compile(r'\b(amend|modif|partially|in continuation|substitut)', re.I)
RE_CITE = re.compile(
    r'(?:Government\s+(?:Decision|Resolution)|शासन\s*निर्णय)[^\n]{0,200}?'
    r'(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', re.I)
RE_PAGE = re.compile(r'^# Page \d+', re.M)

DEV_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')


def numeric_tokens(text: str) -> set:
    """Normalised numeric tokens. Aggressive on purpose — the naive version
    flags 99.5% of pairs as mismatched, which is useless."""
    t = text.translate(DEV_DIGITS)
    out = set()
    for tok in re.findall(r'\d[\d,]*(?:\.\d+)?', t):
        tok = tok.rstrip('.,').replace(',', '')      # kill comma grouping + trailing punct
        if tok and not re.fullmatch(r'0+', tok):
            out.add(tok.lstrip('0') or '0')
    return out


def score(uid: str, en: str, mr: str) -> dict:
    ref_block = RE_REF_BLOCK.search(en)
    n_refs = len(RE_REF_ITEM.findall(ref_block.group(1))) if ref_block else 0
    dev_chars = len(DEVANAGARI.findall(en))
    en_nums, mr_nums = numeric_tokens(en), numeric_tokens(mr)
    only_en, only_mr = en_nums - mr_nums, mr_nums - en_nums

    return {
        "uid": uid,
        "n_refs": n_refs,
        "n_citations": len(set(RE_CITE.findall(en))),
        "devanagari_leak": dev_chars,
        "devanagari_leak_ratio": dev_chars / max(len(en), 1),
        "has_date_line": bool(RE_DATE_LINE.search(en)),
        "has_decision_no": bool(RE_DEC_NO.search(en)),
        "has_ref_block": ref_block is not None,
        "supersedes": bool(RE_SUPERSEDE.search(en)),
        "amends": bool(RE_AMEND.search(en)),
        "n_pages": len(RE_PAGE.findall(en)),
        "len_en": len(en),
        "numeric_divergence": len(only_en) + len(only_mr),
        "divergent_en_only": sorted(only_en)[:8],
        "divergent_mr_only": sorted(only_mr)[:8],
    }


# Each bucket: (name, filter, sort key, how many to take)
BUCKETS = [
    ("many_references",      lambda r: r["n_refs"] >= 5,            lambda r: -r["n_refs"], 5),
    ("devanagari_leakage",   lambda r: r["devanagari_leak"] > 20,   lambda r: -r["devanagari_leak_ratio"], 6),
    ("supersession",         lambda r: r["supersedes"],             lambda r: -r["n_citations"], 6),
    ("amendment",            lambda r: r["amends"],                 lambda r: -r["n_citations"], 5),
    ("numeric_divergence",   lambda r: r["numeric_divergence"] > 0, lambda r: -r["numeric_divergence"], 6),
    ("no_date_line",         lambda r: not r["has_date_line"],      lambda r: -r["len_en"], 4),
    ("no_reference_block",   lambda r: not r["has_ref_block"],      lambda r: -r["n_citations"], 4),
    ("no_decision_no",       lambda r: not r["has_decision_no"],    lambda r: -r["len_en"], 3),
    ("very_long",            lambda r: r["n_pages"] >= 6,           lambda r: -r["n_pages"], 4),
    ("heavily_citing",       lambda r: r["n_citations"] >= 3,       lambda r: -r["n_citations"], 5),
    ("clean_baseline",       lambda r: (r["has_date_line"] and r["has_decision_no"]
                                        and r["has_ref_block"] and r["devanagari_leak"] < 5),
                                                                    lambda r: r["len_en"], 4),
]


def main(src_dir: str, out_dir: str):
    src, out = Path(src_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    records = []
    for f in sorted(src.glob("*.en.txt")):
        uid = f.name.split('.')[0]
        mr_path = src / f"{uid}.pdf.mr.txt"
        if not mr_path.exists():
            continue
        en = f.read_text(encoding='utf-8', errors='ignore')
        mr = mr_path.read_text(encoding='utf-8', errors='ignore')
        records.append(score(uid, en, mr))

    print(f"scored {len(records)} GRs")

    chosen, manifest = {}, defaultdict(list)
    for name, pred, key, n in BUCKETS:
        pool = sorted([r for r in records if pred(r)], key=key)
        taken = 0
        for r in pool:
            if taken >= n:
                break
            if r["uid"] in chosen:          # already covers another pathology
                continue
            chosen[r["uid"]] = r
            manifest[name].append(r["uid"])
            taken += 1
        print(f"  {name:22} pool={len(pool):5}  selected={taken}")

    for uid in chosen:
        for lang in ("en", "mr"):
            shutil.copy(src / f"{uid}.pdf.{lang}.txt", out / f"{uid}.pdf.{lang}.txt")

    (out / "manifest.json").write_text(json.dumps({
        "source": str(src),
        "total_scored": len(records),
        "selected": len(chosen),
        "buckets": dict(manifest),
        "records": {u: r for u, r in chosen.items()},
    }, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f"\nwrote {len(chosen)} fixtures ({len(chosen)*2} files) to {out}/")
    print("manifest.json lists which pathology each fixture was selected for.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "fixtures")
