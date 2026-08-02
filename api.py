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
import os
from pathlib import Path
from collections import defaultdict, Counter
from functools import lru_cache

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
WEB_DIST = ROOT / "web" / "dist"

app = FastAPI(title="MAHA-GR-ALIGN", version="0.1",
              description="Government Resolution dependency graph for Maharashtra")

# Vite dev server runs on 5173; the bundled build is served from this same origin and needs no
# CORS at all. The extra configuration is for a SPLIT deployment — static frontend on one host,
# this API on another — where the browser will refuse the cross-origin call unless the frontend's
# exact origin is allowed here.
#
#   ALLOWED_ORIGINS=https://maha-gr-align.vercel.app,https://foo.vercel.app
#
# `*` is accepted for a demo but should not be used where a draft could be sensitive: with
# credentials disabled it is harmless, but it also means any page on the internet can query this
# service while the tunnel is open.
_DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173",
                    "http://localhost:8000", "http://127.0.0.1:8000"]
_env_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_env_origins or _DEFAULT_ORIGINS,
    # Any *.vercel.app preview deployment, so a new preview URL does not need a restart.
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app",
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def _private_network_access(request, call_next):
    """Chrome's Private Network Access preflight.

    A page served from a public origin (Vercel) that calls a private one (a machine on the
    officer's own network, or localhost) triggers an extra preflight in recent Chrome, and the
    request fails without this header even though ordinary CORS is satisfied. Harmless
    elsewhere — other browsers ignore it.

    This does NOT make `https://…vercel.app` → `http://localhost:8000` work in general: that is
    blocked as mixed content before any preflight happens. Use an HTTPS tunnel. The header is
    here so that the case which *can* work does.
    """
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network"):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


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

        # Every GR with an incoming SUPERSEDES edge. Precomputed because it is the single most
        # asked question about any node, and a caller that had to rescan the edge list to find
        # out whether a neighbour still stands would either be slow or would skip the check.
        self.superseded = {e["dst"] for e in self.graph["edges"]
                           if e["type"] == "SUPERSEDES"}

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
            # Whether each END of the edge still stands. Without this a client showing a
            # neighbourhood has to fetch every neighbour separately to find out that the order
            # in front of it was cancelled — which is the one thing the view exists to reveal.
            "src_in_force": e["src"] not in self.superseded,
            "dst_in_force": e["dst"] not in self.superseded,
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


@app.get("/api/blast/{uid}")
def blast_radius(uid: str, depth: int = Query(3, ge=1, le=6)):
    """What breaks if this GR is superseded — before it is superseded.

    The problem statement asks for *drafting* support, and this is the question a drafting officer
    cannot currently answer: supersede a Finance appropriation order and hundreds of GRs across
    several departments lose the thing they were standing on. Today nobody can see that until the
    complaints arrive.

    Transitive dependents, breadth-first over incoming edges: everything that cites this GR, then
    everything citing those, and so on. Depth is reported per ring because a first-ring dependent
    is affected directly while a third-ring one is affected only through a chain, and conflating
    them would overstate the damage.

    GRs already superseded are counted separately and excluded from the headline — they are
    already dead and cannot break twice.
    """
    if uid not in S.nodes:
        raise HTTPException(404, f"GR {uid} not in the index")

    superseded = {e["dst"] for e in S.graph["edges"] if e["type"] == "SUPERSEDES"}
    rings, seen, frontier = [], {uid}, {uid}
    for d in range(1, depth + 1):
        nxt = set()
        for u in frontier:
            for e in S.in_edges.get(u, []):
                if e["src"] not in seen:
                    seen.add(e["src"])
                    nxt.add(e["src"])
        if not nxt:
            break
        rings.append({
            "depth": d,
            "count": len(nxt),
            "live": len([u for u in nxt if u not in superseded]),
            "already_superseded": len([u for u in nxt if u in superseded]),
            "departments": dict(Counter(S.nodes[u]["dept"] for u in nxt if u in S.nodes)),
            "sample": [{"uid": u, "date": S.nodes[u]["date"], "dept": S.nodes[u]["dept"],
                        "subject": S.nodes[u]["subject"],
                        "in_force": u not in superseded}
                       for u in sorted(nxt, key=lambda x: -S.nodes[x]["in_degree"])[:25]],
        })
        frontier = nxt

    affected = seen - {uid}
    live = affected - superseded
    depts = Counter(S.nodes[u]["dept"] for u in live if u in S.nodes)
    own = S.nodes[uid]["dept"]
    return {
        "uid": uid, "node": S.nodes[uid],
        "in_force": uid not in superseded,
        "total_dependents": len(affected),
        "live_dependents": len(live),
        "already_superseded": len(affected & superseded),
        "departments_affected": dict(depts.most_common()),
        "other_departments_affected": {k: v for k, v in depts.items() if k != own},
        "rings": rings,
        "note": "Transitive dependents via REFERENCES/AMENDS/SUPERSEDES edges. Only citations we "
                "could resolve are counted, so this is a LOWER bound on real blast radius.",
    }


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


