import type { Finding, Lang, Section, Verification } from './draftApi'

/* Shared by Draft GR and Verify GR. One component, because the same rule engine backs both —
   a GR must not pass on one page and fail on the other. */

export default function VerifyPanel({ v, sections, lang, mr }: {
  v: Verification; sections: Section[]; lang: Lang; mr: boolean
}) {
  const order: Record<Finding['severity'], number> = { error: 0, warning: 1, advisory: 2 }
  const findings = [...v.findings].sort((a, b) => order[a.severity] - order[b.severity])
  return (
    <div className="pk-verify">
      <div className="pk-verify-head">
        <b>{mr ? 'नमुना पडताळणी' : 'Template verification'}</b>
        <span className="pk-fine">
          {mr ? 'प्रकार' : 'Type'}: {v.doc_type} · {v.manual_appendix}
          {v.financial_sanction_detected && ` · ${mr ? 'खर्चास मान्यता आढळली' : 'financial sanction detected'}`}
        </span>
      </div>

      <div className="pk-chips pk-secchips">
        {sections.map(s => (
          <span key={s.id}
            className={v.sections_present[s.id] ? 'ok' : (s.required ? 'bad' : 'off')}
            title={s.hint?.[lang] || s.mop || ''}>
            {v.sections_present[s.id] ? '✓' : '·'} {s.label[lang] || s.label.en}
          </span>
        ))}
      </div>

      {findings.length === 0
        ? <p className="pk-ok">{mr
            ? 'कोणतीही त्रुटी आढळली नाही.' : 'No template defects found.'}</p>
        : <ul className="pk-findings">
            {findings.map((f, i) => (
              <li key={i} className={f.severity}>
                <code>{f.code}</code>
                <div>
                  {f.message}
                  <small>{f.authority}</small>
                </div>
              </li>
            ))}
          </ul>}
    </div>
  )
}
