#!/usr/bin/env python3
"""
Pin the template-boilerplate Devanagari leak into the fixture set.

Why this exists: `select_fixtures.py`'s `devanagari_leakage` bucket filters on
`devanagari_leak > 20`, and the leak histogram spikes at *exactly* 20 — 136 GRs. That
cluster is one systematic IndicTrans2 failure (`सदर` left untranslated, 6x per GR, plus
`अभ` once = 20 chars). The bucket therefore selected the 6 extreme outliers and excluded
every instance of the most common leak pattern in the corpus.

This script is additive by contract: it only appends. No existing fixture uid moves, is
removed, or is re-scored. Rerunning it is idempotent.

Selection is deterministic — 2 from the dominant profile at either end of the date range,
plus the sole variant profile, which carries `सदरच` (`सदर` + suffix) and is the case a
naive substring strip would corrupt.

Usage:
    python3 pin_boilerplate.py data/mahGRs/GRs/Higher_and_Technical_Education_Department fixtures/
"""

import sys, re, json, glob, shutil, collections
from pathlib import Path

import select_fixtures as sf

BUCKET = "template_boilerplate"
TARGET_LEAK = 20


def main(src_dir: str, out_dir: str):
    src, out = Path(src_dir), Path(out_dir)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Idempotence: the bucket is pinned once. Re-running must not pick fresh uids —
    # doing so would grow the fixture set on every invocation.
    if BUCKET in manifest["buckets"]:
        pinned = manifest["buckets"][BUCKET]
        absent = [u for u in pinned
                  if not all((out / f"{u}.pdf.{l}.txt").exists() for l in ("en", "mr"))]
        if absent:
            sys.exit(f"bucket '{BUCKET}' is in the manifest but files are missing: {absent}")
        print(f"bucket '{BUCKET}' already pinned with {len(pinned)} uids: {pinned}")
        print("nothing to do.")
        return

    already = set(manifest["records"])

    # Every GR whose English side carries exactly TARGET_LEAK Devanagari characters.
    cluster = []
    for f in sorted(src.glob("*.en.txt")):
        uid = f.name.split(".")[0]
        en = f.read_text(encoding="utf-8", errors="ignore")
        if len(sf.DEVANAGARI.findall(en)) != TARGET_LEAK:
            continue
        profile = tuple(sorted(collections.Counter(re.findall(r"[ऀ-ॿ]+", en)).items()))
        cluster.append((uid, profile))

    by_profile = collections.Counter(p for _, p in cluster)
    dominant = by_profile.most_common(1)[0][0]

    dom = sorted(uid for uid, p in cluster if p == dominant and uid not in already)
    var = sorted(uid for uid, p in cluster if p != dominant and uid not in already)

    picks = [dom[0], dom[-1]] + var[:1]          # earliest, latest, and the variant
    picks = [u for u in dict.fromkeys(picks)]    # order-preserving dedupe

    print(f"cluster at exactly {TARGET_LEAK} leaked chars: {len(cluster)} GRs, "
          f"{len(by_profile)} distinct profiles")
    print(f"dominant profile ({by_profile[dominant]}x): {dominant}")
    for u, p in [(u, dict(p)) for u, p in cluster if u in picks]:
        print(f"  pinned {u}  {p}")

    if set(picks) & already:
        sys.exit("refusing to run: pick collides with an existing fixture uid")

    for uid in picks:
        for lang in ("en", "mr"):
            shutil.copy(src / f"{uid}.pdf.{lang}.txt", out / f"{uid}.pdf.{lang}.txt")
        en = (src / f"{uid}.pdf.en.txt").read_text(encoding="utf-8", errors="ignore")
        mr = (src / f"{uid}.pdf.mr.txt").read_text(encoding="utf-8", errors="ignore")
        manifest["records"][uid] = sf.score(uid, en, mr)

    manifest["buckets"][BUCKET] = picks
    manifest["selected"] = len(manifest["records"])
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nappended bucket '{BUCKET}' with {len(picks)} uids")
    print(f"fixtures now {manifest['selected']} GRs ({manifest['selected'] * 2} files)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "fixtures")
