# Deploying MAHA-GR-ALIGN

The frontend is a static bundle and hosts anywhere. **The Python service cannot follow it onto a
serverless platform** — `torch`, `sentence-transformers` and `easyocr` exceed Vercel's 250 MB
function limit on their own, MahaSBERT's weights are 1.9 GB, Ollama is a separate daemon on
localhost, and WeasyPrint needs Pango/HarfBuzz/Cairo system libraries. So the split is:

| part | where |
| --- | --- |
| React frontend | Vercel (or any static host) |
| FastAPI + models + artefacts | your machine, or a VM / Railway / Render / Fly |

## Everything local (the normal case)

```bash
make dev          # uvicorn on :8000, Vite on :5173 with /api proxied
make doctor       # says what is down
```

Open <http://localhost:5173>. Nothing else is required and nothing leaves the machine.

## Frontend on Vercel, backend on your laptop

### The obstacle

A page served over **HTTPS cannot call `http://localhost:8000`.** Browsers block it as mixed
content before the request is made. Chrome sometimes exempts localhost; Firefox and Safari are
stricter. Do not rely on it.

### The fix: give your local API an HTTPS address

```bash
# 1. Start the backend
make serve                                  # uvicorn on :8000

# 2. In another terminal, tunnel it
cloudflared tunnel --url http://localhost:8000
#   -> https://something-random.trycloudflare.com
```

`ngrok http 8000` works the same way.

### Point the frontend at it

In the Vercel project, set an environment variable and redeploy:

```
VITE_API_BASE = https://something-random.trycloudflare.com
```

It is read at **build time**, so a change needs a redeploy. Locally, copy `web/.env.example` to
`web/.env.local` and set the same value to test the split before deploying.

### Allow the origin on the backend

```bash
ALLOWED_ORIGINS=https://your-project.vercel.app make serve
```

Any `*.vercel.app` origin is already allowed by a regex, so preview deployments work without a
restart. `ALLOWED_ORIGINS` is only needed for a custom domain.

### Vercel project settings

| setting | value |
| --- | --- |
| Root Directory | `web` |
| Framework Preset | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |

`web/vercel.json` already supplies the SPA rewrite, so a deep link to `/verify` or `/graph`
serves `index.html` instead of 404ing.

### What still will not work over a tunnel

Nothing is broken, but two things are slow enough to notice: OCR of a scanned upload (~18 s) and
the on-premise model calls (~20–40 s). Both were slow locally too; the tunnel adds a little.

## Rebuilding the artefacts

The repository ships the graph and the clause index so a clone runs immediately. The corpus
itself is **not** committed — it is a 440 MB public dataset:

```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/orgpedia/mahGRs.git data/mahGRs
cd data/mahGRs && git sparse-checkout set \
  GRs/Higher_and_Technical_Education_Department \
  GRs/General_Administration_Department \
  GRs/Finance_Department \
  GRs/School_Education_and_Sports_Department
```

Then `make graph`, `make index` (~35 min), `make all`. The corpus is needed only for rebuilding
and for the "read the cited GR" popup; every check works without it.
