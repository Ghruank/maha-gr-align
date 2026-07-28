#!/usr/bin/env python3
"""
GR-Lint — template enforcement with rules MINED from the corpus, not copied from a manual.

    python lint.py --mine data/mahGRs/GRs --profile data/template_profile.json
    python lint.py --check fixtures/201803071449402308.pdf.mr.txt
    python lint.py --audit-corpus data/mahGRs/GRs --limit 2000

## Why mining rather than transcribing the Manual of Office Procedure

Because the manual describes what GRs *should* look like and the corpus records what they *do*
look like, and the gap is enormous. `[MEASURED]` over ~700 sampled GRs per department:

| marker | Finance | GAD | HTE | School Ed |
| --- | --- | --- | --- | --- |
| `प्रस्तावना` (preamble) | 43% | 31% | 67% | 78% |
| `शासन निर्णय :` header | 37% | 32% | 69% | 61% |
| `वाचा` (read) | 40% | 37% | 33% | 61% |

A hand-written rule requiring a `प्रस्तावना` would flag **69% of General Administration
resolutions as defective** — and be wrong every time, because that department does not use the
section. A linter that cries wolf on two thirds of a department's output gets switched off in a
week.

So every rule here carries an **empirical support count**, and a rule is only emitted where the
corpus justifies it:

> `GRL-004` — 99.1% of Higher and Technical Education GRs carry a date line. Yours does not.
> *(support: 692 / 698 sampled)*

That number is what makes the finding arguable in a meeting. It also lets thresholds differ per
department without anyone hand-tuning them.

## What is mined

1. **Presence** of each structural marker, per department → rules above a support threshold.
2. **Canonical section order**, from mean relative position. `[MEASURED]` and stable across all
   four departments: Government-of-Maharashtra → department → Mantralaya → reference block →
   date → preamble → order number → decision → signature.
3. **Numbered-condition conventions**, including the displaced-ordinal defect documented in
   CLAUDE.md: 136 GRs share a boilerplate where `१. सदर मान्यता` became `The 1.सदर ...`, fusing
   the list ordinal into the sentence body.
"""

from __future__ import annotations

import re
import json
import random
import argparse
from pathlib import Path
from collections import Counter, defaultdict

DEV = str.maketrans('०१२३४५६७८९', '0123456789')

# Structural markers in the Marathi (authoritative) text. Names are stable rule keys.
MARKERS: dict[str, str] = {
    'govt_of_maharashtra': r'महाराष्ट्र\s*शासन',
    'department':          r'विभाग',
    'mantralaya':          r'मंत्रालय',
    'reference_block':     r'(?:वाचा|संदर्भ|पहा)\s*[:ः]',
    'date_line':           r'(?:दिनांक|दिनाक|दि)\s*[.:ः]?\s*[०-९]',
    'preamble':            r'प्रस्तावना',
    'order_number':        r'क्रमांक\s*[:ः]?\s*\S',
    'decision_header':     r'शासन\s*निर्णय\s*[:ः]',
    'signature':           r'(?:सचिव|अवर\s*सचिव|उप\s*सचिव)',
}
RX = {k: re.compile(v) for k, v in MARKERS.items()}

HUMAN = {
    'govt_of_maharashtra': 'the "महाराष्ट्र शासन" (Government of Maharashtra) heading',
    'department':          'an issuing department name',
    'mantralaya':          'the Mantralaya address block',
    'reference_block':     'a reference block (वाचा / संदर्भ / पहा)',
    'date_line':           'a date line (दिनांक)',
    'preamble':            'a प्रस्तावना (preamble / proposal) section',
    'order_number':        'a Government Decision number (क्रमांक)',
    'decision_header':     'a "शासन निर्णय :" decision header',
    'signature':           'a signatory block (सचिव)',
}

# Ordinals opening a numbered condition. Mirrors resolver.py's handling: `१६)` inside `(३८/१६)`
# is part of a file number, not a list marker, so validation happens in code not the regex.
ORDINAL = re.compile(r'(\(?)([०-९]{1,2})\)')

# The displaced-ordinal defect, e.g. `The 1.सदर approval will always be...`, where Marathi
# `१. सदर मान्यता` had its list ordinal fused into the sentence body by the translation.
#
# TWO CORRECTIONS learned by measuring rather than assuming:
#
# 1. This is an ENGLISH-side artefact. In Marathi, `१. सदर पदे...` opening a line is correct
#    formatting, not a defect. An earlier version checked the Marathi and reported the defect in
#    52% of GRs; the true English-side rate is ~5%, consistent with CLAUDE.md's 136 of 4,715.
# 2. "Fused" means the ordinal has running text before it ON THE SAME LINE. The first regex
#    allowed a preceding `.` plus a newline to satisfy "non-whitespace before", so every
#    legitimate `…आहे.\n1. सदर` matched. Hence the same-line check in `find_fused_ordinal`.
FUSED_TOKEN = re.compile(r'([०-९0-9]{1,2})\.\s*(?:सदर|अभ)')


