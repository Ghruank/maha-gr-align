#!/usr/bin/env python3
"""
Emit data/devanagari_leak_map.json — the exhaustive Devanagari-leak vocabulary.

The vocabulary is closed: 75 token types, 2,109 instances, 441 GRs across HTE. It is
enumerated once, in full, rather than grown incrementally as cases are hit.

Classification is not eyeballed. Every leaked token was bucketed by its structural context:

  ORDINAL  the token follows a displaced list ordinal — `17.अभ Whatever happens...`
           This is the template bug in CLAUDE.md: Marathi `१७. अभ्यास...` became
           `17.अभ ...`, leaving the head of the Marathi sentence untranslated in front
           of its English translation. These are Class A — the English follows, so the
           Devanagari is redundant and is stripped.

  ACRONYM  the token sits inside a dotted run — `एम.ई.ड Digital systems`, `आय.आय.ट`.
           These are Class B — Latin letters transliterated into Devanagari, sitting in
           degree names, institution names, person initials and addresses. Never strip;
           back-transliterate.

The two classes separate almost perfectly, which is why a flat lookup table works at all.

Usage:
    python3 build_leak_map.py data/mahGRs/GRs/<Department> data/devanagari_leak_map.json
"""

import sys, re, json, glob, collections
from pathlib import Path

TOKEN = re.compile(r'[ऀ-ॿ]+')

# ---------------------------------------------------------------------------
# Class A — untranslated Marathi. The English translation follows the token, so the
# Devanagari is redundant: replacement is "" unless the token is load-bearing.
# `gloss` is the Marathi word the OCR truncated.
# ---------------------------------------------------------------------------
MARATHI_WORD = {
    "सदर":       ("",       "सदर — 'the said'"),
    "अभ":        ("",       "अभ्यास… — 'study/course', truncated"),
    "सर":        ("",       "सर्व — 'all'"),
    "सदरह":      ("",       "सदरहू — 'the aforesaid'"),
    "सदरच":      ("",       "सदरच — 'the said' + emphatic -च suffix"),
    "मह":        ("",       "महा… — 'Maha…' (Maharashtra / Mahalekhapal), truncated"),
    "अपर":       ("",       "अपर — 'Additional' (अपर मुख्य सचिव = Addl. Chief Secretary)"),
    "सच":        ("",       "सचिव — 'Secretary'"),
    "उप":        ("",       "उप — 'Deputy'"),
    "सहस":       ("",       "सहसंचालक — 'Joint Director'"),
    "अध":        ("",       "अधीक्षक — 'Superintendent'"),
    "उपर":       ("",       "उपरोक्त — 'the above-mentioned'"),
    "अवर":       ("",       "अवर सचिव — 'Under Secretary'"),
    "आपत":       ("",       "आपत्ती — 'disaster/emergency'"),
    "अन":        ("",       "अन्वये — 'in accordance with'"),
    "समन":       ("",       "समन्वय — 'coordination'"),
    "खर":        ("",       "खरेदी — 'purchase'"),
    "आदर":       ("",       "आदर्श — 'model/ideal'"),
    "एकस":       ("",       "एकत्रित — 'combined'"),
    "उपस":       ("",       "उपस्थित — 'present/attending'"),
    "पदव":       ("",       "पदवी — 'degree'"),
    "अहव":       ("",       "अहवाल — 'report'"),
    "सह":        ("",       "सह… — 'joint/assistant', truncated"),
    "वनस":       ("",       "वनस्पती — 'vegetation/botany'"),
    "आकस":       ("",       "आकस्मिक — 'contingency'"),
    "वसत":       ("",       "वसतिगृह — 'hostel'"),
    "उपलब":      ("",       "उपलब्ध — 'available'"),
    "इम":        ("",       "इमारत — 'building'"),
    "उच":        ("",       "उच्च — 'higher'"),
    "सब":        ("",       "सब… — truncated"),
    "एख":        ("",       "एखाद — 'any/some'"),
    "कक":        ("",       "कक्ष — 'section/cell' (कक्ष अधिकारी = Section Officer)"),
    "य":         ("",       "या — 'this/on', stranded after a URL: `…gov.inय website`"),
    "च":         ("",       "-चा/-च — Marathi genitive suffix stranded after a date"),
    "कल":        ("Kalyan", "कल्याण — place name, in `कल. Karjat Road`"),
    "लिए":       ("",       "Hindi लिए — 'for'; stray Hindi, not Marathi"),
    "है":        ("",       "Hindi है — 'is'; stray Hindi, not Marathi"),
    "लेते":      ("",       "Hindi लेते — 'taking'; stray Hindi, not Marathi"),
    "छफ":        ("",       "OCR garbage inside a mangled URL"),
    "शक्रिमुली": ("",       "OCR garbage in a table cell"),
}

