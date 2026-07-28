#!/usr/bin/env python3
"""
Step 3 — build the GR dependency graph.

    python graph.py data/mahGRs/GRs --out out/graph.json

The thesis made concrete: a GR is a node in a legal dependency graph. This module turns
17,000+ documents into that graph and is the only thing steps 4-9 read.

Fully deterministic. No model is called here — every edge is produced by `resolver.py` from a
Marathi citation string and a matched file-number/date pair. AI edge *typing* runs as a separate
pass (`type_edges.py`) which only ever upgrades an existing edge's type; it cannot invent one.

Three design rules worth knowing before changing anything:

1. **Nodes come from the index, not from the edges.** A GR nothing cites is a real finding, and
   building nodes only where edges land would silently erase it.
2. **Unresolvable citations stay in the file.** `unresolved[]` is a first-class output. Dropping
   it would make the graph look complete and would quietly delete the honesty caveat the
   dead-reference audit depends on (CLAUDE.md rule 3).
3. **Every edge carries the verbatim Marathi sentence that produced it.** If we cannot show the
   judge the sentence, the edge does not ship.
"""

from __future__ import annotations

import re
import json
import time
import argparse
import datetime
from pathlib import Path
from collections import defaultdict, Counter

import resolver as R

EDGE_TYPES = ("REFERENCES", "AMENDS", "SUPERSEDES")
UID_RE = re.compile(r'\d{18}')


def build(corpus_root: Path, window: int = 3, limit: int | None = None,
          progress_every: int = 2000) -> dict:
    dirs = sorted(p for p in Path(corpus_root).iterdir()
                  if p.is_dir() and (p / "GRs.json").exists())
    if not dirs:
        raise SystemExit(f"no department directories with GRs.json under {corpus_root}")

    t0 = time.time()
    idx = R.load_index(dirs)
    in_index = R.indexed_depts(idx)
    meta = idx[3]
    print(f"indexed {len(meta):,} GRs across {len(dirs)} departments "
          f"({', '.join(sorted(in_index))}) in {time.time()-t0:.1f}s")

    files = []
    for d in dirs:
        files.extend(sorted(d.glob("*.mr.txt")))
    if limit:
        files = files[:limit]
    print(f"extracting citations from {len(files):,} Marathi documents…")

    edges, unresolved = [], []
    stats = Counter()
    t0 = time.time()

    for n, f in enumerate(files, 1):
        uid = f.name.split('.')[0]

        # 19 of 17,253 filenames carry a 20-digit uid instead of 18. They are absent from
        # GRs.json, so they have no metadata and cannot become nodes — and a 20-digit uid also
        # makes the trailing 2-digit department code meaningless. `load_index` already filters
        # them; doing the same here keeps edges and nodes consistent. Counted, never silent:
        # a caught-and-reported 0.1% is fine, an unreported one is a hole in the graph.
        if not UID_RE.fullmatch(uid):
            stats["skipped_malformed_uid"] += 1
            continue

        try:
            text = f.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            stats["unreadable"] += 1
            continue

        cits = R.extract_mr_citations(text)
        stats["citations"] += len(cits)
        if cits:
            stats["docs_with_citations"] += 1

        for c in cits:
            res = R.resolve(c, uid, idx, window, in_index=in_index)
            dst = res["resolved_uid"]
            if dst:
                edges.append({
                    "src": uid, "dst": dst,
                    "type": "REFERENCES",          # AI typing may upgrade this, never invent it
                    "confidence": res["confidence"],
                    "evidence": c["raw"],
                    "evidence_en": None,           # filled on demand in the UI, not precomputed
                    "evidence_kind": "citation",
                    "cue": None,
                    "cited_date": c["cited_date"],
                    "cited_no": c["cited_no"],
                    "how": res["reason"],
                    "cross_dept": meta[uid]["dept"] != meta[dst]["dept"]
                    if uid in meta and dst in meta else None,
                })
                stats["resolved"] += 1
            else:
                unresolved.append({
                    "src": uid, "cited_date": c["cited_date"], "cited_no": c["cited_no"],
                    "cited_dept": c["cited_dept"], "is_gr": c["is_gr"],
                    "evidence": c["raw"], "why": _why(res["reason"]),
                    "reason": res["reason"], "candidates": res["candidates"][:5],
                })
                stats["unresolved"] += 1

        if n % progress_every == 0:
            rate = n / max(time.time() - t0, 1e-9)
            print(f"  {n:,}/{len(files):,}  edges={stats['resolved']:,}  "
                  f"unresolved={stats['unresolved']:,}  ({rate:.0f} docs/s)")

    print(f"extraction done in {time.time()-t0:.1f}s")

    # Degrees are computed here so consumers never have to walk every edge to rank a node.
    indeg, outdeg = Counter(), Counter()
    for e in edges:
        outdeg[e["src"]] += 1
        indeg[e["dst"]] += 1

    cited = set(indeg) | set(outdeg)
    nodes = [{
        "uid": uid, "date": m["date"].isoformat(), "dept": m["dept"],
        "dept_code": m["dept_code"], "decision_no": m["no"], "subject": m["subject"],
        "in_degree": indeg.get(uid, 0), "out_degree": outdeg.get(uid, 0),
        "in_corpus": True,
    } for uid, m in sorted(meta.items())]

    dates = [m["date"] for m in meta.values()]
    return {
        "meta": {
            "built_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "corpus": str(corpus_root),
            "departments": sorted(in_index),
            "window_days": window,
            "index_covers": [min(dates).isoformat(), max(dates).isoformat()],
            "documents_scanned": len(files),
            "nodes": len(nodes), "edges": len(edges), "unresolved": len(unresolved),
            "nodes_touched_by_an_edge": len(cited),
            "edge_types": {t: sum(1 for e in edges if e["type"] == t) for t in EDGE_TYPES},
            "cross_dept_edges": sum(1 for e in edges if e.get("cross_dept")),
            "stats": dict(stats),
        },
        "nodes": nodes,
        "edges": edges,
        "unresolved": unresolved,
    }