def find_fused_ordinal(text: str) -> re.Match | None:
    """An ordinal is *fused* only when running text precedes it on the same line."""
    for m in FUSED_TOKEN.finditer(text):
        line_start = text.rfind('\n', 0, m.start()) + 1
        if text[line_start:m.start()].strip():
            return m
    return None

ERROR, WARN, INFO = 'ERROR', 'WARN', 'INFO'


# --------------------------------------------------------------------------- mining

ORDER_MIN_CONSISTENCY = 0.95
ORDER_MIN_SUPPORT = 100


def mine(corpus_root: Path, per_dept: int = 700, seed: int = 7) -> dict:
    random.seed(seed)
    profile: dict = {"sampled_per_department": per_dept, "seed": seed, "departments": {}}
    positions_all: dict[str, list[float]] = defaultdict(list)
    pair_before: Counter = Counter()   # (a,b) -> times a preceded b
    pair_seen: Counter = Counter()     # (a,b) -> times both present

    for d in sorted(p for p in corpus_root.iterdir() if p.is_dir()):
        files = sorted(d.glob('*.mr.txt'))
        if not files:
            continue
        samp = random.sample(files, min(per_dept, len(files)))
        present, pos = Counter(), defaultdict(list)
        seq_ok = seq_bad = fused_mr = fused_en = 0

        for f in samp:
            t = f.read_text(encoding='utf-8', errors='ignore')
            at = {}
            for k, r in RX.items():
                m = r.search(t)
                if m:
                    present[k] += 1
                    at[k] = m.start()
                    rel = m.start() / max(len(t), 1)
                    pos[k].append(rel)
                    positions_all[k].append(rel)
            keys = list(MARKERS)
            for i, a in enumerate(keys):
                for b in keys[i + 1:]:
                    if a in at and b in at:
                        pair_seen[(a, b)] += 1
                        if at[a] < at[b]:
                            pair_before[(a, b)] += 1

            ords_ = _ordinals(t)
            if len(ords_) >= 3:
                (seq_ok, seq_bad) = ((seq_ok + 1, seq_bad) if _is_sequential(ords_)
                                     else (seq_ok, seq_bad + 1))
            if find_fused_ordinal(t):
                fused_mr += 1
            en = f.with_name(f.name.replace('.mr.', '.en.'))
            if en.exists() and find_fused_ordinal(
                    en.read_text(encoding='utf-8', errors='ignore')):
                fused_en += 1

        n = len(samp)
        profile["departments"][d.name] = {
            "sampled": n,
            "presence": {k: {"count": present[k], "rate": round(present[k] / n, 4)}
                         for k in MARKERS},
            "mean_position": {k: round(sum(v) / len(v), 4) for k, v in pos.items() if v},
            "numbered_conditions": {"sequential": seq_ok, "non_sequential": seq_bad,
                                    "fused_ordinal_mr": fused_mr,
                                    "fused_ordinal_en": fused_en},
        }

    # Ordering rules come from PAIRWISE precedence, not from a single canonical sequence.
    #
    # Sorting markers by mean position and demanding that total order produced 2,910 violations
    # over 2,000 GRs — because several pairs are genuinely free variation. `order_number` precedes
    # `date_line` in 58% of documents and `mantralaya` in 51%: coin flips, not conventions.
    # Enforcing them is how a linter earns being switched off.
    #
    # So a rule is emitted only where one order holds in >=95% of documents that contain both
    # markers, with >=100 such documents. Everything else is recorded as free variation, which is
    # itself a finding worth showing.
    order_rules, free = [], []
    for (a, b), n in sorted(pair_seen.items(), key=lambda x: -x[1]):
        if n < ORDER_MIN_SUPPORT:
            continue
        fwd = pair_before[(a, b)] / n
        consistency = max(fwd, 1 - fwd)
        first, second = (a, b) if fwd >= 0.5 else (b, a)
        rec = {"first": first, "second": second, "documents": n,
               "consistency": round(consistency, 4)}
        (order_rules if consistency >= ORDER_MIN_CONSISTENCY else free).append(rec)

    profile["order_rules"] = order_rules
    profile["order_free_variation"] = free
    profile["canonical_order"] = [
        k for k, _ in sorted(((k, sum(v) / len(v)) for k, v in positions_all.items() if v),
                             key=lambda x: x[1])]
    profile["canonical_order_positions"] = {
        k: round(sum(v) / len(v), 4) for k, v in positions_all.items() if v}
    return profile


