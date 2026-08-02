"""Template Enforcement Engine — SRS FR-10/11/12.

Every test here pins a bug that was actually hit while building, or a rule the Manual states.
No model is involved: `template.verify` is deterministic by design, so these run offline and
in milliseconds.
"""

import template


GOOD_MR = "\n".join([
    "विषय :- चाचणी शासन निर्णय",
    "महाराष्ट्र शासन",
    "उच्च व तंत्र शिक्षण विभाग",
    "शासन निर्णय क्रमांक: अबक-२०२६/प्र.क्र.१/तांशि-१",
    "मंत्रालय, मुंबई ४०० ०३२",
    "दिनांक : १ ऑगस्ट २०२६",
    "वाचा :- शासन निर्णय क्रमांक अबक-२०२५, दि. १ जानेवारी २०२५",
    "प्रस्तावना :- पार्श्वभूमी येथे.",
    "शासन निर्णय :- निर्णय येथे.",
    "महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,",
    "(अ. ब. क.)",
    "अवर सचिव",
    "प्रति,",
])


def test_well_formed_draft_is_compliant():
    assert template.verify(GOOD_MR, "mr")["compliant"]


def test_blank_skeleton_reports_the_unfilled_required_fields():
    r = template.verify(template.render_skeleton("mr"), "mr")
    assert not r["compliant"]
    missing = {f["section"] for f in r["findings"] if f["severity"] == "error"}
    assert {"subject", "department", "signature"} <= missing


def test_governor_line_must_precede_signature():
    """Regression: the ordering check originally fired on the CORRECT order.

    `check(a, b)` reports when a sits after b, so the pair had to be
    ("governor_order", "signature"), not the reverse. The inverted version flagged every
    correctly-ordered draft and passed every wrong one.
    """
    swapped = GOOD_MR.replace(
        "महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,\n(अ. ब. क.)\nअवर सचिव",
        "(अ. ब. क.)\nअवर सचिव\nमहाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,",
    )
    codes = {f["code"] for f in template.verify(swapped, "mr")["findings"]}
    assert "T22" in codes, "swapped order must be flagged"
    assert "T22" not in {f["code"] for f in template.verify(GOOD_MR, "mr")["findings"]}


def test_resolution_before_preamble_is_flagged():
    bad = GOOD_MR.replace(
        "प्रस्तावना :- पार्श्वभूमी येथे.\nशासन निर्णय :- निर्णय येथे.",
        "शासन निर्णय :- निर्णय येथे.\nप्रस्तावना :- पार्श्वभूमी येथे.",
    )
    assert "T20" in {f["code"] for f in template.verify(bad, "mr")["findings"]}


def test_financial_sections_are_conditional():
    """Only 16.3% of the corpus sanctions expenditure. Demanding a budget head from the other
    five sixths would make the checker useless."""
    plain = template.verify(GOOD_MR, "mr")
    assert not plain["financial_sanction_detected"]
    assert "expenditure" not in {f["section"] for f in plain["findings"]}

    money = GOOD_MR.replace("निर्णय येथे.", "रुपये ५,००,००० इतक्या खर्चास मान्यता देण्यात येत आहे.")
    r = template.verify(money, "mr")
    assert r["financial_sanction_detected"]
    assert "expenditure" in {f["section"] for f in r["findings"]}


def test_budget_head_matches_regardless_of_separator_or_script():
    """FR-11 writes the head as 2054-00-101-02, but the corpus OCR emits spaces and Marathi
    GRs use Devanagari digits. A hyphen-anchored regex found ZERO heads in 1,500 real GRs."""
    assert template.find_budget_heads("head 2054-00-101-02 here")
    assert template.find_budget_heads("head 2054 00 101 02 here")
    assert template.find_budget_heads("शीर्ष २०५४-००-१०१-०२ खाली")


def test_department_detected_with_trailing_punctuation():
    """The corpus writes 'वित्त विभाग,' with a comma; a `$`-anchored regex missed it."""
    assert template.verify("वित्त विभाग,", "mr")["sections_present"]["department"]
    assert template.verify("वित्त विभाग", "mr")["sections_present"]["department"]


