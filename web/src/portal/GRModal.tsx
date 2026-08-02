import { useEffect, useState } from 'react'
import { verifyApi, type GRSource, type Lang } from './draftApi'

/* The cited order itself, behind a click on a citation.

   Two things are on offer and they are not the same thing:

   - **The corpus text**, which works offline and is instant. It is OCR output, and the crawl
     drops the signature block because that block is an image — so it is the right thing to
     read, and the wrong thing to treat as the document of record.
   - **The official PDF on gr.maharashtra.gov.in**, which IS the document of record and needs
     the network. `GRs.json` records the URL for every crawled GR.

   Both are labelled for what they are. Offering only the text would understate what we can
   prove; offering only the link would break the offline demo. */

export default function GRModal({ uid, lang, mr, onClose }: {
  uid: string
  lang: Lang
  mr: boolean
  onClose: () => void
}) {
  const [d, setD] = useState<GRSource | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [side, setSide] = useState<Lang>(lang)

  useEffect(() => {
    setD(null); setErr(null)
    verifyApi.gr(uid, side).then(setD).catch(e => setErr(String(e.message || e)))
  }, [uid, side])

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', esc); document.body.style.overflow = '' }
  }, [onClose])

  const st = d?.status

  return (
    <div className="pk-modal-back" onClick={onClose} role="presentation">
      <div className="pk-modal" onClick={e => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={uid}>
        <header>
          <div>
            <b>{mr ? 'संदर्भित शासन निर्णय' : 'The cited Government Resolution'}</b>
            <code>{uid}</code>
          </div>
          <button className="pk-modal-x" onClick={onClose}
            aria-label={mr ? 'बंद करा' : 'Close'}>×</button>
        </header>

        {err && <div className="pk-alert">{err}</div>}
        {!d && !err && <p className="pk-fine pk-modal-load">{mr ? 'उघडत आहे…' : 'Opening…'}</p>}

        {d && (
          <>
            <div className="pk-modal-meta">
              <dl className="pk-kv">
                <div><dt>{mr ? 'विभाग' : 'Department'}</dt><dd>{d.node.dept}</dd></div>
                <div><dt>{mr ? 'दिनांक' : 'Date'}</dt><dd>{d.node.date}</dd></div>
                <div><dt>{mr ? 'क्रमांक' : 'Number'}</dt>
                  <dd className="pk-mr">{d.node.decision_no || '—'}</dd></div>
                <div><dt>{mr ? 'याचा संदर्भ देणारे' : 'Cited by'}</dt>
                  <dd>{d.cited_by_count}</dd></div>
              </dl>
              {d.node.subject && <p className="pk-modal-subject">{d.node.subject}</p>}

              <div className="pk-modal-status">
                <span className={`pk-verdict ${st?.in_force ? 'ok' : 'bad'}`}>
                  {st?.in_force ? (mr ? 'अंमलात' : 'In force') : (mr ? 'अधिक्रमित' : 'Superseded')}
                </span>
                {st?.superseded_by.map(k => (
                  <span key={k.uid} className="pk-fine">
                    {mr ? 'अधिक्रमित —' : 'superseded by'} <code>{k.uid}</code> ({k.date}, {k.dept})
                  </span>
                ))}
                {st?.in_force && st.amended_by.map(k => (
                  <span key={k.uid} className="pk-fine">
                    {mr ? 'सुधारित —' : 'amended by'} <code>{k.uid}</code> ({k.date})
                  </span>
                ))}
              </div>
            </div>

            <div className="pk-modal-bar">
              <div className="pk-seg">
                {(['mr', 'en'] as Lang[]).map(l => (
                  <button key={l} className={side === l ? 'on' : ''} onClick={() => setSide(l)}>
                    {l === 'mr' ? 'मराठी' : 'English'}
                  </button>
                ))}
              </div>
              {d.portal.url && (
                <a className="pk-btn sm" href={d.portal.url} target="_blank" rel="noreferrer">
                  {mr ? 'शासनाच्या संकेतस्थळावरील मूळ PDF ↗' : 'Original PDF on gr.maharashtra.gov.in ↗'}
                </a>
              )}
            </div>

            {/* The distinction the officer needs: what they are reading is OCR of the scan, not
                the signed instrument. The link above is the signed instrument. */}
            <p className="pk-fine pk-modal-prov">
              {side === 'mr'
                ? (mr ? 'खाली संग्रहातील मराठी मजकूर — हाच विधिग्राह्य मजकूर आहे. हा स्कॅनचे OCR आहे; स्वाक्षरीचा भाग प्रतिमा असल्याने त्यात नाही.'
                  : 'Below is the corpus Marathi text — the legally operative text. It is OCR of the scan; the signature block is an image and so is absent.')
                : (mr ? 'खालील इंग्रजी मजकूर यंत्र-अनुवाद (IndicTrans2) आहे — तो निष्कर्षाचा आधार नाही.'
                  : 'The English below is machine translation (IndicTrans2), never the basis of a conclusion.')}
              {d.portal.size_kb && <> · {mr ? 'मूळ PDF' : 'original PDF'} {d.portal.size_kb} KB</>}
            </p>

            <div className="pk-modal-body">
              {d.text_available
                ? <pre className={side === 'mr' ? 'pk-mr' : ''}>{d.text}</pre>
                : <p className="pk-fine">{mr
                  ? 'या संगणकावर संग्रहातील मजकूर उपलब्ध नाही. वरील दुव्यावरून मूळ PDF पाहा.'
                  : 'The corpus text is not present on this machine. Use the link above for the original PDF.'}</p>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
