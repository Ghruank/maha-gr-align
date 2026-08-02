#!/usr/bin/env python3
"""
Drafting engine — SRS FR-13, FR-14, FR-15, FR-16 and the AI half of FR-10.

The flow the officer sees:

    prompt  ->  AI asks clarifying questions  ->  officer answers  ->  AI drafts into the
    template  ->  officer edits the preview directly OR prompts for a refinement  ->  verify
    ->  export

Two rules shape every prompt below.

**The template is never generated.** The model fills *fields*; `template.py` renders them into
the Manual of Office Procedure form. Asking a 2B model to reproduce a legal form verbatim on
every call is how you get a form that drifts. It returns JSON field values; we lay them out.

**The latest preview is the context.** When an officer edits the preview by hand and then asks
for a refinement, the edited text is what gets sent — never the last AI version. Otherwise the
model silently reverts human work, which in this domain is a correctness failure, not a UX one.
"""

from __future__ import annotations

import json
import re
from typing import Any

import template
from ai import local

# Fields the model is allowed to fill. Anything outside this set is dropped — a model cannot
# invent a new section of a Government Resolution.
DRAFT_FIELDS = [
    "subject", "department", "resolution_no", "date", "read", "preamble",
    "resolution", "expenditure", "finance_concurrence", "signature", "distribution",
]

_LANG_NAME = {"mr": "Marathi (Devanagari)", "en": "English"}


SYSTEM = (
    "You are a drafting assistant for the Government of Maharashtra. You help desk officers "
    "prepare Government Resolutions that follow the Maharashtra Manual of Office Procedure, "
    "2023. You are precise, formal and administrative in register. You never invent citations "
    "to other Government Resolutions, circulars or court orders: if a reference is needed and "
    "was not supplied by the officer, you leave a blank for the officer to fill. You always "
    "reply with valid JSON and nothing else."
)


# --------------------------------------------------------------------------------------
# Step 1 — clarifying questions
# --------------------------------------------------------------------------------------

def questions_for(prompt: str, lang: str = "mr", max_q: int = 6) -> dict[str, Any]:
    """Ask the model what it needs to know before it can draft."""
    p = f"""An officer wants to draft a Government Resolution. Their request:

"{prompt}"

Ask up to {max_q} short questions you must have answered before you can draft it. Every
question must be SPECIFIC TO THIS REQUEST — mention the actual subject, posts, scheme, body
or amounts named above. Do not ask generic administrative questions.

Reply with JSON only, matching this schema. Words in CAPITALS describe what to put there —
replace them with real content, and never echo the capitalised words or wrap anything in tags:
{{"questions": [
  {{"id": "SHORT_SNAKE_CASE_KEY", "q": "QUESTION SPECIFIC TO THE REQUEST ABOVE",
    "type": "text"}},
  {{"id": "SHORT_SNAKE_CASE_KEY", "q": "QUESTION WITH A SMALL SET OF VALID ANSWERS",
    "type": "choice", "options": ["FIRST ANSWER", "SECOND ANSWER"]}}
]}}

Write the "q" text in {_LANG_NAME.get(lang, 'English')}. Use "choice" with "options" wherever
the answer is one of a small known set, and "text" otherwise. JSON only."""

    obj, stats = local.generate_json(p, system=SYSTEM, max_tokens=700)
    qs = []
    if isinstance(obj, dict):
        for q in obj.get("questions", [])[:max_q]:
            if not isinstance(q, dict) or not q.get("q"):
                continue
            opts = [_strip_markup(str(o)) for o in (q.get("options") or [])][:6]
            opts = [o for o in opts if o]
            qs.append({
                "id": str(q.get("id") or f"q{len(qs)}"),
                "q": _strip_markup(str(q["q"])),
                "type": "choice" if q.get("type") == "choice" and opts else "text",
                "options": opts,
            })
    if not qs:
        qs = _fallback_questions(lang)
        stats["fallback"] = True
    return {"questions": qs, "stats": stats}


_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def _strip_markup(s: str) -> str:
    """Remove stray tags a small model wraps around its own answers.

    Qwen3.5-2B given a bracketed schema placeholder returned literal
    `<option>Post count exceeds ...</option>`. Prompting reduced this; it did not eliminate it,
    and an officer must never see markup in a question.
    """
    return _TAG.sub("", s).strip()


