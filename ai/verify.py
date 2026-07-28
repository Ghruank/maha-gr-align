#!/usr/bin/env python3
"""
The verification gates. Deterministic. No model is called from this file, ever.

`AI_ARCHITECTURE.md` §2 is the spec. The contract: a model *proposes* a claim about the corpus;
these gates decide whether it may be shown. Each gate is a pure function of (claim, corpus) —
the model's reasoning is never an input, which is what stops the check being circular.

Three outcomes, all recorded:

  VERIFIED  passed every applicable gate — display normally, with evidence
  FLAGGED   passed the hard gates but soft-failed one — display WITH the failed gate named
  REJECTED  failed a hard gate — never displayed as a finding, but counted in the Trust Ledger

**What these gates do and do not bound.** They bound *fabrication*: invented quotes, invented
GRs, invented categories, impossible dates. They do **not** bound *judgement* — a model can
quote a real sentence from a real GR and still draw the wrong conclusion from it. This was
observed during the very first probe (`AI_ARCHITECTURE.md` §9.1: a sentence cancelling
*appointments made under* a GR was typed `SUPERSEDES` against the GR itself, and every gate
passed). Say this out loud rather than implying the gates prove correctness.
"""

from __future__ import annotations

import re
import datetime

DEV_DIGITS = str.maketrans('०१२३४५६७८९', '0123456789')

HARD = {"G2_referential", "G3_vocabulary", "G5_temporal"}

# G7 — the scope gate. Nouns that are *things done under* an order rather than the order
# itself. If one of these is what the sentence cancels, the order survives and only its
# arrangements change, so SUPERSEDES must be downgraded to AMENDS. Derived from the granularity
# error found in the first probe; extend this list only with corpus evidence.
SUBORDINATE_OBJECTS = {
    'नियुक्त्या': 'appointments', 'नियुक्ती': 'appointment', 'नियुक्त्या रद्द': 'appointments',
    'मान्यता': 'approval', 'निधी': 'funds', 'परवानगी': 'permission', 'मंजुरी': 'sanction',
    'पद': 'post', 'पदे': 'posts', 'अनुदान': 'grant', 'सदस्य': 'member',
    'सदस्यांच्या नियुक्त्या': 'member appointments', 'समिती': 'committee',
}

# Names for the order ITSELF. If this is what is cancelled, the cancellation is a genuine
# supersession and G7 must not touch it.
#
# `आदेश` ("order") belonged in neither list and was initially, wrongly, treated as subordinate —
# a Government Resolution *is* an order, so `संदर्भाधीन दिनांक ०८.०१.२०२० रोजीचे आदेश रद्द
# करण्यात येत आहेत` ("the orders dated 08.01.2020 are cancelled") is a real SUPERSEDES that got
# downgraded. Found by reading the first 30 verdicts, which is why that review is not optional.
ORDER_ITSELF = {'आदेश', 'शासन निर्णय', 'शासन आदेश', 'निर्णय', 'परिपत्रक', 'शासन परिपत्रक',
                'अधिसूचना', 'शुद्धिपत्रक'}


def _norm_obj(s: str | None) -> str:
    return " ".join((s or "").split()).strip(' ।.,:;"\'')

# Language of *intent*, not of decision. `विचाराधीन` = "under consideration" appears in the
# Proposal section describing what the government was thinking about, which is not an operative
# change to anything. Measured on the corpus: this pattern co-occurs with amendment cue words
# often enough to poison typing if unhandled.
DELIBERATIVE = re.compile(r'विचाराधीन|प्रस्तावित\s+आहे|विचार\s+करण्यात')


def normalise(s: str | None) -> str:
    """Whitespace-collapsed. Used for verbatim comparison — nothing else may differ."""
    return " ".join((s or "").split())


def digits_of(s: str | None) -> list[str]:
    return re.findall(r'\d+', (s or '').translate(DEV_DIGITS))


# --------------------------------------------------------------------------- gates

def g1_grounding(span: str | None, source_text: str) -> tuple[bool, str]:
    """Every quoted span must occur verbatim in the cited source document."""
    if not (span or "").strip():
        return False, "empty evidence span"
    if normalise(span) not in normalise(source_text):
        return False, f"span not verbatim in source: {normalise(span)[:70]!r}"
    return True, ""


def g2_referential(uid: str | None, index: dict) -> tuple[bool, str]:
    """Every uid must exist in the corpus index.

    HARD gate. This is the one that stops the failure mode that would end the project's
    credibility — a citation to a Government Resolution that does not exist. Note the model is
    never asked to supply a uid: `dst` comes from the deterministic resolver. This gate is the
    backstop for that invariant, not the primary mechanism.
    """
    if not uid:
        return False, "no uid"
    if uid not in index:
        return False, f"uid {uid} absent from corpus index"
    return True, ""


def g3_vocabulary(value: str | None, allowed) -> tuple[bool, str]:
    """Labels must come from a closed enum. HARD gate — a freelanced category silently breaks
    every downstream consumer that switches on type."""
    if value not in allowed:
        return False, f"{value!r} not in {sorted(allowed)}"
    return True, ""


