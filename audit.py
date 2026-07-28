#!/usr/bin/env python3
"""
Step 4 — the dead-reference audit. The demo's headline finding.

    python audit.py --graph out/graph.json --out out/audit.json

## The claim this is built to support

> "N Government Resolutions currently in force cite orders that no longer exist."

Everything below exists so that sentence survives a hostile question from someone who has
worked in Mantralaya for twenty years. Two of the three sections are about *not* overclaiming.

## Operational definitions — chosen, not found in the data

Neither "in force" nor "no longer exists" is a field in any GR. Both are definitions, and the
demo must show the definition next to the number.

**IN FORCE** := the GR has no incoming `SUPERSEDES` edge.

This is an *upper* bound on in-force and therefore a *lower* bound on deadness. It misses GRs
superseded by an order outside our four departments, GRs that expired by their own terms (a
scheme "valid up to 31.03.2020"), and silent supersession where no cancellation language was
used at all. Every one of those makes the real number larger, not smaller — so the figure we
report is conservative, which is the correct direction to be wrong in.

**NO LONGER EXISTS** := the cited target has an incoming `SUPERSEDES` edge.

Split by *when* the supersession happened relative to the citing GR, because the two say
completely different things and merging them would blur the headline:

  ROTTED     the target was superseded AFTER the citing GR was issued. The citing GR was
             correct when written and has silently decayed since. **This is the finding.**
  BORN_DEAD  the target was already superseded when the citing GR was issued — a drafting
             error at the moment of issue. Rarer, and a stronger claim about process.

## The trap this deliberately avoids

There is a much larger, much more tempting population: citations that resolve to **nothing**
(`series_gap`, `number_absent`, `outside_range`). Counting those as dead references would
multiply the headline several times over and make it **false** — the honest explanation for
almost all of them is that the cited order is not in the public crawl. `CLAUDE.md` records a
citation dated 16.01.2018, inside the corpus range and inside its department, whose target is
simply absent.

They are reported here under `unverifiable`, in their own section, with that explanation
attached. A resolver scored on "did it find something" rather than "did it find the right thing"
rewards fabrication; the same is true of an audit.
"""

from __future__ import annotations

import json
import argparse
import datetime
from pathlib import Path
from collections import defaultdict, Counter

import resolver as R


def uid_date(uid: str) -> datetime.date:
    return R.uid_date(uid)


def build_audit(g: dict) -> dict:
    nodes = {n["uid"]: n for n in g["nodes"]}
    edges = g["edges"]

    supersedes = [e for e in edges if e["type"] == "SUPERSEDES"]
    amends = [e for e in edges if e["type"] == "AMENDS"]

    # target -> list of superseding GRs
    killed_by: dict[str, list[str]] = defaultdict(list)
    for e in supersedes:
        killed_by[e["dst"]].append(e["src"])

    def in_force(uid: str) -> bool:
        return uid not in killed_by

    findings, counts = [], Counter()
    seen = set()
    for e in edges:
        if e["type"] == "SUPERSEDES":
            continue                      # the killing edge itself is not a dead reference
        killers = killed_by.get(e["dst"])
        if not killers:
            continue
        citing, target = e["src"], e["dst"]
        if not in_force(citing):
            counts["citing_gr_itself_superseded"] += 1
            continue

        cd = uid_date(citing)
        for k in killers:
            # A GR that cancels an order almost always cites it too — typically once in the
            # reference block and again in the operative sentence, producing both a REFERENCES
            # and a SUPERSEDES edge for the same pair. The REFERENCES half must not be read as
            # that GR citing a dead order: it is the very document doing the killing.
            if k == citing:
                counts["excluded_self_supersession"] += 1
                continue

            # The same citation frequently appears twice in one document (reference block and
            # body), giving duplicate src→dst edges. One legal fact deserves one finding, or the
            # headline inflates on a formatting artefact.
            fp = (citing, target, k)
            if fp in seen:
                counts["excluded_duplicate_citation"] += 1
                continue
            seen.add(fp)

            kd = uid_date(k)
            kind = "ROTTED" if kd > cd else "BORN_DEAD"
            counts[kind] += 1
            findings.append({
                "kind": kind,
                "citing_uid": citing,
                "citing_date": nodes[citing]["date"],
                "citing_dept": nodes[citing]["dept"],
                "citing_subject": nodes[citing]["subject"],
                "target_uid": target,
                "target_date": nodes[target]["date"],
                "target_dept": nodes[target]["dept"],
                "target_subject": nodes[target]["subject"],
                "superseded_by": k,
                "superseded_on": nodes[k]["date"],
                "superseded_by_subject": nodes[k]["subject"],
                "days_dead_when_cited": (cd - kd).days if kind == "BORN_DEAD" else None,
                "days_until_death": (kd - cd).days if kind == "ROTTED" else None,
                "cross_dept_citation": e.get("cross_dept"),
                "cross_dept_supersession": nodes[k]["dept"] != nodes[target]["dept"],
                "citation_evidence": e["evidence"],
                "supersession_evidence": next(
                    (s["evidence"] for s in supersedes
                     if s["src"] == k and s["dst"] == target), None),
                "supersession_evidence_en": next(
                    (s.get("evidence_en") for s in supersedes
                     if s["src"] == k and s["dst"] == target), None),
            })

    # --- LATENT: the cross-departmental case, which is the striking one -----------------
    # A live GR in department A depends on an order in department B that department B has since
    # replaced. No official in either department can see this: it needs a cross-departmental
    # reference edge AND a supersession chain. It is a property of the graph, not of any
    # document, so no amount of reading either GR would reveal it.
    latent = [f for f in findings
              if f["kind"] == "ROTTED" and f["citing_dept"] != f["target_dept"]]

    # --- unverifiable, kept rigorously separate ---------------------------------------
    unver = Counter(u["why"] for u in g["unresolved"])
    unverifiable_total = sum(unver[k] for k in
                             ("series_gap", "number_absent", "date_only_insufficient",
                              "no_number", "ambiguous"))

    superseded_uids = set(killed_by)
    return {
        "definitions": {
            "in_force": "no incoming SUPERSEDES edge within the four indexed departments",
            "dead_reference": "citation whose target has an incoming SUPERSEDES edge",
            "ROTTED": "target superseded AFTER the citing GR was issued — silent decay",
            "BORN_DEAD": "target already superseded when the citing GR was issued",
            "caveat": "conservative by construction: supersession from outside these four "
                      "departments, expiry by a GR's own terms, and silent supersession with no "
                      "cancellation language are all invisible here and would only increase N",
        },
        "graph": {
            "nodes": len(nodes), "edges": len(edges),
            "supersedes_edges": len(supersedes), "amends_edges": len(amends),
            "distinct_superseded_grs": len(superseded_uids),
        },
        "headline": {
            "dead_references": counts["ROTTED"] + counts["BORN_DEAD"],
            "rotted": counts["ROTTED"],
            "born_dead": counts["BORN_DEAD"],
            "latent_cross_department": len(latent),
            "distinct_citing_grs_in_force": len({f["citing_uid"] for f in findings}),
            "excluded_citing_gr_already_superseded": counts["citing_gr_itself_superseded"],
        },
        "unverifiable": {
            "total": unverifiable_total,
            "by_reason": {k: unver[k] for k in sorted(unver)},
            "WARNING": "NOT dead references. These citations could not be resolved, and the "
                       "explanation for almost all is that the cited order is absent from the "
                       "public crawl — not that it was superseded. Never merge with the "
                       "headline; reporting them as dead would multiply the number and make "
                       "it false.",
        },
        "findings": sorted(findings, key=lambda f: (f["kind"] != "ROTTED",
                                                    -(f["days_until_death"] or 0))),
        "latent": latent,
    }


