/* Drafting endpoints. Everything here is served by the local FastAPI process, which in turn
   talks only to Ollama on localhost — no request leaves the machine (SRS NFR-2). */

export type Lang = 'mr' | 'en'

export interface Question {
  id: string
  q: string
  type: 'text' | 'choice'
  options?: string[]
}

export interface Finding {
  code: string
  section: string
  label: string
  severity: 'error' | 'warning' | 'advisory'
  message: string
  line: number | null
  authority: string
}

export interface Verification {
  lang: string
  doc_type: string
  manual_appendix: string
  financial_sanction_detected: boolean
  sections_present: Record<string, boolean>
  findings: Finding[]
  counts: { error: number; warning: number; advisory: number }
  compliant: boolean
}

export interface Stats {
  model?: string
  seconds?: number
  eval_tokens?: number
  tokens_per_sec?: number
  local?: boolean
  parsed?: boolean
  fallback?: boolean
}

export interface Section {
  id: string
  code: string
  required: boolean
  corpus_rate: number
  label: Record<string, string>
  mop?: string
  hint?: Record<string, string>
  conditional_on?: string
}

/* ---- Reference checking: SRS FR-1 / FR-2 / FR-3 ---- */

/** A GR in the archive. `evidence` is present only on an edge — the verbatim sentence that
    made us believe one order supersedes or amends another. */
export interface ArchiveGR {
  uid: string
  date: string | null
  dept: string | null
  decision_no: string | null
  subject: string | null
  in_degree: number
  evidence?: string | null
  evidence_en?: string | null
  confidence?: number | null
}

export interface CitationStatus {
  in_force: boolean
  superseded_by: ArchiveGR[]
  amended_by: ArchiveGR[]
  cited_by_count: number
}

/** The five ways of not finding something are kept apart on purpose: only `not_in_archive`
    is a defect in the document. See the module docstring in references.py. */
export type Verdict =
  | 'verified' | 'ambiguous' | 'not_in_archive'
  | 'unverifiable' | 'other_dept' | 'outside_range' | 'out_of_scope'

export interface Citation {
  n: number
  raw: string
  cited_no: string | null
  cited_date: string
  cited_dept: string | null
  kind: string
  kind_label: Record<string, string>
  zone: 'preamble' | 'body'
  line: number
  cue: boolean
  also_at_lines: number[]
  number_inherited: boolean
  verdict: Verdict
  verdict_label: Record<string, string>
  why: string
  side: Lang
  match: ArchiveGR | null
  status: CitationStatus | null
  candidates: ArchiveGR[]
  confidence?: number
  cross_dept?: boolean
  date_drift_days?: number
}

export interface Blast {
  live: number
  total: number
  departments: Record<string, number>
  sample: ArchiveGR[]
}

export interface RefFinding {
  code: string
  severity: 'error' | 'warning' | 'advisory'
  message: string
  citation: number | null
  authority: string
  evidence?: string | null
  related?: string
  kind?: 'BORN_DEAD' | 'ROTTED'
  blast?: Blast
}

/** Computed from the graph, never from a model — a 2B model measurably gets this wrong. */
export interface Alignment {
  verdict: 'aligned' | 'misaligned' | 'partial' | 'unverified'
  label: Record<string, string>
  reasons: string[]
  counts: { verified: number; superseded: number; amended: number; missing: number; unchecked: number }
  basis: string
}

