# Demo script

**Lead with the finding, not the capability.** Capabilities are copyable; findings are not. Every
other team will demo a chatbot over GRs. Do not open by describing features.

## Before you start

```bash
make dev        # uvicorn :8000 + Vite :5173, killed together with Ctrl-C
make doctor     # seven OK lines, or fix it before you present
```

Open **<http://localhost:5173>**.

Then **turn the wifi off and reload.** Everything must still work — the graph, the index, the
models and the fonts are all on this machine. Rehearse that once, in the room, on the actual
laptop.

Clear the in-tray so the contradiction demo starts from nothing:

```bash
curl -X DELETE localhost:5173/api/staging
```

**If the laptop sleeps, `make dev` dies.** Restart it, re-run `make doctor`; ~15 s, nothing lost.

If `ollama` is DOWN the deterministic checks all still work and say the model was unavailable.
Only drafting, the AI summary and the AI notes need it.

---

## The 3-minute version

### 0:00 — The reframing (20 s)

> "Maharashtra has issued lakhs of Government Resolutions since 1960. Every one amends,
> supersedes or depends on earlier ones. **But a GR is not a document — it's a node in a legal
> dependency graph, and that graph has never existed in machine-readable form.** We built it for
> 17,283 GRs across four departments. Here's what it found."

Do not say "we built a system that…". Say what it found.

### 0:20 — The finding (60 s)

**Verify GR** → upload `samples/demo-B-citations-not-aligned.pdf` → **Citations** tab.

> "This General Administration resolution is in force today. It cites one Government Resolution —
> a Finance order on vehicle price limits. **Finance replaced that order in February 2024.**
> Nothing in either document says so.
>
> You cannot find this by reading either one. It needs a cross-departmental citation *and* a
> supersession chain. It is a property of the graph, not of any document."

Click **View this GR**: the superseding order, and a link to the signed PDF on the Government's
own site. Then point at the grey row:

> "Its other citation is a High Court order. We report that as *not a document the GR archive
> holds* — not as missing. **Only red is a defect. Grey is a limit of our coverage, not theirs.**
> Merging those two would quadruple our error count and make it false."

Say the line about evidence:

> "Every claim shows the verbatim Marathi sentence that produced it. If we can't show you the
> sentence, the edge doesn't ship — enforced by a test, not by good intentions."

### 1:20 — The money (60 s)

**Recent GRs** → **Upload GR** → `samples/demo-C-finance-15-crore.pdf`. Clean on all four checks.

Then `samples/demo-D-hte-10-crore.pdf`.

> "Also template-compliant. Citations also aligned. Terminology clean. And —"

*(the badge resolves)*

> "**Finance sanctioned fifteen crore. Higher Education, citing that exact order, wrote ten.**
> Both documents are impeccably drafted. The defect exists only in the relationship between them,
> and it's five crore."

Hover for the computed comparison, then the model's note.

> "That's not a similarity score. It read both documents and compared two integers."

### 2:20 — Why it's hard (25 s)

**Check Graph** → `202504071435036805`.

> "209 GRs depend on this one Finance circular. Supersede it and they all lose their footing —
> across three other departments. That's the question a drafting officer cannot answer today.
>
> And matching citations is harder than it looks: **date alone resolves none of 4,815 citations**
> — it averages 44 candidates. A 'Government Decision No.' isn't unique either; 41% of GRs share
> theirs. We match on the pair, with a digit key that survives both scripts."

### 2:45 — Close (15 s)

> "Four departments today; the same pipeline runs over all 96,617. Every check is 10 milliseconds,
> and every one of them runs on this laptop with the wifi off."

---

## If you have 5 minutes

- **Draft GR → refine.** The suggestion appears *beside* the current text, diffed, with
  `Now: 3 errors → If accepted: compliant`. Accept or discard.
  > "The model never writes to the document. It proposes; the officer decides; both the
  > acceptance and the rejection go into the audit trail."

  Budget ~3 min if you run it live — a 2B model rewriting a full GR on CPU is slow. Consider
  describing it instead.

- **Draft GR → Other departments.** 21,018 indexed clauses, own department excluded, scored hits
  linked to their source GR.
  > "Retrieval, not adjudication. This model separates *topic* cleanly but not the legal act — it
  > scores an amendment higher against a cancellation than a second cancellation. So we surface
  > candidates and the officer decides. The requirement asks for *potential* conflicts."

- **Verify GR → Terminology.**
  > "'Government Decision' appears in 1,861 of 2,500 corpus documents. The Manual of Office
  > Procedure uses it **zero** times — the correct term is 'Government Resolution'. The commonest
  > machine translation is the non-standard one, and no amount of mining the corpus would tell you
  > that. It needs a controlled list."

- **Recent GRs, unfiltered.** 15 recent GRs screened on form and citations at once, 170 ms.

---

## Answers to the hard questions

**"How do you know the AI isn't making things up?"**
> "Mostly it isn't asked to. There is no model call in the citation checker, the template engine,
> the contradiction check or the glossary — a test asserts the imports are absent. The model
> explains findings; it never produces them. Where it does write prose, any sentence containing a
> figure or identifier we didn't give it is discarded before you see it."

**"What's your accuracy?"**
> "98.9% citation extraction, measured across 906 GRs. 48 of 50 on a resolver precision sample
> deliberately weighted towards the hard cases — digit-key matches, cross-department, drifted
> dates. `make metrics` regenerates every number in one command."

**"Why is it so fast?"**
> "The graph was built once, offline. At request time it's regex plus dictionary lookups into an
> index already in memory. The upload animation is paced on purpose — the real server time is
> printed in the row's *why* panel."

**"Only 24 dead references out of 17,000 GRs?"**
> "Yes, and that's the honest number. Citations we could not resolve are reported separately as
> unverifiable — mostly because the cited order isn't in the public crawl. Counting those would
> give us a headline four times bigger and false. Supersession is typed on a fraction of edges so
> far; the number grows with coverage, not with looser definitions."

**"Isn't the English translation unreliable?"**
> "Yes — it's machine translation, which is exactly why every legal conclusion is drawn from the
> Marathi. We use English as an independent witness because its failure modes are uncorrelated.
> And we quantified the unreliability: 335 magnitude errors."

**"Why not just use RAG?"**
> "RAG retrieves documents. This finding isn't in any document — it's in the relationship between
> three of them across two departments. No amount of retrieval surfaces it."

**"How much of Maharashtra is this?"**
> "Four departments of thirty-three, 17,283 GRs, October 2017 to July 2026. So every
> cross-department number is a lower bound — and the interface says so rather than rounding up."

---

## Timings, so nothing looks broken

| action | expect |
| --- | --- |
| All four deterministic checks | 10 ms |
| Upload + screen | ~2.6 s (paced) |
| Contradiction badge | +10 s (paced) |
| Semantic search, warm | 0.6 s |
| AI summary | ~33 s |
| AI conflict note / review | 20–40 s |
| AI refinement of a full draft | up to ~3 min |
| OCR of a scan | ~18 s warm, ~90 s cold |

---

## Do not

- Do not open with the architecture diagram.
- Do not merge unverifiable citations into the dead-reference headline.
- Do not call the semantic hits "conflicts" — they are candidates for review.
- Do not put the AI refinement on the critical path of a timed demo.
- Do not make a live API call on stage. Nothing needs one; keep it that way.
