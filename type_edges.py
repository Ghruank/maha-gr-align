#!/usr/bin/env python3
"""
AI edge typing — upgrade REFERENCES edges to AMENDS / SUPERSEDES.

    python type_edges.py --dry-run          # count candidates, spend nothing
    python type_edges.py --limit 40         # try a slice
    python type_edges.py                    # full pass, then merge into out/graph.json

## Why a model is used here at all

Because cue matching provably cannot do it. Measured: of 40 cue-bearing Marathi sentences, only
28% contain a citation, and the cue is frequently *not a verb* — `वित्तीय सुधारणा-१` is a file
named "Financial Reforms-1". Distinguishing "this order is cancelled" from "file no.
Financial-Reforms-1" is semantic. That is the CLAUDE.md rule-4 test for reaching for a model:
determinism must have provably failed first.

## What the model is and is not allowed to do

It receives ONE sentence and a list of citations the **deterministic resolver** already resolved
inside it. It returns a type and the span that justifies it.

  * It cannot invent an edge — `dst` comes from the resolver, never from the model.
  * It cannot invent a target — it selects by index from candidates it was handed.
  * It cannot invent a quote — G1 requires the span verbatim in the source document.
  * It can only ever *upgrade* an existing verified edge's type.

## The three traps, all found in this corpus rather than imagined

1. **Cue inside an identifier.** `क्र.५(३)/आस्थायीपदे/पुढे चालू/२०१८/०३१` — a file name.
2. **Granularity.** A sentence cancelling *the appointments made under* a GR does not supersede
   the GR. The first probe got this wrong with every gate passing, which is why G7 exists.
3. **Deliberative mood.** `सुधारणा करण्याचे शासनाच्या विचाराधीन होते` — "amendment was under
   consideration" is the Proposal section stating intent, not an operative change.
"""

from __future__ import annotations

import re
import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter

import resolver as R
from ai.client import chat_json, AIUnavailable
from ai import verify as V

CORPUS = Path("data/mahGRs/GRs")
ALLOWED = {"REFERENCES", "AMENDS", "SUPERSEDES", "NONE"}

# Corpus-validated cues only. `पुढे चालू` is deliberately excluded — measured lift ×1.20 against
# an 83.4% base rate, i.e. no signal. See AI_ARCHITECTURE.md §3.3.
CUE = re.compile(r'रद्द|अधिक्रमित|अधिक्रमून|व्यपगत|सुधारणा|अंशत')

# "reference no. N" / "at reference no. N above" — an explicit pointer into the reference block.
REF_ORDINAL = re.compile(r'संदर्भ(?:ाधीन)?\s*(?:क्र|क्रमांक)\s*[.:]?\s*([०-९]{1,2})')

