#!/usr/bin/env python3
"""
Every number that may appear in the pitch, regenerated from the artefacts.

    python metrics.py --graph out/graph.json --out out/metrics.json

CLAUDE.md: "Any number that appears in the pitch must be reproducible by a single command."
This is that command.

## What can and cannot be claimed

The project has no HUMAN-labelled answer key (`tests/resolver_truth.json` does not exist). It
does have an **AI-adjudicated** precision audit as of 2026-08-02 — `out/precision_audit.json`,
48/50 on a deliberately hard sample — run at the officer's instruction because no human was
available. `_accuracy()` reports it with `provenance: ai-adjudicated` attached, and that label
must travel with the number every time it is quoted. Auditor and author are the same model.

The three label-free measures below remain the stronger evidence for a sceptical audience,
because none of them depends on anybody's judgement:

* **Ablation** — what the design choice actually buys, measured on this corpus. Unfalsifiable,
  because it is a property of the data rather than of our code.
* **Cross-language agreement** — a *lower bound* on precision from an independent-ish witness.
* **Invariant violations** — a count of structural laws broken. Zero is meaningful.

Recall is still unmeasured, and the audit surfaced a real instance: a citation naming two dates
produces only one edge. Say "unmeasured" for recall rather than inventing a figure.
"""

from __future__ import annotations

import re
import json
import pathlib
import time
import random
import argparse
import datetime
from pathlib import Path
from collections import Counter, defaultdict

import resolver as R
import parser as P

DEV = str.maketrans('०१२३४५६७८९', '0123456789')
CORPUS = Path("data/mahGRs/GRs")


# ---------------------------------------------------------------- ablation

def ablation(g: dict, idx, window: int = 3) -> dict:
    """What do the two keys buy? Re-resolve every shipped edge with each key alone.

    This is the strongest label-free evidence available, because it measures the corpus rather
    than our opinion of our code. `CLAUDE.md` records that a date-only resolver produced 19,840
    edges with five GRs falsely tied at in-degree 292; this quantifies why.
    """
    by_date, by_no, by_key, meta = idx
    c = Counter()
    cand_counts = []

    for e in g["edges"]:
        cd = datetime.date.fromisoformat(e["cited_date"])
        src_d, src = R.uid_date(e["src"]), e["src"]
        cutoff = src_d + datetime.timedelta(days=window)

        win = [u for delta in range(-window, window + 1)
               for u in by_date.get(cd + datetime.timedelta(days=delta), [])
               if u != src and R.uid_date(u) <= cutoff]
        cand_counts.append(len(win))
        c["date_unique" if len(win) == 1 else
          "date_ambiguous" if len(win) > 1 else "date_none"] += 1
        if len(win) == 1 and win[0] != e["dst"]:
            c["date_unique_but_wrong"] += 1

        no = e["cited_no"]
        series = [u for u in by_no.get(R.norm_no(no), []) if u != src] if no else []
        if not series and no and R.digit_key(no):
            series = [u for u in by_key.get(R.digit_key(no), []) if u != src]
        c["number_unique" if len(series) == 1 else
          "number_ambiguous" if len(series) > 1 else "number_none"] += 1
        if len(series) == 1 and series[0] != e["dst"]:
            c["number_unique_but_wrong"] += 1

    n = max(len(g["edges"]), 1)
    return {
        "edges": len(g["edges"]),
        "date_only": {
            "unique": c["date_unique"], "unique_pct": round(100 * c["date_unique"] / n, 1),
            "ambiguous": c["date_ambiguous"],
            "ambiguous_pct": round(100 * c["date_ambiguous"] / n, 1),
            "unique_but_wrong": c["date_unique_but_wrong"],
            "mean_candidates": round(sum(cand_counts) / n, 1),
            "max_candidates": max(cand_counts) if cand_counts else 0,
        },
        "number_only": {
            "unique": c["number_unique"], "unique_pct": round(100 * c["number_unique"] / n, 1),
            "ambiguous": c["number_ambiguous"],
            "ambiguous_pct": round(100 * c["number_ambiguous"] / n, 1),
            "unique_but_wrong": c["number_unique_but_wrong"],
            "no_match": c["number_none"],
        },
        "both_keys": {"unique": len(g["edges"]), "ambiguous": 0,
                      "note": "ambiguity abstains by design; abstentions counted in unresolved[]"},
    }


# ---------------------------------------------------------------- cross-language agreement

