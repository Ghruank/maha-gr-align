import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../i18n'
import { screenApi, type ScreenPage, type ScreenRow } from '../draftApi'
import GRModal from '../GRModal'
import ConflictNote from '../ConflictNote'
import StageProgress, { CONFLICT_REVEAL_MS, SCREEN_STAGES, UPLOAD_MIN_MS, sleep } from '../StageProgress'

/* Recent GRs — the same two questions Verify GR asks about one upload, asked about a run of
   real documents instead.

   Two things are checked per row and they are genuinely independent:

     Format    is it built to the Manual of Office Procedure's form
     Citations does it still stand on the orders it cites

   A GR can be immaculate on the first and broken on the second, which is the whole argument for
   showing both side by side rather than one "score".

   ## The rule set matters, and the page says so

   Format is scored under `template.verify(mode="issued")`, NOT the drafting rules. These
   documents were issued years ago and read back through OCR; the signature block and the
   Governor's order line are IMAGES in the signed PDF, so the crawl never saw them. Under the
   drafting rules 0.2% of a 400-GR sample scores compliant — a number that measures our
   pipeline, not the Government's drafting. Under the issued rules it is 45%, and the failures
   are real: no discernible operative section, no resolution number in the extracted text.

   Fifteen rows, not 17,283. Screening the whole index is a batch job; this is a window. */

const LIMITS = [10, 15, 25]

const VERDICT_TONE: Record<string, string> = {
  aligned: 'ok', misaligned: 'bad', partial: 'warn', unverified: 'mute',
}