def _why(reason: str) -> str:
    """Collapse the resolver's prose reason into a stable machine label.

    The distinction that matters most is `series_gap` vs everything else: the file number matched
    a real series but no member landed in the date window, which per the in-range-gap finding
    means the cited GR is genuinely absent from the crawl. Those must never be reported as dead
    references — they are unverifiable, which is a different and weaker claim.
    """
    if "outside this index" in reason:
        return "other_dept"
    if "series but no member" in reason:
        return "series_gap"
    if "ambiguous" in reason:
        return "ambiguous"
    if "no file number" in reason:
        return "no_number"
    if "date-only match" in reason:
        return "date_only_insufficient"
    if "matches no GR in corpus" in reason:
        return "number_absent"
    return "other"


def report(g: dict) -> None:
    m = g["meta"]
    print("\n" + "=" * 72)
    print(f"GRAPH  {m['nodes']:,} nodes   {m['edges']:,} edges   "
          f"{m['unresolved']:,} unresolved citations")
    print("=" * 72)
    print(f"  documents scanned      : {m['documents_scanned']:,}")
    print(f"  index covers           : {m['index_covers'][0]} → {m['index_covers'][1]}")
    print(f"  nodes touched by edge  : {m['nodes_touched_by_an_edge']:,} "
          f"({100*m['nodes_touched_by_an_edge']/max(1,m['nodes']):.1f}%)")
    print(f"  CROSS-DEPARTMENT edges : {m['cross_dept_edges']:,}")
    print(f"  edge types             : {m['edge_types']}")

    print("\nwhy citations went unresolved:")
    for why, n in Counter(u["why"] for u in g["unresolved"]).most_common():
        print(f"  {n:7,}  {why}")

    print("\ncross-department flow (src dept → dst dept):")
    flow = Counter((e["src"][-2:], e["dst"][-2:]) for e in g["edges"] if e.get("cross_dept"))
    for (a, b), n in flow.most_common(12):
        print(f"  {n:6,}  {R.DEPT_BY_CODE.get(a,a):32s} → {R.DEPT_BY_CODE.get(b,b)}")

    print("\nmost-cited GRs (in-degree) — the load-bearing orders:")
    for nd in sorted(g["nodes"], key=lambda x: -x["in_degree"])[:8]:
        print(f"  {nd['in_degree']:5,}  {nd['uid']}  {nd['date']}  "
              f"{(nd['dept'] or '?')[:22]:22s} {nd['subject'][:52]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus_root", help="directory containing the per-department GR folders")
    ap.add_argument("--out", default="out/graph.json")
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--limit", type=int, help="scan only the first N documents (smoke test)")
    a = ap.parse_args()

    g = build(Path(a.corpus_root), a.window, a.limit)
    report(g)

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {p}  ({p.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
