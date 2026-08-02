"""Semantic conflict detection — SRS FR-4/5/6.

No model runs here. Clause extraction is pure regex, and the search is exercised against a tiny
synthetic index with hand-made vectors, so the suite stays offline and fast (CLAUDE.md working
conventions). What the real model can and cannot separate is measured in `embed.py`'s docstring
and is a property of the model, not something a unit test can assert.
"""

import json

import numpy as np
import pytest

import embed
import semantic


GR = "\n".join([
    "विषय :- चाचणी",
    "महाराष्ट्र शासन",
    "वित्त विभाग",
    "शासन निर्णय क्रमांक : अ-२०२६/१",
    "वाचा :- शासन निर्णय क्रमांक ब-२०२५, दिनांक ०१.०१.२०२५.",
    "प्रस्तावना :-",
    "ही पार्श्वभूमी आहे आणि ती अनुक्रमित होऊ नये कारण ती प्रस्तावनेत आहे, निर्णयात नाही.",
    "शासन निर्णय :-",
    "संस्थेच्या पायाभूत सुविधा विकासासाठी रु. १५,००,००,००० इतका निधी मंजूर करण्यात येत आहे.",
    "२. सदर खर्च २२०३-००-८००-०१ या लेखाशीर्षाखाली खर्ची टाकण्यात यावा आणि तो नियमानुसार असावा.",
    "३. सदर शासन निर्णय महाराष्ट्र शासनाच्या www.maharashtra.gov.in संकेतस्थळावर उपलब्ध आहे.",
    "महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने,",
    "अवर सचिव",
    "प्रति,",
    "१) संचालक, तंत्र शिक्षण संचालनालय, महाराष्ट्र राज्य, मुंबई.",
])


# --------------------------------------------------------------------------- FR-4: clauses

def test_only_the_operative_section_is_indexed():
    """The header and the वाचा block are near-identical across the corpus. Indexing them would
    make every GR the nearest neighbour of every other for reasons unrelated to what it decides."""
    got = [c["text"] for c in embed.clauses(GR)]
    assert any("पायाभूत सुविधा" in c for c in got)
    assert not any("पार्श्वभूमी" in c for c in got), "preamble must not be indexed"
    assert not any("वाचा" in c for c in got)


def test_the_distribution_list_is_not_indexed():
    """`२) संचालक, तंत्र शिक्षण संचालनालय…` appears near-verbatim in thousands of GRs and would
    dominate any nearest-neighbour search."""
    assert not any("संचालनालय" in c["text"] for c in embed.clauses(GR))


def test_website_boilerplate_is_not_indexed():
    assert not any("maharashtra.gov.in" in c["text"] for c in embed.clauses(GR))


def test_clauses_carry_a_line_number():
    """FR-6 shows the officer where in their draft the match came from."""
    for c in embed.clauses(GR):
        assert c["line"] >= 1
        assert GR.splitlines()[c["line"] - 1].strip()


# --------------------------------------------------------------------------- FR-5: search

