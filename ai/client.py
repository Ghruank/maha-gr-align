#!/usr/bin/env python3
"""
Groq client. Cache-first, offline-capable, stdlib-only.

Three properties this exists to guarantee, all of which matter more than convenience:

1. **The demo can run with the network unplugged.** Every response is persisted to
   `out/ai_cache/` and committed. `AI_MODE=strict` refuses to open a socket at all, so a
   dead conference wifi cannot break the presentation. A live API call on stage is an
   unforced error (CLAUDE.md working conventions).

2. **Runs are reproducible.** Cache key covers model, messages, temperature and schema, so
   the same request always yields the same bytes. Rebuilding an artefact does not silently
   change last night's numbers.

3. **No key ever leaks.** Read from the environment only — never a CLI argument (shell
   history), never a literal, never written into `out/`.

This module deliberately knows nothing about GRs. It moves prompts to a model and responses
back. All correctness enforcement lives in `ai/verify.py`, because a transport layer that
also judges content is a transport layer you cannot reason about.
"""

from __future__ import annotations

import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "out" / "ai_cache"

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class AIUnavailable(RuntimeError):
    """Raised when a response is not cached and cannot be fetched.

    Callers are expected to catch this and degrade — show the deterministic result without the
    model's contribution, labelled as such. It must never surface as a stack trace in the UI:
    "the model was unavailable" is a legitimate state for this system to be in and to display.
    """


# --------------------------------------------------------------------------- config

