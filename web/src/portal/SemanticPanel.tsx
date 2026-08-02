import { useState } from 'react'
import GRModal from './GRModal'
import type { SemanticReport, SemanticStatus } from './draftApi'

/* SRS FR-4 / FR-5 / FR-6 — potential conflicts with other departments.

   ## The one place this project shows a score instead of a verdict

   Everywhere else, a finding is computed and stated: a citation resolves or it does not, an
   order is superseded or it is not. Similarity is different — it is a continuum with no
   defensible cut-off, so a verdict would be an invention. The score is shown raw, the threshold
   is shown next to it, and the wording never hardens past "potential".

   ## Why the caveat is on the panel and not buried

   Measured on this model: a cancellation scores 0.47 against an AMENDMENT and 0.41 against a
   second cancellation. It ranks the wrong pair higher. So the index can say "another department
   has written about this" and cannot say "and it contradicts you". An officer who reads these
   hits as adjudicated conflicts would be misled by us, not by the model, so the limit is stated
   where the results are — not in a tooltip. */

const TONE: Record<string, string> = {
  'very close': 'bad', 'close': 'warn', 'related': 'mute',
}

export default function SemanticPanel({ report, status, mr, busy, onRun }: {
  report: SemanticReport | null
  status: SemanticStatus | null
  mr: boolean
  busy: boolean
  onRun: () => void
}) {
  const [open, setOpen] = useState<string | null>(null)

  if (status && !status.available) {
    return (
      <div className="pk-sem">
        <div className="pk-alert">
          {mr ? 'वाक्यांश निर्देशांक तयार केलेला नाही.'
            : 'The clause index has not been built on this machine.'}
          {status.hint && <><br /><code>{status.hint}</code></>}
        </div>
        {/* The build takes ~35 minutes. Leaving no way to re-check would strand a page that was
            opened while it was still running. */}
        <div className="pk-btnrow">
          <button className="pk-btn sm" onClick={onRun} disabled={busy}>
            {busy ? '…' : (mr ? 'पुन्हा तपासा' : 'Check again')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="pk-sem">
      <div className="pk-sem-head">
        <div>
          <b>{mr ? 'इतर विभागांतील समान तरतुदी' : 'Similar clauses in other departments'}</b>
          <span className="pk-fine">
            {status?.clauses
              ? <>{status.clauses.toLocaleString()} {mr ? 'तरतुदी अनुक्रमित' : 'clauses indexed'}
                {status.grs_sampled && <> · {status.grs_sampled.toLocaleString()} GRs</>}
                {status.model && <> · {status.model.split('/').pop()}</>}</>
              : (mr ? 'निर्देशांक तपासत आहे…' : 'checking the index…')}
          </span>
        </div>
        <button className="pk-btn sm" onClick={onRun} disabled={busy}>
          {busy
            ? (mr ? 'शोधत आहे…' : 'Embedding and searching…')
            : (mr ? 'समान तरतुदी शोधा' : 'Find similar clauses')}
        </button>
      </div>

      {busy && (
        <p className="pk-fine"><i className="pk-spin sm" /> {mr
          ? 'मसुद्यातील तरतुदी वेक्टरमध्ये रूपांतरित करून निर्देशांकात शोधत आहे…'
          : 'Converting this draft’s clauses to vectors and searching the index…'}</p>
      )}

      {report && report.available && (
        <>
          <p className="pk-fine pk-sem-scope">
            {mr
              ? `${report.clauses} तरतुदी तपासल्या · ${report.searched?.toLocaleString()} विरुद्ध · किमान गुण ${report.min_score}`
              : `${report.clauses} clause(s) from this draft searched against ${report.searched?.toLocaleString()} indexed clauses`}
            {report.own_department && <> · {mr ? 'स्वतःचा विभाग वगळला' : 'excluding'} {report.own_department}</>}
            {report.min_score != null && <> · {mr ? 'किमान' : 'threshold'} {report.min_score}</>}
          </p>

          {report.matches.length === 0 ? (
            <p className="pk-ok">{mr
              ? 'इतर विभागांत जवळची तरतूद आढळली नाही.'
              : 'No closely-related clause from another department was found above the threshold.'}</p>
          ) : (
            <ol className="pk-semlist">
              {report.matches.map((m, i) => (
                <li key={i}>
                  <p className="pk-sem-mine pk-mr">{m.clause}</p>
                  <span className="pk-fine">{mr ? 'ओळ' : 'line'} {m.line}</span>
                  <ul>
                    {m.hits.map(h => (
                      <li key={h.uid} className={TONE[h.band]}>
                        <div className="pk-sem-hit">
                          <span className={`pk-verdict ${TONE[h.band]}`}>
                            {h.score.toFixed(2)} · {h.band}
                          </span>
                          <b>{h.dept}</b>
                          <span className="pk-fine">{h.date}</span>
                          {/* FR-6: source GR link. */}
                          <button className="pk-linkish" onClick={() => setOpen(h.uid)}>
                            <code>{h.uid}</code> ↗
                          </button>
                        </div>
                        <p className="pk-mr">{h.clause}</p>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          )}

          {/* Not a tooltip. An officer reading these as adjudicated conflicts would have been
              misled by us, so the limit sits with the results. */}
          <p className="pk-fine pk-sem-caveat">{mr
            ? 'हे विरोधाभास नाहीत — हे समान विषयावरील तरतुदी आहेत. या प्रारूपावर रद्दीकरण व सुधारणा यांतील फरक विश्वासार्हपणे ओळखता येत नाही (०.४७ विरुद्ध ०.४१). अधिकाऱ्याने स्वतः वाचून ठरवावे.'
            : report.note}</p>
        </>
      )}

      {open && <GRModal uid={open} lang="mr" mr={mr} onClose={() => setOpen(null)} />}
    </div>
  )
}
