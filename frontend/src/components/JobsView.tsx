import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ChevronDown, ChevronRight, FilePlus2, LoaderCircle, Pencil, Play, Plus, Printer, Trash2, Upload, X } from 'lucide-react'
import { api } from '../api'
import { ConfirmDialog, Dialog, FormDialog } from './Dialog'
import type { Document, JobCheck, JobDetail, JobDocument, JobEvidence, JobFinding, JobSummary, KnowledgeBase } from '../types'

const ACCEPT = '.pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff'
const KIND_LABEL: Record<string, string> = { consistency: 'Documents disagree', code_rule: 'Code rule', missing: 'Missing information' }
const METHOD_LABEL: Record<string, string> = { table: 'table', text: 'text', model: 'model, found in text', user: 'entered by hand' }

const errorText = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback

function when(value: string | null | undefined): string {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function Counts({ counts }: { counts?: JobCheck['counts'] | null }) {
  if (!counts) return <span className="muted">Not checked</span>
  if (!counts.error && !counts.warning) return <span className="count-clean">No problems</span>
  return <span className="counts">
    {counts.error > 0 && <span className="count-error">{counts.error} error{counts.error === 1 ? '' : 's'}</span>}
    {counts.warning > 0 && <span className="count-warning">{counts.warning} warning{counts.warning === 1 ? '' : 's'}</span>}
  </span>
}

function EvidenceRow({ evidence, onOpen }: { evidence: JobEvidence; onOpen: (evidence: JobEvidence) => void }) {
  const where = evidence.page ? `p. ${evidence.page}` : evidence.locator
  return <button className="evidence" onClick={() => onOpen(evidence)} title="Show in the document">
    <span className="evidence-file">{evidence.filename}</span>
    {evidence.label && <span className="evidence-field">{evidence.label}{evidence.value ? <>: <b>{evidence.value}</b></> : null}</span>}
    <span className="evidence-where">{where}{evidence.method && evidence.method !== 'table' ? ` · ${METHOD_LABEL[evidence.method] ?? evidence.method}` : ''}</span>
  </button>
}

function FindingCard({ finding, onOpen }: { finding: JobFinding; onOpen: (evidence: JobEvidence) => void }) {
  return <li className={`finding finding-${finding.severity}`}>
    <div className="finding-head">
      <span className={`sev sev-${finding.severity}`}>{finding.severity}</span>
      <span className="finding-kind">{KIND_LABEL[finding.kind] ?? finding.kind}</span>
    </div>
    <h3>{finding.title}</h3>
    <p>{finding.detail}</p>
    {finding.rule && <p className="finding-rule">{finding.rule}</p>}
    {finding.evidence.some(e => e.label || e.snippet) && <div className="evidence-list">{finding.evidence.map((evidence, index) => <EvidenceRow key={index} evidence={evidence} onOpen={onOpen} />)}</div>}
  </li>
}

function FieldsTable({ jobId, document, canWrite, onChanged, onOpen, flash }: {
  jobId: string; document: JobDocument; canWrite: boolean; onChanged: () => void; onOpen: (evidence: JobEvidence) => void; flash: (message: string) => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  async function save(key: string, value: string | null) {
    setError('')
    try {
      await api(`/jobs/${jobId}/documents/${document.document_id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ overrides: { [key]: value } }) })
      setEditing(null)
      onChanged()
    } catch (reason) { setError(errorText(reason, 'Could not save')) }
  }

  if (document.log) return <p className="fields-note">{document.log.rows} weld{document.log.rows === 1 ? '' : 's'} read from sheet “{document.log.sheet}”, columns: {Object.entries(document.log.columns).map(([key, header]) => `${header} (${key})`).join(', ')}.</p>
  if (document.log_error) return <p className="fields-note bad">{document.log_error}</p>
  if (!document.fields.length) return <p className="fields-note">No fields are read from documents of this type.</p>
  return <table className="fields">
    <tbody>
      {document.fields.map(field => <tr key={field.key} className={!field.display && field.required ? 'missing' : undefined}>
        <th>{field.label}{field.required && <span title="Needed by the checks">*</span>}</th>
        <td className="field-value">
          {editing === field.key ? <form className="field-edit" onSubmit={event => { event.preventDefault(); void save(field.key, draft) }}>
            <input autoFocus value={draft} onChange={event => setDraft(event.target.value)} />
            <button className="btn btn-sm btn-primary">Save</button>
            <button type="button" className="btn btn-sm" onClick={() => { setEditing(null); setError('') }}>Cancel</button>
            {error && <span className="field-error">{error}</span>}
          </form> : field.display ?? <span className="muted">not found</span>}
        </td>
        <td className="field-source">
          {field.source && editing !== field.key && (field.source.page || field.source.snippet
            ? <button className="link" onClick={() => onOpen({ document_id: document.document_id, filename: document.filename, doc_type: document.doc_type, label: field.label, value: field.display, page: field.source!.page, locator: field.source!.locator, snippet: field.source!.snippet, method: field.source!.method })}>
              {field.source.page ? `p. ${field.source.page}` : field.source.locator}</button>
            : <span>{field.source.locator}</span>)}
          {field.source && editing !== field.key && <span className="muted"> · {METHOD_LABEL[field.source.method] ?? field.source.method}</span>}
        </td>
        <td className="field-actions">
          {canWrite && editing !== field.key && <>
            <button className="btn btn-ghost btn-icon" title="Correct this value" onClick={() => { setEditing(field.key); setDraft(field.source?.raw ?? field.display ?? ''); setError('') }}><Pencil size={13} /></button>
            {field.overridden && <button className="btn btn-ghost btn-sm" title="Go back to the value read from the document" onClick={() => void save(field.key, '').catch(() => flash('Could not revert'))}>Revert</button>}
          </>}
        </td>
      </tr>)}
    </tbody>
  </table>
}

function JobPage({ jobId, library, canWrite, onBack, onOpen, flash }: {
  jobId: string; library: KnowledgeBase | null; canWrite: boolean; onBack: () => void; onOpen: (evidence: JobEvidence) => void; flash: (message: string) => void
}) {
  const [detail, setDetail] = useState<JobDetail | null>(null)
  const [checking, setChecking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'error' | 'warning' | 'note'>('all')
  const [picking, setPicking] = useState(false)
  const [libraryDocs, setLibraryDocs] = useState<Document[]>([])
  const [confirmDelete, setConfirmDelete] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(() => api<JobDetail>(`/jobs/${jobId}`).then(setDetail).catch(error => flash(errorText(error, 'Could not open the job'))), [jobId, flash])
  useEffect(() => { void load() }, [load])

  // documents index in the background: refresh until they're all ready
  const indexing = detail?.documents.some(document => document.status === 'queued' || document.status === 'indexing')
  useEffect(() => {
    if (!indexing) return
    const timer = window.setInterval(() => void load(), 2500)
    return () => window.clearInterval(timer)
  }, [indexing, load])

  async function runChecks() {
    setChecking(true)
    try {
      const result = await api<{ check: JobCheck; checked_at: string }>(`/jobs/${jobId}/check`, { method: 'POST' })
      setDetail(current => current ? { ...current, check: result.check, job: { ...current.job, checked_at: result.checked_at, counts: result.check.counts } } : current)
      setFilter('all')
    } catch (error) { flash(errorText(error, 'Checks failed')) }
    finally { setChecking(false) }
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return
    const form = new FormData()
    Array.from(files).forEach(file => form.append('files', file))
    setUploading(true)
    try {
      const result = await api<{ documents: Document[] }>(`/jobs/${jobId}/upload`, { method: 'POST', body: form })
      const duplicates = result.documents.filter(document => document.status === 'duplicate').length
      if (duplicates) flash(`${duplicates} file${duplicates === 1 ? ' was' : 's were'} already in ${library?.name ?? 'the library'}; use “Add from library” to attach ${duplicates === 1 ? 'it' : 'them'}`)
      await load()
    } catch (error) { flash(errorText(error, 'Upload failed')) }
    finally { setUploading(false); if (fileInput.current) fileInput.current.value = '' }
  }

  async function openPicker() {
    if (!detail) return
    try {
      const result = await api<{ documents: Document[] }>(`/knowledge-bases/${detail.job.knowledge_base_id}/documents`)
      const attached = new Set(detail.documents.map(document => document.document_id))
      setLibraryDocs(result.documents.filter(document => !attached.has(document.id)))
      setPicking(true)
    } catch (error) { flash(errorText(error, 'Could not load the library')) }
  }

  async function attach(documentId: string) {
    try {
      await api(`/jobs/${jobId}/documents`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document_id: documentId }) })
      setLibraryDocs(current => current.filter(document => document.id !== documentId))
      await load()
    } catch (error) { flash(errorText(error, 'Could not add the document')) }
  }

  async function setType(document: JobDocument, docType: string) {
    try {
      await api(`/jobs/${jobId}/documents/${document.document_id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ doc_type: docType }) })
      await load()
    } catch (error) { flash(errorText(error, 'Could not change the type')) }
  }

  async function detach(document: JobDocument) {
    try {
      await api(`/jobs/${jobId}/documents/${document.document_id}`, { method: 'DELETE' })
      await load()
    } catch (error) { flash(errorText(error, 'Could not remove the document')) }
  }

  if (!detail) return <div className="job-loading"><LoaderCircle className="spin" size={16} /></div>
  const check = detail.check
  const findings = check?.findings.filter(finding => filter === 'all' || finding.severity === filter) ?? []
  const stale = check && detail.job.checked_at && new Date(detail.job.updated_at) > new Date(detail.job.checked_at)

  return <div className="job">
    <header className="view-header job-header">
      <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="All jobs"><ArrowLeft size={16} /></button>
      <div className="job-title"><h1>{detail.job.name}</h1><span>{library?.name}</span></div>
      <div className="view-actions">
        {check && <button className="btn" onClick={() => window.print()} title="Print or save as PDF"><Printer size={14} />Report</button>}
        <button className="btn btn-primary" onClick={() => void runChecks()} disabled={checking || !detail.documents.length}>{checking ? <LoaderCircle className="spin" size={14} /> : <Play size={14} />}Run checks</button>
      </div>
    </header>
    <div className="job-body">
      <section className="panel print-keep">
        <header className="panel-header">
          <div>
            <h2>Findings {check && <Counts counts={check.counts} />}</h2>
            <p>{check ? <>Checked {when(detail.job.checked_at)} across {check.documents} document{check.documents === 1 ? '' : 's'}.{stale ? ' Documents changed since; run the checks again.' : ''}{check.pending.length ? ` ${check.pending.length} still indexing, not included.` : ''}</> : 'Add the job’s documents, then run the checks. Nothing is checked by the model; every finding cites where it comes from.'}</p>
          </div>
          {check && check.findings.length > 0 && <div className="segmented no-print">
            {(['all', 'error', 'warning', 'note'] as const).map(value => <button key={value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{value === 'all' ? 'All' : value[0].toUpperCase() + value.slice(1) + 's'}</button>)}
          </div>}
        </header>
        {check && (findings.length ? <ul className="findings">{findings.map(finding => <FindingCard key={finding.id} finding={finding} onOpen={onOpen} />)}</ul>
          : <p className="panel-empty">{check.findings.length ? 'Nothing at this level.' : 'No problems found in the documents checked.'}</p>)}
      </section>

      <section className="panel no-print">
        <header className="panel-header">
          <div><h2>Documents <span className="count">{detail.documents.length}</span></h2><p>Types are guessed from the file; correct any that are wrong. Fields marked * are needed by the checks.</p></div>
          {canWrite && <div className="view-actions">
            <button className="btn" onClick={() => void openPicker()}><FilePlus2 size={14} />Add from library</button>
            <button className="btn" onClick={() => fileInput.current?.click()} disabled={uploading}>{uploading ? <LoaderCircle className="spin" size={14} /> : <Upload size={14} />}Upload</button>
            <input ref={fileInput} type="file" multiple accept={ACCEPT} hidden onChange={event => void upload(event.target.files)} />
          </div>}
        </header>
        {detail.documents.length === 0 ? <p className="panel-empty">No documents yet. Upload the WPS, PQR, welder qualifications, consumable certificates and weld log for this job.</p>
          : <ul className="job-docs">{detail.documents.map(document => {
            const found = document.fields.filter(field => field.display).length
            const open = expanded === document.document_id
            return <li key={document.document_id} className={open ? 'open' : undefined}>
              <div className="job-doc-row">
                <button className="btn btn-ghost btn-icon" onClick={() => setExpanded(open ? null : document.document_id)} aria-label={open ? 'Hide fields' : 'Show fields'}>{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button>
                <span className="job-doc-name" title={document.filename}>{document.filename}</span>
                <select className="select" value={document.doc_type} disabled={!canWrite} onChange={event => void setType(document, event.target.value)}>
                  {Object.entries(detail.doc_types).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <span className="job-doc-meta">{document.status !== 'ready' ? <span className={`status status-${document.status}`}>{document.status}</span>
                  : document.log ? `${document.log.rows} welds` : document.fields.length ? `${found}/${document.fields.length} fields` : ''}</span>
                {canWrite && <button className="btn btn-ghost btn-icon danger" onClick={() => void detach(document)} title="Remove from job (stays in the library)"><X size={14} /></button>}
              </div>
              {open && document.status === 'ready' && <FieldsTable jobId={jobId} document={document} canWrite={canWrite} onChanged={() => void load()} onOpen={onOpen} flash={flash} />}
            </li>
          })}</ul>}
      </section>
      {canWrite && <div className="job-foot no-print"><button className="btn btn-ghost danger" onClick={() => setConfirmDelete(true)}><Trash2 size={14} />Delete job</button></div>}
    </div>

    {picking && <Dialog title="Add from library" onClose={() => setPicking(false)} width={520}>
      <div className="dialog-body">
        {libraryDocs.length === 0 ? <p>Every document in {library?.name} is already in this job.</p>
          : <ul className="pick-list">{libraryDocs.map(document => <li key={document.id}><span>{document.filename}</span><button className="btn btn-sm" onClick={() => void attach(document.id)}><Plus size={13} />Add</button></li>)}</ul>}
      </div>
      <footer className="dialog-footer"><button className="btn" onClick={() => setPicking(false)}>Done</button></footer>
    </Dialog>}
    {confirmDelete && <ConfirmDialog title="Delete job" action="Delete job" body={`${detail.job.name} and its check results will be deleted. Its documents stay in ${library?.name ?? 'the library'}.`}
      onClose={() => setConfirmDelete(false)} onConfirm={async () => {
        try { await api(`/jobs/${jobId}`, { method: 'DELETE' }); onBack() } catch (error) { flash(errorText(error, 'Could not delete the job')) }
      }} />}
  </div>
}

export function JobsView({ libraries, selectedKb, onSelectKb, onOpen, flash, menuButton }: {
  libraries: KnowledgeBase[]; selectedKb: string; onSelectKb: (id: string) => void
  onOpen: (evidence: JobEvidence) => void; flash: (message: string) => void; menuButton: React.ReactNode
}) {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null)
  const [activeJob, setActiveJob] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const own = libraries.filter(kb => !kb.is_reference)
  const library = own.find(kb => kb.id === selectedKb) ?? own[0] ?? null
  const canWrite = Boolean(library && library.role !== 'reader')

  const load = useCallback(() => {
    if (!library) { setJobs([]); return }
    api<{ jobs: JobSummary[] }>(`/knowledge-bases/${library.id}/jobs`).then(result => setJobs(result.jobs)).catch(error => flash(errorText(error, 'Could not load jobs')))
  }, [library, flash])
  useEffect(() => { if (!activeJob) load() }, [load, activeJob])

  async function create(): Promise<string | void> {
    if (!library) return
    try {
      const result = await api<{ job: JobSummary }>(`/knowledge-bases/${library.id}/jobs`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim(), description: description.trim() }) })
      setCreating(false)
      setName('')
      setDescription('')
      setActiveJob(result.job.id)
    } catch (error) { return errorText(error, 'Could not create the job') }
  }

  if (activeJob) return <JobPage jobId={activeJob} library={library} canWrite={canWrite} onBack={() => setActiveJob(null)} onOpen={onOpen} flash={flash} />

  return <section className="library">
    <header className="view-header">
      {menuButton}
      <h1>Jobs</h1>
      {own.length > 0 && <select className="select" value={library?.id ?? ''} onChange={event => onSelectKb(event.target.value)} aria-label="Library">{own.map(kb => <option key={kb.id} value={kb.id}>{kb.name}</option>)}</select>}
      <div className="view-actions">{canWrite && <button className="btn btn-primary" onClick={() => setCreating(true)}><Plus size={14} />New job</button>}</div>
    </header>
    {!library ? <div className="blank">
      <h2>Create a library first</h2>
      <p>Jobs live in a library, so everyone working on the project sees the same documents and findings.</p>
    </div> : <div className="library-body">
      <p className="library-description">A job file holds the WPS, PQR, welder qualifications, consumable certificates and weld log for one piece of work. Datum reads the key fields from each and checks them against each other, so problems are found before the inspector finds them.</p>
      <section className="panel">
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Job</th><th className="num">Documents</th><th>Last check</th><th>Result</th></tr></thead>
          <tbody>
            {jobs === null ? <tr><td colSpan={4} className="table-empty">Loading…</td></tr>
              : jobs.length === 0 ? <tr><td colSpan={4} className="table-empty">No jobs in {library.name} yet.</td></tr>
              : jobs.map(job => <tr key={job.id} className="clickable" onClick={() => setActiveJob(job.id)}>
                <td className="doc-name"><span title={job.name}>{job.name}</span>{job.description && <small className="muted">{job.description}</small>}</td>
                <td className="num">{job.document_count}</td>
                <td className="muted">{job.checked_at ? when(job.checked_at) : '–'}</td>
                <td><Counts counts={job.counts} /></td>
              </tr>)}
          </tbody>
        </table></div>
      </section>
    </div>}
    {creating && <FormDialog title="New job" submitLabel="Create job" onSubmit={create} onClose={() => setCreating(false)} canSubmit={Boolean(name.trim())}>
      <label className="field">Name<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="JOB-2025-118 pipe rack" maxLength={120} required /></label>
      <label className="field">Description <span className="optional">optional</span><textarea value={description} onChange={event => setDescription(event.target.value)} placeholder="Client, drawing number, inspection agency" rows={2} maxLength={1000} /></label>
    </FormDialog>}
  </section>
}
