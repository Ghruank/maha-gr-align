import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useLang } from '../i18n'
import { graphApi, type GraphNode, type NodeView } from '../draftApi'
import GraphView from '../GraphView'
import GRModal from '../GRModal'

/* Check Graph — the thesis made clickable.

   A Government Resolution is a node in a legal dependency graph, and until now nothing in the
   portal let an officer stand on one node and look around. Everything here reads artefacts the
   API already serves: `/api/node/{uid}` for the neighbourhood, `/api/nodes?q=` for lookup. No
   new computation, and nothing is generated — every edge on screen came from a Marathi citation
   that resolved to a real uid.

   The search box accepts a uid, a departmental file number, or words from the subject, because
   an officer holding a paper GR has the file number in front of them and not the eighteen-digit
   portal id. Anything that is not an exact uid goes to search and offers matches. */

export default function CheckGraph() {
  const { t } = useLang()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('uid') || '')
  const [view, setView] = useState<NodeView | null>(null)
  const [hits, setHits] = useState<GraphNode[] | null>(null)
  const [top, setTop] = useState<GraphNode[]>([])
  const [scale, setScale] = useState<{ grs: number; edges: number; cross: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const mr = false   // graph labels stay in the interface language of the rest of the portal

  useEffect(() => {
    graphApi.top(6).then(d => setTop(d.nodes)).catch(() => { })
    graphApi.overview().then(d => setScale({
      grs: d.scale.grs, edges: d.scale.edges, cross: d.scale.cross_dept_edges,
    })).catch(() => { })
  }, [])

  const load = async (uid: string) => {
    setBusy(true); setError(null); setHits(null)
    try {
      setView(await graphApi.node(uid))
      setParams({ uid }, { replace: true })
    } catch (e) {
      setView(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally { setBusy(false) }
  }

  // Deep link / back button: whatever is in the URL is what is on screen.
  useEffect(() => {
    const uid = params.get('uid')
    if (uid && uid !== view?.node.uid) load(uid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.get('uid')])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const term = q.trim()
    if (!term) return
    if (/^\d{18}$/.test(term)) { load(term); return }
    setBusy(true); setError(null); setView(null)
    try {
      const d = await graphApi.search(term, 12)
      setHits(d.nodes)
      if (d.nodes.length === 1) load(d.nodes[0].uid)
      else if (d.nodes.length === 0) setError(
        `Nothing in the index matches “${term}”. Try the 18-digit GR number, a departmental file number, or a word from the subject.`)
    } catch (err) {
      setError(String(err))
    } finally { setBusy(false) }
  }

  return (
    <div className="pk-page">
      <div className="pk-page-head">
        <h2>{t('nav.graph')}</h2>
        <p>Every Government Resolution stands on earlier orders and is stood on by later ones.
          Look one up to see both sides — and which of those orders still hold.</p>
      </div>

      <div className="pk-draft-grid">
        <aside className="pk-panel">
          <div className="pk-block">
            <h4>Find a Government Resolution</h4>
            <form onSubmit={submit}>
              <input className="pk-prompt" value={q} onChange={e => setQ(e.target.value)}
                placeholder="GR number, file number, or a word from the subject"
                aria-label="GR number" />
              <div className="pk-btnrow">
                <button className="pk-btn sm" type="submit" disabled={busy || !q.trim()}>
                  {busy ? 'Looking up…' : 'Show the graph'}
                </button>
                {view && (
                  <button className="pk-btn sm ghost" type="button"
                    onClick={() => { setView(null); setQ(''); setHits(null); setParams({}) }}>
                    Clear
                  </button>
                )}
              </div>
              <p className="pk-fine">Press Enter. An 18-digit number opens directly; anything
                else is searched across file numbers and subjects.</p>
            </form>
            {error && <div className="pk-alert">{error}</div>}
          </div>

          {hits && hits.length > 1 && (
            <div className="pk-block">
              <h4>{hits.length} matches</h4>
              <ul className="pk-hits">
                {hits.map(n => (
                  <li key={n.uid}>
                    <button onClick={() => load(n.uid)}>
                      <code>{n.uid}</code>
                      <span>{n.date} · {n.dept}</span>
                      <em>{n.subject}</em>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!view && top.length > 0 && (
            <div className="pk-block">
              <h4>The load-bearing orders</h4>
              <p className="pk-fine">Most depended-on in the index — a good place to start.</p>
              <ul className="pk-hits">
                {top.map(n => (
                  <li key={n.uid}>
                    <button onClick={() => load(n.uid)}>
                      <code>{n.uid}</code>
                      <span>{n.in_degree} cite this · {n.dept}</span>
                      <em>{n.subject}</em>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {view && (
            <div className="pk-block">
              <h4>This resolution</h4>
              <dl className="pk-kv">
                <div><dt>Department</dt><dd>{view.node.dept}</dd></div>
                <div><dt>Date</dt><dd>{view.node.date}</dd></div>
                <div><dt>Cites</dt><dd>{view.cites.length}</dd></div>
                <div><dt>Cited by</dt><dd>{view.cited_by.length}</dd></div>
              </dl>
              <p className="pk-fine pk-gv-no">{view.node.decision_no}</p>
              <p className="pk-fine">{view.node.subject}</p>
              <div className="pk-btnrow">
                <button className="pk-btn sm" onClick={() => setOpen(view.node.uid)}>
                  Read this GR
                </button>
              </div>
              {/* Unresolved citations belong on this page: a GR that cites five orders we could
                  not verify must not look like a GR that cites nothing. */}
              {view.unresolved_citations.length > 0 && (
                <>
                  <h4 className="pk-gv-h">Cited, but not resolved · {view.unresolved_citations.length}</h4>
                  <p className="pk-fine">These are drawn nowhere on the graph. Most are orders
                    outside the four indexed departments or outside the crawl window — not
                    evidence that the citation is wrong.</p>
                  <ul className="pk-unres">
                    {view.unresolved_citations.slice(0, 6).map((u, i) => (
                      <li key={i}>
                        <span>{u.cited_date}</span>
                        <code>{u.why}</code>
                        <em className="pk-mr">{u.cited_no || '—'}</em>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}

          {scale && (
            <div className="pk-block">
              <h4>The index</h4>
              <dl className="pk-kv">
                <div><dt>GRs</dt><dd>{scale.grs.toLocaleString()}</dd></div>
                <div><dt>Links</dt><dd>{scale.edges.toLocaleString()}</dd></div>
                <div><dt>Cross-department</dt><dd>{scale.cross.toLocaleString()}</dd></div>
              </dl>
              <div className="pk-gv-legend">
                <span><i style={{ background: '#8fa3b8' }} />references</span>
                <span><i style={{ background: '#c9a227' }} />amends</span>
                <span><i style={{ background: '#b3261e' }} />supersedes</span>
              </div>
              <p className="pk-fine">Only citations we could resolve to a real GR are drawn.
                Every link carries the sentence that produced it.</p>
            </div>
          )}
        </aside>

        <section className="pk-preview-wrap">
          <div className="pk-preview-bar">
            <span>{view
              ? `Dependency graph · ${view.node.uid}`
              : 'No Government Resolution selected'}</span>
            {view && (
              <span className={view.in_force ? 'ok' : 'bad'}>
                {view.in_force ? '✓ in force' : 'superseded'}
              </span>
            )}
          </div>

          {view ? (
            <GraphView view={view} mr={mr} onOpen={setOpen} onFocus={load} />
          ) : (
            <div className="pk-empty">
              <p>Enter a Government Resolution number on the left.</p>
              <p className="pk-fine">{busy ? 'Looking up…' : 'Or pick one of the load-bearing orders.'}</p>
            </div>
          )}
        </section>
      </div>

      {open && <GRModal uid={open} lang="mr" mr={false} onClose={() => setOpen(null)} />}
    </div>
  )
}
