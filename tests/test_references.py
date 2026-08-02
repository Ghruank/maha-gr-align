"""Reference Parser Module — SRS FR-1/2/3 and cross-department conflict detection.

Every test runs against a SYNTHETIC eight-node archive rather than `out/graph.json`. Two reasons:
the suite must stay offline and fast (CLAUDE.md working conventions), and a test whose expected
answer depends on which departments happened to be crawled is a test that breaks whenever the
corpus is widened. What is pinned here is behaviour, not corpus content.

Most of these pin a bug that was actually hit while building. The dates below sit inside the
archive's synthetic coverage on purpose — `outside_range` is a separate verdict and has its own
test, so a date drifting out of range must never be the silent cause of another test failing.
"""

import datetime

import pytest

import references as X


# --------------------------------------------------------------------------- fixture archive

def _node(uid, dept, no, subject, in_degree=0):
    return {"uid": uid, "date": f"{uid[0:4]}-{uid[4:6]}-{uid[6:8]}", "dept": dept,
            "dept_code": uid[-2:], "decision_no": no, "subject": subject,
            "in_degree": in_degree, "out_degree": 0, "in_corpus": True}


def _edge(src, dst, type_, evidence):
    return {"src": src, "dst": dst, "type": type_, "confidence": 0.9,
            "evidence": evidence, "evidence_en": None, "cue": evidence,
            "evidence_kind": "citation", "cross_dept": False}


# Two departments. `FIN_LIVE` is in force and three GRs across two other departments stand on it,
# so blast radius has something to report; `FIN_DEAD` was superseded by `FIN_KILLER`; `HTE_AMEND`
# is in force but amended.
FIN_LIVE = "202001151030000005"
FIN_DEAD = "202002031610000005"
FIN_KILLER = "202104021840000005"
HTE_AMEND = "202003100900000008"
HTE_AMENDER = "202105110900000008"
HTE_DEP1 = "202006010900000008"
HTE_DEP2 = "202007010900000008"
GAD_DEP3 = "202008010900000007"


@pytest.fixture(scope="module")
def arc():
    graph = {
        "meta": {},
        "nodes": [
            _node(FIN_LIVE, "Finance", "अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "Live Finance circular", 3),
            _node(FIN_DEAD, "Finance", "पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "Superseded Finance order", 1),
            _node(FIN_KILLER, "Finance", "पदनि-२०२१/प्र.क्र.९/आ.पु.क.", "Replacement Finance order"),
            _node(HTE_AMEND, "Higher and Technical Education",
                  "मुवाढ-२०२०/(३८/२०)/मशि-१", "Amended HTE resolution", 1),
            _node(HTE_AMENDER, "Higher and Technical Education",
                  "मुवाढ-२०२१/(३९/२१)/मशि-१", "Amending HTE resolution"),
            _node(HTE_DEP1, "Higher and Technical Education", "अ-१/२०२०", "Dependent one"),
            _node(HTE_DEP2, "Higher and Technical Education", "अ-२/२०२०", "Dependent two"),
            _node(GAD_DEP3, "General Administration", "ब-३/२०२०", "Dependent three"),
        ],
        "edges": [
            _edge(FIN_KILLER, FIN_DEAD, "SUPERSEDES", "उक्त शासन निर्णय रद्द करण्यात येत आहे."),
            _edge(HTE_AMENDER, HTE_AMEND, "AMENDS", "सदर शासन निर्णयात अंशत: सुधारणा करण्यात येत आहे."),
            _edge(HTE_DEP1, FIN_LIVE, "REFERENCES", "…"),
            _edge(HTE_DEP2, FIN_LIVE, "REFERENCES", "…"),
            _edge(GAD_DEP3, FIN_LIVE, "REFERENCES", "…"),
        ],
        "unresolved": [],
    }
    return X.Archive(graph)


def _doc(dept_line, refs, body="शासन निर्णय :-\nनिर्णय येथे.", date="१५ जून, २०२२"):
    """A Manual-shaped Marathi document with the given reference items."""
    items = "\n".join(f"{n}) {r}" for n, r in enumerate(refs, 1))
    return "\n".join([
        "विषय :- चाचणी",
        "महाराष्ट्र शासन",
        dept_line,
        "शासन निर्णय क्रमांक : चाचणी-२०२२/प्र.क्र.१/अ-१",
        "मंत्रालय, मुंबई ४०० ०३२",
        f"दिनांक : {date}",
        f"वाचा :- {items}",
        body,
    ])


def _cite(no, date, word="शासन निर्णय", dept=""):
    return f"{word}, {dept} क्रमांक {no}, दिनांक {date}."


def _by_n(report, n):
    return next(c for c in report["citations"] if c["n"] == n)


def _codes(report):
    return {f["code"] for f in report["findings"]}


# --------------------------------------------------------------------------- FR-1: extraction

def test_extracts_every_reference_item(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०"),
        _cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०"),
    ]), "mr", arc)
    assert r["summary"]["citations"] == 2
    assert all(c["zone"] == "preamble" for c in r["citations"])


