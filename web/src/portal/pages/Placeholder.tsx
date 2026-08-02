import { FeatherEye } from '../Feather'
import { useLang, type Key } from '../i18n'

/** Blank page frame — the four working tabs are built out one at a time. */
export default function Placeholder({ title, blurb, empty = 'ph' }:
  { title: Key; blurb: Key; empty?: 'ph' | 'nf' }) {
  const { t } = useLang()
  return (
    <div className="pk-page">
      <div className="pk-page-head">
        <h2>{t(title)}</h2>
        <p>{t(blurb)}</p>
      </div>
      <div className="pk-wash">
        <div className="pk-placeholder">
          <FeatherEye size={46} />
          <h3>{t(`${empty}.title` as Key)}</h3>
          <p>{t(`${empty}.body` as Key)}</p>
        </div>
      </div>
    </div>
  )
}
