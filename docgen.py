#!/usr/bin/env python3
"""
Document export — SRS FR-16 ("export the final draft as PDF / DOCX").

**One document model, two renderers.** `parse(text)` turns the officer's plain-text draft into
an ordered list of typed blocks; `to_pdf` and `to_docx` each render that same list. A layout
rule lives in `data/gr_template.json`, never in a renderer, so the PDF and the Word file cannot
disagree about where the subject line sits.

Why not LaTeX. XeLaTeX shaped the conjuncts correctly but the page did not read as a
Government Resolution: Latin and Devanagari came from unrelated families with different
optical sizes, and the text layer it wrote was in visual order, so copying Marathi out of the
PDF produced reordered matras. Both are gone here — WeasyPrint shapes through Pango/HarfBuzz
and writes a logical-order text layer, and one Noto family covers both scripts.

Why not LibreOffice for the PDF. It renders Devanagari well, but it is a ~1 GB system package
needing root on the State Data Centre box. WeasyPrint and python-docx are pip installs against
libraries (Pango, HarfBuzz, Cairo) already present, so the on-prem footprint stays small.

Layout follows Manual of Office Procedure, Appendix 10.6 for section ORDER. Alignment —
subject right, Government title and Mantralaya address centred, everything else left — is
carried per-section in the template file.
"""

from __future__ import annotations

import html
import io
import re
from pathlib import Path
from typing import Any

import template

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "web" / "public" / "fonts"

SECTIONS = {s["id"]: s for s in template.TEMPLATE["sections"]}
ORDER = [s["id"] for s in template.TEMPLATE["sections"]]


# --------------------------------------------------------------------------------------
# Parse the plain-text preview back into typed blocks
# --------------------------------------------------------------------------------------

def parse(text: str) -> list[dict[str, Any]]:
    """Plain text -> [{section, align, lines}].

    Uses the SAME detectors as `template.verify`, so a line that the checker counts as the
    Subject is the line the exporter right-aligns. Two independent notions of "this is the
    subject" would drift apart within a week.

    Lines before any recognised heading, and lines after one, belong to that heading's block.
    Anything before the first match is emitted as an untyped block and left-aligned — an
    officer may legitimately type something we do not model, and dropping it would be worse
    than laying it out plainly.
    """
    blocks: list[dict[str, Any]] = []
    current = {"section": None, "align": "left", "lines": []}

    for raw in text.splitlines():
        line = raw.rstrip()
        sid = _match_section(line)
        if sid is not None:
            if current["lines"]:
                blocks.append(current)
            current = {
                "section": sid,
                "align": SECTIONS.get(sid, {}).get("align", "left"),
                "lines": [line],
            }
        else:
            current["lines"].append(line)

    if current["lines"]:
        blocks.append(current)

    # Drop blocks that are entirely blank.
    return [b for b in blocks if any(l.strip() for l in b["lines"])]


def _match_section(line: str) -> str | None:
    """The section whose pattern matches EARLIEST in the line wins.

    First-in-template-order is wrong: `वाचा :- शासन निर्णय क्रमांक अबक-२०२५` contains the
    resolution-number keyword partway through, so a first-match scan typed a Read block as
    the resolution number and left-aligned nothing correctly. The heading that opens the line
    is the one that classifies it.
    """
    if not line.strip():
        return None
    best: tuple[int, int, str] | None = None
    for rank, sid in enumerate(ORDER):
        pat = template.DETECT.get(sid)
        if not pat:
            continue
        m = re.search(pat, line, re.M)
        if m and (best is None or (m.start(), rank) < (best[0], best[1])):
            best = (m.start(), rank, sid)
    return best[2] if best else None


# --------------------------------------------------------------------------------------
# PDF — WeasyPrint
# --------------------------------------------------------------------------------------