def test_doc_type_is_named_before_conformance_is_judged():
    """The Manual gives circulars their own form (10.5). Judging one against the resolution
    form (10.6) produces confident nonsense."""
    circular = GOOD_MR.replace("शासन निर्णय क्रमांक:", "परिपत्रक क्रमांक:")
    assert template.verify(circular, "mr")["doc_type"] == "circular"
    assert template.verify(GOOD_MR, "mr")["doc_type"] == "resolution"


def test_render_leaves_no_unfilled_placeholders():
    out = template.render_skeleton("en", {"subject": "X"})
    assert "{" not in out and "}" not in out


def test_verify_never_calls_a_model():
    """FR-12 is computed, not generated. If this import ever appears, the guarantee is gone."""
    src = (template.ROOT / "template.py").read_text()
    for banned in ("ai.local", "ai.client", "urllib.request", "requests"):
        assert banned not in src, f"template.py must stay model-free, found {banned}"


def test_devanagari_word_boundary_trap():
    r"""Regression: `\b` does not work after Devanagari.

    `वाचा` ends in the vowel sign U+093E, a combining mark, which Python's `re` treats as a
    NON-word character — so `\b` after it never matches. The section-boundary regex used to
    end in `\b` and silently matched nothing, which let a completely blank template verify as
    fully filled. Anchor on the separator instead.
    """
    import re
    assert not re.match(r"^(वाचा)\b", "वाचा :-"), "if this passes, Python changed and the fix can be revisited"
    assert template._ANY_LABEL.match("वाचा :-")
    assert template._ANY_LABEL.match("प्रस्तावना :-")
    assert template._ANY_LABEL.match("महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,")
    assert not template._ANY_LABEL.match("शासन आता असे आदेश देत आहे की,")


def test_blank_template_fails_every_required_section():
    """The end-to-end guarantee: an untouched template must never verify as compliant."""
    for lang in ("mr", "en"):
        r = template.verify(template.render_skeleton(lang), lang)
        assert not r["compliant"]
        missing = {f["section"] for f in r["findings"] if f["severity"] == "error"}
        for sid in ("subject", "department", "resolution_no", "date", "preamble",
                    "resolution", "signature"):
            assert sid in missing, f"{lang}: blank {sid} should be reported missing"


# --- OCR / extraction repair -------------------------------------------------------------

def test_visual_order_repair_is_gated_not_blind():
    """Some PDF producers (XeTeX, including our own exporter) write Devanagari into the text
    layer in VISUAL order. Repair is necessary, but the reph rule cannot be idempotent — in
    logical text कर्म presents the same characters — so it must only run behind the gate."""
    import ocr
    good = "विषय :- चाचणी शासन निर्णय विभाग कर्म"
    assert not ocr.looks_visual_order(good)
    assert ocr._tidy(good) == good, "correctly-ordered text must pass through untouched"

    visual = "िवषय :- चाचणी शासन िनणर्य िवभाग"
    assert ocr.looks_visual_order(visual)
    assert "विषय" in ocr.repair_visual_order(visual)
    assert "निर्णय" in ocr.repair_visual_order(visual)


def test_anusvara_space_is_rejoined():
    """XeTeX emits a space at the anusvara glyph boundary: 'शासन निर्णय क्रमां क'. That splits
    the resolution-number keyword and silently costs a required section."""
    import ocr
    broken = "िवषय चाचणी शासन िनणर्य क्रमां क: अबक"
    assert "क्रमांक" in ocr.repair_visual_order(broken)


def test_extraction_reports_its_method():
    """An officer told only '3 errors' cannot tell whether they are reading the document's own
    text or a machine reading of a scan. Those warrant different trust."""
    import ocr
    r = ocr._result("विषय :- चाचणी", "text_layer", 1.0, 1, "note")
    assert r["method"] == "text_layer"
    assert r["script"]["lang"] == "mr"
    assert r["script"]["devanagari_share"] > 0.9