def test_classifies_court_orders_circulars_and_resolutions(arc):
    """FR-1 names three document types and they are not interchangeable — see the next test."""
    r = X.check(_doc("वित्त विभाग", [
        _cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०", word="शासन परिपत्रक"),
        "मा. उच्च न्यायालय, मुंबई यांचे रिट याचिका क्रमांक ४४१२/२०२१ मधील दिनांक १२.०३.२०२१ रोजीचे आदेश.",
        _cite("मुवाढ-२०२०/(३८/२०)/मशि-१", "१०.०३.२०२०"),
    ]), "mr", arc)
    assert [c["kind"] for c in r["citations"]] == ["circular", "court", "gr"]


def test_a_court_order_is_out_of_scope_not_missing(arc):
    """The mahGRs archive does not hold court orders. Reporting one as a missing GR would be a
    claim about the draft when it is a fact about our coverage."""
    r = X.check(_doc("वित्त विभाग", [
        "मा. उच्च न्यायालय, मुंबई यांचे रिट याचिका क्रमांक ४४१२/२०२१ मधील दिनांक १२.०३.२०२१ रोजीचे आदेश.",
    ]), "mr", arc)
    c = _by_n(r, 1)
    assert c["verdict"] == "out_of_scope"
    assert r["counts"]["error"] == 0


# --------------------------------------------------------------------------- FR-2: resolution

def test_a_citation_present_in_the_archive_verifies(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०"),
    ]), "mr", arc)
    c = _by_n(r, 1)
    assert c["verdict"] == "verified"
    assert c["match"]["uid"] == FIN_LIVE
    assert c["status"]["in_force"] is True


def test_an_absent_order_in_range_is_the_only_red_verdict(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("नाही-२०२०/प्र.क्र.९९/क्ष-९", "१५.०५.२०२०"),
    ]), "mr", arc)
    assert _by_n(r, 1)["verdict"] == "not_in_archive"
    assert "R01" in _codes(r)


def test_a_date_outside_coverage_is_not_reported_as_missing(arc):
    """The archive begins in 2020 here. An order cited from 2015 cannot be in it, so its absence
    says nothing about the draft and must not be styled as a defect."""
    r = X.check(_doc("वित्त विभाग", [
        _cite("जुने-२०१५/प्र.क्र.१/अ-१", "१५.०१.२०१५"),
    ]), "mr", arc)
    assert _by_n(r, 1)["verdict"] == "outside_range"
    assert r["counts"]["error"] == 0


def test_a_citation_with_no_file_number_abstains(arc):
    """Date alone cannot identify an order — every GR issued that day would match. Abstention is
    the required behaviour (CLAUDE.md rule 3), not a resolution to the nearest candidate."""
    r = X.check(_doc("वित्त विभाग", [
        "शासन निर्णय, वित्त विभाग, दिनांक १५.०१.२०२०.",
    ]), "mr", arc)
    c = _by_n(r, 1)
    assert c["verdict"] == "unverifiable"
    assert c["match"] is None


