import { useCallback, useEffect, useRef, useState } from 'react'
import { useLang } from '../i18n'
import {
  draftApi, downloadDoc, semanticApi,
  type Lang, type Question, type Section, type SemanticReport, type SemanticStatus,
  type Stats, type Verification,
} from '../draftApi'
import VerifyPanel from '../VerifyPanel'
import SemanticPanel from '../SemanticPanel'
import SuggestionDiff from '../SuggestionDiff'

/* SRS FR-13..FR-16.

   The one invariant that matters here: **the preview is the single source of truth.** Officer
   edits and AI revisions write to the same string, and every refine sends that string. If AI
   output were kept separately and merged later, a hand edit could be silently reverted — in a
   legal document that is a correctness failure, not a UX wrinkle. */

type Origin = 'template' | 'ai' | 'human'

interface Version {
  n: number
  origin: Origin
  label: string
  text: string
  at: string
  stats?: Stats
}

const COMMIT_DELAY = 1500   // ms of typing silence before a hand edit becomes a version

export default function DraftGR() {
  const { t } = useLang()

  // Draft language is independent of the portal UI language: an officer may read the portal
  // in English and still draft the operative Marathi text.
  const [lang, setLang] = useState<Lang>('mr')
  const [text, setText] = useState('')
  const [sections, setSections] = useState<Section[]>([])
  const [engine, setEngine] = useState<{ available: boolean; detail: string } | null>(null)

  const [prompt, setPrompt] = useState('')
  const [questions, setQuestions] = useState<Question[] | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [degraded, setDegraded] = useState(false)

  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verification, setVerification] = useState<Verification | null>(null)
  const [versions, setVersions] = useState<Version[]>([])
  const [lastStats, setLastStats] = useState<Stats | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  // FR-4/5/6. Behind a button: embedding the draft's clauses is ~12/second on this CPU, and a
  // draft that is still being typed would be re-embedded on every keystroke otherwise.
  const [semantic, setSemantic] = useState<SemanticReport | null>(null)
  const [semStatus, setSemStatus] = useState<SemanticStatus | null>(null)
  const [semBusy, setSemBusy] = useState(false)
  const [tab, setTab] = useState<'template' | 'semantic'>('template')

  // FR-14. The model's refinement is HELD as a proposal rather than written to the preview, so
  // the original and the suggestion exist at the same moment and can be shown side by side.
  // Accepting is what writes — see SuggestionDiff.tsx for why this does not break the
  // single-source-of-truth invariant.
  const [proposal, setProposal] = useState<
    { text: string; instruction: string; stats?: Stats; verify: Verification } | null>(null)

  // Re-read on every open, not once on mount. The index takes ~35 minutes to build, so a page
  // left open across the end of a build would otherwise keep reporting "not built" for as long
  // as the tab stayed open — and the panel hides its own button in that state, so there is no
  // way back without a reload.
  const refreshSemStatus = useCallback(
    () => { semanticApi.status().then(setSemStatus).catch(() => setSemStatus(null)) }, [])
  useEffect(refreshSemStatus, [refreshSemStatus])

  const openSemantic = () => { setTab('semantic'); refreshSemStatus() }

  const runSemantic = async () => {
    setSemBusy(true); setError(null); setTab('semantic')
    try { setSemantic(await semanticApi.check(text, lang)) }
    catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setSemBusy(false); refreshSemStatus() }
  }

  const commitTimer = useRef<number | undefined>(undefined)
  const lastCommitted = useRef('')

  const mr = lang === 'mr'

  const pushVersion = useCallback((origin: Origin, label: string, body: string, stats?: Stats) => {
    lastCommitted.current = body
    setVersions(v => [...v, {
      n: v.length + 1, origin, label, text: body, stats,
      at: new Date().toLocaleTimeString(),
    }])
  }, [])

  // Load the blank Manual-of-Office-Procedure skeleton whenever the draft language changes.
  useEffect(() => {
    let dead = false
    draftApi.template(lang).then(d => {
      if (dead) return
      setSections(d.sections)
      setText(d.text)
      lastCommitted.current = d.text
      setVersions([{
        n: 1, origin: 'template', at: new Date().toLocaleTimeString(),
        label: mr ? 'रिक्त नमुना (कार्यपद्धती नियमावली, परिशिष्ट १०.६)'
                  : 'Blank template (Manual of Office Procedure, Appendix 10.6)',
        text: d.text,
      }])
      setVerification(null)
    }).catch(e => setError(String(e)))
    return () => { dead = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang])

  useEffect(() => { draftApi.engine().then(setEngine).catch(() => setEngine(null)) }, [])

  // Hand edits become versions once typing settles, so history stays readable instead of
  // recording one entry per keystroke.
  const onEdit = (next: string) => {
    setText(next)
    window.clearTimeout(commitTimer.current)
    commitTimer.current = window.setTimeout(() => {
      if (next !== lastCommitted.current) {
        pushVersion('human', mr ? 'अधिकाऱ्याने थेट संपादन केले' : 'Officer edited the preview directly', next)
      }
    }, COMMIT_DELAY)
  }

  const flushPendingEdit = () => {
    window.clearTimeout(commitTimer.current)
    if (text !== lastCommitted.current) {
      pushVersion('human', mr ? 'अधिकाऱ्याने थेट संपादन केले' : 'Officer edited the preview directly', text)
    }
  }

  const ask = async () => {
    if (!prompt.trim()) return
    flushPendingEdit()
    setBusy('questions'); setError(null); setDegraded(false)
    try {
      const d = await draftApi.questions(prompt, lang)
      setQuestions(d.questions)
      setAnswers({})
      setDegraded(!!d.degraded || !!d.stats?.fallback)
      setLastStats(d.stats)
    } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  const generate = async () => {
    setBusy('generate'); setError(null)
    try {
      const d = await draftApi.generate(prompt, answers, lang)
      setText(d.text)
      setVerification(d.verify)
      setLastStats(d.stats)
      pushVersion('ai', mr ? 'एआयने प्रश्नावलीवरून मसुदा तयार केला'
                           : 'AI drafted from the questionnaire', d.text, d.stats)
      setQuestions(null)
    } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  // Refinement always sends the CURRENT preview, hand edits included. The response is held as
  // a proposal; only `acceptProposal` writes to the preview.
  const refine = async () => {
    if (!prompt.trim()) return
    flushPendingEdit()
    setBusy('refine'); setError(null)
    try {
      const d = await draftApi.refine(text, prompt, lang)
      setLastStats(d.stats)
      if (!d.changed || d.text.trim() === text.trim()) {
        setError(d.note || (mr ? 'मॉडेलने बदल केला नाही.' : 'The model returned no change.'))
        return
      }
      setProposal({ text: d.text, instruction: prompt, stats: d.stats, verify: d.verify })
    } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  const acceptProposal = () => {
    if (!proposal) return
    setText(proposal.text)
    setVerification(proposal.verify)
    pushVersion('ai', (mr ? 'एआय सुधारणा (स्वीकारली): ' : 'AI refinement, accepted: ')
      + proposal.instruction, proposal.text, proposal.stats)
    setProposal(null)
    setPrompt('')
  }

  const discardProposal = () => {
    if (!proposal) return
    // Recorded, because an officer REJECTING a suggestion is part of the audit trail (FR-15)
    // just as much as accepting one — and the text is unchanged, so no version is created.
    setVersions(v => [...v, {
      n: v.length + 1, origin: 'human',
      label: (mr ? 'एआय सूचना नाकारली: ' : 'AI suggestion discarded: ') + proposal.instruction,
      text, at: new Date().toLocaleTimeString(),
    }])
    setProposal(null)
  }

  const verify = async () => {
    flushPendingEdit()
    setBusy('verify'); setError(null)
    try { setVerification(await draftApi.verify(text, lang)) }
    catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  const restore = (v: Version) => {
    flushPendingEdit()
    setText(v.text)
    pushVersion('human', (mr ? 'आवृत्ती पुनर्संचयित: #' : 'Restored version #') + v.n, v.text)
  }

  const started = versions.some(v => v.origin !== 'template')

  return (
    <div className="pk-page pk-draft">
      <div className="pk-page-head">
        <h2>{t('nav.draft')}</h2>
        <p>{mr
          ? 'महाराष्ट्र शासन कार्यपद्धती नियमावली, २०२३ — परिशिष्ट १०.६ नुसार मसुदा. सर्व प्रक्रिया याच संगणकावर चालते.'
          : 'Drafted against the Maharashtra Manual of Office Procedure, 2023 — Appendix 10.6. Everything runs on this machine.'}</p>
      </div>

      <div className="pk-draft-grid">
        {/* ---------------------------------------------------------------- settings */}
        <aside className="pk-panel">
          <Block title={mr ? 'मसुद्याची भाषा' : 'Draft language'}>
            <div className="pk-seg">
              {(['mr', 'en'] as Lang[]).map(l => (
                <button key={l} className={lang === l ? 'on' : ''}
                  onClick={() => { if (l !== lang && (!started || confirm(
                    mr ? 'भाषा बदलल्यास सध्याचा मसुदा रिक्त नमुन्याने बदलला जाईल. पुढे जायचे?'
                       : 'Changing language replaces the current draft with a blank template. Continue?'
                  ))) setLang(l) }}>
                  {l === 'mr' ? 'मराठी' : 'English'}
                </button>
              ))}
            </div>
            <p className="pk-fine">{mr
              ? 'मराठी मजकूर विधिग्राह्य आहे.'
              : 'The Marathi text is the legally operative one.'}</p>
          </Block>

          <Block title={mr ? 'एआय सहाय्यक' : 'AI assistant'}
            note={engine
              ? (engine.available
                  ? `${mr ? 'स्थानिक मॉडेल' : 'Local model'}: ${engine.detail}`
                  : `${mr ? 'अनुपलब्ध' : 'Unavailable'} — ${engine.detail}`)
              : undefined}
            bad={engine ? !engine.available : false}>
            <textarea className="pk-prompt" rows={4} value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder={mr
                ? 'उदा. "अनुदानित महाविद्यालयांतील सहाय्यक प्राध्यापकांच्या ५० पदांना मान्यता देणारा शासन निर्णय तयार करा"'
                : 'e.g. "Draft a GR sanctioning 50 Assistant Professor posts in aided colleges"'} />
            <div className="pk-btnrow">
              <button className="pk-btn sm" onClick={ask}
                disabled={!!busy || !prompt.trim()}>
                {busy === 'questions'
                  ? (mr ? 'विचार करत आहे…' : 'Thinking…')
                  : (mr ? 'प्रश्न विचारा' : 'Ask AI to draft')}
              </button>
              <button className="pk-btn ghost sm" onClick={refine}
                disabled={!!busy || !prompt.trim() || !started}
                title={mr ? 'सध्याच्या पूर्वावलोकनावर लागू' : 'Applies to the current preview'}>
                {busy === 'refine'
                  ? (mr ? 'सुधारत आहे…' : 'Refining…')
                  : (mr ? 'सुधारणा करा' : 'Refine preview')}
              </button>
            </div>
            <p className="pk-fine">{mr
              ? '"सुधारणा करा" नेहमी पूर्वावलोकनातील सध्याचा मजकूर पाठवते — तुमची स्वतःची संपादने धरून.'
              : '"Refine" always sends what is currently in the preview, including your own edits.'}</p>
          </Block>

          {questions && (
            <Block title={mr ? 'एआयचे प्रश्न' : 'AI questionnaire'}
              note={degraded
                ? (mr ? 'मॉडेल अनुपलब्ध — ठराविक प्रश्नावली' : 'Model unavailable — fixed questionnaire')
                : undefined}
              bad={degraded}>
              {questions.map(q => (
                <div key={q.id} className="pk-q">
                  <label>{q.q}</label>
                  {q.type === 'choice' && q.options?.length ? (
                    <div className="pk-chips">
                      {q.options.map(o => (
                        <button key={o}
                          className={answers[q.id] === o ? 'on' : ''}
                          onClick={() => setAnswers(a => ({ ...a, [q.id]: o }))}>{o}</button>
                      ))}
                    </div>
                  ) : (
                    <input value={answers[q.id] || ''}
                      onChange={e => setAnswers(a => ({ ...a, [q.id]: e.target.value }))} />
                  )}
                </div>
              ))}
              <div className="pk-btnrow">
                <button className="pk-btn sm" onClick={generate} disabled={!!busy}>
                  {busy === 'generate'
                    ? (mr ? 'मसुदा तयार होत आहे…' : 'Drafting…')
                    : (mr ? 'उत्तरे पाठवा' : 'Submit answers')}
                </button>
                <button className="pk-btn ghost sm" onClick={() => setQuestions(null)}>
                  {mr ? 'रद्द' : 'Cancel'}
                </button>
              </div>
            </Block>
          )}

          <Block title={mr ? 'आवृत्ती इतिहास' : 'Version history'}
            note={`${versions.length} ${mr ? 'आवृत्त्या' : 'versions'}`}>
            <button className="pk-btn ghost sm" onClick={() => setShowHistory(s => !s)}>
              {showHistory ? (mr ? 'लपवा' : 'Hide') : (mr ? 'दाखवा' : 'Show')}
            </button>
            {showHistory && (
              <ol className="pk-history">
                {versions.map(v => (
                  <li key={v.n} className={`o-${v.origin}`}>
                    <span className="pk-badge">{
                      v.origin === 'ai' ? 'AI' : v.origin === 'human' ? (mr ? 'अधिकारी' : 'Officer') : (mr ? 'नमुना' : 'Template')
                    }</span>
                    <div>
                      <b>#{v.n}</b> {v.label}
                      <small>{v.at}{v.stats?.seconds ? ` · ${v.stats.seconds}s` : ''}</small>
                    </div>
                    {v.n !== versions.length &&
                      <button onClick={() => restore(v)}>{mr ? 'पुनर्संचयित' : 'Restore'}</button>}
                  </li>
                ))}
              </ol>
            )}
          </Block>

          <Block title={mr ? 'अंतिम तपासणी' : 'Final checks'}>
            <div className="pk-btnrow">
              <button className="pk-btn sm" onClick={verify} disabled={!!busy}>
                {busy === 'verify'
                  ? (mr ? 'तपासत आहे…' : 'Checking…')
                  : (mr ? 'नमुना पडताळा' : 'Verify format')}
              </button>
              {(['pdf', 'docx'] as const).map(fmt => (
                <button key={fmt} className="pk-btn ghost sm" disabled={!!busy}
                  onClick={async () => {
                    flushPendingEdit()
                    setBusy(fmt); setError(null)
                    try { await downloadDoc(text, lang, fmt) }
                    catch (e) { setError(String(e)) } finally { setBusy(null) }
                  }}>
                  {busy === fmt
                    ? (mr ? 'तयार होत आहे…' : 'Preparing…')
                    : (mr ? `${fmt.toUpperCase()} उतरवा` : `Download ${fmt.toUpperCase()}`)}
                </button>
              ))}
            </div>
            <p className="pk-fine">{mr
              ? 'पडताळणी पूर्णतः नियमाधारित आहे — यात कोणतेही एआय मॉडेल वापरले जात नाही. PDF व Word याच संगणकावर एकाच मांडणीतून तयार होतात.'
              : 'Verification is purely rule-based — no AI model is consulted (FR-12). PDF and Word are generated on this machine from one layout, so they match each other and every browser.'}</p>
          </Block>

          {error && <div className="pk-alert">{error}</div>}
          {lastStats?.seconds != null && (
            <p className="pk-fine">
              {lastStats.model} · {lastStats.seconds}s
              {lastStats.tokens_per_sec ? ` · ${lastStats.tokens_per_sec} tok/s` : ''}
              {lastStats.parsed === false ? ` · ${mr ? 'JSON वाचता आले नाही' : 'JSON unparsed'}` : ''}
            </p>
          )}
        </aside>

        {/* ---------------------------------------------------------------- preview */}
        <section className="pk-preview-wrap">
          <div className="pk-preview-bar">
            <span>{mr ? 'पूर्वावलोकन — थेट संपादन करता येते' : 'Preview — directly editable'}</span>
            {verification && (
              <span className={verification.compliant ? 'ok' : 'bad'}>
                {verification.compliant
                  ? (mr ? '✓ नमुन्यानुसार' : '✓ Template compliant')
                  : `${verification.counts.error} ${mr ? 'त्रुटी' : 'errors'}`}
              </span>
            )}
          </div>

          {proposal ? (
            <SuggestionDiff
              current={text} proposed={proposal.text} instruction={proposal.instruction}
              stats={proposal.stats} before={verification} after={proposal.verify}
              lang={lang} mr={mr} busy={busy !== null}
              onAccept={acceptProposal} onDiscard={discardProposal} />
          ) : (
          <div className="pk-sheet-scroll">
            <div className="pk-sheet">
              <textarea className={`pk-preview ${mr ? 'pk-mr' : ''}`} value={text}
                onChange={e => onEdit(e.target.value)} onBlur={flushPendingEdit}
                spellCheck={false} />
            </div>
          </div>
          )}

          {(verification || semantic || text.trim()) && (
            <div className="pk-resulttabs">
              <button className={tab === 'template' ? 'on' : ''} onClick={() => setTab('template')}>
                {mr ? 'नमुना पडताळणी' : 'Template'}
                {verification && !verification.compliant &&
                  <em className="bad">{verification.counts.error}</em>}
              </button>
              <button className={tab === 'semantic' ? 'on' : ''} onClick={openSemantic}>
                {mr ? 'आंतरविभागीय तरतुदी' : 'Other departments'}
                {semantic?.matches?.length ? <em className="bad">{semantic.matches.length}</em> : null}
              </button>
            </div>
          )}

          {tab === 'semantic' && (
            <SemanticPanel report={semantic} status={semStatus} mr={mr}
              busy={semBusy} onRun={runSemantic} />
          )}

          {tab === 'template' && verification && <VerifyPanel v={verification} sections={sections}
            lang={lang} mr={mr} />}
        </section>
      </div>

      {/* Kept as the Ctrl+P fallback. The real export is server-side XeLaTeX; a <textarea>
          cannot print its own content (the browser clips it), so the text is mirrored here. */}
      <div className={`pk-printable ${mr ? 'pk-mr' : ''}`} aria-hidden="true">{text}</div>
    </div>
  )
}

function Block({ title, note, bad, children }: {
  title: string; note?: string; bad?: boolean; children: React.ReactNode
}) {
  return (
    <div className="pk-block">
      <h4>{title}{note && <em className={bad ? 'bad' : ''}>{note}</em>}</h4>
      {children}
    </div>
  )
}