# ---------------------------------------------------------------------------
# Class B — Latin letters/abbreviations written in Devanagari. These sit inside names,
# degrees, institutions and decision numbers, all load-bearing downstream. Never strip.
# ---------------------------------------------------------------------------
LATIN_TRANSLIT = {
    "एस":  ("S",     "एस.एस.स → S.S.C"),
    "एम":  ("M",     "एम.ई. → M.E. ; एम.एसस → M.Sc"),
    "एल":  ("L",     "एल.एल.ब → LL.B"),
    "आय":  ("I",     "आय.आय.ट → I.I.T"),
    "एच":  ("H",     "एम.एच.ब → M.H.B Colony"),
    "ए":   ("A",     "ए.आय.एस.एस.एम.एस → A.I.S.S.M.S College"),
    "आर":  ("R",     "आय.आर.ट → I.R.T"),
    "एन":  ("N",     "एच.एल.एन. Marg"),
    "एफ":  ("F",     "एम.एफ.ए → M.F.A"),
    "ई":   ("E",     "एम.ई.ड → M.E.D"),
    "ब":   ("B",     "एल.एल.ब → LL.B"),
    "ड":   ("D",     "एम.ई.ड Digital systems → M.E.D"),
    "ट":   ("T",     "आय.आय.ट Guwahati → I.I.T Guwahati"),
    "व":   ("V",     "एम.ई.व 'HLSI and Embedded Systems' → M.E.V (VLSI)"),
    "स":   ("C",     "सी → C; एम.एस.स IIT → MS-CIT"),
    "म":   ("M",     "य.च.म.म → Y.C.M.M (YCMOU)"),
    "क":   ("C",     "एम.ई.क Computer networks → M.E.C"),
    "प":   ("P",     "initial in addresses and decision numbers"),
    "न":   ("N",     "initial in addresses"),
    "श":   ("Sh",    "initial, institution names"),
    "ज":   ("J",     "initial"),
    "ध":   ("Dh",    "in Central Govt letter no. `F ध0.24-2/2024-ए`"),
    "अ":   ("A",     "Mr. Sunil अ.जगत → A. Jagat"),
    "जगत": ("Jagat", "surname"),
    "एसस": ("Sc",    "एम.एसस → M.Sc"),
    "इन":  ("In",    "एम.ई.इन Information technology → M.E.In"),
    "कम":  ("Com",   "एम.ई.कम Communication networks → M.E.Com"),
    "ऑट":  ("Aut",   "एम.ई.ऑट automotive engineering → M.E.Aut"),
    "आम":  ("M",     "आय.आम.एस, Mumbai (NMIMS)"),
    "रम":  ("Ram",   "रम-एल.एल.ब — degree/name fragment"),
    "ठ":   ("Rs",    "रु. → Rs; `ठ.50.00 Target` = Rs. 50.00"),
    # --- inside Government Decision / Memorandum numbers. Resolver keys on these. ---
    "र":   ("Kra",   "क्र (क्रमांक = 'number'); `PR र.14/22` → `Pra.Kra.14/22`"),
    "त":   ("Ta",    "तांशि — TANSHI section code; `र.56/15/त No.2`"),
    "आस":  ("Astha", "आस्थापना — 'establishment' section; `PRQ र.79/आस Tha-1`"),
    "ण":   ("n",     "tail of संकीर्ण; `Sankeer ण20-22` → `Sankeern20-22`"),
}


def main(src_dir: str, out_path: str):
    src, out = Path(src_dir), Path(out_path)

    inst = collections.Counter()
    files = collections.Counter()
    n_leaked = 0
    for f in sorted(src.glob("*.en.txt")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        found = TOKEN.findall(text)
        if not found:
            continue
        n_leaked += 1
        inst.update(found)
        files.update(set(found))

    declared = set(MARATHI_WORD) | set(LATIN_TRANSLIT)
    observed = set(inst)
    if declared != observed:
        missing, extra = observed - declared, declared - observed
        sys.exit(f"vocabulary is not exhaustive.\n  undeclared in corpus: {sorted(missing)}"
                 f"\n  declared but unseen: {sorted(extra)}")

    tokens = {}
    for tok, _ in inst.most_common():
        if tok in MARATHI_WORD:
            repl, gloss = MARATHI_WORD[tok]
            cls = "marathi_word"
        else:
            repl, gloss = LATIN_TRANSLIT[tok]
            cls = "latin_translit"
        tokens[tok] = {
            "class": cls,
            "replacement": repl,
            "gloss": gloss,
            "instances": inst[tok],
            "files": files[tok],
        }

    doc = {
        "_meta": {
            "source": str(src),
            "note": "Closed vocabulary of Devanagari surviving into the machine-translated "
                    ".en side. Enumerated exhaustively in one pass; not grown incrementally.",
            "leaked_grs": n_leaked,
            "token_types": len(tokens),
            "total_instances": sum(inst.values()),
            "classes": {
                "marathi_word": "Untranslated Marathi. The English follows the token, so it "
                                "is redundant; replacement is \"\" unless load-bearing.",
                "latin_translit": "Latin letters written in Devanagari, inside names, degrees, "
                                  "institutions and decision numbers. Never strip.",
            },
            "matching": "Match whole [ऀ-ॿ]+ runs, never substrings. `सदरच` must not be "
                        "matched as `सदर` + stranded `च`.",
        },
        "tokens": tokens,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    a = sum(1 for v in tokens.values() if v["class"] == "marathi_word")
    b = len(tokens) - a
    print(f"leaked GRs {n_leaked}   types {len(tokens)}   instances {sum(inst.values())}")
    print(f"  marathi_word   {a:>2} types, {sum(v['instances'] for v in tokens.values() if v['class']=='marathi_word'):>5} instances")
    print(f"  latin_translit {b:>2} types, {sum(v['instances'] for v in tokens.values() if v['class']=='latin_translit'):>5} instances")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/devanagari_leak_map.json")