# --------------------------------------------------------------------------- drafting
#
# SRS FR-13..FR-16. Everything here runs on the box: the LLM is Ollama on localhost and the
# template check is pure Python. No request in this section can leave the State Data Centre
# (NFR-2). `/api/draft/verify` deliberately contains no model call — structural compliance is
# computed, never generated.

import template as _template                      # noqa: E402
import docgen as _docgen                          # noqa: E402
import ocr as _ocr                                # noqa: E402
import drafting as _drafting                      # noqa: E402
import references as _references                  # noqa: E402
import refreview as _refreview                    # noqa: E402
import corpus as _corpus                          # noqa: E402
import glossary as _glossary                      # noqa: E402
import conflicts as _conflicts                    # noqa: E402
import staging as _staging                        # noqa: E402
import summarize as _summarize                    # noqa: E402
import semantic as _semantic                      # noqa: E402
from ai.local import LocalAIUnavailable           # noqa: E402
from pydantic import BaseModel                    # noqa: E402

# The citation checker's index is built from the graph this process already holds, not re-read
# from the corpus. One consequence is worth stating: anything a citation resolves to is by
# construction a node whose supersession status we can answer immediately. An index that could
# resolve to a uid the graph does not contain would hand back "verified" with no status.
ARCHIVE = _references.Archive(S.graph)

# The in-tray: GRs uploaded but not yet crawled. Registered in ARCHIVE so a later upload can
# cite one, which is what makes an inter-departmental conflict visible while both documents are
# still drafts. Never written into out/graph.json — see staging.py.
STAGING = _staging.Staging(ARCHIVE)


def _text_of(uid: str) -> str | None:
    """Full text of any GR we can reach: staged first, then the crawled corpus."""
    return STAGING.text_of(uid) or _corpus.text_of(uid, "mr")


class _PromptIn(BaseModel):
    prompt: str
    lang: str = "mr"


class _DraftIn(BaseModel):
    prompt: str
    answers: dict[str, str] = {}
    lang: str = "mr"


class _RefineIn(BaseModel):
    text: str
    instruction: str
    lang: str = "mr"


class _VerifyIn(BaseModel):
    text: str
    lang: str = "mr"


@app.get("/api/draft/template")
def draft_template(lang: str = Query("mr", pattern="^(mr|en)$")):
    """Blank Manual-of-Office-Procedure skeleton + the section contract behind it."""
    return {
        "lang": lang,
        "text": _template.render_skeleton(lang),
        "sections": _template.TEMPLATE["sections"],
        "source": _template.TEMPLATE["_source"],
    }


@app.get("/api/draft/engine")
def draft_engine():
    """Is the local model up? The UI degrades visibly rather than failing on send."""
    ok, detail = _drafting.local.available()
    return {"available": ok, "detail": detail}


@app.post("/api/draft/questions")
def draft_questions(body: _PromptIn):
    try:
        return _drafting.questions_for(body.prompt, body.lang)
    except LocalAIUnavailable as exc:
        # Degrade, never fake: a fixed questionnaire, plainly labelled as such.
        return {"questions": _drafting._fallback_questions(body.lang),
                "stats": {"local": False, "fallback": True, "error": str(exc)},
                "degraded": True}


@app.post("/api/draft/generate")
def draft_generate(body: _DraftIn):
    try:
        out = _drafting.draft(body.prompt, body.answers, body.lang)
    except LocalAIUnavailable as exc:
        raise HTTPException(503, f"Local model unavailable: {exc}") from exc
    out["verify"] = _template.verify(out["text"], body.lang)
    return out


@app.post("/api/draft/refine")
def draft_refine(body: _RefineIn):
    try:
        out = _drafting.refine(body.text, body.instruction, body.lang)
    except LocalAIUnavailable as exc:
        raise HTTPException(503, f"Local model unavailable: {exc}") from exc
    out["verify"] = _template.verify(out["text"], body.lang)
    return out


