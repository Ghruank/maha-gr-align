#!/usr/bin/env python3
"""
Staged GRs — documents uploaded to the portal but not yet in the corpus.

## Why this exists

Every check in this project reads `out/graph.json`, which is the *published* record. A GR
pending issue is therefore invisible to all of it, which is exactly backwards: the moment a
resolution most needs checking is before it goes out, not after it has been crawled.

Staging closes that. An uploaded GR is registered in the live index and thereafter behaves like
any archived order — a second upload can cite it, resolve it, read it in the popup, and be
checked for contradicting it. That is what makes an inter-departmental conflict visible *while
both documents are still drafts*, which is the only time anybody can act on it.

## What a staged GR is not

It is **not** in the corpus and never silently becomes part of it. Staged records live in
`out/staging.json`, are marked `staged: true` on every response, and can be dropped. Nothing
here writes to `out/graph.json`. The distinction matters because the archive is our evidence
base: if an uploaded document could quietly join it, "verified against the official archive"
would stop being true.

The uid is synthesised as `YYYYMMDD` + `99` + a six-digit sequence + the department code. Real
portal uids carry an upload *time* in those middle digits, and no document is uploaded at
99:xx:xx, so a staged uid cannot collide with a crawled one — while still parsing correctly
everywhere `uid_date()` and `dept_of()` are used.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import references as R_refs
import resolver as R

ROOT = Path(__file__).resolve().parent
STORE = ROOT / "out" / "staging.json"

DEPT_CODE = {v: k for k, v in R.DEPT_BY_CODE.items()}


def _mint(d: date, dept: str | None, seq: int) -> str:
    return f"{d:%Y%m%d}99{seq:06d}{DEPT_CODE.get(dept or '', '00')}"


class Staging:
    """The in-tray. Held in memory, mirrored to disk so a restart does not lose a demo."""

    def __init__(self, archive: R_refs.Archive):
        self.archive = archive
        self.records: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._load()

    # ---------------------------------------------------------------- persistence

    def _load(self) -> None:
        if not STORE.exists():
            return
        try:
            saved = json.loads(STORE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for rec in saved.get("records", []):
            self.records[rec["uid"]] = rec
            self.archive.add(rec["uid"], rec["node"])
        self._seq = saved.get("seq", len(self.records))

    def _save(self) -> None:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(
            {"seq": self._seq, "records": list(self.records.values())},
            ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------------------------------------------------------- the in-tray

    def add(self, text: str, lang: str, filename: str,
            extraction: dict | None = None) -> dict[str, Any]:
        """Register an uploaded GR. Header fields are read by the same code the checks use."""
        d = R_refs.doc_date(text)[0] or date.today()
        dept = R_refs.doc_dept(text)
        self._seq += 1
        uid = _mint(d, dept, self._seq)

        subject = _subject(text)
        node = {
            "uid": uid, "date": d.isoformat(), "dept": dept,
            "dept_code": uid[-2:], "decision_no": R_refs.doc_number(text) or "",
            "subject": subject, "in_degree": 0, "out_degree": 0,
            "in_corpus": False, "staged": True,
        }
        rec = {
            "uid": uid, "node": node, "text": text, "lang": lang,
            "filename": filename, "staged": True,
            "uploaded_at": _now(),
            "extraction": extraction or {},
        }
        self.records[uid] = rec
        self.archive.add(uid, node)
        self._save()
        return rec

    def drop(self, uid: str) -> bool:
        if uid not in self.records:
            return False
        del self.records[uid]
        self.archive.drop(uid)
        self._save()
        return True

    def clear(self) -> int:
        n = len(self.records)
        for uid in list(self.records):
            self.drop(uid)
        return n

    def text_of(self, uid: str) -> str | None:
        rec = self.records.get(uid)
        return rec["text"] if rec else None

    def all(self) -> list[dict[str, Any]]:
        """Most recently uploaded first — the in-tray order an officer expects."""
        return sorted(self.records.values(), key=lambda r: r["uploaded_at"], reverse=True)


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _subject(text: str) -> str:
    """First line of substance. The staged list is unreadable without one."""
    import re
    for line in text.splitlines():
        s = re.sub(r"^\s*(विषय|Subject)\s*[:\-–]+\s*", "", line).strip()
        if len(s) >= 12:
            return s[:300]
    return "(no subject line)"
