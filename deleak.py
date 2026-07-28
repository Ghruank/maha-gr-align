#!/usr/bin/env python3
"""
De-leak Devanagari out of the machine-translated .en side of a GR.

Contract: given the English text of any GR in the corpus, return text containing zero
Devanagari codepoints — with Class B tokens back-transliterated rather than deleted.

Two properties that matter more than they look:

1. Matching is on whole `[ऀ-ॿ]+` runs, never substrings. A naive `text.replace("सदर","")`
   turns `सदरच` into a stranded `च` — still Devanagari, and silently corrupt. Fixture
   202603231852133008 exists to catch exactly that.

2. An unmapped run raises. It never passes through silently, because a survivor would
   reach the resolver as a corrupted decision number and fail invisibly.

Usage:
    python3 deleak.py --audit data/mahGRs/GRs/<Department>     # acceptance test
    python3 deleak.py <file.en.txt>                            # de-leak one file
"""

import sys, re, json, glob
from pathlib import Path

TOKEN = re.compile(r'[ऀ-ॿ]+')
DEVANAGARI = re.compile(r'[ऀ-ॿ]')
MAP_PATH = Path(__file__).parent / "data" / "devanagari_leak_map.json"


class UnmappedToken(Exception):
    """A Devanagari run with no entry in the leak map."""


def load_map(path: Path = MAP_PATH) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {tok: e["replacement"] for tok, e in doc["tokens"].items()}


def deleak(text: str, table: dict) -> str:
    """Replace every Devanagari run via the lookup table. Raises on an unmapped run."""
    unknown = {m.group() for m in TOKEN.finditer(text)} - set(table)
    if unknown:
        raise UnmappedToken(f"no mapping for: {sorted(unknown)}")

    out = TOKEN.sub(lambda m: table[m.group()], text)

    # Stripping a token can leave a doubled space or a space before punctuation.
    # Only touch horizontal whitespace; newlines and table pipes are structural.
    out = re.sub(r'[ \t]{2,}', ' ', out)
    out = re.sub(r' +([,.;:)])', r'\1', out)
    return out


def audit(src_dir: str) -> int:
    table = load_map()
    src = Path(src_dir)

    total = leaked = cleaned = 0
    failures, errors = [], []
    for f in sorted(src.glob("*.en.txt")):
        total += 1
        text = f.read_text(encoding="utf-8", errors="ignore")
        if not DEVANAGARI.search(text):
            continue
        leaked += 1
        try:
            out = deleak(text, table)
        except UnmappedToken as e:
            errors.append((f.name, str(e)))
            continue
        if DEVANAGARI.search(out):
            survivors = sorted({m.group() for m in TOKEN.finditer(out)})
            failures.append((f.name, survivors))
        else:
            cleaned += 1

    print(f"GRs scanned           {total}")
    print(f"GRs with leakage      {leaked}")
    print(f"de-leaked clean       {cleaned}")
    print(f"unmapped-token errors {len(errors)}")
    print(f"Devanagari survivors  {len(failures)}")
    for name, e in errors[:10]:
        print(f"   ERROR   {name}: {e}")
    for name, s in failures[:10]:
        print(f"   SURVIVE {name}: {s}")

    ok = leaked > 0 and cleaned == leaked and not errors and not failures
    print("\n" + ("PASS — zero Devanagari remains across all leaked GRs"
                  if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--audit":
        sys.exit(audit(sys.argv[2]))
    table = load_map()
    sys.stdout.write(deleak(Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore"), table))
