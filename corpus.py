#!/usr/bin/env python3
"""
Read-through access to the crawled corpus: the official portal URL for a GR, and its text.

`out/graph.json` holds everything needed to *reason* about a GR — date, department, number,
subject, edges — and deliberately not its text, because 17,283 documents of Marathi would make
the artefact unservable. But when an officer clicks a citation they want to read the thing, so
this module goes back to the corpus on disk for the two fields the graph does not carry.

## Why the portal URL matters more than the text

`GRs.json` records, for every GR, the URL it was crawled from:

    https://gr.maharashtra.gov.in/Site/Upload/Government%20Resolutions/English/<uid>.pdf

That is the authoritative document — the actual signed PDF, with the signature block that the
OCR'd text does not contain because it is an image. Offering it turns "our index says this order
exists" into "here is the order, on the Government's own site". Nothing else we show is that
persuasive to somebody who does not trust the pipeline.

**The corpus itself contains no PDFs** — the crawl publishes OCR'd text only (verified: zero
`.pdf` blobs in the repo tree). So the popup shows corpus text, which works offline, and links
out to the portal for the original, which does not. The demo requirement is that nothing
*breaks* without a network, not that every affordance works without one — so the link is
labelled as leaving the box rather than silently failing.

## Degradation

Every function here tolerates the corpus being absent: a deployment that ships only `out/` still
serves the graph, and the UI grades down to "text not available on this box" instead of 500ing.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "mahGRs" / "GRs"

UID_RE = re.compile(r"\d{18}")


@lru_cache(maxsize=1)
def portal_index(corpus_root: str | None = None) -> dict[str, dict[str, Any]]:
    """uid -> the crawl metadata worth showing a human. Empty when the corpus is not present.

    Built once and cached: four `GRs.json` files, ~17k entries, ~0.4 s. Deliberately keeps only
    the display fields — `order_number`, `date` and `dept` already live in the graph, and two
    copies of the same fact drift.
    """
    root = Path(corpus_root) if corpus_root else CORPUS
    out: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return out
    for meta_file in sorted(root.glob("*/GRs.json")):
        try:
            md = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key, v in md.items():
            uid = key.split(".")[0]
            if not UID_RE.fullmatch(uid) or uid in out:
                continue
            out[uid] = {
                "url": v.get("url"),
                "pages": v.get("num_pages"),
                "size_kb": v.get("size_kb"),
                "order_type": (v.get("order_type") or "").strip() or None,
                "dept_full": (v.get("dept") or "").strip() or None,
            }
    return out


def portal(uid: str) -> dict[str, Any]:
    return portal_index().get(uid, {})


@lru_cache(maxsize=512)
def text_of(uid: str, lang: str = "mr") -> str | None:
    """The GR's crawled text, or None if this box does not carry the corpus.

    Marathi is the default because it is the legally operative text (CLAUDE.md rule 1); the
    English side is IndicTrans2 output and is offered alongside, never instead.
    """
    if not UID_RE.fullmatch(uid or ""):
        return None
    hits = list(CORPUS.glob(f"*/{uid}.pdf.{lang}.txt")) or list(CORPUS.glob(f"*/{uid}*.{lang}.txt"))
    if not hits:
        hits = list((ROOT / "fixtures").glob(f"{uid}*.{lang}.txt"))
    if not hits:
        return None
    try:
        raw = hits[0].read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # `# Page N` is a crawl artefact of the OCR pipeline, not part of the resolution.
    return "\n".join(l for l in raw.splitlines() if not l.startswith("# Page")).strip()


def available() -> tuple[bool, str]:
    idx = portal_index()
    if not idx:
        return False, f"corpus not present at {CORPUS}"
    return True, f"{len(idx):,} GRs indexed with portal URLs"