# --------------------------------------------------------------------------- issued mode
#
# Added 2026-08-02, when screening 400 real GRs scored 0.2% compliant. Three separate causes
# were mixed into that number; each is pinned below.

CORRIGENDUM_MR = "\n".join([
    "“महाराष्ट्र राज्य ऑलिम्पिक क्रीडा स्पर्धा” आयोजित करण्याबाबत.",
    "महाराष्ट्र शासन",
    "शालेय शिक्षण व क्रीडा विभाग",
    "शासन शुद्धिपत्रक क्र. संकीर्ण-१०२२/प्र.क्र.४६/क्रीयुसे-२",
    "मंत्रालय विस्तार, मुंबई - ४०० ०३२",
    "दि. २८ सप्टेंबर, २०२२",
    "वाचा - शासन निर्णय समक्रमांक दिनांक ०१ जून, २०२२",
    "शासन शुद्धिपत्रक:",
    "उपरोक्त संदर्भाधीन शासन निर्णयामधील समितीची कार्यकक्षा बदलण्यात येत आहे.",
])


def test_the_operative_section_may_carry_the_document_type_s_own_name():
    """Regression. `DETECT["resolution"]` matched only `शासन निर्णय`, so a memorandum's
    `शासन ज्ञापन :-` and a corrigendum's `शासन शुद्धिपत्रक:` read as a missing operative
    section — 47% of a 400-GR corpus sample, none of them actually defective."""
    r = template.verify(CORRIGENDUM_MR, "mr")
    assert r["sections_present"]["resolution"], "the corrigendum's own header is its operative section"


def test_a_non_resolution_is_not_judged_by_the_resolution_form():
    """The Manual gives a corrigendum its own specimen form. `data/gr_template.json` encodes
    Appendix 10.6 only, so in issued mode a non-resolution may only fail on sections common to
    every form — a corrigendum has no प्रस्तावना and is not defective for lacking one."""
    r = template.verify(CORRIGENDUM_MR, "mr", mode="issued")
    assert r["doc_type"] == "memorandum"          # शुद्धिपत्रक, Appendix 10.4
    errors = {f["section"] for f in r["findings"] if f["severity"] == "error"}
    assert "preamble" not in errors
    assert "preamble" in r["relaxed"]


def test_the_subject_may_be_a_bare_line_above_the_government_line():
    """Regression: the label-anchored pattern reported the subject missing on 388 of 400 real
    GRs, while the mined profile puts it at 93% present. Real GRs rarely write `विषय :-`."""
    r = template.verify(CORRIGENDUM_MR, "mr")
    assert r["sections_present"]["subject"]


def test_a_blank_skeleton_still_fails_on_subject_in_both_modes():
    """The bare-line fallback must not accept a label with nothing after it, or the blank
    template reads as filled — the exact class of bug the LABELLED rule exists to prevent."""
    blank = template.render_skeleton("mr")
    for mode in ("draft", "issued"):
        r = template.verify(blank, "mr", mode=mode)
        assert not r["sections_present"]["subject"], mode
        assert not r["compliant"], mode


def test_issued_mode_does_not_enforce_sections_ocr_cannot_see():
    """The signature block and the Governor's order line are IMAGES in the signed PDF, present
    in 30.4% and 2.2% of the corpus. Enforcing them on an issued document measures the crawl,
    not the drafting. They stay mandatory on a draft."""
    text = "\n".join(l for l in GOOD_MR.splitlines()
                     if "राज्यपाल" not in l and "अवर सचिव" not in l)
    strict = template.verify(text, "mr", mode="draft")
    lenient = template.verify(text, "mr", mode="issued")
    assert not strict["compliant"]
    assert {"governor_order", "signature"} <= set(lenient["relaxed"])
    assert lenient["compliant"]


def test_draft_mode_is_unchanged_and_is_the_default():
    assert template.verify(GOOD_MR, "mr")["mode"] == "draft"
    assert template.verify(GOOD_MR, "mr")["relaxed"] == []
