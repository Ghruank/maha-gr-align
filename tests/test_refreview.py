"""The review's identifier gate. No model runs here — `_scrub` is pure text."""
import refreview as R


def test_a_sentence_quoting_a_file_number_is_discarded():
    """The measured failure: Qwen3.5-2B corrupted a Devanagari file number it had been shown
    into `मइवाधो-२०ॲ३५/प्र.क्र.२५/तां.क्र.४`, which no whitelist of uids could catch."""
    text = ("Citation [1] must be corrected. "
            "The order मइवाधो-२०ॲ३५/प्र.क्र.२५/तां.क्र.४ should be replaced. "
            "Citation [2] needs no action.")
    out, dropped = R._scrub(text, 2)
    assert dropped == 1
    assert "मइवाधो" not in out and "[1]" in out and "[2]" in out


def test_invented_line_and_year_numbers_are_discarded():
    out, dropped = R._scrub("Citation [1] is sound. See line 43 of the draft from 2021.", 1)
    assert dropped == 1 and out == "Citation [1] is sound."


def test_a_marker_past_the_end_of_the_list_is_discarded():
    out, dropped = R._scrub("Citation [1] is sound. Citation [9] must be removed.", 2)
    assert dropped == 1 and "[9]" not in out


def test_ordinary_prose_survives_untouched():
    text = "Citations [1] and [2] rest on orders that still stand. No action is needed."
    out, dropped = R._scrub(text, 2)
    assert dropped == 0 and out == text


def test_the_prompt_is_never_shown_an_identifier():
    """Half of the guarantee: the model cannot corrupt what it never saw."""
    report = {
        "document": {"department": "Finance", "date": "2026-08-02"},
        "alignment": {"label": {"en": "NOT aligned"}, "reasons": ["1 superseded."]},
        "citations": [{
            "n": 1, "line": 9, "kind_label": {"en": "Government Resolution"},
            "cited_no": "अर्थसं-२०२५/प्र.क्र.४४/अर्थ-३", "cited_date": "2025-04-07",
            "verdict": "verified", "cross_dept": True,
            "match": {"uid": "202504071435036805", "dept": "Finance", "date": "2025-04-07"},
            "status": {"in_force": False, "superseded_by": [
                {"uid": "202602021844052005", "dept": "Finance", "date": "2026-02-02"}],
                "amended_by": []},
        }],
        "findings": [{"code": "R02", "severity": "error", "citation": 1, "message": "x"}],
    }
    facts = R._facts(report)
    for leak in ("202504071435036805", "202602021844052005", "अर्थसं-२०२५", "2025-04-07",
                 "line 9"):
        assert leak not in facts, f"prompt leaked {leak!r}"


def test_a_court_order_is_never_described_as_missing():
    """The gloss handed to the model must not let it collapse a coverage limit into a defect —
    observed: it paraphrased 'the archive does not hold court orders' as 'absent from the
    archive'. Only one gloss may carry the word MISSING."""
    missing = [k for k, v in R._VERDICT_GLOSS.items() if "MISSING" in v]
    assert missing == ["not_in_archive"]
    assert "NOT a missing reference" in R._VERDICT_GLOSS["out_of_scope"]
