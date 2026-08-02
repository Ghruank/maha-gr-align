import { useEffect, useRef, useState } from 'react'
import { useLang } from '../i18n'
import {
  draftApi, glossaryApi, verifyApi,
  type Extraction, type GlossaryReport, type Lang, type ReferenceReport, type ReviewResult,
  type Section, type Summary, type Verification,
} from '../draftApi'
import StageProgress, { UPLOAD_MIN_MS, VERIFY_STAGES, sleep } from '../StageProgress'
import VerifyPanel from '../VerifyPanel'
import ReferencePanel from '../ReferencePanel'
import GlossaryPanel from '../GlossaryPanel'

/* SRS FR-13 (upload a draft) + FR-10/11/12 (template enforcement) applied to an existing
   document.

   The extraction method is shown, always. Text taken from a PDF's own text layer is exact;
   text produced by OCR is a machine reading of a picture. Those deserve different trust, and
   an officer told only "3 errors" cannot tell which they are looking at. */

export default function VerifyGR() {
  const { t } = useLang()
  const [lang, setLang] = useState<Lang>('mr')
  const [file, setFile] = useState<File | null>(null)
  const [forceOcr, setForceOcr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [verification, setVerification] = useState<Verification | null>(null)
  const [refs, setRefs] = useState<ReferenceReport | null>(null)
  const [review, setReview] = useState<ReviewResult | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [gloss, setGloss] = useState<GlossaryReport | null>(null)
  const [stage, setStage] = useState(0)
  const [serverMs, setServerMs] = useState<number | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [summarising, setSummarising] = useState(false)
  const [tab, setTab] = useState<'template' | 'refs' | 'terms'>('template')
  const [sections, setSections] = useState<Section[]>([])
  const [ocr, setOcr] = useState<{ available: boolean; detail: string } | null>(null)
  const [drag, setDrag] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)

  const mr = lang === 'mr'

  useEffect(() => { verifyApi.ocrStatus().then(setOcr).catch(() => setOcr(null)) }, [])
  useEffect(() => { draftApi.template(lang).then(d => setSections(d.sections)).catch(() => { }) }, [lang])

  const run = async (f: File) => {
    setBusy(true); setError(null); setStage(0); setSummary(null)
    const t0 = Date.now()
    // The stage list is paced rather than driven by the response — see StageProgress.tsx. The
    // checks answer in ~200 ms and an instant result reads as pre-baked.
    const tick = window.setInterval(
      () => setStage(s => Math.min(s + 1, VERIFY_STAGES.length - 1)),
      Math.round(UPLOAD_MIN_MS / VERIFY_STAGES.length))
    try {
      const d = await verifyApi.upload(f, 'auto', forceOcr)
      const ms = Date.now() - t0
      await sleep(Math.max(0, UPLOAD_MIN_MS - ms))
      setServerMs(ms)
      setText(d.text)
      setExtraction(d.extraction)
      setVerification(d.verify)
      setRefs(d.references)
      setGloss(d.glossary)
      setReview(null)                 // a new document: the old narrative no longer describes it
      setLang(d.lang)                 // the document decides the language, not the officer
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setExtraction(null); setVerification(null); setRefs(null); setGloss(null)
      setReview(null); setText('')
    } finally { window.clearInterval(tick); setBusy(false) }
  }

  const runSummary = async () => {
    setSummarising(true)
    try { setSummary(await verifyApi.summary(text, lang)) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSummarising(false) }
  }

  const runReview = async () => {
    setReviewing(true)
    try { setReview(await verifyApi.review(text, lang)) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setReviewing(false) }
  }

  const pick = (f: File | null | undefined) => {
    if (!f) return
    setFile(f)
    run(f)
  }

  // Re-check after the officer corrects an OCR slip in the extracted text. Both checks re-run:
  // a corrected file number changes which orders resolve, so leaving the reference report stale
  // would show a verdict against text that is no longer on screen.
  const recheck = async () => {
    setBusy(true); setError(null)
    try {
      const [v, r, g] = await Promise.all([
        draftApi.verify(text, lang),
        verifyApi.references(text, lang),
        glossaryApi.check(text, lang),
      ])
      setVerification(v); setRefs(r); setGloss(g); setReview(null)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  /* FR-3, literally: put the cursor on the offending citation. The preview is a <textarea>, so
     "highlight" means selecting the line — there is no way to paint a background inside one. */
  const jump = (line: number) => {
    const el = textRef.current
    if (!el) return
    const lines = text.split('\n')
    const start = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0)
    el.focus()
    el.setSelectionRange(start, start + (lines[line - 1]?.length ?? 0))
    // Scrolling is left to the browser, which moves the caret into view on focus. Computing it
    // by hand would need a line height, and these lines wrap — an average would land elsewhere.
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }

  return (
    <div className="pk-page">
      <div className="pk-page-head">
        <h2>{t('nav.verify')}</h2>
        <p>{mr
          ? 'निर्गमित किंवा मसुदा शासन निर्णय अपलोड करा. मजकूर काढून तो कार्यपद्धती नियमावली, परिशिष्ट १०.६ विरुद्ध तपासला जातो; आणि त्यातील प्रत्येक संदर्भ प्रत्यक्ष आदेशाशी जोडून तो अद्याप अंमलात आहे की अधिक्रमित झाला आहे हे पाहिले जाते.'
          : 'Upload an issued or draft GR. The text is extracted and checked against the Manual of Office Procedure, Appendix 10.6 — the same rules the drafting page enforces — and every order it cites is resolved against the archive to see whether it still stands.'}</p>
      </div>

      {busy && extraction === null && <StageProgress stages={VERIFY_STAGES} at={stage} />}

      <div className="pk-draft-grid">
        <aside className="pk-panel">
          <Block title={mr ? 'दस्तऐवज अपलोड करा' : 'Upload document'}>
            <div className={`pk-drop ${drag ? 'on' : ''}`}
              onDragOver={e => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={e => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]) }}
              onClick={() => inputRef.current?.click()}>
              <input ref={inputRef} type="file" hidden
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp"
                onChange={e => pick(e.target.files?.[0])} />
              <strong>{file ? file.name : (mr ? 'फाइल निवडा किंवा ओढा' : 'Choose a file or drop it here')}</strong>
              <span>PDF · PNG · JPG · TIFF{file ? ` · ${(file.size / 1024).toFixed(0)} KB` : ''}</span>
            </div>

            <label className="pk-check">
              <input type="checkbox" checked={forceOcr}
                onChange={e => setForceOcr(e.target.checked)} />
              {mr ? 'मजकूर स्तर असला तरी OCR वापरा' : 'Force OCR even if a text layer exists'}
            </label>
            <p className="pk-fine">{mr
              ? 'सामान्यतः PDF मधील स्वतःचा मजकूर स्तर वापरला जातो — तो अचूक असतो. स्कॅन असल्यासच OCR चालते.'
              : "By default the PDF's own text layer is used — it is exact. OCR runs only for scans, where there is nothing to read."}</p>
            {ocr && !ocr.available &&
              <div className="pk-alert">{mr ? 'OCR अनुपलब्ध' : 'OCR unavailable'} — {ocr.detail}</div>}
          </Block>

          {extraction && (
            <Block title={mr ? 'मजकूर कसा मिळाला' : 'How the text was obtained'}>
              <div className={`pk-method ${extraction.method}`}>
                <b>{extraction.method === 'text_layer'
                  ? (mr ? 'PDF चा स्वतःचा मजकूर स्तर' : "The PDF's own text layer")
                  : (mr ? 'OCR (यंत्र वाचन)' : 'OCR (machine reading)')}</b>
                {extraction.method === 'ocr' &&
                  <span>{mr ? 'सरासरी विश्वास' : 'Mean confidence'}: {(extraction.confidence * 100).toFixed(0)}%</span>}
              </div>
              <dl className="pk-kv">
                <div><dt>{mr ? 'पृष्ठे' : 'Pages'}</dt><dd>{extraction.pages}</dd></div>
                <div><dt>{mr ? 'अक्षरे' : 'Characters'}</dt><dd>{extraction.chars.toLocaleString()}</dd></div>
                <div><dt>{mr ? 'देवनागरी' : 'Devanagari'}</dt>
                  <dd>{(extraction.script.devanagari_share * 100).toFixed(0)}%</dd></div>
                <div><dt>{mr ? 'भाषा' : 'Language'}</dt>
                  <dd>{extraction.script.lang === 'mr' ? 'मराठी' : 'English'}</dd></div>
              </dl>
              <p className="pk-fine">{extraction.note}</p>
            </Block>
          )}

          {extraction && (
            <Block title={mr ? 'एआय सारांश (इंग्रजी)' : 'AI summary (English)'}>
              {!summary && (
                <>
                  <button className="pk-btn sm" onClick={runSummary} disabled={summarising || !text}>
                    {summarising
                      ? (mr ? 'लिहीत आहे…' : 'The model is reading it…')
                      : (mr ? 'सारांश तयार करा' : 'Summarise this GR')}
                  </button>
                  <p className="pk-fine">{mr
                    ? 'स्थानिक प्रारूप संपूर्ण मजकूर वाचून इंग्रजीत सारांश लिहिते. सुमारे ३० सेकंद.'
                    : 'The on-premise model reads the whole document and writes an English summary. About 30 seconds — it runs on this machine, on CPU.'}</p>
                </>
              )}
              {summarising && <p className="pk-fine"><i className="pk-spin sm" /> {mr
                ? 'मजकूर वाचत आहे…' : 'Reading the document…'}</p>}
              {summary && (
                <>
                  {summary.available
                    ? <p className="pk-summary">{summary.summary}</p>
                    : <div className="pk-alert">{summary.note}</div>}
                  {summary.available && <p className="pk-fine">{summary.note}
                    {summary.stats?.seconds != null &&
                      ` · ${summary.stats.model} · ${summary.stats.seconds}s`}</p>}
                  <button className="pk-linkish" onClick={() => setSummary(null)}>
                    {mr ? 'पुन्हा लिहा' : 'write it again'}
                  </button>
                </>
              )}
            </Block>
          )}

          <Block title={mr ? 'पडताळणी' : 'Verification'}>
            <div className="pk-btnrow">
              <button className="pk-btn sm" onClick={recheck} disabled={busy || !text}>
                {busy ? (mr ? 'तपासत आहे…' : 'Checking…') : (mr ? 'पुन्हा तपासा' : 'Re-check')}
              </button>
              <div className="pk-seg">
                {(['mr', 'en'] as Lang[]).map(l => (
                  <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>
                    {l === 'mr' ? 'मराठी' : 'English'}
                  </button>
                ))}
              </div>
            </div>
            <p className="pk-fine">{mr
              ? 'काढलेल्या मजकुरात OCR चूक असल्यास ती उजवीकडे दुरुस्त करून पुन्हा तपासा. नियम मसुदा पानाशी समान आहेत. क्रमांक दुरुस्त केल्यास संदर्भही पुन्हा जुळवले जातात.'
              : 'If OCR misread something, correct it on the right and re-check — both the template rules and the citations run again, because a corrected file number changes which orders resolve. The rules are identical to the drafting page.'}</p>
          </Block>

          {refs?.available && (
            <Block title={mr ? 'संदर्भ संग्रह' : 'Reference archive'}>
              <dl className="pk-kv">
                <div><dt>{mr ? 'शासन निर्णय' : 'GRs'}</dt>
                  <dd>{refs.archive.grs.toLocaleString()}</dd></div>
                <div><dt>{mr ? 'विभाग' : 'Departments'}</dt>
                  <dd>{refs.archive.departments.length}</dd></div>
              </dl>
              <p className="pk-fine">{refs.archive.covers[0]} → {refs.archive.covers[1]}. {mr
                ? 'या कालावधीबाहेरचे किंवा अन्य विभागांचे आदेश येथे नाहीत; ते "आढळले नाही" असे न दाखवता वेगळे दर्शवले जातात.'
                : 'Orders outside this range or outside these departments are not held here. They are reported separately rather than as missing — the archive’s limits are not the draft’s defects.'}</p>
            </Block>
          )}

          {error && <div className="pk-alert">{error}</div>}
        </aside>

        <section className="pk-preview-wrap">
          <div className="pk-preview-bar">
            <span>{extraction
              ? (mr ? 'काढलेला मजकूर — संपादन करता येतो' : 'Extracted text — editable')
              : (mr ? 'अद्याप काहीही अपलोड केलेले नाही' : 'Nothing uploaded yet')}</span>
            <span className="pk-barbadges">
              {serverMs != null && <span className="pk-ms">{serverMs} ms</span>}
              {verification && (
                <span className={verification.compliant ? 'ok' : 'bad'}>
                  {verification.compliant
                    ? (mr ? '✓ नमुन्यानुसार' : '✓ Template compliant')
                    : `${verification.counts.error} ${mr ? 'नमुना त्रुटी' : 'template errors'}`}
                </span>
              )}
              {refs?.available && refs.summary.citations > 0 && (
                <button type="button" className="pk-seecites"
                  onClick={() => setTab('refs')}>
                  {mr ? 'संदर्भ पाहा' : 'See citations'} ({refs.summary.citations}) →
                </button>
              )}
            </span>
          </div>

          <div className="pk-sheet-scroll">
            <div className="pk-sheet">
              {extraction ? (
                <textarea ref={textRef} className={`pk-preview ${mr ? 'pk-mr' : ''}`} value={text}
                  onChange={e => setText(e.target.value)} spellCheck={false} />
              ) : (
                <div className="pk-empty">
                  <p>{mr
                    ? 'शासन निर्णयाची PDF किंवा स्कॅन केलेली प्रतिमा अपलोड करा.'
                    : 'Upload a Government Resolution as PDF or a scanned image.'}</p>
                  <p className="pk-fine">{busy ? (mr ? 'वाचत आहे…' : 'Reading…') : ''}</p>
                </div>
              )}
            </div>
          </div>

          {/* Two checks, two questions. A GR can be perfectly formed and still rest on an order
              that was cancelled two years ago, so neither answer substitutes for the other and
              the tabs carry their own error counts. */}
          {(verification || refs || gloss) && (
            <div className="pk-resulttabs">
              <button className={tab === 'template' ? 'on' : ''} onClick={() => setTab('template')}>
                {mr ? 'नमुना पडताळणी' : 'Template'}
                {verification && !verification.compliant &&
                  <em className="bad">{verification.counts.error}</em>}
              </button>
              <button className={tab === 'refs' ? 'on' : ''} onClick={() => setTab('refs')}>
                {mr ? 'संदर्भ तपासणी' : 'Citations'}
                {refs?.available && !refs.clean && <em className="bad">{refs.counts.error}</em>}
                {refs?.available && refs.clean && refs.summary.citations > 0 &&
                  <em className="ok">{refs.summary.citations}</em>}
              </button>
              <button className={tab === 'terms' ? 'on' : ''} onClick={() => setTab('terms')}>
                {mr ? 'परिभाषा' : 'Terminology'}
                {gloss?.available && gloss.counts.total > 0 &&
                  <em className={gloss.clean ? 'ok' : 'bad'}>{gloss.counts.total}</em>}
              </button>
            </div>
          )}

          {tab === 'template' && verification &&
            <VerifyPanel v={verification} sections={sections} lang={lang} mr={mr} />}
          {tab === 'refs' && refs &&
            <ReferencePanel report={refs} lang={lang} mr={mr} onJump={jump}
              onReview={runReview} review={review} reviewing={reviewing} />}
          {tab === 'terms' && gloss &&
            <GlossaryPanel report={gloss} lang={lang} mr={mr} onJump={jump} />}
        </section>
      </div>
    </div>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="pk-block"><h4>{title}</h4>{children}</div>
}