export interface ReferenceReport {
  available: boolean
  hint?: string
  alignment: Alignment
  document: {
    department: string | null
    decision_no: string | null
    date: string
    date_source: string
    side_parsed: Lang
    lang: string
  }
  archive: { grs: number; departments: string[]; covers: [string, string] }
  summary: {
    citations: number
    verified: number
    not_in_archive: number
    unverifiable: number
    out_of_scope: number
    superseded: number
    amended: number
    cross_department: number
    by_verdict: Record<string, number>
    by_kind: Record<string, number>
  }
  counts: { error: number; warning: number; advisory: number }
  clean: boolean
  citations: Citation[]
  findings: RefFinding[]
  definitions: Record<string, string>
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

/* ---- Semantic conflict detection: SRS FR-4 / FR-5 / FR-6 ---- */

export interface SemanticHit {
  score: number
  /** Wording only. There is no evidence for a cut-off separating conflict from coincidence. */
  band: 'very close' | 'close' | 'related'
  uid: string
  dept: string
  date: string
  clause: string
  line: number | null
}

export interface SemanticMatch {
  clause: string
  line: number
  hits: SemanticHit[]
  top_score: number
}

export interface SemanticReport {
  available: boolean
  hint?: string
  clauses: number
  searched?: number
  own_department?: string | null
  min_score?: number
  model?: string
  matches: SemanticMatch[]
  note?: string
}

export interface SemanticStatus {
  available: boolean
  hint?: string
  clauses?: number
  departments?: Record<string, number>
  model?: string
  grs_sampled?: number
  built_at?: string
  model_loaded?: boolean
  model_detail?: string
  default_min_score?: number
}

export const semanticApi = {
  status: (): Promise<SemanticStatus> => fetch('/api/semantic/status').then(r => r.json()),

  check: (text: string, lang: Lang, minScore?: number): Promise<SemanticReport> =>
    post('/api/semantic/check', { text, lang, min_score: minScore }),
}

export const draftApi = {
  engine: (): Promise<{ available: boolean; detail: string }> =>
    fetch('/api/draft/engine').then(r => r.json()),

  template: (lang: Lang): Promise<{ text: string; sections: Section[]; source: unknown }> =>
    fetch(`/api/draft/template?lang=${lang}`).then(r => r.json()),

  questions: (prompt: string, lang: Lang): Promise<{
    questions: Question[]; stats: Stats; degraded?: boolean
  }> => post('/api/draft/questions', { prompt, lang }),

  generate: (prompt: string, answers: Record<string, string>, lang: Lang): Promise<{
    fields: Record<string, string>; text: string; stats: Stats; verify: Verification
  }> => post('/api/draft/generate', { prompt, answers, lang }),

  refine: (text: string, instruction: string, lang: Lang): Promise<{
    text: string; changed: boolean; stats: Stats; verify: Verification; note?: string
  }> => post('/api/draft/refine', { text, instruction, lang }),

  verify: (text: string, lang: Lang): Promise<Verification> =>
    post('/api/draft/verify', { text, lang }),
}

/* ---- Verify GR: upload + OCR ---- */

export interface Extraction {
  method: 'text_layer' | 'ocr'
  confidence: number
  pages: number
  chars: number
  note: string
  script: { devanagari: number; latin: number; lang: Lang; devanagari_share: number }
}

export interface ArchiveStatus {
  available: boolean
  grs?: number
  departments?: string[]
  covers?: [string, string]
  supersedes_edges?: number
  amends_edges?: number
  /** Optional capabilities. Citation checking needs neither; the popup needs the corpus on
      disk and the narrative review needs ollama, so each is offered or greyed separately. */
  corpus?: { available: boolean; detail: string }
  model?: { available: boolean; detail: string }
  hint?: string
}

/** One archived GR, for the popup behind a citation. */
export interface GRSource {
  uid: string
  node: { uid: string; date: string; dept: string; decision_no: string; subject: string; in_degree: number }
  portal: { url?: string; pages?: number; size_kb?: string; order_type?: string; dept_full?: string }
  status: CitationStatus
  lang: Lang
  text: string | null
  /** False means this box does not carry the corpus — NOT that the GR is empty. */
  text_available: boolean
  cited_by_count: number
}

export interface ReviewResult {
  review: string
  /** The summary computed with no model at all. Always true, always shown. */
  computed?: string
  degraded: boolean
  local: boolean
  dropped: number
  note: string
  stats: Stats
  report: ReferenceReport
}

export interface Summary {
  available: boolean
  summary: string | null
  degraded: boolean
  local: boolean
  dropped: number
  truncated: boolean
  note: string
  stats: Stats
}

export const verifyApi = {
  /** A real generative call to the on-premise model — the only one in the project that produces
      content rather than explaining a computed finding. ~30 s, hence its own button. */
  summary: (text: string, lang: Lang): Promise<Summary> => post('/api/summary', { text, lang }),

  ocrStatus: (): Promise<{ available: boolean; detail: string }> =>
    fetch('/api/verify/ocr/status').then(r => r.json()),

  exportStatus: (): Promise<{ available: boolean; detail: string }> =>
    fetch('/api/draft/export/status').then(r => r.json()),

  archiveStatus: (): Promise<ArchiveStatus> =>
    fetch('/api/references/status').then(r => r.json()),

  /** FR-1/2/3. Deterministic and offline — no model is consulted on this path. */
  references: (text: string, lang: Lang): Promise<ReferenceReport> =>
    post('/api/references/check', { text, lang }),

  /** The narrative note. Slow (~20-30 s on the on-premise 2B model), hence its own button. */
  review: (text: string, lang: Lang): Promise<ReviewResult> =>
    post('/api/references/review', { text, lang }),

  gr: (uid: string, lang: Lang = 'mr'): Promise<GRSource> =>
    fetch(`/api/gr/${uid}?lang=${lang}`).then(r => {
      if (!r.ok) throw new Error(`GR ${uid} is not in the index`)
      return r.json()
    }),

  upload: async (file: File, lang: Lang | 'auto', forceOcr: boolean): Promise<{
    extraction: Extraction; text: string; lang: Lang
    verify: Verification; references: ReferenceReport; glossary: GlossaryReport
    filename: string
  }> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('lang', lang)
    fd.append('force_ocr', String(forceOcr))
    const r = await fetch('/api/verify/upload', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
    return r.json()
  },
}

/* ---- Check Graph: the dependency neighbourhood around one GR ---- */

export interface GraphNode {
  uid: string
  date: string
  dept: string
  dept_code: string
  decision_no: string
  subject: string
  in_degree: number
  out_degree: number
}

/** One typed edge. `evidence` is the verbatim sentence that produced it — if we cannot show
    it, the edge does not ship (CLAUDE.md). */
export interface GraphEdge {
  index: number
  src: string
  dst: string
  type: 'REFERENCES' | 'AMENDS' | 'SUPERSEDES'
  confidence: number
  evidence: string
  evidence_en: string | null
  cue: string | null
  cross_dept: boolean | null
  cited_date: string | null
  cited_no: string | null
  how: string | null
  src_dept: string | null
  dst_dept: string | null
  src_subject: string | null
  dst_subject: string | null
  src_date: string | null
  dst_date: string | null
  /** Whether each end still stands. Without these, showing a neighbourhood would need one
      fetch per neighbour to discover that the order in front of you was cancelled. */
  src_in_force: boolean
  dst_in_force: boolean
  verification: { verdict?: string; gloss_en?: string; confidence?: number } | null
}

export interface NodeView {
  node: GraphNode
  /** Out-edges: the orders this GR stands on. */
  cites: GraphEdge[]
  /** In-edges: the orders that stand on this one. */
  cited_by: GraphEdge[]
  /** Citations we could NOT resolve. Shown, because hiding them makes a GR look complete. */
  unresolved_citations: { cited_date: string; cited_no: string | null; why: string; evidence: string }[]
  in_force: boolean
  superseded_by: GraphEdge[]
}

/* ---- Controlled bilingual terminology: SRS FR-7 / FR-8 / FR-9 ---- */

export interface GlossaryTerm {
  id: string
  mr: string
  en: string
  variants_en: string[]
  variants_mr: string[]
  authority: string
  /** Only approved entries are enforced. The rest are proposals awaiting a human decision. */
  approved: boolean
  /** False when a replacement cannot be justified from one side of the document alone —
      `रद्द` (cancelled) and `अधिक्रमित` (superseded) do different things to an order. */
  strict: boolean
  note: string
  evidence: {
    documents_sampled: number
    approved_used_in: number
    variants_used_in: Record<string, number>
    marathi_term_in: number
  }
}

export interface GlossaryFinding {
  code: 'G01' | 'G02' | 'G03'
  term_id: string
  mr: string
  found: string
  occurrences: number
  line: number | null
  approved: string
  /** FR-9. Null where the checker declines to guess. */
  suggestion: string | null
  severity: 'warning' | 'advisory'
  authority: string
  note: string
  also_uses_approved: boolean
  message: string
}

export interface GlossaryReport {
  available: boolean
  hint?: string
  lang: string
  script: 'mr' | 'en'
  glossary: { terms: number; approved: number; source: Record<string, string> }
  terms_present: {
    id: string; mr: string; en: string; approved: boolean; authority: string
    in_marathi: boolean; in_english: boolean
  }[]
  findings: GlossaryFinding[]
  counts: { warning: number; advisory: number; total: number }
  clean: boolean
}

export const glossaryApi = {
  list: (): Promise<{ available: boolean; detail: string; terms: GlossaryTerm[] }> =>
    fetch('/api/glossary').then(r => r.json()),

  check: (text: string, lang: Lang): Promise<GlossaryReport> =>
    post('/api/glossary/check', { text, lang }),
}

/* ---- Recent GRs: both checks over a run of real documents ---- */

/** A monetary figure a draft attributes to an order it cites, which that order contradicts. */
export interface Conflict {
  code: 'X01'
  kind: 'amount_mismatch'
  severity: 'error'
  citation: number
  line: number
  sentence: string
  claimed: { raw: string; value: number; display: string }
  actual: { raw: string; value: number; display: string }
  all_actual: { value: number; display: string }[]
  delta: number
  delta_display: string
  target: ArchiveGR
  cross_dept: boolean
  message: string
  authority: string
}

export interface ConflictExplanation {
  explanation: string
  /** The computed finding, always true, always available even when the model is down. */
  computed: string
  degraded: boolean
  local: boolean
  dropped: number
  note: string
  stats: Stats
}

export interface ScreenRow {
  uid: string
  date: string
  dept: string
  decision_no: string
  subject: string
  portal: string | null
  in_force: boolean
  template: {
    doc_type: string
    appendix: string
    compliant: boolean
    errors: number
    present: number
    total: number
    missing: string[]
    /** Sections not counted against this document — OCR cannot see them, or the Manual gives
        this document type its own form. */
    relaxed: string[]
  }
  references: {
    verdict: Alignment['verdict']
    label: Record<string, string>
    reasons: string[]
    citations: number
    verified: number
    superseded: number
    amended: number
    missing: number
    cross_department: number
    errors: number
  }
  glossary?: { total: number; warning: number; clean: boolean }
  /** Contradictions with the orders this GR cites. Empty for everything in the archive today. */
  conflicts?: Conflict[]
  /** True for a GR uploaded to the in-tray rather than crawled from the portal. */
  staged?: boolean
  node?: GraphNode
  filename?: string
  uploaded_at?: string
}

export interface ScreenPage {
  available: boolean
  rows: ScreenRow[]
  scanned?: number
  index_total?: number
  departments?: string[]
  note?: string
  hint?: string
}

export const screenApi = {
  recent: (limit = 15, dept?: string): Promise<ScreenPage> =>
    fetch(`/api/corpus/recent?limit=${limit}${dept ? `&dept=${encodeURIComponent(dept)}` : ''}`)
      .then(r => r.json()),

  /** The in-tray: GRs uploaded but not yet in the corpus. Re-screened on every read, so an
      earlier upload is checked against everything staged since. */
  staged: (): Promise<{ available: boolean; rows: ScreenRow[]; count: number }> =>
    fetch('/api/staging').then(r => r.json()),

  upload: async (file: File, forceOcr = false): Promise<ScreenRow> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('lang', 'auto')
    fd.append('force_ocr', String(forceOcr))
    const r = await fetch('/api/staging/upload', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
    return r.json()
  },

  drop: (uid: string): Promise<unknown> =>
    fetch(`/api/staging/${uid}`, { method: 'DELETE' }).then(r => r.json()),

  explain: (conflict: Conflict, citing: unknown, lang: Lang): Promise<ConflictExplanation> =>
    post('/api/conflict/explain', { conflict, citing, lang }),
}

export const graphApi = {
  node: (uid: string): Promise<NodeView> =>
    fetch(`/api/node/${uid}`).then(r => {
      if (!r.ok) throw new Error(`No Government Resolution ${uid} in the index.`)
      return r.json()
    }),

  search: (q: string, limit = 10): Promise<{ total: number; nodes: GraphNode[] }> =>
    fetch(`/api/nodes?q=${encodeURIComponent(q)}&limit=${limit}`).then(r => r.json()),

  /** Ranked by in-degree — the load-bearing orders, and a good place for a demo to start. */
  top: (limit = 6): Promise<{ total: number; nodes: GraphNode[] }> =>
    fetch(`/api/nodes?sort=in_degree&limit=${limit}`).then(r => r.json()),

  overview: (): Promise<{
    scale: { grs: number; departments: number; edges: number; cross_dept_edges: number }
    edge_types: Record<string, number>
  }> => fetch('/api/overview').then(r => r.json()),
}

/** Typeset document from the server. PDF and DOCX come from one model, so they cannot drift. */
export async function downloadDoc(text: string, lang: Lang, fmt: 'pdf' | 'docx' = 'pdf') {
  const filename = `government-resolution.${fmt}`
  const r = await fetch(`/api/draft/export?fmt=${fmt}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, lang }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`)
  const blob = await r.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