def _runs(s: str | None) -> tuple:
    return tuple(r.lstrip('0') or '0' for r in re.findall(r'\d+', (s or '').translate(DEV)))


def cross_language(g: dict) -> dict:
    """Does the English translation independently agree with the Marathi-side resolution?

    **A lower bound on precision, not a point estimate.** Disagreement can be caused by either
    side, and inspection shows the English side failing far more often — IndicTrans2 drops or
    mangles file numbers (`भाग-१` → "Part-I", the digit becoming a Roman numeral; the number
    replaced outright by the date). Those cost us agreement without any resolver error.

    Also not a fully independent witness: the English is machine translation *of the same
    Marathi*. It is the best label-free signal this corpus offers, and it is quoted with that
    caveat attached — see AI_ARCHITECTURE.md §3.
    """
    en_files = {}
    for d in sorted(CORPUS.glob("*_Department")):
        for f in d.glob("*.en.txt"):
            en_files[f.name.split('.')[0]] = f

    meta = {n["uid"]: n for n in g["nodes"]}
    by_src = defaultdict(list)
    for e in g["edges"]:
        by_src[e["src"]].append(e)

    def is_date(no, cd):
        dg = R.digit_key(no)
        if not dg:
            return False
        y, m, d = cd.split('-')
        return dg in {f"{d}{m}{y}", f"{y}{m}{d}", f"{d.lstrip('0')}{m.lstrip('0')}{y}"}

    c = Counter()
    residual = []
    for src, edges in by_src.items():
        f = en_files.get(src)
        if not f:
            c["no_en_file"] += len(edges)
            continue
        try:
            rec = P.parse(f.read_text(encoding='utf-8', errors='ignore'), src)
        except Exception:
            c["parse_error"] += len(edges)
            continue
        en_by_date = defaultdict(list)
        for ref in rec["references"]:
            if ref["date"]:
                en_by_date[ref["date"]].append(ref["decision_no"])

        for e in edges:
            nos = en_by_date.get(e["cited_date"])
            if not nos:
                c["en_silent"] += 1
                continue
            tgt = meta.get(e["dst"], {}).get("decision_no", "")
            tk = R.digit_key(tgt)
            if not tk:
                c["target_has_no_number"] += 1
                continue
            eks = [R.digit_key(n) for n in nos if n and not is_date(n, e["cited_date"])]
            eks = [k for k in eks if k]
            if not eks:
                c["en_states_no_number"] += 1
                continue
            if any(k in tk or tk in k for k in eks):
                c["agree"] += 1
                continue
            # Second chance with leading zeros stripped and English-dropped components allowed:
            # `भाग-१` rendering as "Part-I" loses the digit entirely, which is a translation
            # artefact rather than a different file.
            tr = set(_runs(tgt))
            if any(_runs(n) and set(_runs(n)) <= tr for n in nos if n):
                c["agree_after_normalisation"] += 1
            else:
                c["residual_disagreement"] += 1
                residual.append({"src": src, "cited_date": e["cited_date"], "dst": e["dst"],
                                 "target_no": tgt, "english_no": nos[:2]})

    agree = c["agree"] + c["agree_after_normalisation"]
    comparable = agree + c["residual_disagreement"]
    return {
        "comparable_edges": comparable,
        "comparable_pct_of_edges": round(100 * comparable / max(len(g["edges"]), 1), 1),
        "agree_exact": c["agree"],
        "agree_after_normalisation": c["agree_after_normalisation"],
        "residual_disagreement": c["residual_disagreement"],
        "agreement_lower_bound_pct": round(100 * agree / max(comparable, 1), 2),
        "not_comparable": {k: v for k, v in c.items()
                           if k.startswith(("en_", "no_", "target_", "parse_"))},
        "residual_sample": residual[:15],
        "interpretation": "LOWER BOUND on precision. Disagreement may originate on either "
                          "side; inspection shows the English translation failing more often. "
                          "Not a substitute for a hand-labelled accuracy figure.",
    }


# ---------------------------------------------------------------- evidence groundedness

