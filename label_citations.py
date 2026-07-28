#!/usr/bin/env python3
"""
Interactive helper for building tests/resolver_truth.json.

This tool does NOT decide anything. It finds citations, shows you the surrounding
text, and lists plausible target GRs ranked by how well their identifiers overlap
the citation. You choose. Your choice is the ground truth.

Deliberately NOT automated: if the answer key is machine-generated, the resolver
tests prove only that the code agrees with itself.

Design notes (learned the hard way — see CLAUDE.md and CHECKLIST.md):

  * A GR's own date comes from the uid filename prefix, NOT from a "Date:" string
    in the body. Body dates parse for only ~8% of GRs when matched unanchored, and
    ~78% of those are CITED dates from the reference block, not the document's own.
  * uid prefix is the portal publication date and may drift from the signing date,
    so candidates are drawn from a +/- day window, not an exact match.
  * Citations come from `parser.parse()`, not from a local regex. The parser already
    handles `Read:` blocks (25.6% of HTE label the reference block that way), rejects
    statutory sub-sections like "Section 40 (1)", and splits enumerated items
    properly. A weaker local regex produced run-on blobs spanning three citations
    with the date of one and the text of another.
  * Candidate identifiers come from the department's `GRs.json` (97.5% coverage)
    unioned with the OCR-parsed header. The metadata `order_number` is 97.6%
    Devanagari, so its *letters* cannot match Latin citation text but its *digits*
    can once folded — and those digits are the signal that disambiguates.
  * `order_number` is a FILE number, not a unique GR id. 41.1% of HTE GRs share
    theirs with at least one other GR (worst case: 41 GRs on one number), because a
    departmental file accumulates decisions over years. So candidates are drawn from
    TWO paths, because neither key is sufficient alone:
        (a) the +/- day window around the cited date  — date-led
        (b) every GR sharing the citation's digit key, ANY date — number-led
    Path (b) matters because a series member can sit months outside the window: one
    fixture cites six GRs under a single file number spanning 2016-2018. It is also
    script-independent — "Muwad-2016/(38/16)/Mashi-1" and the metadata's
    "मुवाढ-२०१६/( ३८/१६ )/मशि-१" both reduce to "201638161", which no Latin-vs-
    Devanagari string match would ever catch. The key is the digits CONCATENATED,
    not a tuple of runs, because Marathi OCR inserts spaces inside Devanagari digit
    runs, so run boundaries are an OCR artefact while the digit sequence is not.
    `digit_key` is imported from resolver.py so the labelling tool and the resolver
    can never drift apart on what "the same file number" means.

Usage:
    python label_citations.py fixtures/ data/mahGRs/GRs/Higher_and_Technical_Education_Department/ \
        --out tests/resolver_truth.json --n 15

Controls:
    1-9   pick that candidate
    n     no target in corpus  (null)
    s     skip / unsure — revisit later
    ?     dump the full citation context, then re-ask
    q     save and quit  (progress kept; rerun to resume)
"""

import re, json, argparse, datetime, hashlib
from pathlib import Path
from collections import defaultdict

import parser as grparser
from resolver import digit_key   # one definition of the match key for the whole project

RE_IDTOK = re.compile(r'[A-Za-z]{2,}|\d{2,4}')
STOP = {'government', 'decision', 'resolution', 'no', 'dated', 'date', 'the', 'and',
        'department', 'of', 'higher', 'technical', 'education', 'maharashtra', 'section',
        'read', 'reference', 'circular', 'order', 'memorandum', 'letter'}

DEV_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

# Departments whose GRs are cited but which are not in a single-department index.
# ~53% of HTE citations leave HTE — flagging them turns a hard call into a 1-second 'n'.
DEPTS = [
    'Finance', 'General Administration', 'School Education', 'Revenue', 'Home',
    'Water Resources', 'Public Works', 'Tribal Development', 'Social Justice',
    'Agriculture', 'Rural Development', 'Urban Development', 'Medical Education',
    'Law and Judiciary', 'Planning', 'Industries', 'Energy', 'Housing',
    'Women and Child', 'Public Health', 'Cooperation', 'Marathi Language',
    'Minority', 'Skill Development', 'Environment', 'Tourism', 'Culture',
    'Transport', 'Food and Civil Supplies', 'Labour', 'Forest',
    'Animal Husbandry', 'Sports',
]


def uid_date(uid: str) -> datetime.date:
    """Authoritative GR date: the uid filename prefix. Always present."""
    return datetime.date(int(uid[0:4]), int(uid[4:6]), int(uid[6:8]))


def id_tokens(s: str) -> set:
    """Identifier tokens, digit-system normalised. Devanagari letters drop out; digits survive."""
    return {t.lower() for t in RE_IDTOK.findall((s or '').translate(DEV_DIGITS))
            if t.lower() not in STOP}


