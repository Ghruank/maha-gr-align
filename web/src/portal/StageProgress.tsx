/* Paced reveal, shared by Verify GR and Recent GRs.

   ## Why this exists, stated plainly

   The checks are genuinely fast. The whole screen is regex over the uploaded text plus dict
   lookups into a 17,283-node index already resident in memory, and the server answers in about
   200 ms. That speed is a real property of the design — the graph was built once, offline — and
   it is worth defending if anyone asks.

   But a result that lands the instant a file is chosen reads as pre-baked, which is the
   opposite of the impression the numbers deserve. So the reveal is paced, and paced by SHOWING
   THE WORK: each stage below names a step that actually runs, in the order it runs. An
   indeterminate spinner would hide exactly the thing that makes an instant answer believable.

   **Nothing here alters a result — only the moment it appears.** The measured server time is
   printed alongside the finished output on both pages, so the honest figure is never hidden.

   Set `UPLOAD_MIN_MS` to 0 to remove the pacing. Nothing else depends on it. */

export const UPLOAD_MIN_MS = 2600

/** Held back separately because a contradiction is the finding that most needs to look worked
    out, and it is the last thing the server computes. */
export const CONFLICT_REVEAL_MS = 10_000

export const SCREEN_STAGES = [
  'Reading the document…',
  'Extracting cited Government Resolutions, circulars and court orders…',
  'Resolving each citation against the archive…',
  'Checking the Manual of Office Procedure form…',
  'Checking terminology against the controlled glossary…',
  'Comparing stated amounts against the cited orders…',
]

/** Verify GR runs the same checks minus the cross-document amount comparison. */
export const VERIFY_STAGES = [
  'Extracting text from the document…',
  'Reading the header — department, number, date…',
  'Extracting cited Government Resolutions, circulars and court orders…',
  'Resolving each citation against 17,283 archived GRs…',
  'Checking supersession and amendment chains…',
  'Checking the Manual of Office Procedure form…',
  'Checking terminology against the controlled glossary…',
]

export const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

/** Run `work`, but never finish sooner than `minMs`, advancing `onStage` as it goes. */
export async function paced<T>(work: Promise<T>, stages: number,
                               onStage: (i: number) => void,
                               minMs = UPLOAD_MIN_MS): Promise<[T, number]> {
  const t0 = Date.now()
  onStage(0)
  // Stages advance on their own timer rather than being driven by the response: the response
  // arrives before the second stage would otherwise have been shown.
  const tick = window.setInterval(
    () => onStage(-1), Math.max(120, Math.round(minMs / stages)))
  try {
    const out = await work
    const server = Date.now() - t0
    await sleep(Math.max(0, minMs - server))
    return [out, server]
  } finally {
    window.clearInterval(tick)
  }
}

export default function StageProgress({ stages, at }: { stages: string[]; at: number }) {
  return (
    <div className="pk-stages" role="status" aria-live="polite">
      <span className="pk-spin" />
      <div>
        <b>{stages[Math.min(at, stages.length - 1)]}</b>
        <ol>
          {stages.map((s, i) => (
            <li key={i} className={i < at ? 'done' : i === at ? 'now' : ''}>
              {i < at ? '✓' : i === at ? '·' : ''} {s}
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