CSS = """
@font-face { font-family: 'GRDev'; src: url('file://%(fonts)s/NotoSerifDevanagari.ttf');
             font-weight: 100 900; }
@font-face { font-family: 'GRLatin'; src: url('file://%(fonts)s/NotoSerif.ttf');
             font-weight: 100 900; }

@page {
  size: A4;
  margin: 20mm 20mm 22mm;
  @bottom-center { content: counter(page); font-family: 'GRLatin', serif; font-size: 9pt;
                   color: #333; }
}

body {
  font-family: 'GRLatin', 'GRDev', serif;
  font-size: 11.5pt;
  line-height: 1.7;
  color: #000;
  margin: 0;
}

/* Devanagari needs more leading than Latin at the same point size or the matras collide. */
body.mr { font-family: 'GRDev', 'GRLatin', serif; font-size: 12pt; line-height: 1.95; }

p { margin: 0 0 0.55em; white-space: pre-wrap; }
p.right  { text-align: right; }
p.center { text-align: center; }
p.left   { text-align: left; }

/* The Government of Maharashtra / Department / Mantralaya block reads as a masthead. */
p.govt       { margin-bottom: 0.15em; font-weight: 700; letter-spacing: 0.02em; }
p.department { margin-bottom: 0.5em; font-weight: 700; }
p.address    { margin-bottom: 0.9em; }
p.subject    { margin-bottom: 1.1em; }

/* Appendix 10.6 sets these off from the body. */
p.governor_order { margin-top: 1.4em; }
p.signature      { margin-top: 0.2em; }
p.distribution   { margin-top: 1.2em; }
"""


def to_html(text: str, lang: str = "mr") -> str:
    blocks = parse(text)
    parts = []
    for b in blocks:
        body = html.escape("\n".join(b["lines"]).strip())
        cls = " ".join(x for x in (b["align"], b["section"] or "") if x)
        parts.append(f'<p class="{cls}">{body}</p>')
    style = CSS % {"fonts": FONT_DIR.as_posix()}
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{style}</style></head>'
            f'<body class="{"mr" if lang == "mr" else "en"}">'
            + "\n".join(parts) + "</body></html>")


def to_pdf(text: str, lang: str = "mr") -> bytes:
    from weasyprint import HTML
    return HTML(string=to_html(text, lang), base_url=str(ROOT)).write_pdf()


# --------------------------------------------------------------------------------------
# DOCX — python-docx
# --------------------------------------------------------------------------------------

_ALIGN_DOCX = {"left": 0, "center": 1, "right": 2}     # WD_ALIGN_PARAGRAPH values


def to_docx(text: str, lang: str = "mr") -> bytes:
    from docx import Document
    from docx.shared import Pt, Mm
    from docx.oxml.ns import qn

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = Mm(20)
    sec.left_margin = sec.right_margin = Mm(20)

    mr = lang == "mr"
    face = "Noto Serif Devanagari" if mr else "Noto Serif"
    size = Pt(12) if mr else Pt(11.5)

    style = doc.styles["Normal"]
    style.font.name = face
    style.font.size = size
    # Devanagari is a COMPLEX SCRIPT in OOXML. Without w:cs Word applies the complex-script
    # default (usually Mangal) and ignores the chosen face entirely for Marathi runs.
    rpr = style.element.get_or_add_rPr().get_or_add_rFonts()
    rpr.set(qn("w:ascii"), face)
    rpr.set(qn("w:hAnsi"), face)
    rpr.set(qn("w:cs"), face)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.5 if mr else 1.3

    for b in parse(text):
        p = doc.add_paragraph()
        p.alignment = _ALIGN_DOCX.get(b["align"], 0)
        run = p.add_run("\n".join(b["lines"]).strip())
        run.font.name = face
        run.font.size = size
        rf = run._element.get_or_add_rPr().get_or_add_rFonts()
        rf.set(qn("w:ascii"), face)
        rf.set(qn("w:hAnsi"), face)
        rf.set(qn("w:cs"), face)
        if b["section"] in ("govt", "department"):
            run.bold = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def available() -> tuple[bool, str]:
    missing = []
    try:
        import weasyprint            # noqa: F401
    except Exception as exc:
        missing.append(f"weasyprint ({exc})")
    try:
        import docx                  # noqa: F401
    except Exception as exc:
        missing.append(f"python-docx ({exc})")
    if not (FONT_DIR / "NotoSerifDevanagari.ttf").is_file():
        missing.append("NotoSerifDevanagari.ttf")
    return (False, "; ".join(missing)) if missing else (True, "weasyprint + python-docx")


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1]).read_text()
    lang = sys.argv[2] if len(sys.argv) > 2 else "mr"
    Path("gr.pdf").write_bytes(to_pdf(src, lang))
    Path("gr.docx").write_bytes(to_docx(src, lang))
    print("wrote gr.pdf and gr.docx")