def report(a: dict) -> None:
    h, gr = a["headline"], a["graph"]
    print("=" * 74)
    print("DEAD-REFERENCE AUDIT")
    print("=" * 74)
    print(f"\ngraph: {gr['nodes']:,} GRs · {gr['edges']:,} edges · "
          f"{gr['supersedes_edges']} SUPERSEDES · {gr['amends_edges']} AMENDS")
    print(f"       {gr['distinct_superseded_grs']} distinct GRs superseded")

    print(f"\n{'─'*74}")
    print(f"  DEAD REFERENCES: {h['dead_references']}")
    print(f"    rotted (correct when written, dead now) : {h['rotted']}")
    print(f"    born dead (cited an already-dead order) : {h['born_dead']}")
    print(f"    latent cross-departmental               : {h['latent_cross_department']}")
    print(f"    distinct GRs in force affected          : {h['distinct_citing_grs_in_force']}")
    print(f"{'─'*74}")

    if a["findings"]:
        print("\nfindings (most-decayed first):")
        for f in a["findings"][:10]:
            print(f"\n  [{f['kind']}] {f['citing_uid']}  {f['citing_date']}  "
                  f"({f['citing_dept']})")
            print(f"    cites   {f['target_uid']}  {f['target_date']}  ({f['target_dept']})")
            print(f"            {f['target_subject'][:66]}")
            print(f"    which was superseded on {f['superseded_on']} by {f['superseded_by']}")
            if f["days_until_death"] is not None:
                print(f"            → dead {f['days_until_death']} days after the citing GR "
                      f"was issued")
            if f["days_dead_when_cited"] is not None:
                print(f"            → already dead {f['days_dead_when_cited']} days when cited")
            ev = " ".join((f["supersession_evidence"] or "").split())
            if ev:
                print(f"    evidence: {ev[:100]}")
    else:
        print("\n  No dead references at this corpus scale.")
        print("  This is a real result, not a failure. It means no GR that is still in force")
        print("  cites an order we can PROVE was superseded — and with only "
              f"{gr['supersedes_edges']} SUPERSEDES")
        print("  edges the graph simply has few chances to catch one. Widening the corpus or")
        print("  improving supersession recall raises it; loosening the definition would be")
        print("  fabrication.")

    u = a["unverifiable"]
    print(f"\n{'─'*74}")
    print(f"SEPARATELY — {u['total']:,} unverifiable citations (NOT dead references)")
    for k, v in sorted(u["by_reason"].items(), key=lambda x: -x[1]):
        print(f"    {v:7,}  {k}")
    print("  These could not be resolved. The explanation for almost all is that the cited")
    print("  order is absent from the public crawl, not that it was superseded.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="out/graph.json")
    ap.add_argument("--out", default="out/audit.json")
    a = ap.parse_args()

    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    audit = build_audit(g)
    report(audit)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
