import { Link } from 'react-router-dom'
import { FeatherFan } from '../Feather'
import { useLang, type Key } from '../i18n'

const SERVICES: { to: string; title: Key; body: Key }[] = [
  { to: '/draft', title: 'nav.draft', body: 'card.draft' },
  { to: '/verify', title: 'nav.verify', body: 'card.verify' },
  { to: '/graph', title: 'nav.graph', body: 'card.graph' },
  { to: '/recent', title: 'nav.recent', body: 'card.recent' },
]

export default function Home() {
  const { t } = useLang()
  return (
    <div className="pk-page">
      <section className="pk-wash">
        <div className="pk-hero">
          <div>
            <span className="pk-eyebrow">{t('home.eyebrow')}</span>
            <h1>{t('home.h1')}</h1>
            <p>{t('home.lede')}</p>
            <div className="pk-cta">
              <Link className="pk-btn" to="/draft">{t('home.cta1')}</Link>
              <Link className="pk-btn ghost" to="/verify">{t('home.cta2')}</Link>
            </div>
          </div>
          <div className="pk-hero-art"><FeatherFan width={200} /></div>
        </div>
      </section>

      <div className="pk-grid">
        {SERVICES.map(s => (
          <Link key={s.to} to={s.to} className="pk-card">
            <h3>{t(s.title)}</h3>
            <p>{t(s.body)}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
