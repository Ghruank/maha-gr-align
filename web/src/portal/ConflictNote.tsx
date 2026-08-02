import { useEffect, useRef, useState } from 'react'
import { screenApi, type Conflict, type ConflictExplanation } from './draftApi'

/* One amount contradiction, and — on hover — what it means.

   The two halves are not equal and the layout says so. The figures at the top are COMPUTED:
   `conflicts.py` read both documents and compared two integers, and that comparison is the
   finding. The paragraph underneath is the on-premise model explaining it, fetched on demand
   because it costs ~20 s and most hovers do not want it.

   The model is handed the three figures and may use no others; any sentence containing a
   number it was not given is discarded server-side before this component ever sees it. So the
   worst failure mode here is a short explanation, never a wrong figure. */

export default function ConflictNote({ conflict, citing }: {
  conflict: Conflict
  citing: unknown
}) {
  const [shown, setShown] = useState(false)
  const [note, setNote] = useState<ConflictExplanation | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  // Fetched once per conflict and cached in state. A dwell delay keeps a cursor crossing the
  // table from firing a 20-second model call it will never read.
  useEffect(() => {
    if (!shown || note || busy) return
    timer.current = window.setTimeout(() => {
      setBusy(true)
      screenApi.explain(conflict, citing, 'en')
        .then(setNote).catch(() => setNote(null)).finally(() => setBusy(false))
    }, 350)
    return () => window.clearTimeout(timer.current)
  }, [shown, note, busy, conflict, citing])

  const under = conflict.delta < 0

  return (
    <div className="pk-cf"
      onMouseEnter={() => setShown(true)}
      onFocus={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      onBlur={() => setShown(false)}
      tabIndex={0}>
      <span className="pk-verdict bad">
        {under ? '▼' : '▲'} {conflict.delta_display} {under ? 'understated' : 'overstated'}
      </span>

      <div className={`pk-cf-pop ${shown ? 'on' : ''}`} role="tooltip">
        <div className="pk-cf-head">
          <b>Contradicts the order it cites</b>
          <code>{conflict.code}</code>
        </div>

        {/* The computed comparison. Two integers read out of two documents. */}
        <table className="pk-cf-fig">
          <tbody>
            <tr>
              <th>This draft says</th>
              <td className="bad">{conflict.claimed.display}</td>
            </tr>
            <tr>
              <th>{conflict.target.dept} actually sanctioned</th>
              <td className="ok">{conflict.actual.display}</td>
            </tr>
            <tr className="gap">
              <th>Difference</th>
              <td>{conflict.delta_display} {under ? 'short' : 'over'}</td>
            </tr>
          </tbody>
        </table>

        <p className="pk-fine">
          cited at [{conflict.citation}], line {conflict.line} · {conflict.target.uid}
          {conflict.cross_dept && ' · cross-department'}
        </p>

        <div className="pk-cf-ai">
          {busy && <p className="pk-fine">The on-premise model is reading it…</p>}
          {note && (
            <>
              <p className={note.degraded ? 'degraded' : ''}>{note.explanation}</p>
              <small>{note.note}</small>
            </>
          )}
          {!busy && !note && <p className="pk-fine">Hold to read the analysis…</p>}
        </div>
      </div>
    </div>
  )
}