export default function RecentGRs() {
  const { t, lang } = useLang()
  const [data, setData] = useState<ScreenPage | null>(null)
  const [staged, setStaged] = useState<ScreenRow[]>([])
  const [uploading, setUploading] = useState(false)
  const [stage, setStage] = useState(0)
  /** uid whose contradiction check is still being revealed — see CONFLICT_REVEAL_MS. */
  const [pending, setPending] = useState<string | null>(null)
  const [took, setTook] = useState<Record<string, number>>({})
  const [upErr, setUpErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [limit, setLimit] = useState(15)
  const [dept, setDept] = useState<string>('')
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [row, setRow] = useState<string | null>(null)

  useEffect(() => {
    setBusy(true)
    screenApi.recent(limit, dept || undefined)
      .then(setData).catch(() => setData(null)).finally(() => setBusy(false))
  }, [limit, dept])

  // Re-read on every change, never patched in place: an upload can create a conflict in a GR
  // staged EARLIER, so the row that changes is not always the row that was just added.
  const reloadStaged = () =>
    screenApi.staged().then(d => setStaged(d.rows)).catch(() => setStaged([]))
  useEffect(() => { reloadStaged() }, [])

  const upload = async (f: File | null | undefined) => {
    if (!f) return
    setUploading(true); setUpErr(null); setStage(0)
    const t0 = Date.now()
    // Stages advance on their own timer rather than being driven by the response, because the
    // response arrives before the second one would have been shown.
    const tick = window.setInterval(
      () => setStage(s => Math.min(s + 1, SCREEN_STAGES.length - 1)),
      Math.round(UPLOAD_MIN_MS / SCREEN_STAGES.length))
    try {
      const row = await screenApi.upload(f)
      const server = Date.now() - t0
      await sleep(Math.max(0, UPLOAD_MIN_MS - server))
      setTook(m => ({ ...m, [row.uid]: server }))
      await reloadStaged()
      // The contradiction is held back on its own clock: it is the finding that needs to look
      // like it was worked out, and it is the last thing the server computes.
      if ((row.conflicts?.length ?? 0) > 0 && CONFLICT_REVEAL_MS > 0) {
        setPending(row.uid)
        window.setTimeout(() => setPending(p => (p === row.uid ? null : p)), CONFLICT_REVEAL_MS)
      }
    } catch (e) {
      setUpErr(e instanceof Error ? e.message : String(e))
    } finally {
      window.clearInterval(tick)
      setUploading(false)
    }
  }

  const drop = async (uid: string) => {
    await screenApi.drop(uid)
    await reloadStaged()
  }

  const rows = data?.rows ?? []
  const conflicts = staged.reduce((n, r) => n + (r.conflicts?.length ?? 0), 0)
  const okFormat = rows.filter(r => r.template.compliant).length
  const bad = rows.filter(r => r.references.verdict === 'misaligned').length
  const dead = rows.reduce((n, r) => n + r.references.superseded, 0)

  return (
    <div className="pk-page">
      <div className="pk-page-head">
        <h2>{t('nav.recent')}</h2>
        <p>The most recently issued Government Resolutions in the index, each screened on two
          independent questions: is it built to the Manual's form, and does it still stand on
          the orders it cites.</p>
      </div>

      <div className="pk-screenbar">
        <div className="pk-screenstats">
          <span><b>{rows.length}</b> screened</span>
          <span className="ok"><b>{okFormat}</b> follow the form</span>
          <span className="bad"><b>{bad}</b> not aligned with their citations</span>
          <span className="bad"><b>{dead}</b> cite a superseded order</span>
        </div>
        <div className="pk-screenfilters">
          <input ref={fileRef} type="file" hidden
            accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
            onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
          <button className="pk-btn sm" onClick={() => fileRef.current?.click()}
            disabled={uploading}>
            {uploading ? 'Screening…' : '＋ Upload GR'}
          </button>
          <select value={dept} onChange={e => setDept(e.target.value)} aria-label="Department">
            <option value="">All departments</option>
            {(data?.departments ?? []).map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <div className="pk-seg">
            {LIMITS.map(n => (
              <button key={n} className={limit === n ? 'on' : ''} onClick={() => setLimit(n)}>{n}</button>
            ))}
          </div>
        </div>
      </div>

      {uploading && <StageProgress stages={SCREEN_STAGES} at={stage} />}

      {upErr && <div className="pk-alert">{upErr}</div>}

      {staged.length > 0 && (
        <>
          <div className="pk-stagedhead">
            <h3>Pending issue — uploaded, not yet in the archive</h3>
            <span className="pk-fine">
              {staged.length} document{staged.length === 1 ? '' : 's'}
              {conflicts > 0 && <> · <b className="pk-bad">{conflicts} contradict an order they cite</b></>}
            </span>
          </div>
          <div className="pk-tablewrap staged">
            <table className="pk-table">
              <thead>
                <tr><th>Dated</th><th>Government Resolution</th><th>Format</th>
                  <th>Citations</th><th>Conflicts</th><th /></tr>
              </thead>
              <tbody>
                {staged.map(r => (
                  <Row key={r.uid} r={r} lang={lang} open={row === r.uid}
                    onToggle={() => setRow(row === r.uid ? null : r.uid)}
                    onRead={() => setOpen(r.uid)} onDrop={() => drop(r.uid)} staged
                    checking={pending === r.uid} tookMs={took[r.uid]} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {busy && <p className="pk-fine">Screening…</p>}
      {data && !data.available && (
        <div className="pk-alert">The corpus is not present on this machine, so archived GRs
          cannot be read. {data.hint}</div>
      )}

      {rows.length > 0 && (
        <div className="pk-tablewrap">
          <table className="pk-table">
            <thead>
              <tr>
                <th>Issued</th>
                <th>Government Resolution</th>
                <th>Format</th>
                <th>Citations</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <Row key={r.uid} r={r} lang={lang} open={row === r.uid}
                  onToggle={() => setRow(row === r.uid ? null : r.uid)}
                  onRead={() => setOpen(r.uid)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data?.note && <p className="pk-fine pk-screennote">{data.note}</p>}

      {open && <GRModal uid={open} lang="mr" mr={false} onClose={() => setOpen(null)} />}
    </div>
  )
}

function Row({ r, lang, open, onToggle, onRead, onDrop, staged, checking, tookMs }: {
  r: ScreenRow; lang: string; open: boolean; onToggle: () => void; onRead: () => void
  onDrop?: () => void; staged?: boolean; checking?: boolean; tookMs?: number
}) {
  const f = r.references
  const t = r.template
  return (
    <>
      <tr className={open ? 'on' : ''}>
        <td className="pk-td-date">
          {r.date}
          {staged && <em className="pk-td-staged">pending</em>}
          {!r.in_force && <em className="pk-td-dead">superseded</em>}
        </td>
        <td className="pk-td-gr">
          <code>{r.uid}</code>
          <span>{r.dept} · {t.doc_type}</span>
          <em>{r.subject}</em>
        </td>
        <td>
          <span className={`pk-verdict ${t.compliant ? 'ok' : 'bad'}`}>
            {t.compliant ? '✓ follows the form' : `${t.errors} missing`}
          </span>
          <span className="pk-fine">{t.present} of {t.total} sections</span>
        </td>
        <td>
          <span className={`pk-verdict ${VERDICT_TONE[f.verdict]}`}>
            {f.label[lang] || f.label.en}
          </span>
          <span className="pk-fine">
            {f.citations === 0 ? 'cites nothing we could identify'
              : `${f.verified}/${f.citations} resolved`}
            {f.superseded > 0 && ` · ${f.superseded} superseded`}
            {f.missing > 0 && ` · ${f.missing} not in archive`}
            {f.cross_department > 0 && ` · ${f.cross_department} cross-dept`}
          </span>
        </td>
        {staged && (
          <td className="pk-td-cf">
            {checking
              ? <span className="pk-checking"><i className="pk-spin sm" />
                comparing amounts with the cited order…</span>
              : (r.conflicts ?? []).length === 0
                ? <span className="pk-verdict ok">none</span>
                : (r.conflicts ?? []).map((c, i) =>
                  <ConflictNote key={i} conflict={c} citing={r.node ?? {}} />)}
          </td>
        )}
        <td className="pk-td-act">
          <button className="pk-linkish" onClick={onToggle}>{open ? 'less' : 'why'}</button>
          <button className="pk-linkish" onClick={onRead}>read</button>
          <Link className="pk-linkish" to={`/graph?uid=${r.uid}`}>graph</Link>
          {onDrop && <button className="pk-linkish" onClick={onDrop}>remove</button>}
        </td>
      </tr>
      {open && (
        <tr className="pk-td-detail">
          <td colSpan={staged ? 6 : 5}>
            <div>
              <h5>Format</h5>
              {t.missing.length === 0
                ? <p>Every section the Manual's {t.appendix} form requires is present.</p>
                : <p>Missing: {t.missing.join(' · ')}</p>}
              {t.relaxed.length > 0 && (
                <p className="pk-fine">Not counted against this document ({t.relaxed.join(', ')}):
                  either an image in the signed PDF that OCR cannot read, or a section the
                  Manual does not ask of a {t.doc_type}.</p>
              )}
              <h5>Citations</h5>
              {f.reasons.length === 0 ? <p>Nothing to report.</p>
                : <ul>{f.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>}
              {(r.conflicts ?? []).length > 0 && (
                <>
                  <h5>Contradictions</h5>
                  <ul>{(r.conflicts ?? []).map((c, i) => <li key={i}>{c.message}</li>)}</ul>
                </>
              )}
              <p className="pk-fine pk-mr">{r.decision_no}</p>
              {tookMs != null && (
                <p className="pk-fine">All four checks completed server-side in {tookMs} ms —
                  the pacing on screen is presentational.</p>
              )}
              {r.portal && (
                <a className="pk-linkish" href={r.portal} target="_blank" rel="noreferrer">
                  Original PDF on gr.maharashtra.gov.in ↗
                </a>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
