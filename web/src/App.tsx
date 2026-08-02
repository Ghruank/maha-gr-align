import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import Shell from './portal/Shell'
import Home from './portal/pages/Home'
import Placeholder from './portal/pages/Placeholder'
import DraftGR from './portal/pages/DraftGR'
import VerifyGR from './portal/pages/VerifyGR'
import CheckGraph from './portal/pages/CheckGraph'
import RecentGRs from './portal/pages/RecentGRs'
import { LangProvider } from './portal/i18n'

/* The original data dashboard is kept intact under /archive. It is loaded lazily
   so its global stylesheet never touches the portal. */
const LegacyApp = lazy(() => import('./archive/LegacyApp'))

export default function App() {
  return (
    <LangProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="draft" element={<DraftGR />} />
          <Route path="verify" element={<VerifyGR />} />
          <Route path="graph" element={<CheckGraph />} />
          <Route path="recent" element={<RecentGRs />} />
          {/* The two stub tabs are gone. Citation checking lives on Verify GR, where the
              document that raises the question is already on screen; the graph view is what
              the AI Analysis stub was reaching for and now exists for real. */}
          <Route path="*" element={<Placeholder title="nf.title" blurb="nf.body" empty="nf" />} />
        </Route>

        <Route path="/archive/*" element={
          <Suspense fallback={<div style={{ padding: 32 }}>Loading archived dashboard…</div>}>
            <LegacyApp />
          </Suspense>
        } />
      </Routes>
    </LangProvider>
  )
}