def cite_id(uid: str, cited_date: str, cited_no: str | None) -> str:
    """Content-addressed id: (source, cited date, cited number).

    Deliberately NOT a positional index into the reference list. Hand-labelled truth is the
    one artefact in this project that cannot be regenerated, and `parser.py`'s reference
    extraction will keep improving — a positional id would silently re-point every label the
    next time an item is added or split. This id survives that.

    Two references collapsing to one id is intended, not loss: it means the same order was
    cited twice under different renderings. Observed once in 252 fixture citations — the
    section code `विशि` came out `Vishy-1` in one reference and `Special-1` in another, same
    date, same digit key. One cited order deserves one label."""
    key = f"{cited_date}|{digit_key(cited_no) or (cited_no or '').lower()}"
    return f"{uid}#{cited_date}#{hashlib.md5(key.encode()).hexdigest()[:6]}"


def foreign_dept(text: str, own: str) -> str | None:
    """Name of a department cited that is not the indexed one, if any."""
    for d in DEPTS:
        if d.lower() in own.lower():
            continue
        if re.search(rf'{re.escape(d)}\s+Department', text, re.I):
            return d
    return None


def load_corpus(corpus_dir: Path):
    """Index every GR in the department: authoritative date, both identifier strings, subject."""
    meta_path = corpus_dir / "GRs.json"
    md = {}
    if meta_path.exists():
        for k, v in json.loads(meta_path.read_text(encoding='utf-8')).items():
            md[k.split('.')[0]] = v

    by_date, by_key, meta = defaultdict(list), defaultdict(list), {}
    for f in sorted(corpus_dir.glob("*.en.txt")):
        uid = f.name.split('.')[0]
        m = md.get(uid, {})

        # Latin-script identifier from the OCR header — complements the Devanagari metadata.
        head = f.read_text(encoding='utf-8', errors='ignore')[:1500]
        dn = grparser.DECISION_NO.search(head)
        en_no = grparser._clean_no(dn.group('no')) if dn else None

        mr_no = (m.get('order_number') or '').strip()
        d = uid_date(uid)
        meta[uid] = {
            "date": d,
            "no_mr": ' '.join(mr_no.split()) or '—',
            "no_en": en_no or '—',
            "subject": (m.get('text') or '').strip() or '(no subject in metadata)',
            "idtoks": id_tokens(mr_no) | id_tokens(en_no),
        }
        by_date[d].append(uid)
        for key in {digit_key(mr_no), digit_key(en_no)} - {""}:
            by_key[key].append(uid)
    return by_date, by_key, meta


def citations_from(uid: str, text: str) -> list[dict]:
    """One item per parsed reference that carries a date. Tokens come from that item only."""
    rec = grparser.parse(text, uid)
    out = []
    for r in rec["references"]:
        if not r["date"]:
            continue
        out.append({
            "raw": r["raw"],
            "cited_no": r["decision_no"],
            "cited_date": r["date"],
            "cite_toks": sorted(id_tokens(r["raw"])),
        })
    return out