def _fallback_questions(lang: str) -> list[dict[str, Any]]:
    """Used when the model is unavailable or returns unparseable output.

    Degrading to a fixed questionnaire is honest and still useful; pretending the model
    answered is not.
    """
    mr = lang == "mr"
    return [
        {"id": "department", "type": "text",
         "q": "हा शासन निर्णय कोणता विभाग निर्गमित करत आहे?" if mr
              else "Which department is issuing this Resolution?"},
        {"id": "subject", "type": "text",
         "q": "निर्णयाचा विषय काय आहे?" if mr else "What is the subject of the Resolution?"},
        {"id": "financial", "type": "choice", "options": ["Yes", "No"],
         "q": "यामध्ये खर्चास मान्यता आहे का?" if mr
              else "Does this sanction any expenditure?"},
        {"id": "read", "type": "text",
         "q": "कोणत्या पूर्वीच्या आदेशांचा संदर्भ आहे? (क्रमांक व दिनांक)" if mr
              else "Which prior orders does this rest on? (number and date)"},
        {"id": "effective", "type": "text",
         "q": "निर्णय कोणत्या दिनांकापासून लागू होईल?" if mr
              else "From what date does this take effect?"},
    ]


# --------------------------------------------------------------------------------------
# Step 2 — draft from prompt + answers
# --------------------------------------------------------------------------------------

def _blank(lang: str) -> str:
    """A fill-in blank in the draft's own language — a Devanagari word must not leak into an
    English draft, which is exactly what a hardcoded example caused."""
    return ("1) ____________ दिनांक ____________" if lang == "mr"
            else "1) ____________ dated ____________")


def draft(prompt: str, answers: dict[str, str], lang: str = "mr") -> dict[str, Any]:
    """Produce field values, then render them through the deterministic template."""
    qa = "\n".join(f"- {k}: {v}" for k, v in answers.items() if str(v).strip())
    fields = ", ".join(DRAFT_FIELDS)

    p = f"""Draft a Government Resolution for the Government of Maharashtra.

Officer's request:
"{prompt}"

Answers the officer gave:
{qa or "(none)"}

Write the content in {_LANG_NAME.get(lang, 'English')}.

Reply with JSON only — an object whose keys are drawn from: {fields}
Rules:
- "resolution" is the operative decision. Write it as numbered paragraphs starting at 2.
- "preamble" is the background leading to the decision.
- "read" lists prior orders, one per line, numbered "1)", "2)". If the officer did not supply
  a real order number and date, write a blank like "{_blank(lang)}" instead of inventing one.
  NEVER invent a Government Resolution number, circular number or date. A fabricated legal
  citation is worse than an empty line.
- Do not write placeholder citations such as "Order No. X/20XX" or "dated YYYY" in the
  preamble either. Leave an underscore blank the officer can fill.
- Leave out any key you have no content for.
- Do not include headings like "GOVERNMENT OF MAHARASHTRA" — those are added automatically.
JSON only."""

    obj, stats = local.generate_json(p, system=SYSTEM, max_tokens=1400)
    values = _clean_fields(obj)
    text = template.render_skeleton(lang, values)
    return {"fields": values, "text": text, "stats": stats}


def _clean_fields(obj: Any) -> dict[str, str]:
    """Keep only known fields, stringify, drop empties. A model may not add sections."""
    if not isinstance(obj, dict):
        return {}
    out: dict[str, str] = {}
    for k in DRAFT_FIELDS:
        v = obj.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            v = "\n".join(str(x) for x in v)
        v = str(v).strip()
        if v:
            out[k] = v
    return out


# --------------------------------------------------------------------------------------
# Step 3 — refine whatever is currently in the preview
# --------------------------------------------------------------------------------------

def refine(current_text: str, instruction: str, lang: str = "mr") -> dict[str, Any]:
    """Edit the CURRENT preview — including any hand edits — and return the whole document.

    Returning the full text rather than a patch is deliberate: a 2B model's diffs are not
    reliable enough to apply blind to a legal document.
    """
    p = f"""Here is the current draft of a Government Resolution:

<<<DRAFT
{current_text}
DRAFT

The officer asks for this change:
"{instruction}"

Apply ONLY that change. Keep every other line byte-identical, including the headings, the
Mantralaya address, the Governor's order line and the signature block. Do not add commentary.
Do not invent any Government Resolution number, circular number or date that is not already
in the draft above.

Reply with JSON only: {{"text": "<the complete revised draft>"}}"""

    obj, stats = local.generate_json(p, system=SYSTEM, max_tokens=2000)
    text = None
    if isinstance(obj, dict) and isinstance(obj.get("text"), str):
        text = obj["text"].strip()
    if not text:
        return {"text": current_text, "changed": False, "stats": stats,
                "note": "The model did not return a usable revision. The draft is unchanged."}
    return {"text": text, "changed": text != current_text, "stats": stats}
