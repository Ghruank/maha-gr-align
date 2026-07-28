#!/usr/bin/env python3
"""
Field-coverage report for parser v1, per fixture bucket.

The three "missing field" buckets run first and are printed first. They are what breaks a
parser built against well-formed GRs, so they are the acceptance signal, not an afterthought.

Usage:
    python3 parse_report.py fixtures/ out/parsed.json
"""

import sys, json
from pathlib import Path

HARD = ["no_decision_no", "no_reference_block", "no_date_line", "template_boilerplate"]
FIELDS = ["decision_no", "subject", "date", "references", "body", "conditions", "amounts"]


def filled(rec, f):
    v = rec.get(f)
    return bool(v) if not isinstance(v, list) else len(v) > 0


def main(fix_dir: str, parsed_path: str):
    man = json.loads((Path(fix_dir) / "manifest.json").read_text(encoding="utf-8"))
    recs = json.loads(Path(parsed_path).read_text(encoding="utf-8"))
    buckets = man["buckets"]
    order = HARD + [b for b in buckets if b not in HARD]

    print(f"{'bucket':<22}{'n':>3}  " + "".join(f"{f[:9]:>10}" for f in FIELDS))
    print("-" * (25 + 10 * len(FIELDS)))
    for i, b in enumerate(order):
        if b == HARD[0]:
            print(">>> missing-field buckets — the ones that break naive parsers")
        if i == len(HARD):
            print("--- remaining buckets " + "-" * (3 + 10 * len(FIELDS)))
        uids = buckets[b]
        row = f"{b:<22}{len(uids):>3}  "
        for f in FIELDS:
            k = sum(filled(recs[u], f) for u in uids)
            row += f"{k}/{len(uids):<8}".rjust(10)
        print(row)

    print("\n" + "=" * 70)
    n = len(recs)
    print(f"ALL {n} FIXTURES")
    for f in FIELDS:
        k = sum(filled(r, f) for r in recs.values())
        print(f"  {f:<14} {k:>3}/{n}  ({100*k/n:5.1f}%)")

    art = {}
    for r in recs.values():
        for a in r["artifacts"]:
            art[a] = art.get(a, 0) + 1
    print("\nartifacts flagged:")
    for a, c in sorted(art.items(), key=lambda kv: -kv[1]):
        print(f"  {c:>3}  {a}")

    # Invariants that must hold regardless of bucket.
    print("\ninvariants:")
    bad_date = [u for u, r in recs.items() if r["date"] != f"{u[0:4]}-{u[4:6]}-{u[6:8]}"]
    fabricated = [u for u, r in recs.items()
                  if any(x["resolved_uid"] is not None or x["confidence"] != 0.0
                         for x in r["references"])]
    drift = [(u, r["_provenance"]["body_date"], r["date"]) for u, r in recs.items()
             if r["_provenance"]["body_date"] and r["_provenance"]["body_date"] != r["date"]]
    print(f"  date always from uid prefix        {'PASS' if not bad_date else 'FAIL ' + str(bad_date)}")
    print(f"  no fabricated citation resolution  {'PASS' if not fabricated else 'FAIL ' + str(fabricated)}")
    print(f"  body-date drift observed           {len(drift)}/{n} fixtures")
    for u, bd, ud in drift[:6]:
        print(f"      {u}  body={bd}  uid={ud}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out/parsed.json")