def rank_candidates(item, by_date, by_key, meta, window):
    """Two retrieval paths, concatenated: date-led first, then number-led.

    Neither key is sufficient alone — dates collide (every GR issued that day) and file
    numbers collide (41.1% of HTE). Showing both, labelled by origin, is what lets a
    human tell a series member from a same-day coincidence."""
    cd = datetime.date.fromisoformat(item["cited_date"])
    ct = set(item["cite_toks"])

    def row(u, via):
        ov = ct & meta[u]["idtoks"]
        return {"uid": u, "delta": (meta[u]["date"] - cd).days,
                "overlap": sorted(ov), "via": via, "score": len(ov)}

    seen, dated = {item["src_uid"]}, []
    for delta in range(-window, window + 1):
        for u in by_date.get(cd + datetime.timedelta(days=delta), []):
            if u in seen:
                continue
            seen.add(u)
            dated.append(row(u, "date"))
    dated.sort(key=lambda r: (-r["score"], abs(r["delta"])))

    numbered = []
    key = digit_key(item["cited_no"])
    if key:
        for u in by_key.get(key, []):
            if u in seen:
                continue
            seen.add(u)
            numbered.append(row(u, "number"))
    numbered.sort(key=lambda r: abs(r["delta"]))

    return dated + numbered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures"); ap.add_argument("corpus")
    ap.add_argument("--out", default="tests/resolver_truth.json")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--window", type=int, default=3, help="+/- days around cited date")
    a = ap.parse_args()

    corpus_dir = Path(a.corpus)
    own_dept = corpus_dir.name.replace('_', ' ')

    out_path = Path(a.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    labelled = {}
    if out_path.exists():
        labelled = {r["id"]: r for r in json.loads(out_path.read_text(encoding='utf-8'))}
        print(f"resuming — {len(labelled)} already labelled\n")

    print("indexing corpus…")
    by_date, by_key, meta = load_corpus(corpus_dir)
    lo, hi = min(by_date), max(by_date)
    print(f"indexed {len(meta)} GRs, {lo} → {hi}")
    print(f"identifiers: {sum(1 for m in meta.values() if m['no_mr'] != '—')} from metadata, "
          f"{sum(1 for m in meta.values() if m['no_en'] != '—')} from OCR header\n")

    queue, texts = [], {}
    for f in sorted(Path(a.fixtures).glob("*.en.txt")):
        uid = f.name.split('.')[0]
        t = f.read_text(encoding='utf-8', errors='ignore')
        texts[uid] = t
        for c in citations_from(uid, t):
            queue.append({"id": cite_id(uid, c["cited_date"], c["cited_no"]),
                          "src_uid": uid, **c})

    def in_range(q):
        return lo <= datetime.date.fromisoformat(q["cited_date"]) <= hi

    def likely_null(q):
        return (not in_range(q)) or foreign_dept(q["raw"], own_dept)

    # Resolvable-looking citations first — they are the ones that teach disambiguation.
    queue.sort(key=lambda q: (bool(likely_null(q)), q["id"]))
    todo = [q for q in queue if q["id"] not in labelled][:a.n]
    n_teach = sum(1 for q in todo if not likely_null(q))
    print(f"{len(queue)} citations in fixtures. Labelling {len(todo)} "
          f"({n_teach} look resolvable, {len(todo)-n_teach} likely 'n')\n")
    print("=" * 78)

    def save():
        out_path.write_text(json.dumps(
            [{k: v for k, v in r.items() if k != 'cite_toks'}
             for r in sorted(labelled.values(), key=lambda r: r["id"])],
            indent=2, ensure_ascii=False), encoding='utf-8')

    for n, item in enumerate(todo, 1):
        ranked = rank_candidates(item, by_date, by_key, meta, a.window)
        while True:
            print(f"\n[{n}/{len(todo)}]  {item['id']}")
            print(f"  source GR : {item['src_uid']}  dated {uid_date(item['src_uid'])}")
            print(f"  citation  : {item['raw'][:230]}")
            if item["cited_no"]:
                print(f"  cited no. : {item['cited_no']}")
            warn = ''
            if not in_range(item):
                warn = '   ** OUTSIDE corpus date range — probably n **'
            else:
                fd = foreign_dept(item["raw"], own_dept)
                if fd:
                    warn = f'   ** cites {fd} Department — not in this index, probably n **'
            print(f"  cited date: {item['cited_date']}{warn}")
            shown = ranked[:9]
            if not shown:
                print(f"  candidates: NONE — no GR within ±{a.window} days, "
                      f"and no GR shares this file number")
            else:
                heading = {"date": f"by date (±{a.window}d), best identifier overlap first",
                           "number": "by file number, any date"}
                via_seen = set()
                for i, r in enumerate(shown, 1):
                    if r["via"] not in via_seen:
                        via_seen.add(r["via"])
                        print(f"  ── {heading[r['via']]} ──")
                    m, delta = meta[r["uid"]], r["delta"]
                    flag = '' if delta == 0 else f'  [{delta:+d}d]'
                    ov = r["overlap"] or '—'
                    print(f"    {i}) {r['uid']}  overlap={ov}{flag}")
                    print(f"       no. : {m['no_mr'][:70]}")
                    print(f"       (en): {m['no_en'][:70]}")
                    print(f"       sub : {m['subject'][:70]}")
            c = input("  → 1-9 / n / s / ? / q : ").strip().lower()
            if c == '?':
                t = texts[item["src_uid"]]
                k = max(t.find(item["raw"][:40]), 0)
                print("\n--- context " + "-" * 60)
                print(t[max(0, k - 600):k + 600])
                print("-" * 72)
                continue
            break

        if c == 'q':
            save(); print(f"\nsaved {len(labelled)} labels → {out_path}"); return
        if c == 's':
            continue
        if c == 'n':
            labelled[item["id"]] = {**item, "expected_uid": None, "note": "not in corpus"}
        elif c.isdigit() and 1 <= int(c) <= len(shown):
            pick = shown[int(c) - 1]
            labelled[item["id"]] = {**item, "expected_uid": pick["uid"],
                                    "note": f"via {pick['via']}, {pick['delta']:+d}d"}
        else:
            print("  (unrecognised — skipped)"); continue
        save()

    save()
    res = sum(1 for r in labelled.values() if r["expected_uid"])
    print(f"\ndone — {len(labelled)} labelled ({res} resolved, {len(labelled)-res} null) "
          f"→ {out_path}")


if __name__ == "__main__":
    main()