SYSTEM = """You classify one sentence from a Marathi Government Resolution (GR) of Maharashtra.

You are given the sentence and a numbered list of prior GRs that a deterministic resolver has
ALREADY matched inside it. Decide what relationship, if any, the sentence establishes.

TYPES:
  SUPERSEDES - the sentence cancels / annuls / supersedes a prior ORDER ITSELF
               (रद्द करण्यात येत आहे, अधिक्रमित करुन, व्यपगत)
  AMENDS     - the sentence modifies part of a prior order, or cancels something DONE UNDER it
               (सुधारणा, अंशत: बदल), leaving the order itself standing
  REFERENCES - it merely cites or lists a prior order, with no operative change
  NONE       - it establishes no relationship to any listed GR

THREE TRAPS. Each of these has caused a real error on this corpus; read them carefully.

1. CUE WORDS INSIDE FILE NUMBERS ARE NOT VERBS.
   Marathi order numbers often contain words like सुधारणा or पुढे चालू as part of the file's
   NAME: "क्र. १२(भाग-२)/२००४/वित्तीय सुधारणा-१" is a file called "Financial Reforms-1", and
   "क्र.५(३)/आस्थायीपदे/पुढे चालू/२०१८/०३१" is a file name too. A cue appearing inside an
   order number carries NO operative meaning. Judge only the sentence's actual assertion.

2. GRANULARITY: WHAT EXACTLY IS BEING CANCELLED?
   If the sentence cancels APPOINTMENTS, APPROVALS, SANCTIONS, POSTS, FUNDS or COMMITTEE
   MEMBERSHIPS *made under* a prior GR, that GR is NOT superseded — it stands, and its
   arrangements change. That is AMENDS, never SUPERSEDES. Only say SUPERSEDES when the ORDER
   itself is cancelled or replaced. Always report what was cancelled in `cancelled_object`.

3. DELIBERATIVE MOOD IS NOT A DECISION.
   "विचाराधीन होते" / "विचाराधीन आहे" means the matter was UNDER CONSIDERATION. Such sentences
   appear in the Proposal (प्रस्तावना) section and state intent, not an operative change.
   Classify these REFERENCES.

Return JSON only, no prose:
{"type": "SUPERSEDES|AMENDS|REFERENCES|NONE",
 "target_index": <1-based index into the candidate list, or null>,
 "evidence_span": "<EXACT substring of the input sentence justifying the type>",
 "cancelled_object": "<the Marathi noun that is cancelled/amended, or null>",
 "gloss_en": "<literal English translation of the sentence>",
 "confidence": 0.0-1.0}

`evidence_span` MUST be copied character-for-character from the input. Do not translate,
normalise or paraphrase it — it is checked against the source document."""


def load_sources() -> dict:
    return {f.name.split('.')[0]: f
            for d in CORPUS.iterdir() if d.is_dir()
            for f in d.glob('*.mr.txt')}


def candidates(graph: dict, sources: dict) -> list[dict]:
    """Deterministically pair each cue-bearing sentence with the edges it plausibly governs.

    Two independent linkers, both exact — no fuzzy matching, because a wrong link means a
    correctly-typed sentence applied to the wrong GR, which no downstream gate can catch:

      * **by date** — the sentence repeats the edge's cited date
      * **by ordinal** — the sentence says `संदर्भ क्र. १०`, pointing at the Nth citation in the
        document. `extract_mr_citations` returns citations in document order, so the ordinal
        indexes it directly.

    A sentence linking to several edges is kept as one call listing all of them, and the model
    picks by index. That is cheaper and lets it use the contrast between candidates.
    """
    by_src = defaultdict(list)
    for i, e in enumerate(graph["edges"]):
        by_src[e["src"]].append((i, e))

    out, stats = [], Counter()
    for src, edges in by_src.items():
        f = sources.get(src)
        if not f:
            stats["no_source_file"] += 1
            continue
        text = f.read_text(encoding='utf-8', errors='ignore')
        if not CUE.search(text):
            stats["doc_has_no_cue"] += 1
            continue

        # citation order in the document — the ordinal linker's index
        all_cits = R.extract_mr_citations(text)
        order = {(c["cited_date"], c["cited_no"]): n for n, c in enumerate(all_cits, 1)}

        sents = [" ".join(s.split()) for s in re.split(r'[।\n]', text)]
        for s in sents:
            if len(s) < 25 or not CUE.search(s):
                continue
            linked, how = {}, {}
            dates = set()
            for m in R.MR_DATE.finditer(s):
                d = R._mkdate(m.group(1), m.group(2), m.group(3))
                if d:
                    dates.add(d.isoformat())
            ordinals = {int(o.translate(V.DEV_DIGITS)) for o in REF_ORDINAL.findall(s)}

            for i, e in edges:
                if e["cited_date"] in dates:
                    linked[i] = e
                    how[i] = "date"
                elif order.get((e["cited_date"], e["cited_no"])) in ordinals:
                    linked[i] = e
                    how[i] = "ordinal"
            if not linked and len(edges) == 1:
                # Third linker. Many operative sentences name no date and no ordinal —
                # `उपरोक्त शासन निर्णय रद्द करण्यात येतो` ("the above GR is cancelled") — which
                # left 726 cue sentences stranded and cost most of the supersession recall.
                # When the whole document has exactly ONE resolved citation there is no
                # ambiguity about what "the above order" refers to, so the link is still exact.
                # Restricted to len==1 deliberately: with two or more candidates this would be
                # guessing, and a mislinked edge means a correctly-typed sentence attached to
                # the wrong GR, which no downstream gate can catch.
                i, e = edges[0]
                linked[i], how[i] = e, "sole_citation"
            if not linked:
                stats["cue_sentence_unlinked"] += 1
                continue
            out.append({"src": src, "sentence": s, "text": text,
                        "edges": [(i, linked[i], how[i]) for i in sorted(linked)]})
            stats["candidate_calls"] += 1
            stats["candidate_edges"] += len(linked)
    return out, stats


