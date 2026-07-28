#!/usr/bin/env python3
"""
MAHA-GR-ALIGN backend. Serves the cached artefacts to the React frontend.

    .venv/bin/uvicorn api:app --reload --port 8000

## Design rules

**Read-only over precomputed artefacts.** Nothing here computes a finding on request; it serves
`out/*.json` built by `graph.py`, `type_edges.py`, `audit.py` and `metrics.py`. That is what makes
the demo instant and network-independent — the expensive work already happened. A route that
needed to resolve citations live would be a route that can be slow or wrong on stage.

**The graph is never shipped whole.** `out/graph.json` is 25 MB; 17,283 nodes would freeze a
browser and tell a judge nothing. Every graph route returns a bounded neighbourhood or a filtered
page, and the client renders subgraphs.

**Evidence travels with every claim.** Any route returning an edge returns the verbatim Marathi
sentence behind it, plus its verification badge where one exists. If a route could show a
conclusion without its evidence, that route is wrong (CLAUDE.md).

**Absent artefacts degrade.** A missing file yields an empty, well-formed payload and an
`available: false` flag rather than a 500, so the UI can grey out a page instead of breaking.
"""

from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict, Counter
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="MAHA-GR-ALIGN", version="0.1",
              description="Government Resolution dependency graph for Maharashtra")

# Vite dev server runs on 5173; in production the build is served from this same origin.
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173",
                                                  "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------- artefacts

def _load(name: str):
    f = OUT / name
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


class Store:
    """Artefacts plus the lookup indexes the routes need. Built once at import."""

    def __init__(self):
        self.graph = _load("graph.json") or {"meta": {}, "nodes": [], "edges": [],
                                             "unresolved": []}
        self.audit = _load("audit.json")
        self.metrics = _load("metrics.json")
        self.typed = _load("typed_edges.json") or []
        self.rejections = _load("ai_rejections.json") or []

        self.nodes = {n["uid"]: n for n in self.graph["nodes"]}
        self.out_edges = defaultdict(list)
        self.in_edges = defaultdict(list)
        for i, e in enumerate(self.graph["edges"]):
            e["_i"] = i
            self.out_edges[e["src"]].append(e)
            self.in_edges[e["dst"]].append(e)

        # unresolved citations, by citing GR — needed so a node view can show what it cites
        # that we could NOT verify. Hiding these would make every node look fully resolved.
        self.unresolved_by_src = defaultdict(list)
        for u in self.graph["unresolved"]:
            self.unresolved_by_src[u["src"]].append(u)

        # verification verdicts keyed by (src, dst) for badges in the UI
        self.verdicts = {}
        for t in self.typed:
            self.verdicts[(t["src"], t["dst"])] = {
                "verdict": t.get("verdict"), "proposed_type": t.get("proposed_type"),
                "type": t.get("type"), "notes": t.get("notes", []),
                "gates": t.get("gates", {}), "gloss_en": t.get("gloss_en"),
                "confidence": t.get("confidence"),
            }

    def edge_out(self, e: dict) -> dict:
        """Serialisable edge, always carrying evidence and any verification badge."""
        return {
            "index": e["_i"], "src": e["src"], "dst": e["dst"], "type": e["type"],
            "confidence": e["confidence"], "evidence": e["evidence"],
            "evidence_en": e.get("evidence_en"), "cue": e.get("cue"),
            "evidence_kind": e.get("evidence_kind"), "cross_dept": e.get("cross_dept"),
            "cited_date": e.get("cited_date"), "cited_no": e.get("cited_no"),
            "how": e.get("how"),
            "src_dept": (self.nodes.get(e["src"]) or {}).get("dept"),
            "dst_dept": (self.nodes.get(e["dst"]) or {}).get("dept"),
            "dst_subject": (self.nodes.get(e["dst"]) or {}).get("subject"),
            "src_subject": (self.nodes.get(e["src"]) or {}).get("subject"),
            "dst_date": (self.nodes.get(e["dst"]) or {}).get("date"),
            "src_date": (self.nodes.get(e["src"]) or {}).get("date"),
            "verification": self.verdicts.get((e["src"], e["dst"])),
        }


S = Store()


# --------------------------------------------------------------------------- meta

@app.get("/api/health")
def health():
    """What the UI may offer. Reads the AI roster so a page for an unconfigured capability can
    be greyed out rather than failing on click."""
    try:
        from ai.client import configured_roles, cache_stats, MODE
        ai = {"mode": MODE, "roles": configured_roles(), "cache": cache_stats()}
    except Exception as exc:
        ai = {"error": str(exc)}
    return {
        "ok": True,
        "artefacts": {
            "graph": bool(S.graph["edges"]), "audit": S.audit is not None,
            "metrics": S.metrics is not None, "typed_edges": bool(S.typed),
            "trust_ledger": bool(S.rejections),
        },
        "graph_meta": S.graph.get("meta", {}),
        "ai": ai,
    }


