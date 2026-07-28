# MAHA-GR-ALIGN
#
# CLAUDE.md: "Any number that appears in the pitch must be reproducible by a single command."
# This is that file. Every target is deterministic and needs no network — the only exception is
# `type-edges`, which calls Groq and is therefore NOT part of `all`: its output is committed under
# out/ and out/ai_cache/ so the demo never depends on an API being reachable.

PY      := .venv/bin/python
CORPUS  := data/mahGRs/GRs
OUT     := out

.PHONY: all graph audit metrics lint bilingual test serve build demo clean-artefacts help

help:
	@echo "make all        build every offline artefact (~30 s)"
	@echo "make demo       all + build the web UI + serve on :8000"
	@echo "make graph      17,283 nodes, 4,815 edges          -> $(OUT)/graph.json"
	@echo "make audit      dead-reference finding             -> $(OUT)/audit.json"
	@echo "make metrics    every number quoted in the pitch   -> $(OUT)/metrics.json"
	@echo "make lint       mined template rules               -> data/template_profile.json"
	@echo "make bilingual  numeric parity + glossary          -> $(OUT)/bilingual.json"
	@echo "make test       41 tests, zero API calls"
	@echo "make type-edges AI edge typing (NEEDS GROQ QUOTA; not part of 'all')"

all: graph audit lint bilingual metrics
	@echo ""
	@echo "All artefacts built. 'make serve' to view, 'make test' to verify."

# --- the graph is the substrate; everything else reads it -----------------------------
graph:
	$(PY) graph.py $(CORPUS) --out $(OUT)/graph.json

# NOTE: audit depends on SUPERSEDES edges, which come from `type-edges`. Running `graph`
# alone resets the graph to REFERENCES-only and the audit will legitimately find nothing.
# Re-run `make type-edges` (needs quota) or restore out/graph.json from git.
audit:
	$(PY) audit.py --graph $(OUT)/graph.json --out $(OUT)/audit.json

metrics:
	$(PY) metrics.py --graph $(OUT)/graph.json --out $(OUT)/metrics.json

lint:
	$(PY) lint.py --mine $(CORPUS) --profile data/template_profile.json
	$(PY) lint.py --audit-corpus $(CORPUS) --limit 2000 --out $(OUT)/lint_corpus.json

bilingual:
	$(PY) bilingual.py --all $(CORPUS) --limit 3000 --out $(OUT)/bilingual.json

# --- the only target that spends tokens ------------------------------------------------
# Batched 8 sentences per call: 60% of tokens were prompt, re-sent identically every time.
type-edges:
	$(PY) type_edges.py --batch 8

# --- verification -----------------------------------------------------------------------
# conftest.py forces AI_MODE=strict, so the suite cannot open a socket or spend a token.
test:
	$(PY) -m pytest tests/ -q

# --- interface ---------------------------------------------------------------------------
build:
	cd web && npm install --silent && npm run build

serve:
	@echo "http://localhost:8000"
	AI_MODE=strict .venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000

demo: all build serve

clean-artefacts:
	rm -f $(OUT)/graph.json $(OUT)/audit.json $(OUT)/metrics.json \
	      $(OUT)/lint_corpus.json $(OUT)/bilingual.json
	@echo "AI cache under $(OUT)/ai_cache/ deliberately kept — it is what makes the demo offline."