def test_a_reference_list_pointer_is_not_treated_as_a_file_number(arc):
    """Regression. `संदर्भ क्र. १६ येथील शासन निर्णय` means "the GR at reference no. 16" — a
    pointer into the document's own list. It was being read as file number `१६`, which resolves
    to nothing, and reported as a missing archive entry: a fabricated defect."""
    r = X.check(_doc("वित्त विभाग",
                     [_cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०")],
                     body="शासन निर्णय :-\nसंदर्भ क्र. १६ येथील शासन निर्णयान्वये दिनांक ०९.०९.२०२० "
                          "रोजी मान्यता देण्यात आली होती."),
                "mr", arc)
    pointer = [c for c in r["citations"] if c["zone"] == "body"]
    assert all(c["verdict"] != "not_in_archive" for c in pointer)


# --------------------------------------------------------------------------- FR-3 + conflicts

def test_citing_a_superseded_order_is_an_error_carrying_its_evidence(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०"),
    ]), "mr", arc)
    c = _by_n(r, 1)
    assert c["verdict"] == "verified" and c["status"]["in_force"] is False
    f = next(f for f in r["findings"] if f["code"] == "R02")
    assert f["severity"] == "error"
    # No evidence, no edge, no finding. A supersession claim must show the sentence behind it.
    assert "रद्द" in f["evidence"]
    assert f["related"] == FIN_KILLER


def test_supersession_across_departments_is_a_distinct_finding(arc):
    """R11: a General Administration draft standing on a Finance order that Finance has since
    replaced. Invisible from either document alone, which is why it gets its own code."""
    r = X.check(_doc("सामान्य प्रशासन विभाग", [
        _cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०"),
    ]), "mr", arc)
    assert "R11" in _codes(r) and "R02" not in _codes(r)
    assert _by_n(r, 1)["cross_dept"] is True


def test_an_amended_order_warns_rather_than_errors(arc):
    r = X.check(_doc("उच्च व तंत्र शिक्षण विभाग", [
        _cite("मुवाढ-२०२०/(३८/२०)/मशि-१", "१०.०३.२०२०"),
    ]), "mr", arc)
    f = next(f for f in r["findings"] if f["code"] == "R03")
    assert f["severity"] == "warning"
    assert f["related"] == HTE_AMENDER


