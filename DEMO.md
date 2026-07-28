# Demo script

**Lead with the finding, not the capability.** Capabilities are copyable; findings are not. Every
other team will demo a chatbot over GRs. Do not open by describing features.

## Before you start

```bash
make serve          # http://localhost:8000
```

Then **turn the wifi off** and reload the page. Everything must still work. `AI_MODE=strict` makes
the client physically unable to open a socket, so this is guaranteed rather than hoped for — but
rehearse it once anyway, in the room, on the actual machine.

Have these two tabs open: **The Finding**, and **Reference Audit** filtered to the latent case.

---

## The 3-minute version

### 0:00 — The reframing (20 s)

> "Maharashtra has issued lakhs of Government Resolutions since 1960. Every one amends,
> supersedes or depends on earlier ones. **But a GR is not a document — it's a node in a legal
> dependency graph, and that graph has never existed in machine-readable form.** We built it for
> 17,283 GRs across four departments. Here's what it found."

Do not say "we built a system that…". Say what it found.

### 0:20 — The finding (60 s)

Open **Reference Audit**. Show the vehicle-policy case.

> "Finance issued an E-Vehicle Price Limit Policy in February 2022. **Finance replaced it itself**
> two years later. But two General Administration resolutions approving vehicle purchases are
> still in force and still depend on the replaced policy.
>
> **Neither department can see this.** General Administration doesn't track Finance's
> supersessions. Finance doesn't know who relies on its policy. You cannot find this by reading
> either document — it requires crossing a departmental boundary *and* following a supersession
> chain. It is a property of the graph."

Click through to the Marathi evidence. Say the line:

> "Every claim we make shows the verbatim Marathi sentence that produced it. If we can't show you
> the sentence, the edge doesn't ship — and that's enforced by a test, not by good intentions."

**21 dead references total.** Say the honest scope if asked: 5 distinct dead orders behind them.

### 1:20 — Why it's hard (40 s)

Open **The Finding**, scroll to the ablation table.

> "The obvious approach is to match citations by date. **Date alone cannot resolve a single one of
> 4,815 citations in this corpus** — it averages 44 candidate GRs and peaks at 380.
>
> So match on the decision number instead? A 'Government Decision No.' is a **departmental file
> number, not a unique identifier**. 41% of GRs share theirs — one number is on 41 different GRs.
>
> Neither key works alone. We match on the pair, using a digit key that survives both scripts:
> the metadata is Devanagari, the citations are transliterated Latin, so no string match can ever
> connect them — but the digits are the same."

This is the slide that separates you from a team that joined on dates and shipped 19,840 wrong edges.

### 2:00 — Trust (45 s)

Open **Trust Ledger**.

> "This is an AI hackathon, so: we do use a model — but only where we *measured* that rules fail.
> Cue-word matching can't distinguish 'this order is cancelled' from a file *named* 'Financial
> Reforms-1'. That's semantic.
>
> So the model proposes, and seven deterministic gates verify against the corpus before anything
> reaches this screen. **Here's the model quoting `अधिकरणित करुन` when the document actually says
> `अधिक्रमित करुन`** — it corrupted a Devanagari word while copying. Right answer, fabricated
> evidence. The gate caught it, and we show you rather than hiding it."

If a judge asks *"how do you know your AI isn't making things up"* — that question is already
answered on screen. That is the point of the page.

### 2:45 — Close (15 s)

> "Four departments today. The same pipeline runs over all 96,617 GRs — the graph builds in ten
> seconds. And it runs entirely offline, on-prem, with no data leaving the building."

---

## If you have 5 minutes

Add, in this order:

- **Graph Explorer** — click the Finance appropriation order with in-degree 209. "One Finance
  circular that 209 GRs across four departments depend on. Supersede it and they all rot at once.
  That's the blast radius." Superseded nodes are drawn hollow in dashed red — an arrow into one
  *is* a dead reference, visible at a glance.
- **GR-Lint** — "We didn't transcribe the Manual of Office Procedure. We mined what 2,800 GRs
  actually do, per department. A preamble appears in 78% of School Education resolutions and 31%
  of General Administration's — a hand-written rule would flag two-thirds of a department's lawful
  output as defective. Every rule carries its support count, and we publish the 18 orderings we
  deliberately *don't* enforce."
- **Bilingual Terms** — "₹17,56,70,000 in the Marathi appears as ₹1,75,670 in the English officials
  actually read. Off by a factor of 100,000. We found 335 of these."

---

## Answers to the hard questions

**"What's your accuracy?"**
> "Unmeasured, and we say so in the artefact rather than inventing a number — it needs a
> human-labelled answer key we haven't built. What we can show is label-free: date-only resolution
> is 100% ambiguous, cross-language agreement is 94.3% as a *lower bound*, evidence groundedness is
> 100% of 600 sampled edges, and zero structural violations across 4,815 edges. We'd rather show
> you five things we measured than one we didn't."

**"Only 21 dead references out of 17,000 GRs?"**
> "Yes, and that's the honest number. 21,121 citations we could *not* resolve are reported
> separately as unverifiable — mostly because the cited order isn't in the public crawl. Counting
> those would give us a headline four times bigger and false. Also, we've typed supersession on
> 15% of edges so far; the number grows with coverage, not with looser definitions."

**"Isn't the English translation unreliable?"**
> "Yes — it's machine translation, and that's exactly why every legal conclusion is drawn from the
> Marathi. We use the English only as an independent witness, because its failure modes are
> uncorrelated with the Marathi side. And we quantified its unreliability: 335 magnitude errors."

**"Could the LLM be hallucinating these findings?"**
> "It can't invent a citation — the target uid comes from our deterministic resolver, never from
> the model. It can't invent a quote — that's gate G1. It can't invent a category — that's G3. What
> it *can* do is misjudge, and we show a real example of that on the Trust Ledger too."

**"Why not just use RAG?"**
> "RAG retrieves documents. This finding isn't in any document — it's in the relationship between
> three of them across two departments. No amount of retrieval surfaces it."

---

## Do not

- Do not open with the architecture diagram.
- Do not claim an accuracy percentage.
- Do not merge the 21,121 unverifiable citations into the headline.
- Do not call the bilingual glossary a dictionary — it's lead generation, ~40% noise, and saying
  so is what makes the parity numbers credible.
- Do not make a live API call on stage.
