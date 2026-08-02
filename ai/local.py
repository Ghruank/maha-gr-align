#!/usr/bin/env python3
"""
Local LLM transport — Ollama. The on-prem replacement for `ai/client.py` (hosted Groq).

NFR-2 says sensitive drafts must not leave the State Data Centre. This module talks only to
`localhost:11434`; there is no code path here that can reach the internet. That is the point.

Three things learned by measuring, all encoded as defaults:

* **`think: false` is mandatory.** Qwen3.5 reasons by default. One classification with thinking
  on burned 500 tokens and 54 s without emitting an answer — NFR-1 allows 30 s for a whole
  reference check. Callers may opt back in, but nothing on the drafting path does.
* **Roughly 9 tokens/sec on the target CPU.** A 600-token GR body is a ~65 s generation. Long
  outputs must stream or be chunked; do not promise a 30 s round trip on a full draft.
* **Temperature 0.** Reproducibility is a requirement (CLAUDE.md rule 4), not a preference.

This module knows nothing about GRs. It moves prompts to a model and JSON back. All correctness
enforcement lives in `template.py` (structure) and `ai/verify.py` (citations).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "data" / "models.json"

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class LocalAIUnavailable(RuntimeError):
    """Ollama is not reachable or the model is not pulled.

    Callers must catch this and degrade — show the deterministic result and say the model did
    not contribute. "The model was unavailable" is a legitimate state to display.
    """


def _model() -> str:
    try:
        return json.loads(ROSTER.read_text())["llm"]["id"]
    except Exception:
        return "qwen3.5:2b"


def available() -> tuple[bool, str]:
    """(reachable, detail). Cheap enough to call on every health check."""
    try:
        with urllib.request.urlopen(f"{DEFAULT_HOST}/api/tags", timeout=3) as r:
            tags = {m["name"] for m in json.loads(r.read()).get("models", [])}
    except Exception as exc:
        return False, f"ollama unreachable at {DEFAULT_HOST}: {exc}"
    m = _model()
    if m not in tags:
        return False, f"model {m} not pulled (run: ollama pull {m})"
    return True, m


def generate(prompt: str, *, system: str | None = None, max_tokens: int = 800,
             temperature: float = 0.0, think: bool = False,
             timeout: int = 600) -> tuple[str, dict[str, Any]]:
    """One completion. Returns (text, stats). Raises LocalAIUnavailable on transport failure."""
    body: dict[str, Any] = {
        "model": _model(),
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if system:
        body["system"] = system

    req = urllib.request.Request(
        f"{DEFAULT_HOST}/api/generate",
        json.dumps(body).encode(),
        {"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except urllib.error.URLError as exc:
        raise LocalAIUnavailable(f"{DEFAULT_HOST}: {exc}") from exc
    except TimeoutError as exc:
        raise LocalAIUnavailable(f"timed out after {timeout}s") from exc

    elapsed = time.time() - t0
    eval_count = d.get("eval_count") or 0
    stats = {
        "model": _model(),
        "seconds": round(elapsed, 2),
        "eval_tokens": eval_count,
        "tokens_per_sec": round(eval_count / max(d.get("eval_duration", 1) / 1e9, 1e-9), 1),
        "local": True,
    }
    return (d.get("response") or "").strip(), stats


# --------------------------------------------------------------------------------------
# JSON extraction
#
# A 2B model wraps JSON in prose and code fences no matter how firmly it is told not to.
# Parsing is therefore a documented step, not an afterthought — and a parse failure returns
# None so the caller can degrade rather than surface half-parsed rubbish to an officer.
# --------------------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> Any | None:
    """Best-effort JSON out of a chatty completion. None when nothing valid is found."""
    for candidate in _candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _candidates(text: str):
    text = text.strip()
    yield text
    for m in _FENCE.finditer(text):
        yield m.group(1).strip()
    # First balanced {...} or [...] span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    yield text[start:i + 1]
                    break


def generate_json(prompt: str, **kw) -> tuple[Any | None, dict[str, Any]]:
    """generate() plus parsing. `stats['parsed']` says whether JSON came back."""
    raw, stats = generate(prompt, **kw)
    obj = parse_json(raw)
    stats["parsed"] = obj is not None
    if obj is None:
        stats["raw_preview"] = raw[:300]
    return obj, stats