@app.post("/api/draft/verify")
def draft_verify(body: _VerifyIn):
    """FR-12. Deterministic; no model is consulted and none ever will be."""
    return _template.verify(body.text, body.lang)


# --------------------------------------------------------------------------- references
#
# SRS FR-1/2/3 and the problem statement's cross-department conflict bullet. Like the template
# check above, deterministic end to end: citations come out by regex, resolve against the graph's
# own index, and every supersession claim is an edge carrying the sentence that produced it.
#
# Measured at ~4 ms on a 19-citation GR, which is why it can ride along on the upload response
# instead of being a second round trip the officer has to wait through.

@app.get("/api/references/status")
def references_status():
    """Whether the archive is loaded, and what it covers. The UI states the denominator rather
    than implying the corpus is all of Maharashtra's GRs."""
    if not ARCHIVE.available:
        return {"available": False,
                "hint": "run: python graph.py data/mahGRs/GRs --out out/graph.json"}
    corpus_ok, corpus_detail = _corpus.available()
    model_ok, model_detail = _refreview.local.available()
    return {"available": True, "grs": len(ARCHIVE.nodes),
            "departments": sorted(ARCHIVE.in_index),
            "covers": [ARCHIVE.covers[0].isoformat(), ARCHIVE.covers[1].isoformat()],
            "supersedes_edges": sum(len(v) for v in ARCHIVE.killed_by.values()),
            "amends_edges": sum(len(v) for v in ARCHIVE.amended_by.values()),
            # Two independent optional capabilities. Citation checking needs neither; the popup
            # needs the corpus and the narrative review needs the model, so the UI can offer or
            # grey each one rather than failing on click.
            "corpus": {"available": corpus_ok, "detail": corpus_detail},
            "model": {"available": model_ok, "detail": model_detail}}


@app.post("/api/references/check")
def references_check(body: _VerifyIn):
    """FR-1 + FR-2 + FR-3 over a pasted, drafted or extracted document."""
    return _references.check(body.text, body.lang, ARCHIVE)


# --------------------------------------------------------------------------- glossary
#
# SRS FR-7/8/9. Deterministic: whether a document writes "Government Decision" where the Manual
# says "Government Resolution" is settled by a string comparison, not by a model.

@app.get("/api/glossary")
def glossary_list():
    """FR-7 — the controlled list itself, so it can be read and argued with."""
    ok, detail = _glossary.available()
    g = _glossary.load()
    return {"available": ok, "detail": detail,
            "source": g.get("_source", {}), "terms": g.get("terms", [])}


# --------------------------------------------------------------------------- semantic (FR-4/5/6)
#
# The one place in the project that shows a SCORE rather than a verdict. Unlike a citation,
# which either resolves or does not, similarity is a continuum with no defensible cut-off — so
# the threshold is a display convenience, is returned with the response, and is stated on screen.

@app.get("/api/semantic/status")
def semantic_status():
    """Is the clause index built, and what does it cover?"""
    st = _semantic.index().status()
    ok, detail = _semantic.embed.available("mr")
    return {**st, "model_loaded": ok, "model_detail": detail,
            "default_min_score": _semantic.DEFAULT_MIN}


class _SemanticIn(BaseModel):
    text: str
    lang: str = "mr"
    dept: str | None = None
    top_k: int = 4
    min_score: float = _semantic.DEFAULT_MIN
    include_own: bool = False


@app.post("/api/semantic/check")
def semantic_check(body: _SemanticIn):
    """FR-4/5/6. Embeds the draft's operative clauses and searches other departments.

    The department is read from the draft when not supplied, because FR-5 asks specifically for
    clauses from OTHER departments and an officer should not have to state their own.
    """
    dept = body.dept
    if dept is None:
        dept = _references.doc_dept(body.text)
    return _semantic.check(body.text, body.lang, dept, body.top_k, body.min_score,
                           body.include_own)


