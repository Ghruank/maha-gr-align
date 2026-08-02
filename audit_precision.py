#!/usr/bin/env python3
"""
Assemble adjudication packets for a precision audit of the resolver.

    python audit_precision.py --n 50 --out out/precision_packets.json

## What this does and does not do

It does NOT decide anything. It pulls, for each sampled edge, the evidence an adjudicator needs
to judge it independently of how the resolver arrived at it:

  * the verbatim Marathi citation, as it appears in the citing document
  * the target's `order_number`, `text` and `date` **from `GRs.json`** — crawled portal metadata,
    produced by a different pipeline than our OCR text, so agreeing with it is real evidence
  * the date delta, the citing GR's own subject, and the other candidates that were available

The last item is what makes this an audit rather than a confirmation. A resolver can be wrong in
two ways: it can pick a document that is not the cited one, and it can pick one document when
another was equally good. The packet shows every candidate that shared the file number so the
second failure is visible.

## The stratification, and why it is not a uniform sample

A uniform sample of 4,815 edges would be ~95% `exact number + date`, which is the easy case, and
would report a precision that says almost nothing about the hard ones. The sample is therefore
weighted towards the paths most likely to be wrong:

  * `digit key` matches, where letters could not be compared because one side was transliterated
  * cross-departmental edges, where a file number could collide across departments
  * edges whose date drifted furthest from the citation
  * `समक्रमांक` inheritances, where the number came from the citing GR rather than the citation

Per-stratum precision is reported separately. A single blended number over a deliberately
skewed sample would understate the true rate and would be the wrong kind of dishonest.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import resolver as R

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "mahGRs" / "GRs"


def _portal_meta() -> dict[str, dict]:
    """uid -> crawled metadata. Independent of our OCR: this is what the portal published."""
    out: dict[str, dict] = {}
    for f in sorted(CORPUS.glob("*/GRs.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8")).items():
            uid = k.split(".")[0]
            if len(uid) == 18 and uid.isdigit():
                out[uid] = v
    return out


def stratum(e: dict) -> str:
    how = (e.get("how") or "").lower()
    if "समक्रमांक" in (e.get("how") or ""):
        return "inherited_number"
    if e.get("cross_dept"):
        return "cross_department"
    if "digit key" in how:
        return "digit_key"
    if "+0d" not in how and "d)" in how:
        return "date_drifted"
    return "exact_number"


def build(graph: dict, n: int, seed: int) -> list[dict]:
    meta = _portal_meta()
    nodes = {x["uid"]: x for x in graph["nodes"]}
    by_stratum: dict[str, list] = defaultdict(list)
    for e in graph["edges"]:
        by_stratum[stratum(e)].append(e)

    # Oversample the hard paths; `exact_number` fills whatever is left.
    quota = {"digit_key": 14, "cross_department": 12, "date_drifted": 8,
             "inherited_number": 6, "exact_number": 10}
    rng = random.Random(seed)
    picked: list[dict] = []
    for s, want in quota.items():
        pool = by_stratum.get(s, [])
        picked += rng.sample(pool, min(want, len(pool)))
    picked = picked[:n]

    # Every GR sharing the target's file number: the "was there a better candidate" check.
    by_key: dict[str, list[str]] = defaultdict(list)
    for uid, m in meta.items():
        k = R.digit_key((m.get("order_number") or ""))
        if k:
            by_key[k].append(uid)

    packets = []
    for i, e in enumerate(picked, 1):
        src, dst = e["src"], e["dst"]
        tm, sm = meta.get(dst, {}), meta.get(src, {})
        key = R.digit_key(e.get("cited_no"))
        siblings = [u for u in by_key.get(key, []) if u != dst][:8]
        packets.append({
            "n": i,
            "stratum": stratum(e),
            "citing": {"uid": src, "date": nodes.get(src, {}).get("date"),
                       "dept": nodes.get(src, {}).get("dept"),
                       "own_number": sm.get("order_number"),
                       "subject": (sm.get("text") or "")[:220]},
            "citation_text": " ".join((e.get("evidence") or "").split())[:400],
            "cited_no_extracted": e.get("cited_no"),
            "cited_date_extracted": e.get("cited_date"),
            "digit_key": key,
            "resolved_to": {
                "uid": dst, "date": nodes.get(dst, {}).get("date"),
                "dept": nodes.get(dst, {}).get("dept"),
                "portal_order_number": tm.get("order_number"),
                "portal_subject": (tm.get("text") or "")[:260],
                "portal_date": tm.get("date"),
            },
            "date_delta_days": _delta(e.get("cited_date"), nodes.get(dst, {}).get("date")),
            "how": e.get("how"),
            "confidence": e.get("confidence"),
            "other_gr_with_same_file_number": [
                {"uid": u, "date": meta[u].get("date"),
                 "subject": (meta[u].get("text") or "")[:110]} for u in siblings],
        })
    return packets


def _delta(cited: str | None, actual: str | None) -> int | None:
    if not cited or not actual:
        return None
    import datetime
    try:
        return (datetime.date.fromisoformat(actual)
                - datetime.date.fromisoformat(cited)).days
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="out/graph.json")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--out", default="out/precision_packets.json")
    a = ap.parse_args()

    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    packets = build(g, a.n, a.seed)
    Path(a.out).write_text(json.dumps(packets, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"{len(packets)} packets -> {a.out}")
    for s, c in Counter(p["stratum"] for p in packets).most_common():
        print(f"  {c:3d}  {s}")


if __name__ == "__main__":
    main()
