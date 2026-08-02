#!/usr/bin/env python3
"""
Fetch and verify the local model roster declared in `data/models.json`.

Why this exists: NFR-2 says sensitive drafts must not leave the State Data Centre, so every
model runs on the box. That only holds if the roster is pinned, reproducible and checkable —
"it worked on the laptop" is not a deployment. Run `python fetch_models.py --check` on the
target machine and it tells you exactly what is missing before anything tries to serve.

Two of the models (IndicTrans2) are GATED on HuggingFace. There is no way around that
programmatically: a human must accept the licence once, signed in, on each model page. This
script detects that case and says so rather than failing with a bare 401.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

# MUST be set before huggingface_hub is imported anywhere.
#
# With hf_xet active, the IndicTrans2 downloads stall silently at a fixed byte count — no
# error, no timeout, no progress. Observed twice in a row at identical offsets; disabling
# Xet fixed it immediately. Slower transport, but one that finishes.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ROOT = Path(__file__).resolve().parent
ROSTER = ROOT / "data" / "models.json"

OLLAMA = "http://localhost:11434"


def load_roster() -> dict:
    return json.loads(ROSTER.read_text())


def hf_ids(roster: dict) -> list[tuple[str, str, bool]]:
    """(role, repo_id, gated) for every HuggingFace model in the roster."""
    t = roster["translation"]
    e = roster["embeddings"]
    out = [(f"translation/{k}", v, True) for k, v in t["ids"].items()]
    for key in ("marathi", "marathi_alt", "english"):
        out.append((f"embeddings/{key}", e[key]["id"], False))
    return out


# --------------------------------------------------------------------------------------


def check_ollama(roster: dict) -> bool:
    model = roster["llm"]["id"]
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            tags = {m["name"] for m in json.loads(r.read())["models"]}
    except Exception as exc:
        print(f"  MISSING  {model:44s} ollama not reachable at {OLLAMA} ({exc})")
        return False
    if model in tags:
        print(f"  ok       {model:44s} (ollama)")
        return True
    print(f"  MISSING  {model:44s} run: ollama pull {model}")
    return False


def check_hf(role: str, repo: str, gated: bool) -> bool:
    """Verify real weights are on disk, by looking at the cache directly.

    Two things make the obvious implementation wrong, both found the hard way:

    * `snapshot_download(local_files_only=True)` SUCCEEDS on the empty directory a *failed*
      download leaves behind — it reported two gated, never-downloaded models as present.
    * It also RAISES when the snapshot is merely incomplete against the repo manifest, which
      it always is here because we skip the ONNX/H5/TF duplicates — reporting a fully working
      model as missing.

    So it is wrong in both directions. Look for actual weight bytes instead.
    """
    from huggingface_hub.constants import HF_HUB_CACHE

    root = Path(HF_HUB_CACHE) / f"models--{repo.replace('/', '--')}" / "snapshots"
    weights = [
        p for p in root.rglob("*")
        if p.suffix in (".safetensors", ".bin", ".pt")
        and p.is_file() and p.stat().st_size > 1_000_000
    ] if root.is_dir() else []

    if weights:
        mb = sum(p.stat().st_size for p in weights) / 1e6
        print(f"  ok       {repo:44s} ({role}, {mb:.0f} MB)")
        return True

    note = f"GATED — accept the licence at https://huggingface.co/{repo}" if gated else ""
    print(f"  MISSING  {repo:44s} ({role}) {note}")
    return False


def fetch_hf(role: str, repo: str, gated: bool) -> bool:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import GatedRepoError

    try:
        snapshot_download(repo, ignore_patterns=["*.msgpack", "*.h5", "*.onnx", "*.tflite"])
        print(f"  fetched  {repo}  ({role})")
        return True
    except GatedRepoError:
        print(
            f"  GATED    {repo}\n"
            f"           A human must do this once, it cannot be automated:\n"
            f"             1. open https://huggingface.co/{repo} while signed in\n"
            f"             2. accept the licence\n"
            f"             3. run `hf auth login` and paste a read token\n"
            f"           Then re-run this script."
        )
        return False
    except Exception as exc:
        print(f"  FAILED   {repo}: {type(exc).__name__}: {exc}")
        return False


def fetch_ollama(roster: dict) -> bool:
    model = roster["llm"]["id"]
    print(f"  pulling  {model} …")
    return subprocess.run(["ollama", "pull", model]).returncode == 0


# --------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report what is present without downloading anything")
    args = ap.parse_args()

    roster = load_roster()
    verb = "Checking" if args.check else "Fetching"
    print(f"{verb} local model roster from {ROSTER.relative_to(ROOT)}\n")

    results = [check_ollama(roster) if args.check else fetch_ollama(roster)]
    for role, repo, gated in hf_ids(roster):
        results.append(check_hf(role, repo, gated) if args.check else fetch_hf(role, repo, gated))

    ok, total = sum(results), len(results)
    print(f"\n{ok}/{total} models ready.")
    if ok < total:
        print("The engine degrades rather than crashes on a missing model — but the feature "
              "that depends on it will report itself unavailable.")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
