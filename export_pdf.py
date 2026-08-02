#!/usr/bin/env python3
"""
SUPERSEDED 2026-08-01 by `docgen.py`. Not wired to any route.

Replaced because the Marathi did not look professional: Latin came from FreeSerif and
Devanagari from Noto with mismatched optical sizes, and XeTeX wrote a VISUAL-order text
layer so copied Marathi came out reordered. `docgen.py` uses one Noto superfamily across
both scripts, shapes through Pango/HarfBuzz, and emits DOCX as well (FR-16 asks for both).
Kept only for the xelatex.fmt bootstrap below, which took a while to work out.

PDF export via XeLaTeX — SRS FR-16.

**The officer never sees LaTeX.** They edit plain text in the preview; this module turns that
text into a `.tex` document and compiles it. LaTeX is an output format here, not an input.

Why XeLaTeX rather than the browser's print dialogue:

* The browser route made the PDF depend on which browser the officer used, and on their paper
  size and margin settings. This produces the same bytes on every machine.
* Devanagari needs real OpenType shaping. XeLaTeX with `fontspec` and `Script=Devanagari`
  renders क्ष, ज्ञ and त्र correctly; verified before this module was written.

Two operational facts, both learned the hard way on this box:

* **The `xelatex.fmt` format file may not exist even when the `xetex` binary does.** Arch ships
  the binary without provisioning the format, and `fmtutil` has no entry to build it. It can be
  built WITHOUT root into `$TEXMFVAR`; `ensure_format()` does that on demand and caches it.
* **The font is passed by PATH, not by name.** `fc-list :lang=mr` on the target box returns no
  Devanagari family at all, so a name lookup fails. The vendored Noto Devanagari files under
  `web/public/fonts/` are addressed directly, which also keeps the State Data Centre install
  free of any font packaging step.

Known limitation, stated because it is not obvious: the text layer XeLaTeX writes for Devanagari
is in *visual* order, so copying Marathi out of the produced PDF gives reordered matras. The
rendering is correct; only extraction is affected. Do not feed our own exported PDFs back into
the OCR/verify path expecting clean text — verify the source text instead.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "web" / "public" / "fonts"
TEXMFVAR = Path(os.environ.get("TEXMFVAR", Path.home() / ".texlive-var"))
FMT = TEXMFVAR / "web2c" / "xetex" / "xelatex.fmt"
XELATEX_INI = "/usr/share/texmf-dist/tex/latex/tex-ini-files/xelatex.ini"


class ExportUnavailable(RuntimeError):
    """XeLaTeX cannot run. Callers degrade to the browser print path."""


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e["TEXMFVAR"] = str(TEXMFVAR)
    return e


def available() -> tuple[bool, str]:
    if not shutil.which("xelatex"):
        return False, "xelatex not installed"
    if not (FONT_DIR / "NotoSerifDevanagari.ttf").is_file():
        return False, f"Devanagari font missing from {FONT_DIR}"
    if not FMT.is_file():
        return False, "xelatex format not built (will be built on first export)"
    return True, "xelatex"


def ensure_format(timeout: int = 300) -> None:
    """Build xelatex.fmt into TEXMFVAR if the distribution never provisioned it.

    Needs no root. Takes ~20 s once, then the format is cached forever.
    """
    if FMT.is_file():
        return
    if not Path(XELATEX_INI).is_file():
        raise ExportUnavailable(f"{XELATEX_INI} not found; install the tex-ini-files package")
    FMT.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["xetex", "-ini", "-etex", "-jobname=xelatex",
         f"-output-directory={FMT.parent}", XELATEX_INI],
        capture_output=True, text=True, timeout=timeout, env=_env(), cwd=FMT.parent,
    )
    if not FMT.is_file():
        raise ExportUnavailable(f"could not build xelatex.fmt: {r.stdout[-400:]}")


# --------------------------------------------------------------------------------------
# Escaping
#
# The draft is plain text written by an officer. Every LaTeX-special character in it must be
# neutralised or the compile fails on something as ordinary as a rupee amount with a % in it.
# --------------------------------------------------------------------------------------

_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(s: str) -> str:
    return "".join(_ESCAPES.get(c, c) for c in s)


DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _wrap_devanagari(line: str) -> str:
    """Mark Devanagari runs so they get the Devanagari font, leaving Latin in the roman face.

    A GR is routinely mixed — a Marathi body with Latin file numbers and English institution
    names. Setting the whole document in one font would make one script or the other wrong.
    """
    out, buf, in_dev = [], [], False
    for ch in line:
        is_dev = bool(DEVANAGARI.match(ch))
        # Digits and punctuation inherit the current run so they do not split it.
        if ch.isspace() or (not ch.isalpha() and not is_dev):
            buf.append(ch)
            continue
        if is_dev != in_dev and buf:
            out.append(_emit(("".join(buf)), in_dev))
            buf = []
        in_dev = is_dev
        buf.append(ch)
    if buf:
        out.append(_emit("".join(buf), in_dev))
    return "".join(out)


def _emit(chunk: str, dev: bool) -> str:
    esc = tex_escape(chunk)
    return f"{{\\dev {esc}}}" if dev and DEVANAGARI.search(chunk) else esc


PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage[top=22mm,bottom=24mm,left=20mm,right=20mm]{geometry}
\usepackage{fontspec}
\usepackage{fancyhdr}
\setmainfont{FreeSerif}
\newfontfamily\dev[Script=Devanagari,Path=%(fontdir)s/]{NotoSerifDevanagari.ttf}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.45em}
\linespread{1.25}
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0pt}
\begin{document}
"""


def build_tex(text: str) -> str:
    """Blank lines separate paragraphs; single newlines are HARD BREAKS.

    LaTeX normally reflows lines within a paragraph, which ran the entire GR header —
    "महाराष्ट्र शासन", the department, the resolution number, the Mantralaya address — together
    onto one line. In a Government Resolution those are separate lines by form, so every
    newline in the officer's text is preserved with `\\\\`.
    """
    blocks = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        blocks.append(" \\\\\n".join(_wrap_devanagari(ln) for ln in lines))
    return (PREAMBLE % {"fontdir": FONT_DIR.as_posix()}) + "\n\n".join(blocks) + \
        "\n\\end{document}\n"


def to_pdf(text: str, timeout: int = 180) -> bytes:
    """Compile a draft to PDF bytes. Raises ExportUnavailable with the TeX log on failure."""
    if not shutil.which("xelatex"):
        raise ExportUnavailable("xelatex not installed")
    ensure_format()

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "gr.tex").write_text(build_tex(text), encoding="utf-8")
        r = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "gr.tex"],
            cwd=d, capture_output=True, text=True, timeout=timeout, env=_env(),
        )
        pdf = d / "gr.pdf"
        if not pdf.is_file():
            log = (d / "gr.log").read_text(errors="ignore") if (d / "gr.log").is_file() else r.stdout
            raise ExportUnavailable("xelatex failed:\n" + _last_error(log))
        return pdf.read_bytes()


def _last_error(log: str) -> str:
    """The one line a human needs out of a 400-line TeX log."""
    errs = [ln for ln in log.splitlines() if ln.startswith("!")]
    return "\n".join(errs[-4:]) or log[-500:]


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else sys.stdin.read()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("gr.pdf")
    out.write_bytes(to_pdf(src))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
