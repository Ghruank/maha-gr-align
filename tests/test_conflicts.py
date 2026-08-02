"""Cross-document amount contradiction — the money case.

`references.py` asks whether the cited order still stands. This asks whether the citing document
agrees with it. Both demo GRs pass the template check, both resolve their citations, and both
name an order in force — the defect exists only between them.
"""

import conflicts as C


FINANCE = "\n".join([
    "विषय :- पायाभूत सुविधा विकासासाठी निधी मंजूर करण्याबाबत.",
    "महाराष्ट्र शासन",
    "वित्त विभाग",
    "शासन निर्णय :-",
    "संस्थेच्या पायाभूत सुविधा विकासासाठी रु. १५,००,००,००० (रुपये पंधरा कोटी फक्त) "
    "इतका निधी मंजूर करण्यात येत आहे.",
])

TARGET = "202608109900000105"


def _report(citation_no="अर्थसं-२०२६/प्र.क्र.८८/अर्थ-३"):
    return {"citations": [{
        "n": 1, "cited_no": citation_no, "cited_date": "2026-08-10",
        "verdict": "verified", "cross_dept": True,
        "match": {"uid": TARGET, "dept": "Finance", "date": "2026-08-10",
                  "decision_no": citation_no, "subject": "Funds", "in_degree": 0},
    }]}


def _text_of(uid):
    return FINANCE if uid == TARGET else None


# --------------------------------------------------------------------------- amounts

def test_devanagari_and_latin_figures_both_parse():
    got = {a["value"] for a in C.amounts(
        "रु. १५,००,००,००० आणि Rs. 2,50,000 आणि ₹ 3 crore")}
    assert {150000000, 250000, 30000000} <= got


def test_a_spelled_out_gloss_is_not_counted_twice():
    """`रु. १५,००,००,००० (रुपये पंधरा कोटी फक्त)` is one figure written twice; the words carry
    no digits, so requiring a digit to open the match keeps it from doubling."""
    assert [a["value"] for a in C.amounts("रु. १५,००,००,००० (रुपये पंधरा कोटी फक्त)")] \
        == [150000000]


# --------------------------------------------------------------------------- the finding

def test_a_restated_figure_that_disagrees_is_a_conflict():
    citing = ("प्रस्तावना :-\nसंदर्भ क्रमांक १ येथील वित्त विभागाच्या शासन निर्णयान्वये "
              "रु. १०,००,००,००० (रुपये दहा कोटी फक्त) इतका निधी मंजूर करण्यात आला आहे.")
    r = C.check(citing, _report(), _text_of)
    assert len(r["conflicts"]) == 1
    k = r["conflicts"][0]
    assert k["claimed"]["value"] == 100000000
    assert k["actual"]["value"] == 150000000
    assert k["delta"] == -50000000
    assert k["cross_dept"] is True


def test_a_part_release_is_not_a_contradiction():
    """`... रु. १५,००,००,००० इतक्या निधीपैकी पहिला हप्ता म्हणून रु. ५,००,००,०००` releases five
    crore out of fifteen. The five is not a claim about what the cited order sanctioned, and
    comparing it against that order's total would be a fabricated defect."""
    citing = ("शासन निर्णय :-\nसंदर्भ क्रमांक १ येथील शासन निर्णयान्वये मंजूर झालेल्या "
              "रु. १५,००,००,००० इतक्या निधीपैकी पहिला हप्ता म्हणून रु. ५,००,००,००० "
              "इतकी रक्कम वितरित करण्यास मान्यता देण्यात येत आहे.")
    assert C.check(citing, _report(), _text_of)["conflicts"] == []


def test_an_agreeing_figure_raises_nothing():
    citing = ("संदर्भ क्रमांक १ येथील शासन निर्णयान्वये रु. १५,००,००,००० इतका निधी "
              "मंजूर करण्यात आला आहे.")
    assert C.check(citing, _report(), _text_of)["conflicts"] == []


# --------------------------------------------------------------------------- restraint

def test_an_amount_not_attributed_to_any_citation_is_ignored():
    """A GR that cites an order AND separately sanctions its own money is the normal case. Only
    a figure explicitly credited to a cited order may be compared against it."""
    citing = ("शासन निर्णय :-\nया संस्थेस रु. ७,००,००,००० इतका निधी मंजूर करण्यात येत आहे.")
    r = C.check(citing, _report(), _text_of)
    assert r["conflicts"] == [] and r["checked"] == 0


def test_an_attribution_cannot_reach_across_a_paragraph_break():
    citing = ("संदर्भ क्रमांक १ येथील शासन निर्णय.\n\n"
              "स्वतंत्र बाब म्हणून रु. ९,००,००,००० इतका निधी मंजूर करण्यात येत आहे.")
    assert C.check(citing, _report(), _text_of)["conflicts"] == []


def test_silence_when_the_cited_order_cannot_be_read():
    """If we cannot read the cited document, our ignorance is not the drafter's error."""
    citing = "संदर्भ क्रमांक १ येथील शासन निर्णयान्वये रु. १०,००,००,००० मंजूर."
    r = C.check(citing, _report(), lambda uid: None)
    assert r["conflicts"] == [] and r["checked"] == 0


def test_the_same_discrepancy_is_reported_once():
    """A figure restated in the preamble and again in the operative paragraph is one defect."""
    citing = ("संदर्भ क्रमांक १ येथील शासन निर्णयान्वये रु. १०,००,००,००० मंजूर.\n\n"
              "संदर्भ क्रमांक १ येथील शासन निर्णयान्वये रु. १०,००,००,००० मंजूर.")
    assert len(C.check(citing, _report(), _text_of)["conflicts"]) == 1


def test_conflict_detection_never_calls_a_model():
    """A restated figure is an integer that matches or does not. Rule 4."""
    import pathlib
    src = (pathlib.Path(C.__file__)).read_text()
    for banned in ("ai.local", "ai.client", "urllib.request", "requests", "ollama"):
        assert banned not in src, f"conflicts.py must stay model-free, found {banned}"
