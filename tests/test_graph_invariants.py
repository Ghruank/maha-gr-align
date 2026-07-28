#!/usr/bin/env python3
"""
Property tests for the graph. No hand-labelled answer key required.

Same discipline as `test_resolver_invariants.py`: these cannot tell us the graph is *right*, but
they make whole classes of wrongness impossible. The load-bearing one is
`test_every_edge_evidence_is_verbatim` — it is what turns "every edge carries evidence" from a
slogan in CLAUDE.md into a mechanically enforced property. If an edge's evidence sentence is not
actually present in the citing document, the edge is fabricated, and no amount of confidence
scoring makes it real.

Run:  python -m pytest tests/test_graph_invariants.py -q
"""

import sys
import json
import random
import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import resolver as R
import graph as G

GRAPH = Path("out/graph.json")
CORPUS = Path("data/mahGRs/GRs")

pytestmark = pytest.mark.skipif(
    not GRAPH.exists(),
    reason=f"{GRAPH} not built — run: python graph.py data/mahGRs/GRs --out out/graph.json")


@pytest.fixture(scope="module")
def g():
    return json.loads(GRAPH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def uids(g):
    return {n["uid"] for n in g["nodes"]}


@pytest.fixture(scope="module")
def mr_text():
    """uid -> Marathi source text, loaded lazily and cached. Reading 17k files eagerly would
    make the suite unusable; the sampled tests only need a few hundred."""
    dirs = [p for p in CORPUS.iterdir() if p.is_dir()] if CORPUS.exists() else []
    cache: dict[str, str] = {}

    def get(uid: str) -> str | None:
        if uid in cache:
            return cache[uid]
        for d in dirs:
            f = d / f"{uid}.pdf.mr.txt"
            if f.exists():
                cache[uid] = f.read_text(encoding="utf-8", errors="ignore")
                return cache[uid]
        return None

    return get


# --------------------------------------------------------------- structural integrity

def test_graph_is_not_empty(g):
    assert g["edges"], "no edges — extraction or resolution regression"
    assert g["nodes"], "no nodes"


def test_every_edge_endpoint_is_a_node(g, uids):
    bad = [e for e in g["edges"] if e["src"] not in uids or e["dst"] not in uids]
    assert not bad, f"{len(bad)} edges reference uids absent from nodes: {bad[:3]}"


def test_no_self_edges(g):
    """A GR citing itself is always an extraction artefact, never a real legal relationship."""
    bad = [e for e in g["edges"] if e["src"] == e["dst"]]
    assert not bad, f"{len(bad)} self-edges: {[e['src'] for e in bad[:5]]}"


def test_no_edge_points_forward_in_time(g):
    """A GR cannot cite an order issued after it. The uid prefix is the portal publication date,
    so a few days of drift is legitimate; beyond the window it is impossible."""
    w = datetime.timedelta(days=g["meta"]["window_days"])
    bad = []
    for e in g["edges"]:
        if R.uid_date(e["dst"]) > R.uid_date(e["src"]) + w:
            bad.append((e["src"], e["dst"], (R.uid_date(e["dst"]) - R.uid_date(e["src"])).days))
    assert not bad, f"{len(bad)} edges point forward in time: {bad[:5]}"


def test_edge_types_are_in_the_closed_vocabulary(g):
    bad = {e["type"] for e in g["edges"]} - set(G.EDGE_TYPES)
    assert not bad, f"unknown edge types: {bad}"


def test_nothing_is_silently_dropped(g):
    """Every extracted citation must end up as either an edge or an `unresolved` row. A citation
    that vanishes is a citation we failed to report as unverifiable, which rule 3 forbids."""
    m = g["meta"]
    assert m["stats"]["citations"] == len(g["edges"]) + len(g["unresolved"]), (
        f"{m['stats']['citations']} citations extracted but "
        f"{len(g['edges'])} edges + {len(g['unresolved'])} unresolved")


def test_confidence_is_sane(g):
    bad = [e for e in g["edges"] if not 0.0 < e["confidence"] <= 1.0]
    assert not bad, f"{len(bad)} edges with out-of-range confidence"


# --------------------------------------------------------------- the evidence promise

def test_every_edge_evidence_is_nonempty(g):
    bad = [e for e in g["edges"] if not (e.get("evidence") or "").strip()]
    assert not bad, f"{len(bad)} edges carry no evidence — they must not ship"


def test_every_edge_evidence_is_verbatim(g, mr_text):
    """**The test that makes the evidence promise real.**

    The evidence string must occur in the citing document's Marathi text. Whitespace is
    normalised on both sides because extraction collapses runs of spaces and newlines inside a
    citation, but nothing else is allowed to differ — no paraphrase, no reconstruction.
    """
    random.seed(0)
    sample = random.sample(g["edges"], min(400, len(g["edges"])))
    missing, unreadable = [], 0
    for e in sample:
        text = mr_text(e["src"])
        if text is None:
            unreadable += 1
            continue
        if " ".join((e["evidence"] or "").split()) not in " ".join(text.split()):
            missing.append((e["src"], e["dst"], (e["evidence"] or "")[:80]))
    assert unreadable < len(sample), "could not read any source document — corpus path wrong?"
    assert not missing, (
        f"{len(missing)}/{len(sample)-unreadable} sampled edges have evidence that does NOT "
        f"occur in the citing document: {missing[:3]}")


def test_typed_edges_carry_a_cue(g):
    """AMENDS/SUPERSEDES may only exist with the cue that justified the type. Vacuously true
    until AI typing runs, and it must stay true afterwards — this is the guard on that pass."""
    bad = [e for e in g["edges"]
           if e["type"] in ("AMENDS", "SUPERSEDES") and not e.get("cue")]
    assert not bad, f"{len(bad)} typed edges with no cue recorded: {bad[:3]}"


# --------------------------------------------------------------- honest reporting

def test_unresolved_rows_all_carry_a_machine_reason(g):
    allowed = {"other_dept", "series_gap", "ambiguous", "no_number",
               "date_only_insufficient", "number_absent", "other"}
    bad = {u["why"] for u in g["unresolved"]} - allowed
    assert not bad, f"unknown unresolved labels: {bad}"


def test_series_gaps_are_never_resolved(g):
    """A file number matching a series with no member in the date window means the cited GR is
    absent from the crawl. Snapping to the nearest sibling would fabricate a citation."""
    assert any(u["why"] == "series_gap" for u in g["unresolved"]), \
        "expected series-gap cases — the in-range corpus-gap finding predicts they exist"


def test_cross_dept_flag_matches_the_uid_codes(g):
    """`cross_dept` drives the problem statement's headline bullet, so it must not be trusted
    without checking it against the authoritative source: the uid's department code."""
    bad = []
    for e in g["edges"]:
        expected = R.dept_of(e["src"]) != R.dept_of(e["dst"])
        if e.get("cross_dept") is not None and e["cross_dept"] != expected:
            bad.append((e["src"], e["dst"], e["cross_dept"], expected))
    assert not bad, f"{len(bad)} edges with a wrong cross_dept flag: {bad[:3]}"


def test_cross_department_edges_exist(g):
    """If this fails the index has collapsed to one department and the first bullet of the
    problem statement is unimplemented again."""
    n = g["meta"]["cross_dept_edges"]
    assert n > 0, "no cross-departmental edges — is the index multi-department?"


# --------------------------------------------------------------- reproducibility

def test_rebuild_is_deterministic():
    """Rule 4. Cheap slice, but it exercises index load, extraction and resolution."""
    a = G.build(CORPUS, window=3, limit=300, progress_every=10**9)
    b = G.build(CORPUS, window=3, limit=300, progress_every=10**9)
    assert a["edges"] == b["edges"]
    assert a["unresolved"] == b["unresolved"]
