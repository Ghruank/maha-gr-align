#!/usr/bin/env python3
"""
Semantic conflict detection — SRS FR-4, FR-5, FR-6.

    FR-4  convert new draft clauses into vector embeddings
    FR-5  search the mahGRs vector database for semantically similar clauses from OTHER
          departments
    FR-6  display potential conflicts with similarity score and source GR link

## What this finds, stated so nobody over-reads it

It finds **clauses from other departments about the same subject matter**. It does not find
contradictions, and the measurement in `embed.py` says why it cannot:

    cancellation vs a differently-worded cancellation   0.406
    cancellation vs an AMENDMENT                        0.467   <- higher
    cancellation vs an unrelated clause                 0.167

Topic separates cleanly; the legal *act* does not. A model that ranks an amendment above a
second cancellation cannot be asked which of two clauses overrides the other. So every hit here
is labelled a **candidate for review**, the officer decides, and the word "conflict" never
appears without "potential" in front of it. That is also exactly what FR-6 asks for.

This is the one place in the project where a *score* is shown rather than a verdict, and the
reason is honest: unlike a citation, which either resolves or does not, similarity is a
continuum with no defensible cut-off. The threshold below is a display convenience, not a
finding, and it is stated on screen.

## Why "other departments" is the whole point

Within a department an officer already knows the standing orders. The failure mode this
addresses is the one nobody can see: Higher Education writing a clause that School Education
settled differently two years ago. `--include-own` exists for debugging and is off by default.

## Cost

Exact search, no ANN index: one `matmul` of the draft's clause vectors against a
23,977 x 768 float32 matrix, a few milliseconds. The expensive part is embedding the draft
itself — ~12 clauses/second on this CPU — which is why the API route is behind a button.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

import embed

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "out" / "clause_index"

# Display threshold, not a finding. Calibrated against the measured floor: unrelated Marathi
# clause pairs sit near 0.17, so anything below ~0.45 is noise. Shown on screen so a reader can
# discount it.
DEFAULT_MIN = 0.55

# Bands, for wording only. There is no evidence for a cut-off that separates "conflict" from
# "coincidence", so these describe strength of resemblance and nothing more.
def band(score: float) -> str:
    if score >= 0.80:
        return "very close"
    if score >= 0.68:
        return "close"
    return "related"


class ClauseIndex:
    """The corpus clause vectors, loaded once."""

    def __init__(self, path: Path | str = INDEX):
        p = Path(path)
        self.available = False
        self.meta: list[dict] = []
        self.info: dict[str, Any] = {}
        self.vectors = np.zeros((0, 768), dtype="float32")
        npz, js = p.with_suffix(".npz"), p.with_suffix(".json")
        if not (npz.exists() and js.exists()):
            self.hint = (f"index not built — run: python index_clauses.py --out {p}")
            return
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
            # Stored float16 to halve the file; promoted once here so every search is float32.
            self.vectors = np.load(npz)["vectors"].astype("float32")
            self.meta = d["meta"]
            self.info = {k: v for k, v in d.items() if k != "meta"}
        except Exception as exc:                                   # pragma: no cover
            self.hint = f"index unreadable: {exc}"
            return
        if len(self.meta) != self.vectors.shape[0]:
            self.hint = "index and metadata are out of step; rebuild"
            return

        # Procedural furniture is masked HERE, not at index time, so the boilerplate list can be
        # tightened without a 3-hour re-encode. Measured before this mask existed: the top three
        # hits for a Finance draft were other departments' Finance-concurrence and budget-head
        # clauses at 0.905/0.872/0.867, and the clause that said what the GR actually does
        # ranked third overall at 0.688. Those clauses match everything and mean nothing.
        self.formulaic = np.array([bool(embed.BOILERPLATE.search(m["text"]))
                                   for m in self.meta])
        self.available = True
        self.hint = ""

    def status(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "hint": self.hint}
        depts: dict[str, int] = {}
        for m in self.meta:
            depts[m["dept"]] = depts.get(m["dept"], 0) + 1
        return {"available": True, "clauses": len(self.meta),
                "substantive": int((~self.formulaic).sum()),
                "departments": depts, **self.info}

    def search(self, vecs: np.ndarray, exclude_dept: str | None,
               top_k: int, min_score: float) -> list[list[dict]]:
        """Top matches per query vector. One matmul; no approximation."""
        if not self.available or vecs.shape[0] == 0:
            return [[] for _ in range(vecs.shape[0])]
        sims = vecs @ self.vectors.T                     # (queries, clauses)

        keep = ~self.formulaic
        if exclude_dept:
            keep &= np.array([m["dept"] != exclude_dept for m in self.meta])
        sims[:, ~keep] = -1.0

        out: list[list[dict]] = []
        for row in sims:
            # Over-fetch, because several clauses of one GR routinely match and only the best
            # of each should be shown — otherwise one document fills the whole list.
            idx = np.argpartition(-row, min(len(row) - 1, top_k * 8))[:top_k * 8]
            idx = idx[np.argsort(-row[idx])]
            seen: set[str] = set()
            hits = []
            for i in idx:
                s = float(row[i])
                if s < min_score:
                    break
                m = self.meta[i]
                if m["uid"] in seen:
                    continue
                seen.add(m["uid"])
                hits.append({"score": round(s, 4), "band": band(s), "uid": m["uid"],
                             "dept": m["dept"], "date": m["date"], "clause": m["text"],
                             "line": m.get("line")})
                if len(hits) >= top_k:
                    break
            out.append(hits)
        return out


_INDEX: ClauseIndex | None = None


def index() -> ClauseIndex:
    """The loaded index, cached — but a FAILED load is never cached.

    `index_clauses.py` takes ~35 minutes, so the API is routinely started before the files
    exist. Caching the miss would mean the server had to be restarted to notice a completed
    build, and the failure mode is silent: the page would keep reporting "index not built" long
    after it was. A successful load is cached; an unsuccessful one is retried on the next call,
    which costs one `Path.exists()` until the build lands.
    """
    global _INDEX
    if _INDEX is None or not _INDEX.available:
        ix = ClauseIndex()
        if ix.available or _INDEX is None:
            _INDEX = ix
    return _INDEX


def check(text: str, lang: str = "mr", own_dept: str | None = None,
          top_k: int = 4, min_score: float = DEFAULT_MIN,
          include_own: bool = False) -> dict[str, Any]:
    """FR-4 + FR-5 + FR-6 over a draft. Returns one entry per clause that matched something."""
    ix = index()
    if not ix.available:
        return {"available": False, "hint": ix.hint, "clauses": [], "matches": []}

    ok, detail = embed.available(lang)
    if not ok:
        return {"available": False, "hint": detail, "clauses": [], "matches": []}

    cl = [c for c in embed.clauses(text, lang)
          if not embed.BOILERPLATE.search(c["text"])]
    if not cl:
        return {"available": True, "clauses": 0, "matches": [], "searched": 0,
                "own_department": own_dept, "min_score": min_score,
                "note": "No operative clauses were found in this draft. Clauses are read from "
                        "the section below 'शासन निर्णय :-'; a draft with no operative section "
                        "has nothing to compare."}

    vecs = embed.encode([c["text"] for c in cl], lang)
    hits = ix.search(vecs, None if include_own else own_dept, top_k, min_score)

    matches = []
    for c, hs in zip(cl, hits):
        if not hs:
            continue
        matches.append({"clause": c["text"], "line": c["line"], "hits": hs,
                        "top_score": hs[0]["score"]})
    matches.sort(key=lambda m: -m["top_score"])

    return {
        "available": True,
        "clauses": len(cl),
        "searched": len(ix.meta),
        "own_department": own_dept,
        "min_score": min_score,
        "model": ix.info.get("model"),
        "matches": matches,
        "note": ("These are clauses from OTHER departments on closely related subject matter. "
                 "High similarity means overlapping subject, NOT contradiction: on this model a "
                 "cancellation scores higher against an amendment (0.47) than against another "
                 "cancellation (0.41). Each hit is a candidate for an officer to read, and the "
                 "score is a measured cosine, not a probability of conflict."),
    }
