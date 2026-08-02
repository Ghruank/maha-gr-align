import { Link } from 'react-router-dom'
import { FeatherEye } from './Feather'
import { useLang } from './i18n'

const EXTERNAL = [
  { key: 'link.maha', href: 'https://www.maharashtra.gov.in' },
  { key: 'link.grportal', href: 'https://gr.maharashtra.gov.in' },
  { key: 'link.india', href: 'https://www.india.gov.in' },
  { key: 'link.mygov', href: 'https://www.mygov.in' },
  { key: 'link.rti', href: 'https://rtionline.gov.in' },
] as const

const POLICIES = ['foot.disclaimer', 'foot.privacy', 'foot.terms', 'foot.access',
  'foot.sitemap', 'foot.help'] as const

export default function Footer() {
  const { t, lang } = useLang()
  const updated = lang === 'mr' ? '३१ जुलै २०२६' : '31 July 2026'

  return (
    <footer className="pk-footer">
      <div className="pk-footer-main">
        <div className="pk-footer-cols">
          <section className="pk-fcol pk-fcol-wide">
            <div className="pk-fbrand">
              <FeatherEye size={34} />
              <div>
                <strong>{t('brand.title')}</strong>
                <span>{t('brand.govt')}</span>
              </div>
            </div>
            <p>{t('foot.aboutBody')}</p>
            <p className="pk-fsource">{t('foot.source')}</p>
          </section>

          <section className="pk-fcol">
            <h4>{t('foot.quick')}</h4>
            <ul>
              <li><Link to="/">{t('nav.home')}</Link></li>
              <li><Link to="/draft">{t('nav.draft')}</Link></li>
              <li><Link to="/verify">{t('nav.verify')}</Link></li>
              <li><Link to="/graph">{t('nav.graph')}</Link></li>
              <li><Link to="/recent">{t('nav.recent')}</Link></li>
            </ul>
          </section>

          <section className="pk-fcol">
            <h4>{t('foot.related')}</h4>
            <ul>
              {EXTERNAL.map(l => (
                <li key={l.href}>
                  <a href={l.href} target="_blank" rel="noreferrer noopener">
                    {t(l.key)}<span className="pk-ext" aria-hidden="true"> ↗</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>

          <section className="pk-fcol">
            <h4>{t('foot.contact')}</h4>
            <address className="pk-faddr">
              <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" className="pk-pin">
                <path d="M8 1.5a4.5 4.5 0 0 0-4.5 4.5c0 3.4 4.5 8.5 4.5 8.5s4.5-5.1 4.5-8.5A4.5 4.5 0 0 0 8 1.5Z"
                  fill="none" stroke="currentColor" strokeWidth="1.3" />
                <circle cx="8" cy="6" r="1.7" fill="currentColor" />
              </svg>
              <div>
                <strong>{t('foot.addrName')}</strong>
                {t('foot.addrL1')}<br />
                {t('foot.addrL2')}
              </div>
            </address>
            <p className="pk-fmr">{t('foot.mrNote')}</p>
          </section>
        </div>
      </div>

      <div className="pk-footer-bar">
        <div className="pk-footer-bar-inner">
          <span>{t('foot.copyright')}</span>
          <nav className="pk-fpolicies">
            {POLICIES.map(k => <span key={k}>{t(k)}</span>)}
          </nav>
          <span>{t('foot.updated')}: {updated}</span>
        </div>
      </div>

      <div className="pk-footer-proto">{t('foot.proto')}</div>
    </footer>
  )
}