@app.get("/api/metrics")
def metrics():
    if S.metrics is None:
        return {"available": False}
    return {"available": True, **S.metrics}


@app.get("/api/overview")
def overview():
    """Everything the landing page needs, in one round trip.

    Deliberately leads with findings rather than capabilities — the tiles are a dead-reference
    count and a cross-departmental edge count, not a feature list."""
    m = S.graph.get("meta", {})
    head = (S.audit or {}).get("headline", {})
    unver = (S.audit or {}).get("unverifiable", {})
    by_dept = Counter(n["dept"] for n in S.graph["nodes"] if n.get("dept"))
    flows = Counter()
    for e in S.graph["edges"]:
        if e.get("cross_dept"):
            flows[f'{S.nodes[e["src"]]["dept"]} → {S.nodes[e["dst"]]["dept"]}'] += 1
    return {
        "scale": {
            "grs": m.get("nodes", 0), "departments": len(m.get("departments", [])),
            "citations": m.get("stats", {}).get("citations", 0),
            "edges": m.get("edges", 0),
            "cross_dept_edges": m.get("cross_dept_edges", 0),
            "index_covers": m.get("index_covers"),
            "by_department": dict(by_dept.most_common()),
        },
        "edge_types": m.get("edge_types", {}),
        "findings": head,
        "unverifiable": {"total": unver.get("total", 0),
                         "by_reason": unver.get("by_reason", {}),
                         "warning": unver.get("WARNING")},
        "cross_dept_flows": dict(flows.most_common(10)),
        "ai_typing": m.get("ai_typing", {}),
    }


# --------------------------------------------------------------------------- nodes

@app.get("/api/nodes")
def nodes(q: str | None = None, dept: str | None = None,
          type_: str | None = Query(None, alias="type"),
          min_in_degree: int = 0, sort: str = "in_degree",
          limit: int = Query(50, le=500), offset: int = 0):
    """Filtered, paginated node search. Never returns the whole node set."""
    rows = S.graph["nodes"]
    if dept:
        rows = [n for n in rows if n.get("dept") == dept]
    if q:
        ql = q.lower()
        rows = [n for n in rows
                if ql in (n.get("subject") or "").lower()
                or ql in (n.get("decision_no") or "").lower()
                or ql in n["uid"]]
    if min_in_degree:
        rows = [n for n in rows if n["in_degree"] >= min_in_degree]
    if type_:
        want = {e["src"] for e in S.graph["edges"] if e["type"] == type_} | \
               {e["dst"] for e in S.graph["edges"] if e["type"] == type_}
        rows = [n for n in rows if n["uid"] in want]

    key = {"in_degree": lambda n: -n["in_degree"],
           "out_degree": lambda n: -n["out_degree"],
           "date": lambda n: n["date"]}.get(sort, lambda n: -n["in_degree"])
    rows = sorted(rows, key=key)
    return {"total": len(rows), "offset": offset, "limit": limit,
            "nodes": rows[offset:offset + limit]}


@app.get("/api/node/{uid}")
def node(uid: str):
    n = S.nodes.get(uid)
    if not n:
        raise HTTPException(404, f"GR {uid} not in the index")
    return {
        "node": n,
        "cites": [S.edge_out(e) for e in S.out_edges.get(uid, [])],
        "cited_by": [S.edge_out(e) for e in S.in_edges.get(uid, [])],
        # unresolved citations belong on the node view: a GR that cites five orders we could not
        # verify should not look like a GR that cites nothing.
        "unresolved_citations": S.unresolved_by_src.get(uid, []),
        "in_force": not any(e["type"] == "SUPERSEDES" for e in S.in_edges.get(uid, [])),
        "superseded_by": [S.edge_out(e) for e in S.in_edges.get(uid, [])
                          if e["type"] == "SUPERSEDES"],
    }


@app.get("/api/subgraph/{uid}")
def subgraph(uid: str, depth: int = Query(1, ge=1, le=3),
             max_nodes: int = Query(120, le=400)):
    """Bounded neighbourhood for the graph view.

    Breadth-first over both directions, capped hard. The cap matters: the most-cited node has
    in-degree 209, and an uncapped 2-hop expansion from a Finance appropriation order would pull
    in thousands of nodes and render as an unreadable hairball.
    """
    if uid not in S.nodes:
        raise HTTPException(404, f"GR {uid} not in the index")

    keep, frontier, edges = {uid}, {uid}, []
    for _ in range(depth):
        nxt = set()
        for u in frontier:
            for e in S.out_edges.get(u, []) + S.in_edges.get(u, []):
                if len(keep) >= max_nodes and e["src"] not in keep or \
                   len(keep) >= max_nodes and e["dst"] not in keep:
                    continue
                edges.append(e)
                for v in (e["src"], e["dst"]):
                    if v not in keep:
                        keep.add(v)
                        nxt.add(v)
        frontier = nxt
        if not frontier or len(keep) >= max_nodes:
            break

    seen, uniq = set(), []
    for e in edges:
        if e["_i"] in seen:
            continue
        seen.add(e["_i"])
        if e["src"] in keep and e["dst"] in keep:
            uniq.append(S.edge_out(e))
    return {
        "center": uid, "depth": depth, "truncated": len(keep) >= max_nodes,
        "nodes": [{**S.nodes[u],
                   "in_force": not any(x["type"] == "SUPERSEDES"
                                       for x in S.in_edges.get(u, []))}
                  for u in keep if u in S.nodes],
        "edges": uniq,
    }


