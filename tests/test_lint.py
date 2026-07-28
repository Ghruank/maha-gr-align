#!/usr/bin/env python3
"""
Tests for GR-Lint. Zero API calls, zero labels.

The property that matters most here is **not crying wolf**. A linter that flags three quarters of
a department's own output is worse than no linter: it gets switched off, and the real defects go
with it. Two earlier versions of this module did exactly that, and both bugs are pinned below as
regression tests.
"""

import sys
import json
import random
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lint as L

PROFILE = Path("data/template_profile.json")
CORPUS = Path("data/mahGRs/GRs")

pytestmark = pytest.mark.skipif(
    not PROFILE.exists() or not CORPUS.exists(),
    reason="run: python lint.py --mine data/mahGRs/GRs")


@pytest.fixture(scope="module")
def profile():
    return json.loads(PROFILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sample():
    """A fixed random sample of Marathi GRs with their English counterparts."""
    random.seed(11)
    files = [f for d in CORPUS.iterdir() if d.is_dir() for f in sorted(d.glob("*.mr.txt"))]
    picked = random.sample(files, min(400, len(files)))
    out = []
    for f in picked:
        en = f.with_name(f.name.replace(".mr.", ".en."))
        out.append((f, f.read_text(encoding="utf-8", errors="ignore"),
                    en.read_text(encoding="utf-8", errors="ignore") if en.exists() else None))
    return out


# ------------------------------------------------------- rules must be earned, not asserted

def test_every_rule_carries_a_support_statement(profile):
    """A rule without measured support is an opinion. Opinions do not survive a meeting with a
    Deputy Secretary."""
    for dept in profile["departments"]:
        for r in L.rules_for(profile, dept):
            assert r.get("support"), f"{r['code']} in {dept} has no support statement"
            assert r["severity"] in (L.ERROR, L.WARN, L.INFO)


def test_no_presence_rule_below_ninety_percent(profile):
    """Presence varies hugely by department — `प्रस्तावना` is 78% in School Education and 31% in
    General Administration. Emitting a rule for a convention a department mostly ignores is the
    exact failure this project must avoid."""
    for dept, dp in profile["departments"].items():
        emitted = {r["marker"] for r in L.rules_for(profile, dept) if r["marker"] in L.MARKERS}
        for mk in emitted:
            assert dp["presence"][mk]["rate"] >= 0.90, (
                f"{dept}: rule emitted for {mk} at only "
                f"{dp['presence'][mk]['rate']*100:.1f}% support")


def test_department_specific_rules_actually_differ(profile):
    """If every department got the same rule set, mining would be pointless theatre."""
    sets = {d: frozenset(r["code"] for r in L.rules_for(profile, d))
            for d in profile["departments"]}
    assert len(set(sets.values())) > 1, "all departments produced identical rules"


def test_order_rules_are_consistent_and_free_variation_is_excluded(profile):
    for r in profile["order_rules"]:
        assert r["consistency"] >= L.ORDER_MIN_CONSISTENCY
        assert r["documents"] >= L.ORDER_MIN_SUPPORT
    for r in profile["order_free_variation"]:
        assert r["consistency"] < L.ORDER_MIN_CONSISTENCY
    assert profile["order_free_variation"], (
        "no free-variation pairs recorded — either mining broke, or every ordering is a "
        "convention, which the corpus contradicts")


# ------------------------------------------------------- the two regressions

def test_marathi_line_initial_ordinal_is_not_a_defect():
    """REGRESSION. `१. सदर पदे…` opening a line is correct Marathi numbering, not the fused
    ordinal defect. The first implementation let a preceding `.` plus newline satisfy
    "non-whitespace before", flagging 52% of GRs."""
    ok = "मान्यता देण्यात येत आहे.\n1. सदर पदे ज्या प्रयोजनासाठी निर्माण"
    assert L.find_fused_ordinal(ok) is None
    bad = "The 1.सदर approval will always be on a non-grant basis."
    assert L.find_fused_ordinal(bad) is not None


def test_fused_ordinal_is_reported_from_the_english_side(profile, sample):
    """REGRESSION. The defect is a translation artefact. It must be far commoner in `.en` than in
    `.mr`; the reverse means we are checking the wrong side again."""
    mr = sum(1 for _, m, _ in sample if L.find_fused_ordinal(m))
    en = sum(1 for _, _, e in sample if e and L.find_fused_ordinal(e))
    assert en > mr, f"expected the English side to dominate, got mr={mr} en={en}"


def test_file_number_digits_are_not_read_as_list_ordinals():
    """`१६)` inside `(३८/१६)` is part of a file number. Same trap resolver.py already solved."""
    assert L._ordinals("क्र. मुवाढ-२०१६/(३८/१६)/मशि-१") == []
    assert L._ordinals("१) पहिला\n२) दुसरा\n३) तिसरा") == [1, 2, 3]


# ------------------------------------------------------- the anti-wolf property

def test_most_government_resolutions_pass(profile, sample):
    """**The load-bearing test.** A linter mined from a corpus should find that corpus mostly
    compliant. Two earlier versions scored 1.2% clean; both were bugs in the linter, not an
    epidemic of malformed GRs."""
    clean = 0
    for f, mr, en in sample:
        dept = L._dept_dir_of(f, [p for p in CORPUS.iterdir() if p.is_dir()])
        if not L.lint(mr, profile, dept, en):
            clean += 1
    rate = clean / len(sample)
    assert rate >= 0.60, (
        f"only {rate*100:.1f}% of sampled GRs are clean — the rule set is crying wolf")


def test_errors_are_rare(profile, sample):
    """ERROR severity is reserved for things ≥99% of a department's own output does. It should
    therefore fire on very few documents."""
    errs = 0
    for f, mr, en in sample:
        dept = L._dept_dir_of(f, [p for p in CORPUS.iterdir() if p.is_dir()])
        errs += sum(1 for v in L.lint(mr, profile, dept, en) if v["severity"] == L.ERROR)
    assert errs / len(sample) < 0.10, f"{errs} ERRORs over {len(sample)} GRs is too many"


def test_violations_are_actionable(profile, sample):
    """Every violation must name a rule code, a message, a support figure and a detail — enough
    for a drafting officer to act without reading our source."""
    for f, mr, en in sample[:120]:
        dept = L._dept_dir_of(f, [p for p in CORPUS.iterdir() if p.is_dir()])
        for v in L.lint(mr, profile, dept, en):
            assert v["code"].startswith("GRL-")
            assert v["message"] and v["support"] and v["detail"]
            assert v["line"] is None or v["line"] >= 1


def test_lint_is_deterministic(profile, sample):
    f, mr, en = sample[0]
    dept = L._dept_dir_of(f, [p for p in CORPUS.iterdir() if p.is_dir()])
    assert L.lint(mr, profile, dept, en) == L.lint(mr, profile, dept, en)


def test_unknown_department_degrades_quietly(profile, sample):
    """An unrecognised department yields no rules rather than an exception — a draft from a
    department we have not indexed must not crash the linter."""
    _, mr, en = sample[0]
    assert L.lint(mr, profile, "Nonexistent_Department", en) == []
