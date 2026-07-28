#!/usr/bin/env python3
"""
Property tests for the resolver that need NO hand-labelled answer key.

These do not measure accuracy — only `tests/resolver_truth.json` can do that, and it must be
hand-labelled (CLAUDE.md). What these do is make whole classes of bug impossible, using facts
that hold independently of which uid is the *right* answer:

  * a document cannot cite itself
  * a document cannot cite an order issued after it
  * a resolved uid must exist in the corpus
  * a resolution must rest on two agreeing keys, never on a date alone
  * the same input must always give the same output
  * the English side, whose failure modes are uncorrelated with the Devanagari side, must not
    contradict the Marathi-side answer

The last one is the closest thing to an independent witness this corpus has. It is not a second
run of the same logic: the Marathi path does exact Devanagari string matching against crawled
portal metadata, the English path sees IndicTrans2 transliteration with unstable section codes.
Agreement between them is evidence. Disagreement is a bug in one of them.

Run:  python3 -m pytest tests/test_resolver_invariants.py -q
"""

import sys, json, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import resolver as R
import parser as P

CORPUS = Path("data/mahGRs/GRs/Higher_and_Technical_Education_Department")
FIXTURES = Path("fixtures")
WINDOW = 3

pytestmark = pytest.mark.skipif(
    not CORPUS.exists(), reason=f"corpus not present at {CORPUS} — see CHECKLIST.md step 0")


@pytest.fixture(scope="module")
def idx():
    return R.load_index(CORPUS)


@pytest.fixture(scope="module")
def rows(idx):
    out = []
    for f in sorted(FIXTURES.glob("*.mr.txt")):
        uid = f.name.split('.')[0]
        text = f.read_text(encoding='utf-8', errors='ignore')
        for c in R.extract_mr_citations(text):
            out.append({"src_uid": uid, **c,
                        **R.resolve(c, uid, idx, WINDOW, "Higher and Technical Education")})
    assert out, "no citations extracted — extraction regression, not a test-setup problem"
    return out


@pytest.fixture(scope="module")
def resolved(rows):
    r = [x for x in rows if x["resolved_uid"]]
    assert r, "nothing resolved at all — resolver regression"
    return r


# ---------------------------------------------------------------- no fabrication

def test_resolved_uid_exists_in_corpus(resolved, idx):
    """Rule 3: a surfaced citation must resolve to a real uid or be labelled unresolved."""
    missing = [r for r in resolved if r["resolved_uid"] not in idx[3]]
    assert not missing, f"{len(missing)} resolutions point at uids absent from the corpus"


def test_never_resolves_to_itself(resolved):
    self_cites = [r for r in resolved if r["resolved_uid"] == r["src_uid"]]
    assert not self_cites, f"{len(self_cites)} GRs resolved a citation to themselves"


def test_never_resolves_forward_in_time(resolved):
    """A GR cannot cite an order issued after it. Publication drift justifies a few days of
    slack (uid prefix is the portal date, not the signing date); beyond that it is impossible."""
    bad = []
    for r in resolved:
        src, dst = R.uid_date(r["src_uid"]), R.uid_date(r["resolved_uid"])
        if dst > src + datetime.timedelta(days=WINDOW):
            bad.append((r["src_uid"], r["resolved_uid"], (dst - src).days))
    assert not bad, f"resolved forward in time: {bad[:5]}"


# ------------------------------------------------------- two keys, never one

def test_resolution_always_rests_on_a_number_match(resolved):
    """Date alone is never sufficient — the same-date collision trap. Every resolution must cite
    a number match in its reason."""
    weak = [r for r in resolved
            if not ("exact number" in r["reason"] or "digit key" in r["reason"])]
    assert not weak, f"{len(weak)} resolutions rest on date alone: {[r['reason'] for r in weak[:3]]}"


def test_ambiguity_is_never_silently_resolved(rows):
    """Where two GRs match both keys, the resolver must abstain rather than pick one."""
    amb = [r for r in rows if "ambiguous" in r["reason"]]
    assert all(r["resolved_uid"] is None for r in amb), \
        "an ambiguous citation was resolved to a single uid"