@app.post("/api/summary")
def summary(body: _VerifyIn):
    """A plain-English summary of an uploaded GR — genuinely generative.

    The only place in this project where the model produces content rather than explaining a
    computed finding, because nothing can compute "what does this seven-page Marathi order
    actually do". The frame is still deterministic: department, date, number and every monetary
    figure are extracted and handed over, and a sentence quoting any other figure is discarded
    before the response leaves this process.
    """
    ref = _references.check(body.text, body.lang, ARCHIVE)
    header = {
        "department": ref.get("document", {}).get("department"),
        "date": ref.get("document", {}).get("date"),
        "decision_no": ref.get("document", {}).get("decision_no"),
        "citations": ref.get("summary", {}).get("citations", 0),
    }
    return _summarize.summarize(body.text, header)


@app.post("/api/glossary/check")
def glossary_check(body: _VerifyIn):
    """FR-8 + FR-9 over a document."""
    return _glossary.check(body.text, body.lang)


@app.get("/api/gr/{uid}")
def gr_source(uid: str, lang: str = Query("mr", pattern="^(mr|en)$")):
    """One archived GR, for the popup behind a citation.

    Text comes from the corpus on disk rather than the graph, which carries no text on purpose
    (17,283 documents of Marathi would make the artefact unservable). The portal URL is the
    prize here: it is the actual signed PDF on the Government's own site, which is a stronger
    answer to "does this order really exist" than anything we can render ourselves.
    """
    node = S.nodes.get(uid)
    if not node:
        raise HTTPException(404, f"GR {uid} is not in the index")
    body = _corpus.text_of(uid, lang)
    return {
        "uid": uid,
        "node": node,
        "portal": _corpus.portal(uid),
        "status": ARCHIVE.status(uid),
        "lang": lang,
        "text": body,
        # Distinguish "we do not hold the text on this box" from "the GR is empty". Only the
        # first is a deployment fact; the UI must not present it as a property of the GR.
        "text_available": body is not None,
        "cites": [S.edge_out(e) for e in S.out_edges.get(uid, [])][:40],
        "cited_by_count": len(S.in_edges.get(uid, [])),
    }


@lru_cache(maxsize=32)
def _screen(uid: str) -> dict | None:
    """Run BOTH checks over one archived GR. Cached: the corpus never changes under us."""
    text = _corpus.text_of(uid, "mr")
    if not text:
        return None
    # `issued`, not `draft`. These documents already exist and were read back through OCR, so
    # the signature block and the Governor's order line are images the crawl could not see.
    # Judging them by the drafting rules scores 0.2% of a valid corpus as compliant, which
    # measures our pipeline rather than the Government's drafting.
    tpl = _template.verify(text, "mr", mode="issued")
    ref = _references.check(text, "mr", ARCHIVE)
    node = S.nodes.get(uid, {})
    return {
        "uid": uid,
        "date": node.get("date"),
        "dept": node.get("dept"),
        "decision_no": node.get("decision_no"),
        "subject": node.get("subject"),
        "portal": (_corpus.portal(uid) or {}).get("url"),
        "in_force": uid not in S.superseded,
        "template": {
            "doc_type": tpl["doc_type"],
            "appendix": tpl["manual_appendix"],
            "compliant": tpl["compliant"],
            "errors": tpl["counts"]["error"],
            "present": sum(1 for v in tpl["sections_present"].values() if v),
            "total": len(tpl["sections_present"]),
            "missing": [f["label"] for f in tpl["findings"] if f["severity"] == "error"],
            "relaxed": tpl["relaxed"],
        },
        "references": {
            "verdict": ref["alignment"]["verdict"],
            "label": ref["alignment"]["label"],
            "reasons": ref["alignment"]["reasons"],
            "citations": ref["summary"]["citations"],
            "verified": ref["summary"]["verified"],
            "superseded": ref["summary"]["superseded"],
            "amended": ref["summary"]["amended"],
            "missing": ref["summary"]["not_in_archive"],
            "cross_department": ref["summary"]["cross_department"],
            "errors": ref["counts"]["error"],
        },
    }


# --------------------------------------------------------------------------- staging
#
# Upload a GR that is not in the corpus, check it against everything that is — and against
# everything else uploaded. The second half is the point: a contradiction between two draft
# resolutions from different departments is invisible until both exist in one index.