BATCH_SUFFIX = """

You will be given SEVERAL numbered items. Judge each INDEPENDENTLY and return a JSON object:
{"results": [{"item": <item number>, "type": "...", "target_index": <n or null>,
              "evidence_span": "...", "cancelled_object": "...", "gloss_en": "...",
              "confidence": 0.0-1.0}, ...]}
Return exactly one result per item, in order. `evidence_span` must be copied
character-for-character from that item's own sentence."""


def type_batch(cands: list[dict], index: dict, window: int) -> list[dict]:
    """Judge several sentences in ONE call.

    Why this exists: `[MEASURED]` over 231 single-sentence calls, **60% of all tokens were prompt
    tokens**, and the ~836-token system prompt was re-sent identically every time. One sentence
    per call meant a 702-call pass costs ~1,042K tokens against a 200,000/day organisation cap —
    the instructions alone accounted for more than half of it.
    Batching sends the rules once per batch instead of once per sentence.

    Reasoning tokens (83% of completions) are per-decision and do NOT shrink with batching, so
    this is a ~30% total saving, not 10x. `reasoning_effort="low"` was tested as a second lever
    and rejected: it changed a verdict on the first sample, and a cheaper wrong answer is not a
    saving in a legal graph.

    Each item keeps its own candidate list and is judged independently; the model must return one
    result per item. A batch that comes back malformed or short is retried one-at-a-time rather
    than dropped, so batching can never silently lose an edge.
    """
    blocks = []
    for n, c in enumerate(cands, 1):
        cl = "\n".join(
            f"   {j}. GR dated {e['cited_date']}"
            + (f", number {e['cited_no']}" if e["cited_no"] else "")
            for j, (_, e, _) in enumerate(c["edges"], 1))
        blocks.append(f"ITEM {n}\nSENTENCE: {c['sentence']}\nCANDIDATE PRIOR GRs:\n{cl}")

    parsed, rec = chat_json(
        [{"role": "system", "content": SYSTEM + BATCH_SUFFIX},
         {"role": "user", "content": "\n\n".join(blocks)}],
        "reasoning", schema={}, max_tokens=900 + 420 * len(cands), reasoning_effort="medium")

    results = (parsed or {}).get("results") if isinstance(parsed, dict) else None
    if not results or len(results) != len(cands):
        # Never silently lose an edge: fall back to one call per sentence for this batch.
        out = []
        for c in cands:
            out.extend(type_one(c, index, window))
        return out

    by_item = {r.get("item"): r for r in results if isinstance(r, dict)}
    out = []
    for n, c in enumerate(cands, 1):
        claim = by_item.get(n)
        if claim is None:
            out.extend(type_one(c, index, window))
            continue
        out.extend(_verdicts_for(c, claim, rec, index, window))
    return out