def test_series_without_a_dated_member_stays_unresolved(rows):
    """A file number identifies a FILE (41.1% of HTE GRs share one), so the date selects the
    member. If no member lands in the window the cited GR is absent — snapping to the nearest
    sibling would fabricate a citation."""
    gaps = [r for r in rows if "series but no member" in r["reason"]]
    assert gaps, "expected at least one series-gap case in the fixtures"
    assert all(r["resolved_uid"] is None for r in gaps), \
        "resolved to a sibling in the same file instead of abstaining"


def test_confidence_and_resolution_agree(rows):
    for r in rows:
        if r["resolved_uid"] is None:
            assert r["confidence"] == 0.0, f"unresolved row carries confidence {r['confidence']}"
        else:
            assert 0.0 < r["confidence"] <= 1.0, f"resolved row carries {r['confidence']}"


def test_exact_date_outranks_drifted_date(resolved):
    for r in resolved:
        exact = R.uid_date(r["resolved_uid"]) == datetime.date.fromisoformat(r["cited_date"])
        assert (r["confidence"] >= 0.97) == exact, \
            "confidence must distinguish an exact date hit from one inside the drift window"


# ------------------------------------------------------------- reproducibility

def test_deterministic(idx):
    """Rule 4: deterministic before probabilistic. Reference tracking must be reproducible."""
    f = sorted(FIXTURES.glob("*.mr.txt"))[0]
    uid, text = f.name.split('.')[0], f.read_text(encoding='utf-8', errors='ignore')

    def run():
        return [R.resolve(c, uid, idx, WINDOW, "Higher and Technical Education")["resolved_uid"]
                for c in R.extract_mr_citations(text)]

    assert run() == run() == run()


def test_extraction_rejects_header_words_as_file_numbers(rows):
    """`ाचा`, the tail of the header word `वाचा`, was being captured as a file number."""
    bad = [r for r in rows if r["cited_no"] and
           R.MR_NO_REJECT.search(r["cited_no"])]
    assert not bad, f"noise captured as file numbers: {[r['cited_no'] for r in bad[:5]]}"


def test_file_numbers_contain_a_digit(rows):
    bad = [r["cited_no"] for r in rows if r["cited_no"] and not any(c in '०१२३४५६७८९0123456789'
                                                                   for c in r["cited_no"])]
    assert not bad, f"file numbers with no digits: {bad[:5]}"


def test_scope_buckets_partition_every_citation(rows, idx, capsys):
    """The in-scope rate is a pitch number, so its denominator must be airtight.

    Two ways it could lie: a citation counted in two buckets (inflating the numerator's share) or
    a resolution sitting in a bucket declared unresolvable (which would mean the buckets are not
    describing what the resolver actually did)."""
    counts = R.scope_report(rows, idx)
    capsys.readouterr()
    assert sum(counts.values()) == len(rows), \
        f"buckets sum to {sum(counts.values())} but there are {len(rows)} citations"
    assert counts["in_scope"] > 0, "no citation is in scope — the bucketing has gone wrong"


def test_every_resolution_is_in_scope(rows, idx):
    """A resolution in `not_a_gr`, `other_dept` or `outside_range` means the resolver contradicted
    its own stated reason for calling a citation unresolvable."""
    meta = idx[3]
    dates = [m["date"] for m in meta.values()]
    lo, hi = min(dates), max(dates)
    stray = []
    for r in rows:
        if not r["resolved_uid"]:
            continue
        cd = datetime.date.fromisoformat(r["cited_date"])
        if not r["is_gr"] or "outside this index" in r["reason"] or not (lo <= cd <= hi):
            stray.append((r["src_uid"], r["cited_date"], r["reason"]))
    assert not stray, f"{len(stray)} resolutions fall in a bucket declared unresolvable: {stray[:3]}"


# ------------------------------------------- the independent witness: the other language