def _load_dotenv() -> None:
    """Minimal .env reader. Real environment always wins, so `AI_MODE=strict python ...`
    overrides the file without editing it."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

MODE = os.environ.get("AI_MODE", "warm").lower()
TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0"))
BASE_URL = os.environ.get("GROQ_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

MODELS = {
    "reasoning": os.environ.get("GROQ_MODEL_REASONING", ""),
    "tools": os.environ.get("GROQ_MODEL_TOOLS", ""),
    "stt": os.environ.get("GROQ_MODEL_STT", ""),
    "vision": os.environ.get("GROQ_MODEL_VISION", ""),
    "tts": os.environ.get("GROQ_MODEL_TTS", ""),
}


def model_for(role: str) -> str:
    m = MODELS.get(role, "")
    if not m:
        raise AIUnavailable(
            f"no model configured for role '{role}'. Set GROQ_MODEL_{role.upper()} in .env "
            f"(see .env.example). The feature depending on it should degrade, not crash."
        )
    return m


def configured_roles() -> dict[str, bool]:
    """Which capabilities are actually available. The UI reads this to hide or grey out
    features rather than offering something that will fail on click."""
    return {k: bool(v) for k, v in MODELS.items()}


# --------------------------------------------------------------------------- cache

def cache_key(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]


def _cache_path(role: str, key: str) -> Path:
    return CACHE_DIR / role / f"{key}.json"


def cache_stats() -> dict:
    if not CACHE_DIR.exists():
        return {}
    return {d.name: len(list(d.glob("*.json"))) for d in sorted(CACHE_DIR.iterdir()) if d.is_dir()}


# --------------------------------------------------------------------------- transport

def _post(path: str, payload: dict, timeout: int = 90) -> dict:
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise AIUnavailable("GROQ_API_KEY is not set — copy .env.example to .env and fill it in")

    # A default `Python-urllib/x.y` User-Agent is rejected by Cloudflare in front of the API
    # with `403 error code: 1010` (browser-signature ban). Identify as a normal client.
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "maha-gr-align/0.1",
            "Accept": "application/json",
        },
        method="POST",
    )

    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:500]
            # 429 and 5xx are transient; other 4xx is our bug and retrying wastes quota.
            if e.code != 429 and e.code < 500:
                raise AIUnavailable(f"HTTP {e.code} from Groq: {body}") from e
            last = f"HTTP {e.code}: {body}"
            # The free tier is token-per-minute limited (8,000 TPM observed) and the 429 body
            # states exactly how long to wait: "Please try again in 7.1774s". Honour it —
            # exponential backoff from 1s undershoots and burns the whole retry budget.
            if e.code == 429:
                # Two different 429s, and conflating them wastes an entire run.
                #
                # TPM (per-minute) is waitable: the body says "try again in 7.17s", so honour it.
                # TPD (per-DAY, 200,000 on the free tier) is not: the body says "try again in
                # 9m20s" and sleeping that — six times over, per call — hangs the job for hours
                # while achieving nothing. Fail fast so the caller degrades and the operator
                # finds out immediately.
                if 'tokens per day' in body or 'TPD' in body:
                    raise AIUnavailable(
                        "Groq DAILY token limit (TPD) exhausted — no further calls will "
                        "succeed today. Cached results are unaffected; rerun after the quota "
                        "resets or upgrade the tier. Original: " + body[:200]) from e
                m = re.search(r'try again in ([\d.]+)s', body)
                wait = float(m.group(1)) + 0.75 if m else 8.0
                if wait > 90:
                    raise AIUnavailable(
                        f"Groq asked us to wait {wait:.0f}s — treating as exhausted rather "
                        f"than stalling the run. Original: {body[:200]}") from e
                time.sleep(wait)
                continue
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"network: {e}"
        time.sleep(2 ** attempt)
    raise AIUnavailable(f"Groq unreachable after 6 attempts — {last}")


# --------------------------------------------------------------------------- public API

def chat(messages: list[dict], role: str = "reasoning", *, schema: dict | None = None,
         tools: list[dict] | None = None, temperature: float | None = None,
         max_tokens: int = 4096, reasoning_effort: str | None = None) -> dict:
    """One chat completion, cache-first.

    Returns `{"text", "raw", "cached", "model", "key"}`. `key` is the cache id and is carried
    into every downstream artefact so any claim in the UI can be traced back to the exact
    request that produced it — the model-facing equivalent of the `evidence` field on a graph
    edge.

    `schema` requests JSON-shaped output. Structured output support needs confirming against
    the Groq docs; until then a schema is also restated inside the prompt, and `ai/verify.py`
    validates the parse regardless. Never trust a mode flag to guarantee shape.
    """
    temp = TEMPERATURE if temperature is None else temperature
    # NOTE: Groq uses `max_completion_tokens`, not OpenAI's older `max_tokens`. Reasoning
    # models additionally accept `reasoning_effort`. Confirmed from the working JS snippet.
    payload: dict[str, Any] = {
        "model": model_for(role),
        "messages": messages,
        "temperature": temp,
        "max_completion_tokens": max_tokens,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if schema is not None:
        payload["response_format"] = {"type": "json_object"}
    if tools:
        payload["tools"] = tools

    key = cache_key({**payload, "_schema": schema})
    path = _cache_path(role, key)

    if MODE != "refresh" and path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["cached"] = True
        return rec

    if MODE == "strict":
        raise AIUnavailable(
            f"AI_MODE=strict and no cached response for {role}/{key}. Rebuild the artefact "
            f"with AI_MODE=warm, or degrade this feature."
        )

    raw = _post("/chat/completions", payload)
    rec = {
        "text": (raw.get("choices") or [{}])[0].get("message", {}).get("content", ""),
        "raw": raw,
        "cached": False,
        "model": payload["model"],
        "key": key,
        "role": role,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def chat_json(messages: list[dict], role: str = "reasoning", *, schema: dict | None = None,
              **kw) -> tuple[dict | list | None, dict]:
    """`chat` plus a tolerant JSON parse. Returns `(parsed_or_None, record)`.

    Never raises on malformed output — a model returning prose where JSON was asked for is an
    expected event, and it is `verify.py`'s job to record that as a rejection with a reason
    rather than this module's job to explode. Strips ```json fences, then falls back to the
    outermost brace/bracket span.
    """
    rec = chat(messages, role, schema=schema, **kw)
    txt = (rec.get("text") or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```", 2)[1] if txt.count("```") >= 2 else txt.strip("`")
        if txt.lstrip().lower().startswith("json"):
            txt = txt.lstrip()[4:]
    try:
        return json.loads(txt), rec
    except json.JSONDecodeError:
        pass
    for a, b in (("{", "}"), ("[", "]")):
        i, j = txt.find(a), txt.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(txt[i:j + 1]), rec
            except json.JSONDecodeError:
                continue
    return None, rec


def transcribe(audio_path: str | Path, *, language: str = "mr",
               temperature: float = 0.0) -> dict:
    """Marathi dictation → text, cache-first.

    Cached on the audio bytes, so a rehearsed demo clip is a cache hit and stays offline.
    `language="mr"` is passed explicitly rather than letting the model auto-detect: Marathi and
    Hindi share Devanagari and autodetect confuses them.

    The transcript is **input, never a finding.** It lands in an editable field and nothing
    downstream trusts it — so it needs no verification gate, unlike anything asserting a fact
    about the corpus.
    """
    p = Path(audio_path)
    data = p.read_bytes()
    model = model_for("stt")
    key = cache_key({"sha": hashlib.sha256(data).hexdigest(), "model": model,
                     "language": language, "temperature": temperature})
    path = _cache_path("stt", key)

    if MODE != "refresh" and path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["cached"] = True
        return rec
    if MODE == "strict":
        raise AIUnavailable(f"AI_MODE=strict and no cached transcript for {p.name}")

    fields = {"model": model, "language": language,
              "temperature": str(temperature), "response_format": "verbose_json"}
    raw = _post_multipart("/audio/transcriptions", fields, p.name, data)
    rec = {"text": (raw.get("text") or "").strip(), "raw": raw, "cached": False,
           "model": model, "key": key, "role": "stt"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def _post_multipart(path: str, fields: dict, filename: str, filedata: bytes,
                    timeout: int = 180) -> dict:
    """multipart/form-data POST. The transcription endpoint takes a file upload, not JSON."""
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise AIUnavailable("GROQ_API_KEY is not set")

    boundary = "----maha" + hashlib.sha256(filedata[:64] + filename.encode()).hexdigest()[:16]
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                f"{v}\r\n").encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    out += filedata + b"\r\n" + f"--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=bytes(out),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "maha-gr-align/0.1"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AIUnavailable(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:400]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise AIUnavailable(f"network: {e}") from e


def read_image(image_data_url: str, prompt: str, *, max_tokens: int = 3000) -> dict:
    """Vision: read an uploaded GR scan. `image_data_url` is a `data:image/...;base64,...` URI.

    Everything extracted here is untrusted text about a document **outside** the corpus, so it
    gets the same treatment as any other citation source: numbers and dates go through the
    deterministic resolver, and nothing is asserted about a page we could not read cleanly.
    """
    return chat(
        [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_data_url}}]}],
        role="vision", max_tokens=max_tokens)


if __name__ == "__main__":
    print(f"AI_MODE   : {MODE}")
    print(f"base url  : {BASE_URL}")
    print(f"api key   : {'set' if os.environ.get('GROQ_API_KEY') else 'MISSING'}")
    print("\nconfigured roles:")
    for r, ok in configured_roles().items():
        print(f"  {'✓' if ok else '·'} {r:10s} {MODELS[r] or '(unset)'}")
    print(f"\ncache: {cache_stats() or 'empty'}")
