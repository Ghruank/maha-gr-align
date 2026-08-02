import type { Lang, Stats, Verification } from './draftApi'

/* SRS FR-14 — original text, AI suggestion and validation results, side by side.

   ## Why the suggestion is held rather than applied

   Refinement used to overwrite the preview the moment the model answered. That made FR-14
   impossible to satisfy: there was never an instant at which the original and the suggestion
   both existed, so there was nothing to put side by side. Worse, an officer who disliked the
   result had to reach for the version history to undo something they had never agreed to.

   Now the model's output is a **proposal**. It sits beside the current text until the officer
   accepts or discards it, and only an acceptance writes to the preview.

   ## The invariant this must not break

   `CLAUDE.md`: the preview is the single source of truth, and every refinement sends the CURRENT
   preview text, hand edits included. That is preserved exactly — the request is unchanged, and
   the proposal is a whole-document replacement that is never *merged* into the preview. A merge
   is what could silently revert a hand edit; an accept-or-discard cannot.

   Holding the proposal also improves the audit trail (FR-15): an accepted suggestion is now an
   explicit human decision with a timestamp, rather than something that happened to the document
   while the officer watched.

   ## The diff

   Line-level, by longest common subsequence. Government Resolutions are short and line-oriented
   — the form puts the subject, the department, the number and the address on separate lines —
   so a word-level diff would add noise without adding information. */

type Kind = 'same' | 'add' | 'del' | 'change'
interface Row { left: string | null; right: string | null; kind: Kind }

/** Longest common subsequence over lines, then walked back into aligned rows. */
export function diffLines(a: string[], b: string[]): Row[] {
  const n = a.length, m = b.length
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const rows: Row[] = []
  let i = 0, j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) { rows.push({ left: a[i], right: b[j], kind: 'same' }); i++; j++ }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { rows.push({ left: a[i], right: null, kind: 'del' }); i++ }
    else { rows.push({ left: null, right: b[j], kind: 'add' }); j++ }
  }
  while (i < n) rows.push({ left: a[i++], right: null, kind: 'del' })
  while (j < m) rows.push({ left: null, right: b[j++], kind: 'add' })

  // A deletion immediately followed by an addition is one line rewritten, not two events.
  // Pairing them keeps the two columns aligned, which is the whole point of a side-by-side.
  const merged: Row[] = []
  for (let k = 0; k < rows.length; k++) {
    if (rows[k].kind === 'del' && rows[k + 1]?.kind === 'add') {
      merged.push({ left: rows[k].left, right: rows[k + 1].right, kind: 'change' })
      k++
    } else merged.push(rows[k])
  }
  return merged
}

export default function SuggestionDiff({ current, proposed, instruction, stats,
                                         before, after, mr, busy, onAccept, onDiscard }: {
  current: string
  proposed: string
  instruction: string
  stats?: Stats
  /** Validation of the text as it stands, and of what the model proposes. */
  before: Verification | null
  after: Verification | null
  /** Accepted for symmetry with the other panels; the diff renders the document's own script. */
  lang?: Lang
  mr: boolean
  busy: boolean
  onAccept: () => void
  onDiscard: () => void
}) {
  const rows = diffLines(current.split('\n'), proposed.split('\n'))
  const changed = rows.filter(r => r.kind !== 'same').length
  const font = mr ? 'pk-mr' : ''

  const delta = before && after ? after.counts.error - before.counts.error : null

  return (
    <div className="pk-diff">
      <div className="pk-diff-head">
        <div>
          <b>{mr ? 'एआयने सुचवलेला बदल' : 'The model proposes a change'}</b>
          <span className="pk-fine">
            {mr ? 'सूचना' : 'Instruction'}: “{instruction}”
            {' · '}{changed} {mr ? 'ओळी बदलल्या' : changed === 1 ? 'line differs' : 'lines differ'}
            {stats?.seconds != null && ` · ${stats.model} · ${stats.seconds}s`}
          </span>
        </div>
        <div className="pk-btnrow">
          <button className="pk-btn sm" onClick={onAccept} disabled={busy}>
            {mr ? 'स्वीकारा' : 'Accept'}
          </button>
          <button className="pk-btn sm ghost" onClick={onDiscard} disabled={busy}>
            {mr ? 'नाकारा' : 'Discard'}
          </button>
        </div>
      </div>

      {/* FR-14's third element: what the change does to compliance, before and after. */}
      {before && after && (
        <div className="pk-diff-verify">
          <span className={before.compliant ? 'ok' : 'bad'}>
            {mr ? 'सध्या' : 'Now'}: {before.compliant
              ? (mr ? 'नमुन्यानुसार' : 'compliant') : `${before.counts.error} ${mr ? 'त्रुटी' : 'errors'}`}
          </span>
          <span className="pk-diff-arrow">→</span>
          <span className={after.compliant ? 'ok' : 'bad'}>
            {mr ? 'स्वीकारल्यास' : 'If accepted'}: {after.compliant
              ? (mr ? 'नमुन्यानुसार' : 'compliant') : `${after.counts.error} ${mr ? 'त्रुटी' : 'errors'}`}
          </span>
          {delta !== null && delta !== 0 && (
            <span className={delta < 0 ? 'pk-diff-better' : 'pk-diff-worse'}>
              {delta < 0
                ? `${-delta} ${mr ? 'त्रुटी कमी' : 'fewer'}`
                : `${delta} ${mr ? 'त्रुटी अधिक' : 'more'}`}
            </span>
          )}
        </div>
      )}

      <div className="pk-diff-cols">
        <span>{mr ? 'सध्याचा मजकूर' : 'Current text'}</span>
        <span>{mr ? 'सुचवलेला मजकूर' : 'Proposed'}</span>
      </div>

      <div className="pk-diff-body">
        <table>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={r.kind}>
                <td className={font}>{r.left ?? ''}</td>
                <td className={font}>{r.right ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="pk-fine">{mr
        ? 'स्वीकारेपर्यंत पूर्वावलोकनात कोणताही बदल होत नाही. स्वीकारल्यास तो आवृत्ती इतिहासात अधिकाऱ्याचा निर्णय म्हणून नोंदवला जातो.'
        : 'Nothing is written to the preview until you accept. An acceptance is recorded in the version history as your decision, not the model’s.'}</p>
    </div>
  )
}
