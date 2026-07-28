// Typed client for the FastAPI backend. Every route reads a precomputed artefact, so calls are
// fast and the whole app works offline.

export type Node = {
  uid: string; date: string; dept: string | null; dept_code: string
  decision_no: string; subject: string
  in_degree: number; out_degree: number
  in_force?: boolean
}

export type Verification = {
  verdict: 'VERIFIED' | 'FLAGGED' | 'REJECTED' | null
  proposed_type: string | null; type: string | null
  notes: string[]; gates: Record<string, { pass: boolean; why: string }>
  gloss_en: string | null; confidence: number | null
}

export type Edge = {
  index: number; src: string; dst: string
  type: 'REFERENCES' | 'AMENDS' | 'SUPERSEDES'
  confidence: number
  evidence: string            // verbatim Marathi — never absent, never paraphrased
  evidence_en: string | null  // model gloss, a reading aid only
  cue: string | null; evidence_kind: string | null
  cross_dept: boolean | null
  cited_date: string; cited_no: string | null; how: string
  src_dept: string | null; dst_dept: string | null
  src_subject: string; dst_subject: string
  src_date: string; dst_date: string
  verification: Verification | null
}

export type Overview = {
  scale: {
    grs: number; departments: number; citations: number; edges: number
    cross_dept_edges: number; index_covers: [string, string]
    by_department: Record<string, number>
  }
  edge_types: Record<string, number>
  findings: {
    dead_references?: number; rotted?: number; born_dead?: number
    latent_cross_department?: number; distinct_citing_grs_in_force?: number
  }
  unverifiable: { total: number; by_reason: Record<string, number>; warning: string | null }
  cross_dept_flows: Record<string, number>
  ai_typing: { calls?: number; edges_upgraded?: number; verdicts?: Record<string, number> }
}

export type Finding = {
  kind: 'ROTTED' | 'BORN_DEAD'
  citing_uid: string; citing_date: string; citing_dept: string; citing_subject: string
  target_uid: string; target_date: string; target_dept: string; target_subject: string
  superseded_by: string; superseded_on: string; superseded_by_subject: string
  days_dead_when_cited: number | null; days_until_death: number | null
  cross_dept_citation: boolean | null; cross_dept_supersession: boolean
  citation_evidence: string
  supersession_evidence: string | null; supersession_evidence_en: string | null
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`)
  return r.json()
}

export const api = {
  health: () => get<any>('/health'),
  overview: () => get<Overview>('/overview'),
  metrics: () => get<any>('/metrics'),
  departments: () => get<{ departments: { name: string; grs: number }[] }>('/departments'),
  nodes: (p: Record<string, string | number>) =>
    get<{ total: number; nodes: Node[] }>(
      '/nodes?' + new URLSearchParams(p as any).toString()),
  node: (uid: string) => get<{
    node: Node; cites: Edge[]; cited_by: Edge[]
    unresolved_citations: any[]; in_force: boolean; superseded_by: Edge[]
  }>(`/node/${uid}`),
  subgraph: (uid: string, depth = 1, max = 120) =>
    get<{ center: string; depth: number; truncated: boolean; nodes: Node[]; edges: Edge[] }>(
      `/subgraph/${uid}?depth=${depth}&max_nodes=${max}`),
  audit: (kind?: string) =>
    get<{
      available: boolean; definitions: Record<string, string>
      headline: Overview['findings']; graph: any
      unverifiable: { total: number; by_reason: Record<string, number>; WARNING: string }
      total: number; findings: Finding[]
    }>('/audit' + (kind ? `?kind=${kind}` : '')),
  ledger: () => get<any>('/ledger'),
}

export const DEPT_COLOR: Record<string, string> = {
  'Finance': '#c2410c',
  'General Administration': '#1d4ed8',
  'Higher and Technical Education': '#047857',
  'School Education': '#7c3aed',
}

export const EDGE_COLOR: Record<string, string> = {
  REFERENCES: '#94a3b8',
  AMENDS: '#d97706',
  SUPERSEDES: '#dc2626',
}

export const fmt = (n: number | undefined) =>
  n === undefined ? '—' : n.toLocaleString('en-IN')