def _screen_text(text: str, lang: str, uid: str | None = None) -> dict:
    """All four checks over one document, in the shape the listing renders."""
    tpl = _template.verify(text, lang, mode="issued")
    ref = _references.check(text, lang, ARCHIVE)
    gls = _glossary.check(text, lang)
    con = _conflicts.check(text, ref, _text_of)
    return {
        "template": {
            "doc_type": tpl["doc_type"], "appendix": tpl["manual_appendix"],
            "compliant": tpl["compliant"], "errors": tpl["counts"]["error"],
            "present": sum(1 for v in tpl["sections_present"].values() if v),
            "total": len(tpl["sections_present"]),
            "missing": [f["label"] for f in tpl["findings"] if f["severity"] == "error"],
            "relaxed": tpl["relaxed"],
        },
        "references": {
            "verdict": ref["alignment"]["verdict"], "label": ref["alignment"]["label"],
            "reasons": ref["alignment"]["reasons"],
            "citations": ref["summary"]["citations"], "verified": ref["summary"]["verified"],
            "superseded": ref["summary"]["superseded"], "amended": ref["summary"]["amended"],
            "missing": ref["summary"]["not_in_archive"],
            "cross_department": ref["summary"]["cross_department"],
            "errors": ref["counts"]["error"],
        },
        "glossary": {"total": gls["counts"]["total"], "warning": gls["counts"]["warning"],
                     "clean": gls["clean"]},
        "conflicts": con["conflicts"],
    }


@app.post("/api/staging/upload")
async def staging_upload(file: UploadFile = File(...), lang: str = Form("auto"),
                         force_ocr: bool = Form(False)):
    """Upload a GR into the in-tray and screen it against the archive AND the other uploads."""
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "File larger than 25 MB.")
    try:
        extracted = _ocr.extract(data, file.filename or "upload.pdf", force_ocr=force_ocr)
    except _ocr.OCRUnavailable as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read the file: {exc}") from exc
    if not extracted["text"].strip():
        raise HTTPException(422, "No text could be extracted from this file.")

    chosen = extracted["script"]["lang"] if lang == "auto" else lang
    # Registered BEFORE screening so the checks see a consistent index — but a document is never
    # compared with itself: `resolver.resolve` excludes the citing uid from its own candidates.
    rec = STAGING.add(extracted["text"], chosen,
                      file.filename or "upload.pdf",
                      {k: v for k, v in extracted.items() if k != "text"})
    return {"uid": rec["uid"], "node": rec["node"], "staged": True,
            "filename": rec["filename"], "uploaded_at": rec["uploaded_at"],
            "extraction": rec["extraction"], "lang": chosen,
            **_screen_text(rec["text"], chosen, rec["uid"])}


@app.get("/api/staging")
def staging_list():
    """The in-tray, re-screened on read so an upload reflects everything staged since."""
    rows = []
    for rec in STAGING.all():
        rows.append({"uid": rec["uid"], "node": rec["node"], "staged": True,
                     "filename": rec["filename"], "uploaded_at": rec["uploaded_at"],
                     "date": rec["node"]["date"], "dept": rec["node"]["dept"],
                     "decision_no": rec["node"]["decision_no"],
                     "subject": rec["node"]["subject"], "portal": None, "in_force": True,
                     **_screen_text(rec["text"], rec["lang"], rec["uid"])})
    return {"available": True, "rows": rows, "count": len(rows)}


class _ConflictIn(BaseModel):
    conflict: dict
    citing: dict = {}
    lang: str = "en"


@app.post("/api/conflict/explain")
def conflict_explain(body: _ConflictIn):
    """Plain-language note on one amount contradiction, from the ON-PREMISE model.

    The contradiction itself is computed by `conflicts.py`; the model only says what it means.
    The three figures are supplied and whitelisted — a sentence containing any other number is
    discarded before the response leaves this process.
    """
    return _refreview.explain_conflict(body.conflict, body.citing, body.lang)


@app.delete("/api/staging/{uid}")
def staging_drop(uid: str):
    if not STAGING.drop(uid):
        raise HTTPException(404, f"{uid} is not in the in-tray")
    return {"dropped": uid, "remaining": len(STAGING.records)}


@app.delete("/api/staging")
def staging_clear():
    return {"dropped": STAGING.clear()}


