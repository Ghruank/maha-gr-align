#!/usr/bin/env python3
"""
Document ingest for the Verify page — get text out of an uploaded GR, English or Marathi.

**Text layer first, OCR only when there isn't one.** This is the whole design. A GR downloaded
from `gr.maharashtra.gov.in` usually carries a real text layer, and `pdftotext` returns it
perfectly in milliseconds. Running OCR over that would be slower AND less accurate — OCR on a
document you can already read exactly is a way to introduce errors, not remove them. So OCR is
the fallback for scans, and the response always says which path produced the text.

Language handling: EasyOCR is given `['mr', 'en']` together. Marathi and Devanagari share a
recogniser, and GRs are routinely mixed — Marathi body, Latin file numbers, English institution
names — so a single-language pass drops half of a typical page.

CLAUDE.md says "the OCR problem is already solved — do not build an OCR pipeline". That was
about the *corpus*, which orgpedia already OCR'd. It does not cover an officer uploading a fresh
scan, which SRS FR-13 requires and section 6 explicitly asks for. This module is that path only;
nothing here touches the corpus.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# A page with fewer than this many characters of text layer is treated as a scan. Chosen
# because GR pages that are genuinely text run into the thousands, while an image-only page
# yields a handful of stray characters from headers or stamps.
TEXT_LAYER_MIN_CHARS = 120

_READER = None          # EasyOCR loads ~100 MB of weights; build once, reuse.


class OCRUnavailable(RuntimeError):
    """No usable extraction path. Callers degrade rather than returning empty text as success."""


# --------------------------------------------------------------------------------------
# Path 1 — existing text layer
# --------------------------------------------------------------------------------------

def pdf_text_layer(path: Path) -> str:
    if not shutil.which("pdftotext"):
        return ""
    r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                       capture_output=True, text=True, timeout=120)
    return r.stdout if r.returncode == 0 else ""


# --------------------------------------------------------------------------------------
# Path 2 — OCR
# --------------------------------------------------------------------------------------

def _reader():
    global _READER
    if _READER is None:
        try:
            import easyocr
        except ImportError as exc:                     # pragma: no cover
            raise OCRUnavailable(f"easyocr not installed: {exc}") from exc
        # gpu=False is explicit: the target box has no NVIDIA GPU and the default would
        # emit a warning per call and silently fall back anyway.
        _READER = easyocr.Reader(["mr", "en"], gpu=False, verbose=False)
    return _READER


def available() -> tuple[bool, str]:
    try:
        import easyocr                                  # noqa: F401
    except ImportError:
        return False, "easyocr not installed"
    if not shutil.which("pdftoppm"):
        return False, "poppler (pdftoppm) not installed — cannot rasterise PDFs"
    return True, "easyocr (mr+en), CPU"


def rasterise(pdf: Path, out_dir: Path, dpi: int = 200, max_pages: int = 10) -> list[Path]:
    """PDF -> PNG pages. 200 dpi is the floor at which Devanagari matras survive; 150 loses them."""
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", str(max_pages),
         str(pdf), str(out_dir / "pg")],
        check=True, capture_output=True, timeout=300,
    )
    return sorted(out_dir.glob("pg-*.png"))


def ocr_image(path: Path) -> tuple[str, float]:
    """(text, mean confidence). Lines are rebuilt in reading order by vertical position."""
    reader = _reader()
    results = reader.readtext(str(path), detail=1, paragraph=False)
    if not results:
        return "", 0.0
    # Group boxes into lines: EasyOCR returns boxes, not lines, and naive concatenation
    # scrambles a two-column header into nonsense.
    rows: list[tuple[float, float, str, float]] = []
    for box, text, conf in results:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        rows.append((sum(ys) / len(ys), min(xs), text, float(conf)))
    rows.sort(key=lambda r: (round(r[0] / 12), r[1]))     # 12px vertical tolerance

    lines, current, last_y = [], [], None
    for y, _x, text, _c in rows:
        if last_y is not None and abs(y - last_y) > 12:
            lines.append(" ".join(current))
            current = []
        current.append(text)
        last_y = y
    if current:
        lines.append(" ".join(current))

    confs = [r[3] for r in rows]
    return "\n".join(lines), sum(confs) / len(confs)


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------

def extract(data: bytes, filename: str, force_ocr: bool = False) -> dict[str, Any]:
    """Text out of an uploaded PDF or image, with provenance.

    Always reports `method` so the UI can tell the officer whether they are looking at the
    document's own text or a machine reading of a scan — those warrant different trust.
    """
    suffix = Path(filename).suffix.lower() or ".pdf"
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / f"upload{suffix}"
        src.write_bytes(data)

        if suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"):
            text, conf = ocr_image(src)
            return _result(text, "ocr", conf, pages=1,
                           note="Image upload — OCR is the only path.")

        if suffix != ".pdf":
            raise OCRUnavailable(f"unsupported file type: {suffix}")

        if not force_ocr:
            layer = pdf_text_layer(src)
            if len(layer.strip()) >= TEXT_LAYER_MIN_CHARS:
                return _result(layer, "text_layer", 1.0, pages=layer.count("\f") + 1,
                               note="The PDF carried its own text layer; OCR was not needed "
                                    "and would have been less accurate.")

        ok, detail = available()
        if not ok:
            raise OCRUnavailable(
                f"This PDF has no usable text layer and OCR is unavailable ({detail}).")

        pages = rasterise(src, d)
        if not pages:
            raise OCRUnavailable("could not rasterise the PDF")
        chunks, confs = [], []
        for p in pages:
            t, c = ocr_image(p)
            if t.strip():
                chunks.append(t)
                confs.append(c)
        text = "\n\n".join(chunks)
        conf = sum(confs) / len(confs) if confs else 0.0
        return _result(text, "ocr", conf, pages=len(pages),
                       note="No text layer found; the document was read by OCR. "
                            "Treat extracted numbers and citations as unverified.")


def _result(text: str, method: str, conf: float, pages: int, note: str) -> dict[str, Any]:
    text = _tidy(text)
    return {
        "text": text,
        "method": method,
        "confidence": round(conf, 3),
        "pages": pages,
        "chars": len(text),
        "script": _script_mix(text),
        "note": note,
    }


# --------------------------------------------------------------------------------------
# Visual-order Devanagari repair
#
# Some PDF producers — XeTeX among them, including our own exporter — write Devanagari into
# the text layer in VISUAL order rather than logical order. The page renders correctly, but the
# extracted characters are in the sequence they appear left-to-right, so:
#
#     विषय  (व ि ष य, logical)   extracts as   िवषय  (ि व ष य, visual)
#
# Every template detector matches logical order, so an un-repaired extraction fails every
# check for reasons that have nothing to do with the document. Two reorderings cover the
# common cases; both are mechanical and safe.
# --------------------------------------------------------------------------------------

CONSONANT = r"[क-हक़-य़ॹ-ॿ]"
VIRAMA = "्"

# 1. Pre-base vowel sign I (ि).
#
#    The discriminator is what comes BEFORE it, not after. In LOGICAL order ि always follows
#    its base consonant (व + ि + ष + य). In VISUAL order it is detached and sits at the start
#    of the cluster (ि + व + ष + य), preceded by a space or line start.
#
#    An earlier version matched "ि followed by a consonant", which is true of correctly
#    ordered text too — so running it on a good document CORRUPTED it (विषय -> वषिय). The
#    lookbehind is what makes this safe and idempotent.
_PREBASE_I = re.compile(rf"(?<![ऀ-ॿ])ि({CONSONANT}(?:{VIRAMA}{CONSONANT})*)")

# 2. Reph: "र्" that logically STARTS a cluster is drawn at its END.
#
#    Unlike the ि case this one is genuinely ambiguous and CANNOT be made idempotent. Logical
#    कर्म is क-र-्-म; visual निर्णय extracts as न-ण-र-्-य. Both present a consonant followed
#    by "र्", so the pattern cannot tell them apart from the characters alone. Running it on
#    correctly ordered text turns कर्म into र्कम.
#
#    That is why `repair_visual_order` must only ever be called behind `looks_visual_order`,
#    which decides from the ि evidence — unambiguous — whether the WHOLE document is reordered.
_REPH = re.compile(rf"({CONSONANT})र{VIRAMA}")


# 3. Spurious space after anusvara.
#
#    Measured on our own exported PDF, EVERY intra-word space in the extraction landed
#    immediately after "ं": पदां ना, क्रमां क, सं कीर्ण, मं त्रालय, तं त्र, दिनां क. The
#    producer emits a space at that glyph boundary. Marathi never starts a word with a
#    combining mark, so joining across this specific boundary is safe, and it matters:
#    "शासन निर्णय क्रमां क" does not match the resolution-number detector, so the split
#    silently costs a required section.
_ANUSVARA_SPLIT = re.compile(rf"ं\s+(?=[ऀ-ॿ])")


def repair_visual_order(text: str) -> str:
    """Move visually-reordered marks back to logical position.

    NOT idempotent and NOT safe on arbitrary text — see the `_REPH` note. Call only when
    `looks_visual_order(text)` is True; `_tidy` does exactly that.
    """
    text = _PREBASE_I.sub(lambda m: m.group(1) + "ि", text)
    text = _REPH.sub(lambda m: "र" + VIRAMA + m.group(1), text)
    text = _ANUSVARA_SPLIT.sub("ं", text)
    return text


def looks_visual_order(text: str) -> bool:
    """Does ि appear detached at cluster start more often than attached after a consonant?

    Repairing unconditionally is not safe, so the repair only runs on documents that actually
    look reordered.
    """
    detached = len(_PREBASE_I.findall(text))
    attached = len(re.findall(rf"{CONSONANT}ि", text))
    return detached > attached


def _tidy(text: str) -> str:
    text = text.replace("\f", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if looks_visual_order(text):
        text = repair_visual_order(text)
    return text.strip()


DEV = re.compile(r"[ऀ-ॿ]")
LAT = re.compile(r"[A-Za-z]")


def _script_mix(text: str) -> dict[str, Any]:
    """Which script dominates — decides which language to verify the template against."""
    dev = len(DEV.findall(text))
    lat = len(LAT.findall(text))
    total = dev + lat
    return {
        "devanagari": dev,
        "latin": lat,
        "lang": "mr" if dev >= lat else "en",
        "devanagari_share": round(dev / total, 3) if total else 0.0,
    }
