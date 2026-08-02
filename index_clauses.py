#!/usr/bin/env python3
"""
Build the clause vector index — SRS FR-4/FR-5.

    python index_clauses.py --corpus data/mahGRs/GRs --grs 6000 --out out/clause_index

Writes two files:
    <out>.npz    float16 matrix, one L2-normalised row per clause
    <out>.json   uid / department / date / clause text, aligned row-for-row

## Why a numpy matrix and not FAISS

Neither FAISS nor hnswlib is installed, and neither is needed. At ~23,000 clauses the index is a
23k x 768 matrix; a search is one `matmul` against a 768-vector, which numpy does in a few
milliseconds. An approximate-nearest-neighbour structure would buy speed we do not need and cost
a dependency that would have to be installed on a State Data Centre box. Exact search also means
the similarity scores shown to an officer are exact, not estimates.

float16 halves the file (68 MB -> 34 MB) and costs nothing measurable: the vectors are
L2-normalised so every component is in [-1, 1], where float16 has ~3 decimal digits of
precision, and scores are displayed to two.

## Sampling

`--grs` caps the number of documents read, sampled with a fixed seed across all departments so
the index is reproducible and every department is represented. The full corpus is 17,283 GRs and
~65,000 clauses, which is roughly 20 minutes of CPU encoding — buildable, but not something to
do casually. 6,000 GRs is about 7 minutes and is the committed default.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np

import embed
import resolver as R


def build(corpus: Path, n_grs: int, lang: str, seed: int, batch: int) -> tuple:
    files = sorted(str(p) for p in corpus.glob(f"*/*.{lang}.txt"))
    random.Random(seed).shuffle(files)
    files = files[:n_grs]
    print(f"reading {len(files):,} GRs…")

    meta: list[dict] = []
    texts: list[str] = []
    for p in files:
        uid = Path(p).name.split(".")[0]
        if len(uid) != 18 or not uid.isdigit():
            continue
        try:
            body = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        body = "\n".join(l for l in body.splitlines() if not l.startswith("# Page"))
        for c in embed.clauses(body, lang):
            meta.append({"uid": uid, "dept": R.dept_of(uid), "date": R.uid_date(uid).isoformat(),
                         "text": c["text"], "line": c["line"]})
            texts.append(c["text"])

    print(f"{len(texts):,} clauses from {len(files):,} GRs "
          f"({len(texts)/max(1,len(files)):.1f} each)")
    for d, k in Counter(m["dept"] for m in meta).most_common():
        print(f"    {k:6,}  {d}")

    # Rate is measured over the LAST CHUNK, not since the start.
    #
    # A cumulative average is wrong for a job this long on a laptop: suspend the machine for an
    # hour and the elapsed-time denominator absorbs the whole sleep, so the reported rate
    # collapses and the ETA inflates to nonsense — a run at a healthy 11 clauses/s reported
    # "1 clauses/s, eta 8209s" and looked hung when it was doing exactly what it should.
    t0 = time.time()
    vecs = np.zeros((len(texts), 768), dtype="float32")
    step = max(batch * 20, 500)
    for i in range(0, len(texts), step):
        chunk_start = time.time()
        vecs[i:i + step] = embed.encode(texts[i:i + step], lang, batch_size=batch)
        done = min(i + step, len(texts))
        rate = (done - i) / max(time.time() - chunk_start, 1e-9)
        print(f"  {done:,}/{len(texts):,}  {rate:.0f} clauses/s  "
              f"eta {(len(texts)-done)/max(rate, 1e-9)/60:.0f} min", flush=True)
    print(f"encoded in {time.time()-t0:.0f}s")
    return vecs, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/mahGRs/GRs")
    ap.add_argument("--grs", type=int, default=6000)
    ap.add_argument("--lang", default="mr", choices=["mr", "en"])
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--out", default="out/clause_index")
    a = ap.parse_args()

    ok, detail = embed.available(a.lang)
    if not ok:
        raise SystemExit(f"embedding model unavailable: {detail}")
    print(detail)

    vecs, meta = build(Path(a.corpus), a.grs, a.lang, a.seed, a.batch)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out.with_suffix(".npz"), vectors=vecs.astype("float16"))
    out.with_suffix(".json").write_text(json.dumps({
        "model": embed.MODELS[a.lang], "lang": a.lang, "dim": 768,
        "grs_sampled": a.grs, "seed": a.seed, "clauses": len(meta),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "meta": meta,
    }, ensure_ascii=False), encoding="utf-8")
    mb = out.with_suffix(".npz").stat().st_size / 1e6
    print(f"\nwrote {out}.npz ({mb:.0f} MB) and {out}.json ({len(meta):,} clauses)")


if __name__ == "__main__":
    main()