def _ordinals(text: str) -> list[int]:
    """Ordinals that genuinely open a numbered item, in document order."""
    out = []
    for m in ORDINAL.finditer(text):
        start = m.start()
        prev = text[start - 1] if start else '\n'
        if m.group(1):                       # "(२)" — the bracket must follow whitespace
            if not (prev.isspace() or start == 0):
                continue
        elif prev in '/(' or '०' <= prev <= '९':
            continue                          # inside a file number like (३८/१६)
        out.append(int(m.group(2).translate(DEV)))
    return out


def _is_sequential(ords: list[int]) -> bool:
    """A run of >=3 consecutive ascending integers starting at 1 somewhere in the list."""
    for i in range(len(ords)):
        if ords[i] != 1:
            continue
        run = 1
        for j in range(i + 1, len(ords)):
            if ords[j] == run + 1:
                run += 1
            elif ords[j] <= run:
                break
        if run >= 3:
            return True
    return False


# --------------------------------------------------------------------------- rules

def rules_for(profile: dict, dept_dir: str) -> list[dict]:
    """Emit the rule set for one department, thresholded by measured support.

    Severity comes from the data, not from opinion: something 99% of the department's own output
    does is an ERROR to omit; something 90-99% do is a WARN; below 90% we say nothing, because a
    convention two thirds of a department ignores is not a rule.
    """
    dp = profile["departments"].get(dept_dir)
    if not dp:
        return []
    out = []
    for i, (key, _) in enumerate(MARKERS.items(), start=1):
        p = dp["presence"][key]
        rate = p["rate"]
        sev = ERROR if rate >= 0.99 else WARN if rate >= 0.90 else None
        if not sev:
            continue
        out.append({
            "code": f"GRL-{i:03d}", "marker": key, "severity": sev,
            "message": f"Missing {HUMAN[key]}.",
            "support": f"{p['count']} / {dp['sampled']} sampled GRs in this department "
                       f"({rate*100:.1f}%) include it",
            "rate": rate,
        })
    out.append({"code": "GRL-050", "marker": "section_order", "severity": WARN,
                "message": "Two sections appear in an order this corpus almost never uses.",
                "support": f"{len(profile.get('order_rules', []))} section orderings hold in "
                           f"≥{int(ORDER_MIN_CONSISTENCY*100)}% of documents containing both "
                           f"markers; {len(profile.get('order_free_variation', []))} further "
                           f"pairs vary freely and are deliberately NOT enforced",
                "rate": None})
    nc = dp["numbered_conditions"]
    out.append({"code": "GRL-060", "marker": "numbered_conditions", "severity": WARN,
                "message": "Numbered conditions are not sequentially numbered from 1.",
                "support": f"{nc['sequential']} of {nc['sequential'] + nc['non_sequential']} "
                           f"sampled GRs with ≥3 numbered items are sequential",
                "rate": None})
    out.append({"code": "GRL-061", "marker": "fused_ordinal_en", "severity": WARN,
                "message": "In the English translation a list ordinal is fused into the sentence "
                           "body (e.g. `The 1.सदर approval ...`) instead of opening the item.",
                "support": f"{nc['fused_ordinal_en']} of {dp['sampled']} sampled GRs show this in "
                           f"their English translation (Marathi side: {nc['fused_ordinal_mr']}). "
                           f"It originates in one shared boilerplate template and mis-indexes "
                           f"every numbered condition downstream",
                "rate": None})
    return out


def lint(text: str, profile: dict, dept_dir: str, en_text: str | None = None) -> list[dict]:
    """Check one Marathi GR. Returns violations with line numbers so a UI can point at them.

    `en_text` is the aligned English translation, needed only for GRL-061, which is a
    translation defect rather than a defect in the resolution itself.
    """
    offs: dict[str, int] = {}
    for k, r in RX.items():
        m = r.search(text)
        if m:
            offs[k] = m.start()
    line_of = {k: text[:o].count('\n') + 1 for k, o in offs.items()}

    violations = []
    for rule in rules_for(profile, dept_dir):
        mk = rule["marker"]
        if mk in MARKERS:
            if mk not in offs:
                violations.append({**rule, "line": None,
                                   "detail": f"No match for /{MARKERS[mk]}/ anywhere in the text."})
        elif mk == "section_order":
            for orule in profile.get("order_rules", []):
                a, b = orule["first"], orule["second"]
                if a in offs and b in offs and offs[a] > offs[b]:
                    violations.append({
                        **rule, "line": line_of[b],
                        "detail": f"{HUMAN[b]} (line {line_of[b]}) appears before {HUMAN[a]} "
                                  f"(line {line_of[a]}), but {a} precedes {b} in "
                                  f"{orule['consistency']*100:.1f}% of "
                                  f"{orule['documents']} documents containing both."})
        elif mk == "numbered_conditions":
            ords = _ordinals(text)
            if len(ords) >= 3 and not _is_sequential(ords):
                violations.append({**rule, "line": None,
                                   "detail": f"Ordinals found in order: {ords[:14]}"})
        elif mk == "fused_ordinal_en":
            if en_text:
                m = find_fused_ordinal(en_text)
                if m:
                    violations.append({
                        **rule, "line": None,
                        "detail": f"In the English text: "
                                  f"{en_text[max(0, m.start()-30):m.end()+30]!r}"})
    return violations


