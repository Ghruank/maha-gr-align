#!/usr/bin/env python3
"""
Clause extraction and sentence embeddings — the substrate for SRS FR-4/5/6.

Two models, never mixed into one space:

  * **MahaSBERT** (`l3cube-pune/marathi-sentence-similarity-sbert`) over the Marathi clauses,
    which are the legally operative text.
  * **BGE** (`BAAI/bge-base-en-v1.5`) over the English side, offered for an English draft.

Decided 2026-07-31 and recorded in CLAUDE.md: two indexes, not one translated space. Embedding
a machine translation and comparing it to Marathi would measure IndicTrans2 as much as it
measures the documents.

## What the model can and cannot separate `[MEASURED 2026-08-02]`

Run on this box, cosine on normalised MahaSBERT vectors:

    उक्त शासन निर्णय याद्वारे रद्द करण्यात येत आहे.        (cancellation)
      vs संदर्भाधीन शासन निर्णय अधिक्रमित करण्यात येत आहे.  (cancellation)   0.406
      vs सदर शासन निर्णयात अंशत: सुधारणा करण्यात येत आहे.   (amendment)      0.467
      vs राज्यातील शाळांमध्ये क्रीडा स्पर्धा आयोजित...       (unrelated)      0.167

**Topical relatedness separates cleanly. The legal ACT does not** — an amendment scored *higher*
against a cancellation than a second cancellation did. So this index can answer "which other
department has written about the same thing" and it emphatically cannot answer "do these two
clauses contradict each other". The UI says so, and FR-6's word is "potential conflicts", which
is exactly the weaker claim the measurement supports.

An earlier note in CLAUDE.md recorded 0.802 for two differently-worded cancellations. That was a
different sentence pair; on the pair above the figure is 0.406, and the ordering against
`अंशत: सुधारणा` is the part that matters. Do not quote 0.802 as evidence that this separates
supersession from amendment — measured here, it does not.
"""

from __future__ import annotations

import functools
import os
import re
from typing import Any

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

MODELS = {
    "mr": "l3cube-pune/marathi-sentence-similarity-sbert",
    "en": "BAAI/bge-base-en-v1.5",
}

# The operative part of a GR. Everything above it is the header and the recital of references —
# indexing those would match every GR against every other on boilerplate alone.
OPERATIVE = re.compile(
    r"शासन\s*(?:निर्णय|ज्ञापन|परिपत्रक|शुद्धिपत्रक|आदेश)\s*[:\-–]|"
    r"^\s*शासन\s*(?:निर्णय|ज्ञापन|परिपत्रक|आदेश)\s*$|"
    r"^\s*Resolution\s*[:\-–]|^\s*Government\s+Decision\s*[:\-–]", re.M)

# Numbered clause openers, both scripts, plus the danda.
SPLIT = re.compile(r"(?<=[।])\s+|\n\s*(?=[०-९\d]{1,2}[.)\)]\s)|\n{2,}")

MIN_CHARS, MAX_CHARS = 60, 600

# The operative part ENDS here. Below the Governor's order line sit the signature and the
# distribution list, whose entries ("२) संचालक, तंत्र शिक्षण संचालनालय…") are near-identical
# across thousands of GRs and would dominate any nearest-neighbour search.
END_OF_OPERATIVE = re.compile(
    r"राज्यपाल.{0,40}आदेशानुसार|आदेशानुसार व नावाने|^\s*प्रति\s*[,:\-]|"
    r"[Bb]y order and in the name|^\s*To\s*[,:]", re.M)

# Boilerplate that appears near-verbatim in thousands of GRs. Indexing it makes every document
# the nearest neighbour of every other and buries any real match.
#
# The second group below was added after MEASURING the first search results: the top hit for a
# Finance draft was another department's Finance-concurrence clause at 0.905, and its budget-head
# clause at 0.811, while the one clause that actually said what the GR DOES ranked third at
# 0.688. Both are procedural furniture present in a large fraction of all GRs, so they match
# everything and mean nothing. A cross-department conflict check that surfaces "this GR was also
# issued with Finance concurrence" is worse than useless — it buries the real hit.
#
# Applied at SEARCH time as well as at index time (`semantic.ClauseIndex`), so the existing
# index did not have to be re-encoded to benefit.
BOILERPLATE = re.compile(
    r"maharashtra\.gov\.in|संकेतस्थळावर उपलब्ध|राज्यपाल.{0,40}आदेशानुसार|"
    r"सदर शासन निर्णय.{0,60}(संकेतस्थळ|उपलब्ध)|"
    r"या शासन निर्णयाची प्रत|प्रत\s*[,:]|डिजिटल स्वाक्षरी|"
    # procedural furniture — present in a large share of GRs, identical in wording
    r"अनौपचारिक\s*संदर्भ|वित्त\s*विभाग.{0,40}सहमती|"
    r"लेखाशीर्ष|लेखाशिर्ष|प्रधानशिर्ष|मुख्य\s*लेखाशीर्ष|खर्ची\s*टाकण्यात|"
    r"मागणी\s*क्र|उपयोगिता\s*प्रमाणपत्र|"
    r"सांकेतांक|संगणक\s*सांके|या\s*शासन\s*निर्णयासोबत", re.I)


class EmbedUnavailable(RuntimeError):
    pass


@functools.lru_cache(maxsize=2)
def model(lang: str = "mr"):
    """Loaded once per process. ~0.6 s from a warm page cache; the weights are on disk."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:                                    # pragma: no cover
        raise EmbedUnavailable(f"sentence-transformers not installed: {exc}") from exc
    try:
        return SentenceTransformer(MODELS[lang], device="cpu")
    except Exception as exc:
        raise EmbedUnavailable(f"could not load {MODELS[lang]}: {exc}") from exc


def available(lang: str = "mr") -> tuple[bool, str]:
    try:
        m = model(lang)
    except EmbedUnavailable as exc:
        return False, str(exc)
    return True, f"{MODELS[lang]} ({m.get_sentence_embedding_dimension()}-dim, CPU)"


def clauses(text: str, lang: str = "mr") -> list[dict[str, Any]]:
    """The operative clauses of a GR, with their character offsets.

    Only the operative part. A GR's header and `वाचा` block are near-identical across the
    corpus, so indexing them would make every document similar to every other for reasons that
    have nothing to do with what it decides.
    """
    m = OPERATIVE.search(text)
    body = text[m.end():] if m else text
    base = m.end() if m else 0
    stop = END_OF_OPERATIVE.search(body)
    if stop:
        body = body[:stop.start()]

    out: list[dict[str, Any]] = []
    at = 0
    for chunk in SPLIT.split(body):
        if chunk is None:
            continue
        start, at = at, at + len(chunk) + 1
        s = " ".join(chunk.split()).lstrip("-–:. ")
        if not (MIN_CHARS <= len(s) <= MAX_CHARS):
            continue
        if BOILERPLATE.search(s):
            continue
        out.append({"text": s, "offset": base + start,
                    "line": text.count("\n", 0, base + start) + 1})
    return out


def encode(texts: list[str], lang: str = "mr", batch_size: int = 32):
    """L2-normalised vectors, so cosine similarity is a dot product."""
    import numpy as np
    if not texts:
        return np.zeros((0, 768), dtype="float32")
    return model(lang).encode(texts, batch_size=batch_size, normalize_embeddings=True,
                              show_progress_bar=False, convert_to_numpy=True).astype("float32")