def _verdicts_for(cand: dict, parsed: dict, rec: dict, index: dict, window: int) -> list[dict]:
    """Gate one model claim against the edges its sentence governs."""
    ti = parsed.get("target_index")
    results = []
    for n, (i, e, how) in enumerate(cand["edges"], 1):
        if ti is not None and n != ti:
            continue
        v = V.verify_edge_type(
            parsed, src_uid=cand["src"], dst_uid=e["dst"], source_text=cand["text"],
            index=index, allowed_types=ALLOWED, window_days=window)
        results.append({
            "edge_index": i, "src": cand["src"], "dst": e["dst"], "link": how,
            "sentence": cand["sentence"], "evidence_span": parsed.get("evidence_span"),
            "cancelled_object": parsed.get("cancelled_object"),
            "gloss_en": parsed.get("gloss_en"), "confidence": parsed.get("confidence"),
            "cache_key": rec.get("key"), **v})
    return results


def type_one(cand: dict, index: dict, window: int) -> list[dict]:
    """One model call → verified verdicts for the edges that sentence governs."""
    lines = [f"{n}. GR dated {e['cited_date']}"
             + (f", number {e['cited_no']}" if e["cited_no"] else "")
             for n, (_, e, _) in enumerate(cand["edges"], 1)]
    user = (f"SENTENCE:\n{cand['sentence']}\n\n"
            f"CANDIDATE PRIOR GRs MENTIONED IN IT:\n" + "\n".join(lines))

    parsed, rec = chat_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "reasoning", schema={}, max_tokens=1800, reasoning_effort="medium")

    results = []
    if parsed is None:
        for i, e, how in cand["edges"]:
            results.append({"edge_index": i, "src": cand["src"], "dst": e["dst"],
                            "link": how, "sentence": cand["sentence"],
                            "verdict": "REJECTED", "type": None, "proposed_type": None,
                            "failed_hard": ["output was not parseable JSON"],
                            "failed_soft": [], "gates": {}, "notes": [],
                            "cache_key": rec.get("key")})
        return results

    ti = parsed.get("target_index")
    for n, (i, e, how) in enumerate(cand["edges"], 1):
        # The model names ONE target; other edges in the same sentence stay REFERENCES rather
        # than inheriting a type they were not judged on.
        if ti is not None and n != ti:
            continue
        v = V.verify_edge_type(
            parsed, src_uid=cand["src"], dst_uid=e["dst"], source_text=cand["text"],
            index=index, allowed_types=ALLOWED, window_days=window)
        results.append({
            "edge_index": i, "src": cand["src"], "dst": e["dst"], "link": how,
            "sentence": cand["sentence"], "evidence_span": parsed.get("evidence_span"),
            "cancelled_object": parsed.get("cancelled_object"),
            "gloss_en": parsed.get("gloss_en"), "confidence": parsed.get("confidence"),
            "cache_key": rec.get("key"), **v})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="out/graph.json")
    ap.add_argument("--out-graph", default="out/graph.json")
    ap.add_argument("--rejections", default="out/ai_rejections.json")
    ap.add_argument("--typed", default="out/typed_edges.json")
    ap.add_argument("--window", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--batch", type=int, default=8,
                    help="sentences per model call. 60%% of tokens are prompt, so batching is "
                         "the main cost lever; 1 disables it")
    ap.add_argument("--dry-run", action="store_true", help="count candidates, make no calls")
    a = ap.parse_args()

    g = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    sources = load_sources()
    index = {n["uid"] for n in g["nodes"]}

    cands, stats = candidates(g, sources)
    print("candidate selection (deterministic, no model involved):")
    for k, v in stats.most_common():
        print(f"  {v:6,}  {k}")
    print(f"\n{len(cands):,} model calls would cover {stats['candidate_edges']:,} edges "
          f"({100*stats['candidate_edges']/max(len(g['edges']),1):.1f}% of {len(g['edges']):,})")
    by_link = Counter(h for c in cands for _, _, h in c["edges"])
    print(f"  link type: {dict(by_link)}")
    if a.dry_run:
        return

    if a.limit:
        cands = cands[:a.limit]
    bs = max(1, a.batch)
    groups = [cands[i:i + bs] for i in range(0, len(cands), bs)]
    print(f"\ntyping {len(cands):,} sentences in {len(groups):,} call(s) "
          f"(batch size {bs})…")

    verdicts, tally = [], Counter()
    done = 0
    for gi, grp in enumerate(groups, 1):
        try:
            rs = type_batch(grp, index, a.window) if bs > 1 else type_one(grp[0], index, a.window)
        except AIUnavailable as e:
            print(f"  [batch {gi}] model unavailable — degrading: {e}")
            tally["unavailable"] += len(grp)
            if "DAILY token limit" in str(e):
                print("  stopping: no further call can succeed today. "
                      "Partial results are kept and cached.")
                break
            continue
        for r in rs:
            verdicts.append(r)
            tally[r["verdict"]] += 1
            if r["verdict"] != "REJECTED" and r["type"] in ("AMENDS", "SUPERSEDES"):
                tally[f"typed_{r['type']}"] += 1
            if r.get("notes"):
                tally["G7_downgraded"] += 1
        done += len(grp)
        if gi % 5 == 0 or done >= len(cands):
            print(f"  {done}/{len(cands)}  {dict(tally)}")

    # --- merge: only ever UPGRADE an existing edge, never create one
    upgraded = 0
    for r in verdicts:
        if r["verdict"] == "REJECTED" or r["type"] not in ("AMENDS", "SUPERSEDES"):
            continue
        e = g["edges"][r["edge_index"]]
        e["type"] = r["type"]
        # If G1 failed, the model's span is NOT in the document and must never be shown as
        # evidence — observed: it quoted `अधिकरणित करुन` where the source reads `अधिक्रमित करुन`,
        # subtly corrupting a Devanagari word while copying. Fall back to the deterministically
        # extracted sentence, which is verbatim by construction, and record the substitution.
        # The cue must always be text that genuinely occurs in the document, because a typed edge
        # without a real justification is indistinguishable from a fabricated one. When G1 fails
        # we fall back to the whole extracted sentence rather than dropping the cue: the sentence
        # is verbatim by construction and does contain the operative language — only the model's
        # transcription of it was corrupt (it wrote `अधिकरणित करुन` where the source reads
        # `अधिक्रमित करुन`). Dropping the cue instead would leave a typed edge with no evidence of
        # its type, which `test_typed_edges_carry_a_cue` rightly rejects.
        g1_ok = r.get("gates", {}).get("G1_grounding", {}).get("pass", True)
        e["cue"] = r.get("evidence_span") if g1_ok else r["sentence"]
        if not g1_ok:
            e["evidence"] = r["sentence"]
        e["evidence_kind"] = "operative_sentence"
        e["evidence_en"] = r.get("gloss_en")
        e["typed_by"] = {"model": "ai", "verdict": r["verdict"],
                         "link": r["link"], "cache_key": r.get("cache_key"),
                         "notes": r.get("notes", []),
                         "cue_source": "model_span" if g1_ok else
                                       "extracted_sentence (model span failed G1 grounding)"}
        upgraded += 1

    g["meta"]["edge_types"] = {t: sum(1 for e in g["edges"] if e["type"] == t)
                               for t in ("REFERENCES", "AMENDS", "SUPERSEDES")}
    g["meta"]["ai_typing"] = {
        "calls": len(cands), "verdicts": dict(tally), "edges_upgraded": upgraded,
        "candidate_stats": dict(stats),
    }

    Path(a.out_graph).write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    Path(a.typed).write_text(json.dumps(verdicts, ensure_ascii=False, indent=1), encoding="utf-8")
    rej = [r for r in verdicts if r["verdict"] != "VERIFIED"]
    Path(a.rejections).write_text(json.dumps(rej, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'='*70}\nverdicts: {dict(tally)}")
    print(f"edges upgraded: {upgraded}")
    print(f"edge types now: {g['meta']['edge_types']}")
    print(f"\nwrote {a.out_graph}, {a.typed}, {a.rejections} "
          f"({len(rej)} non-VERIFIED rows for the Trust Ledger)")


if __name__ == "__main__":
    main()