def test_cancelling_an_order_reports_who_still_depends_on_it(arc):
    """R12 — blast radius before the damage. Three GRs stand on FIN_LIVE, two in HTE and one in
    GAD, and none of them can see this draft coming."""
    r = X.check(_doc("वित्त विभाग",
                     [_cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०")],
                     body="शासन निर्णय :-\nसंदर्भ क्रमांक १ येथील शासन परिपत्रक, वित्त विभाग, "
                          "क्रमांक अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३, दिनांक १५.०१.२०२० "
                          "याद्वारे रद्द करण्यात येत आहे."),
                "mr", arc)
    f = next(f for f in r["findings"] if f["code"] == "R12")
    assert f["blast"]["live"] == 3
    assert set(f["blast"]["departments"]) == {"Higher and Technical Education",
                                              "General Administration"}


def test_the_same_order_cited_twice_is_one_row(arc):
    """The preamble names an order and the operative paragraph names it again. One legal fact,
    one row — otherwise the citation count inflates on a formatting habit."""
    r = X.check(_doc("वित्त विभाग",
                     [_cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०")],
                     body="शासन निर्णय :-\nसंदर्भ क्रमांक १ येथील शासन निर्णय क्रमांक "
                          "पदनि-२०२०/प्र.क्र.८/आ.पु.क., दिनांक ०३.०२.२०२० याद्वारे रद्द "
                          "करण्यात येत आहे."),
                "mr", arc)
    assert r["summary"]["citations"] == 1
    assert _by_n(r, 1)["also_at_lines"]           # the body mention is remembered, not dropped


# --------------------------------------------------------------------------- header parsing

def test_the_documents_own_date_is_not_taken_from_a_citation():
    """Regression, measured on fixture 201803071449402308: the document's own date is 07.03.2018
    and the first numeric date in the file is 04.10.2004, belonging to its first citation. The
    misread is not cosmetic — the document date is the horizon for "a GR cannot cite an order
    issued after it", so a 2004 header date silently rejects every real citation."""
    text = _doc("वित्त विभाग", [_cite("अ-२००४/प्र.क्र.१/ब-१", "०४.१०.२००४")],
                date="७ मार्च, २०१८")
    assert X.doc_date(text)[0] == datetime.date(2018, 3, 7)


def test_the_department_is_not_taken_from_a_cited_order():
    """Below the वाचा line every cited order names its own department."""
    text = _doc("उच्च व तंत्र शिक्षण विभाग",
                [_cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०", dept="वित्त विभाग,")])
    assert X.doc_dept(text) == "Higher and Technical Education"


def test_an_unlabelled_reference_block_still_counts_as_the_preamble():
    """IndicTrans2 routinely drops the `वाचा :` header, so the English rendering of a GR with a
    perfectly good reference block arrives as bare lines. Labelling those citations as body
    mentions would warn that the preamble cites nothing when in fact it cites everything."""
    text = "\n".join([
        "Subject :- Test",
        "The Government of Maharashtra",
        "Finance Department",
        "GOVERNMENT DECISION NO.: TEST-2022/1/A-1",
        "Mantralaya, Mumbai 400 032",
        "Date of release: June 15, 2022",
        "Government Resolution No. Arthasan-2020/ Pr.Kr.12/ Artha-3 dated 15.01.2020.",
        "Government Decision:",
        "Decision here.",
    ])
    r = X.check(text, "en", X.Archive({"meta": {}, "nodes": [
        _node(FIN_LIVE, "Finance", "अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "Live Finance circular")],
        "edges": [], "unresolved": []}))
    assert r["document"]["date"] == "2022-06-15"
    assert r["citations"] and r["citations"][0]["zone"] == "preamble"
    assert "R13" not in _codes(r)


def test_english_citations_resolve_through_the_digit_key(arc):
    """The archive's `order_number` is Devanagari; an English citation carries a transliterated
    file number, and transliteration is unstable across GRs for the same file. Digits survive
    both, which is the only reason the English path can resolve at all."""
    text = "\n".join([
        "Subject :- Test",
        "The Government of Maharashtra",
        "Finance Department",
        "Mantralaya, Mumbai 400 032",
        "Date: 15.06.2022",
        "Read :- 1) Government Resolution No. Padani-2020/ Pr.Kr.8/ A.P.C. dated 03.02.2020.",
        "Government Decision:",
    ])
    r = X.check(text, "en", arc)
    assert _by_n(r, 1)["match"]["uid"] == FIN_DEAD


# --------------------------------------------------------------------------- guarantees

def test_the_reference_check_never_calls_a_model():
    """Rule 4. Whether a cited order was superseded is settled by a graph edge, never asserted by
    a model. If one of these imports ever appears, the guarantee is gone."""
    src = (X.P.Path(__file__).resolve().parent.parent / "references.py").read_text()
    for banned in ("ai.local", "ai.client", "urllib.request", "requests", "ollama"):
        assert banned not in src, f"references.py must stay model-free, found {banned}"


def test_verdict_buckets_are_exhaustive_and_the_summary_adds_up(arc):
    """The denominator cannot be gamed: every citation lands in exactly one verdict, and the
    headline counts partition the total."""
    r = X.check(_doc("वित्त विभाग", [
        _cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०"),
        _cite("नाही-२०२०/प्र.क्र.९९/क्ष-९", "१५.०५.२०२०"),
        _cite("जुने-२०१५/प्र.क्र.१/अ-१", "१५.०१.२०१५"),
        "मा. उच्च न्यायालय, मुंबई यांचे याचिका क्रमांक ४४१२/२०२१ दिनांक १२.०३.२०२१ रोजीचे आदेश.",
        "शासन निर्णय, वित्त विभाग, दिनांक १५.०१.२०२०.",
    ]), "mr", arc)
    s = r["summary"]
    assert set(s["by_verdict"]) <= set(X.VERDICTS)
    assert sum(s["by_verdict"].values()) == s["citations"]
    assert (s["verified"] + s["not_in_archive"] + s["unverifiable"]
            + s["out_of_scope"]) == s["citations"]


def test_an_absent_archive_degrades_instead_of_raising():
    r = X.check("विषय :- चाचणी", "mr", X.Archive({"meta": {}, "nodes": [], "edges": [],
                                                  "unresolved": []}))
    assert r["available"] is False and "hint" in r


# --------------------------------------------------------------------------- alignment verdict

def test_alignment_is_misaligned_when_a_cited_order_was_superseded(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("पदनि-२०२०/प्र.क्र.८/आ.पु.क.", "०३.०२.२०२०"),
    ]), "mr", arc)
    assert r["alignment"]["verdict"] == "misaligned"


def test_alignment_is_misaligned_when_a_cited_order_is_absent(arc):
    r = X.check(_doc("वित्त विभाग", [
        _cite("नाही-२०२०/प्र.क्र.९९/क्ष-९", "१५.०५.२०२०"),
    ]), "mr", arc)
    assert r["alignment"]["verdict"] == "misaligned"


def test_alignment_is_aligned_when_every_resolvable_order_is_in_force(arc):
    """A court order alongside is fine: the archive never holds those, so not checking one
    cannot cost the document its verdict."""
    r = X.check(_doc("वित्त विभाग", [
        _cite("अर्थसं-२०२०/प्र.क्र.१२/अर्थ-३", "१५.०१.२०२०"),
        "मा. उच्च न्यायालय, मुंबई यांचे रिट याचिका क्रमांक ४४१२/२०२१ मधील दिनांक १२.०३.२०२१ रोजीचे आदेश.",
    ]), "mr", arc)
    assert r["alignment"]["verdict"] == "aligned"


def test_an_amended_citation_is_partial_not_misaligned(arc):
    """The order still stands, so the document is not resting on nothing — but the officer
    should cite the amendment. Collapsing this into 'misaligned' would overstate it."""
    r = X.check(_doc("उच्च व तंत्र शिक्षण विभाग", [
        _cite("मुवाढ-२०२०/(३८/२०)/मशि-१", "१०.०३.२०२०"),
    ]), "mr", arc)
    assert r["alignment"]["verdict"] == "partial"


def test_nothing_checkable_is_unverified_not_aligned(arc):
    """Saying 'aligned' when nothing could be checked would be a claim we have not earned."""
    r = X.check(_doc("वित्त विभाग", [
        "मा. उच्च न्यायालय, मुंबई यांचे याचिका क्रमांक ४४१२/२०२१ दिनांक १२.०३.२०२१ रोजीचे आदेश.",
    ]), "mr", arc)
    assert r["alignment"]["verdict"] == "unverified"


def test_the_alignment_verdict_is_computed_without_a_model():
    src = (X.P.Path(__file__).resolve().parent.parent / "references.py").read_text()
    assert "_alignment" in src
    for banned in ("ai.local", "ai.client", "ollama"):
        assert banned not in src


# --------------------------------------------------------------------------- month skeletons

def test_month_names_survive_visual_order_reordering():
    """Regression: a PDF text layer returns `एप्रिल` (April) as `एिप्रल`, matras reordered.
    A literal month table matched neither, so the document's own date silently became today —
    which flips a 'superseded since' finding into 'was already superseded'."""
    text = _doc("वित्त विभाग", [_cite("अ-२०२०/प्र.क्र.१/ब-१", "१५.०१.२०२०")],
                date="३० एिप्रल, २०२४")
    assert X.doc_date(text)[0] == datetime.date(2024, 4, 30)


def test_month_skeletons_stay_distinct():
    """Stripping matras must not merge two months into one key."""
    assert len(X.MONTH_BY_SKELETON) == 12