def test_english_side_does_not_contradict_marathi_resolution(resolved, idx):
    """Cross-language agreement.

    The Marathi path matches Devanagari file numbers exactly against crawled portal metadata.
    The English path sees IndicTrans2 output where the same number arrives transliterated and
    unstable (`Masi-1` / `Mashi-1` / `Special-1`). The two fail in uncorrelated ways, so where
    both see the same cited date, the digit key of the English citation must not contradict the
    resolved target's own number. Abstention on either side is fine; contradiction is a bug.

    Two English-side rows carry no independent information and are skipped rather than counted:

      * `decision_no` that is merely the cited date again — a parser.py weakness where the
        reference splitter hands back the date as the number. Comparing it to a file number is
        comparing a date to a number, not a cross-language disagreement.
      * nothing at all — the English reference block omitted the number.

    The key is compared **concatenated**, not as a tuple of digit runs, because Marathi OCR
    inserts spaces inside Devanagari digit runs: `( १२ ९/१३ )` segments as `2013|12|9|13|2`
    while the English `(129/13)` segments as `2013|129|13|2`. Both concatenate to `201312913`.
    Segment boundaries are an OCR artefact; the digit sequence is not.

    Agreement means *containment in either direction*, not equality, because IndicTrans2 reorders
    the components of a file number and parser.py's capture stops at the first comma, so the
    English key is sometimes a truncation of the real one — observed once here:
    `संकीर्ण-२०१६/प्र.क्र.२६२/१६/विशि-१` (`2016262161`) arrived as
    `262/16/ VC-1, 2016/ No. 262/16/ VC-1`, captured as `262/16/ VC-1` → `262161`, with the year
    run stranded after the comma. Dropping digits is a transcription loss; *substituting* them
    would be a different file, and containment still rejects that. 10 of the 11 comparable rows
    match exactly, and the relaxed check remains discriminating: a mean of 3.6 GRs out of 4,718
    are compatible with a given English key, so it excludes 99.92% of the corpus.
    """
    meta = idx[3]
    contradictions = []
    by_src = {}
    for r in resolved:
        by_src.setdefault(r["src_uid"], []).append(r)

    for src_uid, rs in by_src.items():
        en = FIXTURES / f"{src_uid}.pdf.en.txt"
        if not en.exists():
            continue
        rec = P.parse(en.read_text(encoding='utf-8', errors='ignore'), src_uid)
        en_by_date = {}
        for ref in rec["references"]:
            if ref["date"]:
                en_by_date.setdefault(ref["date"], []).append(ref["decision_no"])

        for r in rs:
            en_nos = en_by_date.get(r["cited_date"])
            if not en_nos:
                continue                                  # English side abstains — fine
            target_key = R.digit_key(meta.get(r["resolved_uid"], {}).get("no", ""))
            if not target_key:
                continue
            en_keys = [R.digit_key(n) for n in en_nos
                       if n and not _is_just_the_date(n, r["cited_date"])]
            en_keys = [k for k in en_keys if k]
            if en_keys and not any(k in target_key or target_key in k for k in en_keys):
                contradictions.append((src_uid, r["cited_date"], r["resolved_uid"],
                                       target_key, en_keys))

    assert not contradictions, (
        f"{len(contradictions)} Marathi-side resolutions contradicted by the English text "
        f"(first 3: {contradictions[:3]})")


def _is_just_the_date(no: str, cited_date: str) -> bool:
    """True when a `decision_no` is only a restatement of the citation's date, in any order.

    parser.py sometimes returns e.g. `'22.02.2018'` as the decision number for a reference dated
    2018-02-22. Such a row carries no information the resolver did not already use, so it can
    neither confirm nor contradict a resolution."""
    digits = R.digit_key(no)
    if not digits:
        return False
    y, m, d = cited_date.split('-')
    return digits in {f"{d}{m}{y}", f"{y}{m}{d}", f"{d.lstrip('0')}{m.lstrip('0')}{y}"}