def groundedness(g: dict, sample: int = 600, seed: int = 0) -> dict:
    """Fraction of sampled edges whose evidence sentence really occurs in the source document.

    This is the one promise in CLAUDE.md that is purely mechanical — "if we cannot show the judge
    the sentence, the edge does not ship" — so it should be measured, not asserted.
    """
    cache: dict[str, str | None] = {}
    dirs = [p for p in CORPUS.iterdir() if p.is_dir()] if CORPUS.exists() else []

    def text_of(uid):
        if uid not in cache:
            cache[uid] = None
            for d in dirs:
                f = d / f"{uid}.pdf.mr.txt"
                if f.exists():
                    cache[uid] = " ".join(
                        f.read_text(encoding='utf-8', errors='ignore').split())
                    break
        return cache[uid]

    random.seed(seed)
    edges = random.sample(g["edges"], min(sample, len(g["edges"])))
    ok = bad = unread = 0
    failures = []
    for e in edges:
        t = text_of(e["src"])
        if t is None:
            unread += 1
        elif " ".join((e["evidence"] or "").split()) in t:
            ok += 1
        else:
            bad += 1
            failures.append({"src": e["src"], "evidence": (e["evidence"] or "")[:100]})
    checked = ok + bad
    return {"sampled": len(edges), "checked": checked, "verbatim": ok, "not_verbatim": bad,
            "unreadable_source": unread,
            "groundedness_pct": round(100 * ok / max(checked, 1), 2),
            "failures": failures[:5]}


# ---------------------------------------------------------------- structural laws

def invariants(g: dict, window: int = 3) -> dict:
    """Count violations of laws that must hold regardless of which uid is the right answer.
    Zero violations over thousands of edges is a real, if narrow, correctness claim."""
    uids = {n["uid"] for n in g["nodes"]}
    w = datetime.timedelta(days=window)
    v = {
        "self_edges": sum(1 for e in g["edges"] if e["src"] == e["dst"]),
        "endpoint_not_a_node": sum(1 for e in g["edges"]
                                   if e["src"] not in uids or e["dst"] not in uids),
        "forward_in_time": sum(1 for e in g["edges"]
                               if R.uid_date(e["dst"]) > R.uid_date(e["src"]) + w),
        "type_out_of_vocabulary": sum(1 for e in g["edges"]
                                      if e["type"] not in ("REFERENCES", "AMENDS", "SUPERSEDES")),
        "empty_evidence": sum(1 for e in g["edges"] if not (e.get("evidence") or "").strip()),
        "typed_without_cue": sum(1 for e in g["edges"]
                                 if e["type"] in ("AMENDS", "SUPERSEDES") and not e.get("cue")),
        "confidence_out_of_range": sum(1 for e in g["edges"]
                                       if not 0.0 < e["confidence"] <= 1.0),
        "citations_lost": (g["meta"]["stats"]["citations"]
                           - len(g["edges"]) - len(g["unresolved"])),
    }
    return {"violations": v, "total_violations": sum(v.values()),
            "edges_checked": len(g["edges"])}


# ---------------------------------------------------------------- scale & refusals

def scale(g: dict) -> dict:
    m = g["meta"]
    return {
        "departments": len(m["departments"]),
        "grs_indexed": m["nodes"],
        "documents_scanned": m["documents_scanned"],
        "citations_extracted": m["stats"]["citations"],
        "documents_with_citations": m["stats"]["docs_with_citations"],
        "edges": m["edges"],
        "cross_department_edges": m["cross_dept_edges"],
        "cross_department_pct": round(100 * m["cross_dept_edges"] / max(m["edges"], 1), 1),
        "nodes_touched_by_an_edge": m["nodes_touched_by_an_edge"],
        "index_covers": m["index_covers"],
        "skipped_malformed_uid": m["stats"].get("skipped_malformed_uid", 0),
    }


def refusals(g: dict) -> dict:
    """Unresolved citations, by machine-readable reason.

    Deliberately NOT presented as a failure rate. `date_only_insufficient` is a *correct
    refusal* — the same-date collision trap — and `series_gap` means the cited GR is absent from
    the public crawl. A resolver that guessed would score better on a naive "resolution rate",
    which is exactly why rule 3 exists.
    """
    by = Counter(u["why"] for u in g["unresolved"])
    total = len(g["unresolved"]) + len(g["edges"])
    return {
        "unresolved": len(g["unresolved"]),
        "by_reason": dict(by.most_common()),
        "resolution_rate_pct_DO_NOT_QUOTE_ALONE": round(100 * len(g["edges"]) / max(total, 1), 1),
        "note": "resolution rate is not an accuracy metric. Most unresolved citations cannot "
                "resolve for structural reasons (not a GR, outside the crawl, another "
                "department). Quote the breakdown, never the bare rate.",
    }