@app.get("/api/corpus/recent")
def corpus_recent(limit: int = Query(15, ge=1, le=40), dept: str | None = None):
    """The most recently issued GRs, each screened on BOTH questions at once.

    Answers, for a run of real documents rather than one upload: is it built to the Manual's
    form, and does it still stand on the orders it cites. Deliberately a small window — the
    index holds 17,283 GRs and screening all of them is a batch job, not a page load.

    Ordered by the uid date prefix, which is the portal publication date and is present for
    100% of GRs (the body `Date:` line is not usable — CLAUDE.md).
    """
    if not _corpus.portal_index():
        return {"available": False, "rows": [],
                "hint": "the corpus is not present on this box; clone data/mahGRs"}

    pool = [n for n in S.graph["nodes"] if not dept or n.get("dept") == dept]
    pool.sort(key=lambda n: n["date"], reverse=True)

    rows, scanned = [], 0
    for n in pool:
        if len(rows) >= limit:
            break
        scanned += 1
        if scanned > limit * 6:          # corpus text missing for a long run: stop, don't crawl
            break
        r = _screen(n["uid"])
        if r:
            rows.append(r)

    return {
        "available": True,
        "rows": rows,
        "scanned": scanned,
        "index_total": len(S.nodes),
        "departments": sorted({n["dept"] for n in S.graph["nodes"] if n.get("dept")}),
        "note": "Template compliance is scored under the ISSUED rule set: sections that are "
                "images in the signed PDF (signature block, the Governor's order line) cannot "
                "be read by OCR and are not counted against an already-issued document. The "
                "drafting page applies the full Manual form.",
    }


@app.post("/api/references/review")
def references_review(body: _VerifyIn):
    """Plain-language review of a citation check, written by the ON-PREMISE model.

    The model explains findings it is handed; it never produces them and never sees the evidence
    a verdict would rest on, so it cannot reach a different verdict from the deterministic check.
    Any GR number it invents is stripped before the response leaves this process — see
    `refreview._scrub`. Degrades to the computed summary when ollama is down.
    """
    report = _references.check(body.text, body.lang, ARCHIVE)
    out = _refreview.review(report, body.lang)
    out["report"] = report
    return out


# --------------------------------------------------------------------------- verify upload
#
# SRS FR-13 ("upload or type a draft") + FR-10/11/12 applied to an existing document. The
# template check is the SAME `template.verify` the drafting page uses — one rule engine, so a
# GR cannot pass on one page and fail on the other.

@app.get("/api/verify/ocr/status")
def verify_ocr_status():
    ok, detail = _ocr.available()
    return {"available": ok, "detail": detail}


@app.post("/api/verify/upload")
async def verify_upload(file: UploadFile = File(...),
                        lang: str = Form("auto"),
                        force_ocr: bool = Form(False)):
    """Extract text from an uploaded GR, then run the Manual-of-Office-Procedure check.

    `lang=auto` picks Marathi or English from the script mix, because an officer should not
    have to tell us what they just uploaded.
    """
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "File larger than 25 MB.")
    try:
        extracted = _ocr.extract(data, file.filename or "upload.pdf", force_ocr=force_ocr)
    except _ocr.OCRUnavailable as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read the file: {exc}") from exc

    if not extracted["text"].strip():
        raise HTTPException(422, "No text could be extracted from this file.")

    chosen = extracted["script"]["lang"] if lang == "auto" else lang
    return {
        "extraction": {k: v for k, v in extracted.items() if k != "text"},
        "text": extracted["text"],
        "lang": chosen,
        "verify": _template.verify(extracted["text"], chosen),
        # Structure, citations and terminology answer three different questions and an officer
        # needs all three before signing: a GR can be perfectly formed, rest on an order that
        # was cancelled two years ago, and call it by a name the Manual does not use. All three
        # are computed, so all three come back on the one upload.
        "references": _references.check(extracted["text"], chosen, ARCHIVE),
        "glossary": _glossary.check(extracted["text"], chosen),
        "filename": file.filename,
    }


@app.get("/api/draft/export/status")
def draft_export_status():
    ok, detail = _docgen.available()
    return {"available": ok, "detail": detail}


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.post("/api/draft/export")
def draft_export(body: _VerifyIn, fmt: str = Query("pdf", pattern="^(pdf|docx)$")):
    """FR-16 — PDF or DOCX from one document model, so the two cannot drift.

    Layout (section order from Manual Appendix 10.6, alignment from data/gr_template.json)
    is applied by `docgen.parse`, which reuses the same detectors as the template checker.
    """
    try:
        if fmt == "docx":
            data, mime, name = (_docgen.to_docx(body.text, body.lang), _DOCX_MIME,
                                "government-resolution.docx")
        else:
            data, mime, name = (_docgen.to_pdf(body.text, body.lang), "application/pdf",
                                "government-resolution.pdf")
    except Exception as exc:
        raise HTTPException(503, f"Export failed: {exc}") from exc
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


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
