import { NavLink, Outlet } from 'react-router-dom'
import { FeatherEye } from './Feather'
import Footer from './Footer'
import { useLang, type Key, type Lang } from './i18n'

const TABS: { to: string; key: Key; end?: boolean }[] = [
  { to: '/', key: 'nav.home', end: true },
  { to: '/draft', key: 'nav.draft' },
  { to: '/verify', key: 'nav.verify' },
  { to: '/graph', key: 'nav.graph' },
  { to: '/recent', key: 'nav.recent' },
]

function LangToggle() {
  const { lang, setLang, t } = useLang()
  return (
    <div className="pk-lang" role="group" aria-label={t('lang.label')}>
      {(['en', 'mr'] as Lang[]).map(l => (
        <button key={l} type="button" onClick={() => setLang(l)}
          className={lang === l ? 'on' : ''} aria-pressed={lang === l}
          lang={l === 'mr' ? 'mr' : 'en'}>
          {l === 'mr' ? 'मराठी' : 'English'}
        </button>
      ))}
    </div>
  )
}

export default function Shell() {
  const { t } = useLang()
  return (
    <div className="portal">
      <header className="pk-masthead">
        <div className="pk-masthead-inner">
          <div className="pk-emblem"><FeatherEye size={40} /></div>
          <div className="pk-titles">
            <h1 className="pk-title">{t('brand.title')}</h1>
            <p className="pk-title-mr">{t('brand.sub')}</p>
          </div>
          <div className="pk-masthead-right">
            <LangToggle />
            <div className="pk-masthead-meta">
              <strong>{t('brand.govt')}</strong>
              {t('brand.addr')}
            </div>
          </div>
        </div>
      </header>

      <nav className="pk-nav">
        <div className="pk-nav-inner">
          {TABS.map(tab => (
            <NavLink key={tab.to} to={tab.to} end={tab.end}
              className={({ isActive }) => isActive ? 'on' : ''}>
              {t(tab.key)}
            </NavLink>
          ))}
        </div>
      </nav>

      <main className="pk-body"><Outlet /></main>

      <Footer />
    </div>
  )
}