def _accuracy() -> dict:
    """The precision figure, if an audit has been run — with its provenance attached.

    Two states, and the difference is not cosmetic:

    * **`hand-labelled`** — a human adjudicated the sample. This is what CLAUDE.md's rule asks
      for and the only kind that is ground truth.
    * **`ai-adjudicated`** — Claude adjudicated it, at the officer's instruction, because no
      human was available. Auditor and author are the same model, so shared blind spots cannot
      be ruled out. It is materially better than nothing and materially worse than a human, and
      the `provenance` field says so wherever the number is quoted.

    An absent audit still reports UNMEASURED. Nothing here invents a figure.
    """
    import json as _json
    f = pathlib.Path(__file__).resolve().parent / "out" / "precision_audit.json"
    if not f.exists():
        return {"value": None,
                "status": "UNMEASURED — run: python audit_precision.py, then adjudicate",
                "note": "Do not quote an accuracy figure. Quote ablation, cross-language "
                        "agreement (a lower bound) and invariant violations instead."}
    a = _json.loads(f.read_text(encoding="utf-8"))
    return {
        "value": a["precision_conservative"],
        "status": f"{a['correct']}/{a['sample']} on a sample weighted towards the hard paths",
        "provenance": "ai-adjudicated, NOT human ground truth — see out/precision_audit.json",
        "demonstrably_wrong": a["wrong"],
        "uncertain_counted_as_error": a["uncertain_counted_as_error"],
        "by_stratum": a["by_stratum"],
        "note": ("The sample deliberately over-weights digit-key, cross-department, "
                 "date-drifted and inherited-number edges, so this UNDERSTATES precision over "
                 "the graph as a whole: 88.6% of all edges have an exact date match and were "
                 "not sampled at that rate. Quote per stratum, and quote the provenance."),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="out/graph.json")
    ap.add_argument("--out", default="out/metrics.json")
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--skip-slow", action="store_true",
                    help="skip cross-language agreement (the only pass that reads 2.5k files)")
    a = ap.parse_args()

    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    idx = R.load_index(sorted(CORPUS.glob("*_Department")))

    t0 = time.time()
    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "graph_built_at": g["meta"]["built_at"],
        "accuracy": _accuracy(),
        "scale": scale(g),
        "ablation": ablation(g, idx, a.window),
        "invariants": invariants(g, a.window),
        "groundedness": groundedness(g),
        "refusals": refusals(g),
    }
    if not a.skip_slow:
        out["cross_language"] = cross_language(g)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    ab, iv, gr = out["ablation"], out["invariants"], out["groundedness"]
    print("=" * 74)
    print("METRICS — every figure below is reproducible by this command")
    print("=" * 74)
    s = out["scale"]
    print(f"\nSCALE   {s['grs_indexed']:,} GRs · {s['departments']} departments · "
          f"{s['citations_extracted']:,} citations · {s['edges']:,} edges")
    print(f"        {s['cross_department_edges']:,} cross-departmental "
          f"({s['cross_department_pct']}%)")

    print(f"\nABLATION — what the two-key design buys ({ab['edges']:,} edges)")
    d, nn = ab["date_only"], ab["number_only"]
    print(f"  date alone   : {d['ambiguous_pct']}% ambiguous · "
          f"mean {d['mean_candidates']} candidates · worst {d['max_candidates']}")
    print(f"  number alone : {nn['ambiguous_pct']}% ambiguous · "
          f"{nn['unique_pct']}% unique · {nn['no_match']:,} no match")
    print(f"  both keys    : unique by construction, ambiguity abstains")

    print(f"\nINVARIANTS   {iv['total_violations']} violations over "
          f"{iv['edges_checked']:,} edges")
    for k, n in iv["violations"].items():
        print(f"    {'✓' if n == 0 else '✗'} {k}: {n}")

    print(f"\nEVIDENCE     {gr['groundedness_pct']}% of {gr['checked']} sampled edges have "
          f"verbatim evidence in the source document")

    if "cross_language" in out:
        x = out["cross_language"]
        print(f"\nCROSS-LANGUAGE AGREEMENT (lower bound on precision)")
        print(f"  {x['agreement_lower_bound_pct']}% over {x['comparable_edges']:,} comparable "
              f"edges ({x['comparable_pct_of_edges']}% of all edges)")
        print(f"  exact {x['agree_exact']:,} · after normalisation "
              f"{x['agree_after_normalisation']:,} · residual {x['residual_disagreement']:,}")

    print(f"\nACCURACY     {out['accuracy']['status']}")
    print(f"\n({time.time()-t0:.0f}s)  wrote {a.out}")


if __name__ == "__main__":
    main()
