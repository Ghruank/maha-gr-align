"""Controlled bilingual terminology — SRS FR-7/8/9.

Runs against the committed `data/glossary.json`, which is the deliverable: a list meant to be
read and corrected by hand. These tests pin the rules that keep it from producing nonsense, and
one measured fact about the corpus that motivates the whole feature.
"""

import glossary


# --------------------------------------------------------------------------- FR-7: the list

def test_the_glossary_loads_and_has_approved_entries():
    ok, detail = glossary.available()
    assert ok, detail
    g = glossary.load()
    assert sum(t["approved"] for t in g["terms"]) >= 10


def test_every_entry_states_its_authority():
    """An officer must be able to see WHY a term is the approved one before acting on it."""
    for t in glossary.load()["terms"]:
        assert t["authority"].strip(), t["id"]


def test_no_approved_term_is_listed_as_its_own_wrong_variant():
    """A self-contradicting entry would flag the correct usage as an error."""
    for t in glossary.load()["terms"]:
        low = {v.lower() for v in t["variants_en"]}
        assert t["en"].lower() not in low, t["id"]


def test_marathi_terms_are_unique():
    """Two entries claiming the same Marathi term would give contradictory suggestions."""
    mr = [t["mr"] for t in glossary.load()["terms"]]
    assert len(mr) == len(set(mr))


# --------------------------------------------------------------------------- FR-8: flagging

def test_the_manual_s_term_is_enforced_against_the_corpus_s_habit():
    """The finding the module exists for. Measured on 2,500 corpus documents: 'Government
    Decision' appears in 1,861 and 'Government Resolution' in 1,021 — while the Manual of
    Office Procedures uses 'Government Resolution' six times and 'Government Decision' never.
    The commonest rendering is the non-standard one, which no amount of mining could reveal."""
    r = glossary.check("Government Decision No. ABC-2026/1 dated 01.08.2026", "en")
    f = next(x for x in r["findings"] if x["found"] == "Government Decision")
    assert f["severity"] == "warning"
    assert f["suggestion"] == "Government Resolution"
    assert "Manual of Office Procedures" in f["authority"]


def test_the_approved_term_raises_nothing():
    r = glossary.check("Government Resolution No. ABC-2026/1 dated 01.08.2026", "en")
    assert not [x for x in r["findings"] if x["term_id"] == "resolution"]


def test_matching_is_whole_phrase_not_substring():
    r"""Regression from seeding: without `\b`, "Re" matched inside "Regarding", "Reference" and
    "Resolution" and scored 2,497 of 2,500 documents; "Memo" matched inside "Memorandum"."""
    r = glossary.check("Regarding the Reference and the Resolution of the Memorandum.", "en")
    found = {x["found"] for x in r["findings"]}
    assert "Memo" not in found and "Re" not in found


def test_an_unapproved_entry_is_advisory_and_says_so():
    """The list is part Manual and part one person's judgement. An officer must be able to tell
    which is which, so an unapproved entry can never raise a warning."""
    for t in glossary.load()["terms"]:
        if t["approved"] or not t["variants_en"]:
            continue
        r = glossary.check(f"This document mentions {t['variants_en'][0]} once.", "en")
        hits = [x for x in r["findings"] if x["term_id"] == t["id"]]
        if hits:
            assert hits[0]["severity"] == "advisory", t["id"]
            return
    raise AssertionError("no unapproved entry with a variant to exercise")


# --------------------------------------------------------------------------- FR-9: suggesting

def test_a_suggestion_is_withheld_where_it_cannot_be_justified():
    """`रद्द` (cancelled), `अधिक्रमित` (superseded) and `व्यपगत` (lapsed) do different things to
    an order, so "cancelled" in an English GR may be a perfectly correct rendering of रद्द.
    Proposing "superseded" there would corrupt the meaning. Declining is the requirement
    working, not failing."""
    non_strict = [t for t in glossary.load()["terms"] if not t["strict"] and t["variants_en"]]
    assert non_strict, "the ambiguity gate has no entries to exercise"
    t = non_strict[0]
    r = glossary.check(f"The order was {t['variants_en'][0]} last year.", "en")
    hits = [x for x in r["findings"] if x["term_id"] == t["id"]]
    if hits:
        assert hits[0]["suggestion"] is None
        assert "no replacement" in hits[0]["message"].lower()


def test_suggest_resolves_a_term_in_either_direction():
    assert glossary.suggest("Government Decision")["en"] == "Government Resolution"
    assert glossary.suggest("शासन निर्णय")["en"] == "Government Resolution"
    assert glossary.suggest("a phrase that is not in the list") is None


# --------------------------------------------------------------------------- the Marathi side

def test_the_marathi_side_lists_terms_rather_than_correcting_them():
    """Marathi is the legally operative text — there is no rendering in it to correct against an
    English glossary. What an officer needs is the English each term must take."""
    r = glossary.check("महाराष्ट्र शासन\nशासन निर्णय क्रमांक : अ-१\nमंत्रालय, मुंबई", "mr")
    assert r["script"] == "mr"
    ids = {t["id"] for t in r["terms_present"]}
    assert {"govt", "resolution", "mantralaya"} <= ids
    assert r["counts"]["warning"] == 0


def test_a_non_standard_marathi_spelling_is_flagged():
    """Both शुद्धिपत्रक and शुध्दीपत्रक occur in the corpus — `template.py` has to accept both."""
    r = glossary.check("शासन शुध्दीपत्रक क्रमांक : अ-१", "mr")
    f = next(x for x in r["findings"] if x["code"] == "G03")
    assert f["suggestion"] == "शुद्धिपत्रक"


# --------------------------------------------------------------------------- guarantees

def test_the_glossary_check_never_calls_a_model():
    src = (glossary.ROOT / "glossary.py").read_text()
    for banned in ("ai.local", "ai.client", "urllib.request", "requests", "ollama"):
        assert banned not in src, f"glossary.py must stay model-free, found {banned}"