def _index(tmp_path, rows):
    """A 3-dimensional synthetic index. Vectors are hand-made and L2-normalised."""
    vecs = np.array([r[3] for r in rows], dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    p = tmp_path / "ix"
    np.savez_compressed(p.with_suffix(".npz"), vectors=vecs.astype("float16"))
    p.with_suffix(".json").write_text(json.dumps({
        "model": "synthetic", "lang": "mr", "dim": 3, "clauses": len(rows),
        "meta": [{"uid": r[0], "dept": r[1], "date": "2024-01-01", "text": r[2], "line": 1}
                 for r in rows],
    }, ensure_ascii=False), encoding="utf-8")
    return semantic.ClauseIndex(p)


ROWS = [
    ("100000000000000005", "Finance", "finance clause A", [1.0, 0.0, 0.0]),
    ("200000000000000005", "Finance", "finance clause B", [0.98, 0.02, 0.0]),
    ("300000000000000008", "Higher and Technical Education", "hte clause", [0.95, 0.05, 0.0]),
    ("400000000000000021", "School Education", "unrelated", [0.0, 0.0, 1.0]),
]


def test_the_officers_own_department_is_excluded(tmp_path):
    """FR-5 asks for clauses from OTHER departments. Within a department an officer already
    knows the standing orders; the failure this addresses is the one nobody can see."""
    ix = _index(tmp_path, ROWS)
    q = np.array([[1.0, 0.0, 0.0]], dtype="float32")
    hits = ix.search(q, exclude_dept="Finance", top_k=5, min_score=0.1)[0]
    assert hits and all(h["dept"] != "Finance" for h in hits)


def test_one_hit_per_source_gr(tmp_path):
    """Several clauses of one GR routinely match. Without collapsing, a single document fills
    the whole list and hides every other department."""
    rows = ROWS + [("300000000000000008", "Higher and Technical Education",
                    "hte clause two", [0.94, 0.06, 0.0])]
    ix = _index(tmp_path, rows)
    q = np.array([[1.0, 0.0, 0.0]], dtype="float32")
    hits = ix.search(q, exclude_dept="Finance", top_k=5, min_score=0.1)[0]
    assert len({h["uid"] for h in hits}) == len(hits)


def test_the_threshold_excludes_the_unrelated(tmp_path):
    ix = _index(tmp_path, ROWS)
    q = np.array([[1.0, 0.0, 0.0]], dtype="float32")
    hits = ix.search(q, exclude_dept=None, top_k=5, min_score=0.5)[0]
    assert all(h["text"] != "unrelated" for h in hits if "text" in h)
    assert all(h["score"] >= 0.5 for h in hits)


def test_hits_are_ordered_by_score(tmp_path):
    ix = _index(tmp_path, ROWS)
    q = np.array([[1.0, 0.0, 0.0]], dtype="float32")
    hits = ix.search(q, exclude_dept=None, top_k=5, min_score=0.0)[0]
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


# --------------------------------------------------------------------------- FR-6: reporting

def test_bands_are_wording_not_verdicts():
    """No band may be named in a way that asserts a contradiction: the model ranks an amendment
    ABOVE a second cancellation, so nothing here may imply adjudication."""
    for s in (0.95, 0.7, 0.56):
        assert semantic.band(s) in {"very close", "close", "related"}
    assert "conflict" not in " ".join(semantic.band(s) for s in (0.95, 0.7, 0.56))


def test_an_absent_index_degrades_instead_of_raising(tmp_path):
    ix = semantic.ClauseIndex(tmp_path / "does-not-exist")
    assert ix.available is False and ix.hint
    assert ix.status() == {"available": False, "hint": ix.hint}


def test_a_draft_with_no_operative_section_says_so(monkeypatch, tmp_path):
    """Not an error: a draft that has not reached its operative part has nothing to compare."""
    monkeypatch.setattr(semantic, "index", lambda: _index(tmp_path, ROWS))
    monkeypatch.setattr(embed, "available", lambda lang="mr": (True, "stub"))
    r = semantic.check("विषय :- अपूर्ण मसुदा\nमहाराष्ट्र शासन", "mr", "Finance")
    assert r["available"] and r["clauses"] == 0 and r["matches"] == []
    assert "operative" in r["note"]


def test_the_report_states_its_own_threshold(monkeypatch, tmp_path):
    """The score is a continuum with no defensible cut-off, so the cut-off used must travel
    with the result rather than being an invisible constant."""
    monkeypatch.setattr(semantic, "index", lambda: _index(tmp_path, ROWS))
    monkeypatch.setattr(embed, "available", lambda lang="mr": (True, "stub"))
    monkeypatch.setattr(embed, "encode",
                        lambda t, lang="mr", batch_size=32: np.tile(
                            np.array([[1.0, 0.0, 0.0]], dtype="float32"), (len(t), 1)))
    r = semantic.check(GR, "mr", "Finance", min_score=0.42)
    assert r["min_score"] == 0.42
    assert r["own_department"] == "Finance"
    assert "NOT contradiction" in r["note"]