# --------------------------------------------------------------------------- audit / ledger

@app.get("/api/audit")
def audit(kind: str | None = None, limit: int = Query(50, le=500), offset: int = 0):
    if S.audit is None:
        return {"available": False,
                "hint": "run: python audit.py --graph out/graph.json --out out/audit.json"}
    f = S.audit["findings"]
    if kind:
        f = [x for x in f if x["kind"] == kind.upper()]
    return {"available": True, "definitions": S.audit["definitions"],
            "headline": S.audit["headline"], "graph": S.audit["graph"],
            "unverifiable": S.audit["unverifiable"],
            "total": len(f), "findings": f[offset:offset + limit]}


@app.get("/api/ledger")
def ledger(limit: int = Query(100, le=500)):
    """The Trust Ledger: what the model proposed and what the gates did about it.

    The point of surfacing this is to answer "how do you know your AI isn't making things up"
    with a number and a browsable list rather than a reassurance."""
    tally = Counter(t.get("verdict") for t in S.typed)
    gate_fails = Counter()
    for t in S.typed:
        for g, r in (t.get("gates") or {}).items():
            if not r.get("pass"):
                gate_fails[g] += 1
    downgrades = [t for t in S.typed if t.get("notes")]
    return {
        "available": bool(S.typed),
        "summary": {
            "claims": len(S.typed), "verdicts": dict(tally),
            "gate_failures": dict(gate_fails.most_common()),
            "downgraded_by_G7": len(downgrades),
            "edges_upgraded": S.graph.get("meta", {})
                                    .get("ai_typing", {}).get("edges_upgraded", 0),
        },
        "downgrades": downgrades[:limit],
        "non_verified": [t for t in S.typed if t.get("verdict") != "VERIFIED"][:limit],
        "verified_sample": [t for t in S.typed if t.get("verdict") == "VERIFIED"][:limit],
    }


@app.get("/api/lint/profile")
def lint_profile():
    """The mined template profile: which conventions this corpus actually follows.

    Serves the free-variation list alongside the enforced rules on purpose. "Here are 18
    orderings we do NOT enforce because the corpus varies" is the evidence that the rule set was
    measured rather than asserted, and it is the part a sceptical official will check first.
    """
    prof = _load("../data/template_profile.json")
    if prof is None:
        prof = json.loads((ROOT / "data" / "template_profile.json").read_text(encoding="utf-8")) \
            if (ROOT / "data" / "template_profile.json").exists() else None
    if prof is None:
        return {"available": False, "hint": "run: python lint.py --mine data/mahGRs/GRs"}
    try:
        import lint as L
        rules = {d: L.rules_for(prof, d) for d in prof["departments"]}
    except Exception:
        rules = {}
    return {"available": True, "profile": prof, "rules_by_department": rules,
            "markers": getattr(__import__("lint"), "MARKERS", {}),
            "human": getattr(__import__("lint"), "HUMAN", {})}


@app.get("/api/lint/corpus")
def lint_corpus(limit: int = Query(60, le=400)):
    d = _load("lint_corpus.json")
    if d is None:
        return {"available": False,
                "hint": "run: python lint.py --audit-corpus data/mahGRs/GRs --limit 2000"}
    return {"available": True, "linted": d["linted"], "clean": d["clean"],
            "severity_tally": d["severity_tally"], "by_code": d["by_code"],
            "findings": d["sample_findings"][:limit]}


@app.get("/api/bilingual")
def bilingual(limit: int = Query(80, le=300)):
    d = _load("bilingual.json")
    if d is None:
        return {"available": False, "hint": "run: python bilingual.py --all data/mahGRs/GRs"}
    p = d.get("parity", {})
    g = d.get("glossary", {})
    return {
        "available": True,
        "parity": {**{k: v for k, v in p.items() if k != "findings"},
                   "findings": p.get("findings", [])[:limit]},
        "glossary": {**{k: v for k, v in g.items() if k not in ("terms", "inconsistent_terms")},
                     "inconsistent_terms": g.get("inconsistent_terms", [])[:limit],
                     "terms": g.get("terms", [])[:limit]},
    }


@app.get("/api/departments")
def departments():
    c = Counter(n["dept"] for n in S.graph["nodes"] if n.get("dept"))
    return {"departments": [{"name": k, "grs": v} for k, v in c.most_common()]}


# --------------------------------------------------------------------------- static

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        """SPA fallback — any non-API path returns index.html so client routing works."""
        f = WEB_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