# --------------------------------------------------------------------------- cli

def _dept_dir_of(path: Path, roots: list[Path]) -> str:
    for r in roots:
        if r.name.endswith("_Department") and path.is_relative_to(r):
            return r.name
    code = path.name[:18][-2:]
    return {'05': 'Finance_Department', '07': 'General_Administration_Department',
            '08': 'Higher_and_Technical_Education_Department',
            '21': 'School_Education_and_Sports_Department'}.get(code, '')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mine", metavar="CORPUS_ROOT")
    ap.add_argument("--profile", default="data/template_profile.json")
    ap.add_argument("--check", metavar="MR_TXT")
    ap.add_argument("--audit-corpus", metavar="CORPUS_ROOT")
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--out", default="out/lint_corpus.json")
    a = ap.parse_args()

    if a.mine:
        prof = mine(Path(a.mine))
        Path(a.profile).parent.mkdir(parents=True, exist_ok=True)
        Path(a.profile).write_text(json.dumps(prof, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"mined {len(prof['departments'])} departments → {a.profile}\n")
        print("canonical section order (mean relative position):")
        for k in prof["canonical_order"]:
            print(f"  {prof['canonical_order_positions'][k]:.3f}  {k}")
        print("\nrules emitted per department (severity from measured support):")
        for d in prof["departments"]:
            rs = rules_for(prof, d)
            e = sum(1 for r in rs if r['severity'] == ERROR)
            w = sum(1 for r in rs if r['severity'] == WARN)
            print(f"  {d[:42]:44s} {e} ERROR, {w} WARN")
        return

    prof = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    roots = []

    if a.check:
        p = Path(a.check)
        dept = _dept_dir_of(p, roots)
        _en = p.with_name(p.name.replace(".mr.", ".en."))
        vs = lint(p.read_text(encoding="utf-8", errors="ignore"), prof, dept,
                  _en.read_text(encoding="utf-8", errors="ignore") if _en.exists() else None)
        print(f"{p.name}  [{dept}]  →  {len(vs)} violation(s)\n")
        for v in vs:
            loc = f"line {v['line']}" if v["line"] else "document"
            print(f"  [{v['severity']:5s}] {v['code']}  {loc}: {v['message']}")
            print(f"          {v['detail']}")
            print(f"          support: {v['support']}\n")
        return

    if a.audit_corpus:
        root = Path(a.audit_corpus)
        roots = [p for p in root.iterdir() if p.is_dir()]
        random.seed(11)
        files = [f for r in roots for f in sorted(r.glob('*.mr.txt'))]
        files = random.sample(files, min(a.limit, len(files)))
        tally, per_code, clean = Counter(), Counter(), 0
        rows = []
        for f in files:
            dept = _dept_dir_of(f, roots)
            en = f.with_name(f.name.replace(".mr.", ".en."))
            vs = lint(f.read_text(encoding="utf-8", errors="ignore"), prof, dept,
                      en.read_text(encoding="utf-8", errors="ignore") if en.exists() else None)
            if not vs:
                clean += 1
            for v in vs:
                tally[v["severity"]] += 1
                per_code[f'{v["code"]} {v["marker"]}'] += 1
            if vs:
                rows.append({"uid": f.name.split('.')[0], "dept": dept,
                             "violations": vs})
        print(f"linted {len(files):,} GRs · {clean:,} clean ({100*clean/len(files):.1f}%)")
        print(f"violations: {dict(tally)}\n")
        for k, n in per_code.most_common():
            print(f"  {n:6,}  {k}   ({100*n/len(files):.1f}% of GRs)")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(
            {"linted": len(files), "clean": clean, "severity_tally": dict(tally),
             "by_code": dict(per_code.most_common()), "sample_findings": rows[:400]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
        return

    ap.error("one of --mine / --check / --audit-corpus is required")


if __name__ == "__main__":
    main()