def g4_numeric(claimed, source_text: str) -> tuple[bool, str]:
    """Every number asserted must appear in the source, digit-normalised across scripts.

    Devanagari and ASCII digits are folded together, so a figure written `३३,५४,००,०००` in the
    Marathi satisfies a claim of `335400000`. Catches the magnitude-error class measured in this
    corpus (a factor of 1000 repeated down a table column).
    """
    if claimed in (None, ""):
        return True, ""
    src = "".join(digits_of(source_text))
    for want in ([claimed] if isinstance(claimed, (str, int)) else claimed):
        w = "".join(digits_of(str(want)))
        if w and w not in src:
            return False, f"number {want} does not occur in source"
    return True, ""


def g5_temporal(src_uid: str, dst_uid: str, window_days: int = 3) -> tuple[bool, str]:
    """No relationship may point forward in time beyond the publication-drift window.
    HARD gate — a GR cannot amend or supersede an order issued after it."""
    try:
        sd = datetime.date(int(src_uid[0:4]), int(src_uid[4:6]), int(src_uid[6:8]))
        dd = datetime.date(int(dst_uid[0:4]), int(dst_uid[4:6]), int(dst_uid[6:8]))
    except (ValueError, IndexError):
        return False, "unparseable uid"
    if dd > sd + datetime.timedelta(days=window_days):
        return False, f"target is {(dd - sd).days}d after source"
    return True, ""


def g6_determinism(a: dict | None, b: dict | None, keys=("type",)) -> tuple[bool, str]:
    """Two runs at temperature 0 must agree on the load-bearing fields. Disagreement does not
    reject — it downgrades to FLAGGED, because nondeterminism means low confidence, not
    fabrication."""
    if a is None or b is None:
        return False, "a run produced no parseable output"
    for k in keys:
        if a.get(k) != b.get(k):
            return False, f"nondeterministic on {k}: {a.get(k)!r} vs {b.get(k)!r}"
    return True, ""


def g7_scope(claim_type: str, span: str, cancelled_object: str | None) -> tuple[str, str]:
    """Scope gate. Returns a possibly-DOWNGRADED type plus a note.

    Two corpus-derived corrections, both of which every other gate passes straight through:

    1. **Granularity.** If what is cancelled is a thing *done under* the order (an appointment,
       an approval, a sanction) rather than the order itself, the order survives — so
       `SUPERSEDES` becomes `AMENDS`.
    2. **Deliberative mood.** `विचाराधीन` ("under consideration") marks the Proposal section
       stating intent. Intent changes nothing, so any operative type becomes `REFERENCES`.
    """
    if DELIBERATIVE.search(span or "") and claim_type in ("SUPERSEDES", "AMENDS"):
        return "REFERENCES", "deliberative mood (विचाराधीन) — states intent, not a decision"

    if claim_type == "SUPERSEDES":
        obj = _norm_obj(cancelled_object)
        if obj in ORDER_ITSELF:                    # the order itself → genuine supersession
            return claim_type, ""
        # Exact match, not substring: `पद` ("post") is a substring of `पदभरती` ("recruitment"),
        # and matching loosely would downgrade unrelated supersessions.
        if obj in SUBORDINATE_OBJECTS:
            return "AMENDS", (f"cancels {obj} ({SUBORDINATE_OBJECTS[obj]}) under the order, "
                              f"not the order itself")
    return claim_type, ""


# --------------------------------------------------------------------------- runner

def verify_edge_type(claim: dict, *, src_uid: str, dst_uid: str, source_text: str,
                     index: dict, allowed_types, window_days: int = 3,
                     second_run: dict | None = None) -> dict:
    """Run every applicable gate over one edge-typing claim.

    Returns a verdict record carrying the gate results, the final (possibly downgraded) type, and
    a reason. Never raises: a malformed claim is a REJECTED verdict, not an exception, because
    the rejection count is itself a product (the Trust Ledger).
    """
    gates, failed_hard, failed_soft, notes = {}, [], [], []

    ok, why = g2_referential(dst_uid, index)
    gates["G2_referential"] = (ok, why)
    ok3, why3 = g3_vocabulary(claim.get("type"), allowed_types)
    gates["G3_vocabulary"] = (ok3, why3)
    ok5, why5 = g5_temporal(src_uid, dst_uid, window_days)
    gates["G5_temporal"] = (ok5, why5)

    span = claim.get("evidence_span") or ""
    ok1, why1 = g1_grounding(span, source_text)
    gates["G1_grounding"] = (ok1, why1)

    ok4, why4 = g4_numeric(claim.get("amount"), source_text)
    gates["G4_numeric"] = (ok4, why4)

    if second_run is not None:
        ok6, why6 = g6_determinism(claim, second_run)
        gates["G6_determinism"] = (ok6, why6)

    for name, (ok, why) in gates.items():
        if ok:
            continue
        (failed_hard if name in HARD else failed_soft).append(f"{name}: {why}")

    final_type = claim.get("type")
    if ok3:
        final_type, note = g7_scope(final_type, span, claim.get("cancelled_object"))
        gates["G7_scope"] = (final_type == claim.get("type"), note)
        if note:
            notes.append(f"G7 downgraded {claim.get('type')} → {final_type}: {note}")

    if failed_hard:
        verdict = "REJECTED"
    elif failed_soft:
        verdict = "FLAGGED"
    else:
        verdict = "VERIFIED"

    return {
        "verdict": verdict,
        "type": final_type if verdict != "REJECTED" else None,
        "proposed_type": claim.get("type"),
        "gates": {k: {"pass": v[0], "why": v[1]} for k, v in gates.items()},
        "failed_hard": failed_hard,
        "failed_soft": failed_soft,
        "notes": notes,
    }
