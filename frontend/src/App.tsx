import { FormEvent, KeyboardEvent, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp, ExternalLink, FileText, FolderOpen, LoaderCircle, LogOut, Menu, MessageSquareText,
  Paperclip, Plus, Search, Trash2, Upload, UserPlus, X,
} from 'lucide-react'
import { api, formatBytes } from './api'
import { AnswerBody, ConfidenceBadge } from './components/AnswerBody'
import { DiagramCard } from './components/DiagramCard'
import { ConfirmDialog, Dialog, FormDialog } from './components/Dialog'
import { DatumMark } from './components/Logo'
import { MemoryPanel } from './components/MemoryPanel'
import type { ViewerTarget } from './components/PdfViewer'
import type { Chat, Citation, Document, KnowledgeBase, Message, User } from './types'

type Page = 'ask' | 'library'
type Health = { ollama_available: boolean; chat_model: string }
type Pending = { title: string; body: string; action: string; run: () => Promise<void> }

const ACCEPT = '.pdf,.docx,.txt,.md,.pptx,.xlsx,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff,.bmp'

// pdf.js is most of the bundle; load it the first time a citation is opened.
const PdfViewer = lazy(() => import('./components/PdfViewer').then(module => ({ default: module.PdfViewer })))

const errorText = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`
const isPdf = (filename: string) => filename.toLowerCase().endsWith('.pdf')

function shortDate(value: string): string {
  const date = new Date(value)
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(value).setHours(0, 0, 0, 0)) / 86_400_000)
  if (days === 0) return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  if (days === 1) return 'Yesterday'
  if (days < 7) return date.toLocaleDateString(undefined, { weekday: 'short' })
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function SignIn({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [registering, setRegistering] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    const data = new FormData(event.currentTarget)
    const payload = {
      email: String(data.get('email') || ''),
      password: String(data.get('password') || ''),
      ...(registering ? { display_name: String(data.get('name') || '') } : {}),
    }
    try {
      const result = await api<{ user: User }>(`/auth/${registering ? 'register' : 'login'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })
      onSignedIn(result.user)
    } catch (reason) {
      setError(errorText(reason, 'Something went wrong'))
    } finally { setBusy(false) }
  }

  return <main className="auth">
    <form className="auth-card" onSubmit={submit}>
      <div className="auth-brand"><DatumMark size={28} /><span>Datum</span></div>
      <h1>{registering ? 'Create an account' : 'Sign in'}</h1>
      <p className="auth-lede">Ask technical questions of your datasheets and specs. Every answer points to the page it came from.</p>
      {registering && <label className="field">Name<input name="name" autoComplete="name" required minLength={1} /></label>}
      <label className="field">Email<input name="email" type="email" autoComplete="email" required /></label>
      <label className="field">Password<input name="password" type="password" autoComplete={registering ? 'new-password' : 'current-password'} required minLength={registering ? 10 : 1} />{registering && <small>At least 10 characters.</small>}</label>
      {error && <p className="form-error">{error}</p>}
      <button className="btn btn-primary btn-block" disabled={busy}>{busy && <LoaderCircle className="spin" size={14} />}{registering ? 'Create account' : 'Sign in'}</button>
      <p className="auth-switch">{registering ? 'Already have an account?' : 'No account yet?'} <button type="button" className="link" onClick={() => { setRegistering(!registering); setError('') }}>{registering ? 'Sign in' : 'Create one'}</button></p>
    </form>
    <p className="auth-foot">Runs on this machine. Documents and models never leave it.</p>
  </main>
}

function StatusTag({ status, error }: { status: string; error?: string | null }) {
  const labels: Record<string, string> = { queued: 'Queued', indexing: 'Indexing', ready: 'Ready', failed: 'Failed', duplicate: 'Duplicate' }
  return <span className={`status status-${status}`} title={error || undefined}>{status === 'indexing' && <LoaderCircle className="spin" size={11} />}{labels[status] || status}</span>
}

function SourceList({ citations, onOpen }: { citations: Citation[]; onOpen: (citation: Citation) => void }) {
  return <ol className="refs">
    {citations.map(citation => <li key={`${citation.document_id}-${citation.index}`} className={citation.score != null && citation.score < 4 ? 'weak' : undefined} title={citation.score != null && citation.score < 4 ? 'Retrieved, but the reranker judged it weakly relevant' : undefined}>
      <button onClick={() => onOpen(citation)} title={isPdf(citation.filename) && citation.page_start ? 'Show on the page' : 'Show excerpt'}>
        <span className="ref-n">{citation.index}</span>
        <span className="ref-file">{citation.filename}</span>
        <span className="ref-loc">{citation.location}</span>
        <span className={`ref-score ${citation.exact ? 'exact' : ''}`}>{citation.exact ? 'table value' : citation.score != null ? `${citation.score}/10` : ''}</span>
      </button>
    </li>)}
  </ol>
}

function SourceDialog({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const snippet = citation.snippet.length > 900 ? `${citation.snippet.slice(0, 900)}…` : citation.snippet
  return <Dialog title={`[${citation.index}] ${citation.filename}`} onClose={onClose} width={560}>
    <div className="dialog-body">
      <p className="excerpt-meta">{citation.location}{citation.exact ? ' · exact value read from a table' : ''}</p>
      <blockquote className="excerpt">{snippet}</blockquote>
    </div>
    <footer className="dialog-footer"><a className="btn" href={`/api/documents/${citation.document_id}/file`} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open original</a></footer>
  </Dialog>
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [checkingAuth, setCheckingAuth] = useState(true)

  useEffect(() => {
    api<{ user: User }>('/auth/me').then(result => setUser(result.user)).catch(() => setUser(null)).finally(() => setCheckingAuth(false))
  }, [])

  if (checkingAuth) return <div className="boot"><DatumMark size={26} /></div>
  if (!user) return <SignIn onSignedIn={setUser} />
  return <Workspace user={user} onSignOut={() => setUser(null)} />
}

function Workspace({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const [page, setPage] = useState<Page>('ask')
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [selectedKb, setSelectedKb] = useState('')
  const [activeChat, setActiveChat] = useState<Chat | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [chatDocuments, setChatDocuments] = useState<Document[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [kbLoading, setKbLoading] = useState(false)
  const [kbDocuments, setKbDocuments] = useState<Document[]>([])
  const [dialog, setDialog] = useState<'create' | 'invite' | null>(null)
  const [newKbName, setNewKbName] = useState('')
  const [newKbDescription, setNewKbDescription] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [pending, setPending] = useState<Pending | null>(null)
  const [kbSearch, setKbSearch] = useState('')
  const [source, setSource] = useState<Citation | null>(null)
  const [viewer, setViewer] = useState<ViewerTarget | null>(null)
  const [toast, setToast] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [mobileSidebar, setMobileSidebar] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const chatFileInput = useRef<HTMLInputElement>(null)
  const knowledgeSearchInput = useRef<HTMLInputElement>(null)
  const messageEnd = useRef<HTMLDivElement>(null)
  const composer = useRef<HTMLTextAreaElement>(null)

  const activeKb = useMemo(() => knowledgeBases.find(kb => kb.id === selectedKb) || null, [knowledgeBases, selectedKb])
  const selectedChatKb = activeChat ? (activeChat.knowledge_base_id || '') : selectedKb
  const chatKnowledgeBase = knowledgeBases.find(kb => kb.id === selectedChatKb)
  const modelOffline = health !== null && !health.ollama_available

  const flash = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 3300)
  }, [])

  const loadBaseData = useCallback(async () => {
    try {
      const [kbResult, chatResult] = await Promise.all([
        api<{ knowledge_bases: KnowledgeBase[] }>('/knowledge-bases'),
        api<{ chats: Chat[] }>('/chats'),
      ])
      setKnowledgeBases(kbResult.knowledge_bases)
      setChats(chatResult.chats)
      setSelectedKb(current => current && kbResult.knowledge_bases.some(kb => kb.id === current) ? current : (kbResult.knowledge_bases[0]?.id || ''))
    } catch (error) {
      flash(errorText(error, 'Could not load your workspace'))
    }
  }, [flash])

  useEffect(() => { void loadBaseData() }, [loadBaseData])
  useEffect(() => {
    function shortcuts(event: globalThis.KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) return
      if (event.key.toLowerCase() === 'k') {
        event.preventDefault()
        void startNewChat()
      } else if (event.key.toLowerCase() === 'f' && page === 'library') {
        event.preventDefault()
        knowledgeSearchInput.current?.focus()
      }
    }
    window.addEventListener('keydown', shortcuts)
    return () => window.removeEventListener('keydown', shortcuts)
  })
  useEffect(() => {
    api<Health>('/health').then(setHealth).catch(() => setHealth({ ollama_available: false, chat_model: '' }))
  }, [])

  const openCitation = useCallback((citation: Citation) => {
    if (isPdf(citation.filename) && citation.page_start) {
      setViewer({ documentId: citation.document_id, filename: citation.filename, page: citation.page_start, snippet: citation.exact ? null : citation.snippet, nonce: Date.now() })
    } else {
      setSource(citation)
    }
  }, [])

  const openPage = useCallback((documentId: string, filename: string, pageNumber: number) => {
    setViewer({ documentId, filename, page: pageNumber, snippet: null, nonce: Date.now() })
  }, [])

  const loadChat = useCallback(async (chatId: string) => {
    setViewer(null)
    try {
      const result = await api<{ chat: Chat; messages: Message[]; documents: Document[] }>(`/chats/${chatId}`)
      setActiveChat(result.chat)
      setMessages(result.messages)
      setChatDocuments(result.documents)
      if (result.chat.knowledge_base_id) setSelectedKb(result.chat.knowledge_base_id)
    } catch (error) { flash(errorText(error, 'Could not open this thread')) }
  }, [flash])

  // attachments index in the background; poll only while one is still in progress
  useEffect(() => {
    if (!activeChat || !chatDocuments.some(document => document.status === 'queued' || document.status === 'indexing')) return
    const timer = window.setInterval(() => {
      api<{ documents: Document[] }>(`/chats/${activeChat.id}`).then(result => setChatDocuments(result.documents)).catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [activeChat, chatDocuments])

  useEffect(() => {
    if (page !== 'library' || !selectedKb) { setKbDocuments([]); return }
    let alive = true
    const refresh = () => api<{ documents: Document[] }>(`/knowledge-bases/${selectedKb}/documents`)
      .then(result => { if (alive) setKbDocuments(result.documents) })
      .catch(error => { if (alive) flash(errorText(error, 'Could not load documents')) })
    setKbLoading(true)
    refresh().finally(() => { if (alive) setKbLoading(false) })
    const timer = window.setInterval(refresh, 2500)
    return () => { alive = false; window.clearInterval(timer) }
  }, [page, selectedKb, flash])

  useEffect(() => { messageEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, sending])

  // the Ask view lists the library's documents when a thread is empty
  useEffect(() => {
    if (page !== 'ask' || messages.length || !selectedChatKb) return
    api<{ documents: Document[] }>(`/knowledge-bases/${selectedChatKb}/documents`).then(result => setKbDocuments(result.documents)).catch(() => undefined)
  }, [page, messages.length, selectedChatKb])

  async function startNewChat() {
    setActiveChat(null)
    setMessages([])
    setChatDocuments([])
    setViewer(null)
    setPage('ask')
    setMobileSidebar(false)
    composer.current?.focus()
  }

  async function ensureChat(): Promise<Chat | null> {
    if (activeChat) return activeChat
    try {
      const created = await api<{ chat: Chat }>('/chats', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ knowledge_base_id: selectedKb || null }),
      })
      setActiveChat(created.chat)
      void loadBaseData()
      return created.chat
    } catch (error) { flash(errorText(error, 'Could not start a thread')); return null }
  }

  async function chooseChat(chat: Chat) {
    setPage('ask')
    setMobileSidebar(false)
    await loadChat(chat.id)
  }

  async function createKnowledgeBase(): Promise<string | void> {
    try {
      const result = await api<{ knowledge_base: KnowledgeBase }>('/knowledge-bases', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newKbName.trim(), description: newKbDescription.trim() }),
      })
      setKnowledgeBases(current => [result.knowledge_base, ...current])
      setSelectedKb(result.knowledge_base.id)
      setNewKbName('')
      setNewKbDescription('')
      setDialog(null)
      setPage('library')
    } catch (error) { return errorText(error, 'Could not create the library') }
  }

  async function inviteMember(): Promise<string | void> {
    if (!activeKb) return
    try {
      await api(`/knowledge-bases/${activeKb.id}/members`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: inviteEmail.trim() }) })
      setInviteEmail('')
      setDialog(null)
      flash(`${inviteEmail.trim()} can now use ${activeKb.name}`)
    } catch (error) { return errorText(error, 'Could not add member') }
  }

  async function uploadFiles(files: FileList | null, destination: 'library' | 'chat') {
    if (!files?.length) return
    const targetKb = selectedKb
    if (destination === 'library' && !targetKb) { flash('Create a library first'); return }
    const chat = destination === 'chat' ? await ensureChat() : null
    if (destination === 'chat' && !chat) return
    const form = new FormData()
    Array.from(files).forEach(file => form.append('files', file))
    setUploading(true)
    try {
      const path = destination === 'library' ? `/knowledge-bases/${targetKb}/documents` : `/chats/${chat!.id}/documents`
      const result = await api<{ documents: Document[] }>(path, { method: 'POST', body: form })
      const duplicates = result.documents.filter(document => document.status === 'duplicate').length
      const added = result.documents.length - duplicates
      flash(duplicates ? `${plural(added, 'file')} added, ${duplicates} already in this library` : `${plural(added, 'file')} added. Indexing…`)
      if (destination === 'library') {
        const refreshed = await api<{ documents: Document[] }>(`/knowledge-bases/${targetKb}/documents`)
        setKbDocuments(refreshed.documents)
        void loadBaseData()
      } else {
        const refreshed = await api<{ documents: Document[] }>(`/chats/${chat!.id}`)
        setChatDocuments(refreshed.documents)
      }
    } catch (error) { flash(errorText(error, 'Upload failed')) }
    finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
      if (chatFileInput.current) chatFileInput.current.value = ''
    }
  }

  async function sendMessage(event?: FormEvent, suggested?: string) {
    event?.preventDefault()
    const content = (suggested || input).trim()
    if (!content || sending) return
    const chat = await ensureChat()
    if (!chat) return
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content, citations: [], created_at: new Date().toISOString() }
    const pendingId = crypto.randomUUID()
    setMessages(current => [...current, userMessage, { id: pendingId, role: 'assistant', content: '', citations: [], created_at: new Date().toISOString() }])
    setInput('')
    setSending(true)
    if (composer.current) composer.current.style.height = 'auto'
    const update = (change: (message: Message) => Message) => setMessages(current => current.map(message => message.id === pendingId ? change(message) : message))
    try {
      const response = await fetch(`/api/chats/${chat.id}/messages`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      if (!response.ok || !response.body) {
        let detail = 'Could not send your question'
        try { detail = (await response.json()).detail || detail } catch { /* non-JSON response */ }
        throw new Error(detail)
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventName = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() || ''
        for (const frame of frames) {
          let payload = ''
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) eventName = line.slice(6).trim()
            if (line.startsWith('data:')) payload += line.slice(5).trim()
          }
          if (!payload) continue
          const data = JSON.parse(payload)
          if (eventName === 'sources') update(message => ({ ...message, citations: data.sources, confidence: data.confidence }))
          else if (eventName === 'diagram') update(message => ({ ...message, diagram: data.diagram }))
          else if (eventName === 'delta') update(message => ({ ...message, content: message.content + data.text }))
          else if (eventName === 'done') { update(() => data.message); void loadBaseData() }
          else if (eventName === 'error') update(message => ({ ...message, content: '', error: data.message }))
          eventName = ''
        }
      }
    } catch (error) {
      update(message => ({ ...message, error: errorText(error, 'Could not send your question') }))
    } finally { setSending(false) }
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage() }
  }

  function confirmDeleteDocument(document: Document) {
    setPending({
      title: 'Remove document', action: 'Remove',
      body: `${document.filename} and everything indexed from it (passages, table values, figures) will be deleted.`,
      run: async () => {
        try {
          await api(`/documents/${document.id}`, { method: 'DELETE' })
          setKbDocuments(current => current.filter(item => item.id !== document.id))
          setChatDocuments(current => current.filter(item => item.id !== document.id))
          void loadBaseData()
        } catch (error) { flash(errorText(error, 'Could not remove the document')) }
        setPending(null)
      },
    })
  }

  function confirmDeleteLibrary() {
    if (!activeKb) return
    setPending({
      title: 'Delete library', action: 'Delete library',
      body: `${activeKb.name}, its ${plural(activeKb.document_count ?? kbDocuments.length, 'document')} and its project memory will be deleted. Threads that used it are kept.`,
      run: async () => {
        try {
          await api(`/knowledge-bases/${activeKb.id}`, { method: 'DELETE' })
          setSelectedKb('')
          setKbDocuments([])
          await loadBaseData()
        } catch (error) { flash(errorText(error, 'Could not delete the library')) }
        setPending(null)
      },
    })
  }

  function confirmDeleteChat(chat: Chat) {
    setPending({
      title: 'Delete thread', action: 'Delete',
      body: `"${chat.title}" and any files attached to it will be deleted.`,
      run: async () => {
        try {
          await api(`/chats/${chat.id}`, { method: 'DELETE' })
          if (activeChat?.id === chat.id) void startNewChat()
          await loadBaseData()
        } catch (error) { flash(errorText(error, 'Could not delete the thread')) }
        setPending(null)
      },
    })
  }

  function changeChatLibrary(value: string) {
    setSelectedKb(value)
    if (!activeChat) return
    api<{ chat: Chat }>(`/chats/${activeChat.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ knowledge_base_id: value || null }) })
      .then(result => setActiveChat(result.chat)).catch(error => flash(errorText(error, 'Could not change the library')))
  }

  async function signOut() {
    await api('/auth/logout', { method: 'POST' }).catch(() => undefined)
    onSignOut()
  }

  const filteredDocuments = kbDocuments.filter(document => document.filename.toLowerCase().includes(kbSearch.toLowerCase()))
  const lastId = messages[messages.length - 1]?.id
  const readyDocuments = kbDocuments.filter(document => document.status === 'ready')

  function renderAssistant(message: Message) {
    const streaming = sending && message.id === lastId
    if (message.error) return <p className="answer-error">{message.error}</p>
    if (message.diagram) return <><DiagramCard diagram={message.diagram} onOpenPage={openPage} />{!streaming && <p className="answer-note">{message.content}</p>}</>
    if (!message.content) {
      const status = message.citations.length ? `Reading ${plural(message.citations.length, 'source')}…` : `Searching ${chatKnowledgeBase?.name ?? 'attached files'}…`
      return <p className="answer-status"><LoaderCircle className="spin" size={13} />{status}</p>
    }
    return <AnswerBody content={message.content} streaming={streaming} citationCount={message.citations?.length ?? 0} onCite={index => { const citation = message.citations.find(item => item.index === index); if (citation) openCitation(citation) }} />
  }

  return <div className={`app ${mobileSidebar ? 'nav-open' : ''}`}>
    {mobileSidebar && <button className="scrim" aria-label="Close menu" onClick={() => setMobileSidebar(false)} />}
    <aside className="sidebar">
      <div className="brand"><DatumMark /><span>Datum</span><button className="btn btn-ghost btn-icon sidebar-close" onClick={() => setMobileSidebar(false)} aria-label="Close menu"><X size={16} /></button></div>
      <button className="btn new-thread" onClick={() => void startNewChat()}><Plus size={14} />New thread<kbd>⌘K</kbd></button>
      <nav className="nav">
        <button className={page === 'ask' ? 'active' : ''} onClick={() => { setPage('ask'); setMobileSidebar(false) }}><MessageSquareText size={15} />Ask</button>
        <button className={page === 'library' ? 'active' : ''} onClick={() => { setPage('library'); setMobileSidebar(false) }}><FolderOpen size={15} />Library<span className="nav-count">{knowledgeBases.length || ''}</span></button>
      </nav>
      <div className="nav-heading">Threads</div>
      <div className="threads">
        {chats.length === 0 ? <p className="threads-empty">No threads yet.</p> : chats.map(chat => <div key={chat.id} className={`thread ${activeChat?.id === chat.id && page === 'ask' ? 'active' : ''}`}>
          <button className="thread-open" onClick={() => void chooseChat(chat)} title={chat.title}><span>{chat.title || 'Untitled'}</span><time>{shortDate(chat.updated_at)}</time></button>
          <button className="thread-delete" onClick={() => confirmDeleteChat(chat)} aria-label="Delete thread"><Trash2 size={13} /></button>
        </div>)}
      </div>
      <footer className="sidebar-foot">
        <div className={`model-status ${modelOffline ? 'offline' : ''}`} title={modelOffline ? 'Start Ollama: ollama serve' : 'Local model via Ollama'}><i />{health === null ? 'Checking model…' : modelOffline ? 'Ollama not reachable' : health.chat_model}</div>
        <div className="account"><div><strong>{user.display_name}</strong><span>{user.email}</span></div><button className="btn btn-ghost btn-icon" onClick={() => void signOut()} title="Sign out"><LogOut size={15} /></button></div>
      </footer>
    </aside>

    <main className="main">
      {page === 'library' ? <section className="library">
        <header className="view-header">
          <button className="btn btn-ghost btn-icon menu-button" onClick={() => setMobileSidebar(true)} aria-label="Menu"><Menu size={17} /></button>
          <h1>Library</h1>
          {knowledgeBases.length > 0 && <select className="select" value={selectedKb} onChange={event => setSelectedKb(event.target.value)} aria-label="Library">{knowledgeBases.map(kb => <option value={kb.id} key={kb.id}>{kb.name}</option>)}</select>}
          <div className="view-actions">
            {activeKb?.role === 'owner' && <>
              <button className="btn" onClick={() => setDialog('invite')}><UserPlus size={14} />Invite</button>
              <button className="btn btn-ghost btn-icon danger" onClick={confirmDeleteLibrary} title="Delete library"><Trash2 size={15} /></button>
            </>}
            <button className="btn btn-primary" onClick={() => setDialog('create')}><Plus size={14} />New library</button>
          </div>
        </header>

        {knowledgeBases.length === 0 ? <div className="blank">
          <h2>No libraries yet</h2>
          <p>A library is a set of documents you ask questions against: one per product, project or review. Create one, then add datasheets, specs or reports to it.</p>
          <button className="btn btn-primary" onClick={() => setDialog('create')}><Plus size={14} />New library</button>
        </div> : <div className="library-body">
          {activeKb?.description && <p className="library-description">{activeKb.description}</p>}
          <div className={`dropzone ${dragging ? 'over' : ''}`}
            onDragOver={event => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={event => { event.preventDefault(); setDragging(false); void uploadFiles(event.dataTransfer.files, 'library') }}>
            <Upload size={16} />
            <span>Drop files here or <button className="link" onClick={() => fileInput.current?.click()}>choose files</button>. PDF, DOCX, PPTX, XLSX, Markdown, text, HTML or images, up to 50 MB each.</span>
            {uploading && <LoaderCircle className="spin" size={15} />}
            <input ref={fileInput} type="file" multiple accept={ACCEPT} hidden onChange={event => void uploadFiles(event.target.files, 'library')} />
          </div>

          <section className="panel">
            <header className="panel-header">
              <div><h2>Documents <span className="count">{kbDocuments.length}</span></h2></div>
              <label className="search"><Search size={14} /><input ref={knowledgeSearchInput} placeholder="Filter" value={kbSearch} onChange={event => setKbSearch(event.target.value)} /><kbd>⌘F</kbd></label>
            </header>
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Name</th><th>Status</th><th className="num">Pages</th><th className="num">Passages</th><th className="num" title="Values extracted from tables for exact lookup">Table values</th><th className="num">Figures</th><th className="num">Size</th><th>Added</th><th /></tr></thead>
              <tbody>
                {kbLoading && !kbDocuments.length ? <tr><td colSpan={9} className="table-empty">Loading…</td></tr>
                  : filteredDocuments.length === 0 ? <tr><td colSpan={9} className="table-empty">{kbDocuments.length ? 'No documents match the filter.' : 'No documents in this library yet.'}</td></tr>
                  : filteredDocuments.map(document => <tr key={document.id}>
                    <td className="doc-name"><FileText size={14} /><span title={document.filename}>{document.filename}</span>{document.error_message && <small className="doc-error" title={document.error_message}>{document.error_message}</small>}</td>
                    <td><StatusTag status={document.status} error={document.error_message} /></td>
                    <td className="num">{document.page_count || '–'}</td>
                    <td className="num">{document.status === 'ready' ? document.chunk_count : '–'}</td>
                    <td className="num">{document.status === 'ready' ? document.fact_count ?? 0 : '–'}</td>
                    <td className="num">{document.status === 'ready' ? document.figure_count ?? 0 : '–'}</td>
                    <td className="num">{formatBytes(document.byte_size)}</td>
                    <td className="muted">{shortDate(document.created_at)}</td>
                    <td className="row-actions">
                      {isPdf(document.filename) && document.status === 'ready' && <button className="btn btn-ghost btn-icon" onClick={() => { openPage(document.id, document.filename, 1); setPage('ask') }} title="Open"><ExternalLink size={14} /></button>}
                      <button className="btn btn-ghost btn-icon danger" onClick={() => confirmDeleteDocument(document)} title="Remove"><Trash2 size={14} /></button>
                    </td>
                  </tr>)}
              </tbody>
            </table></div>
          </section>

          {selectedKb && <MemoryPanel knowledgeBaseId={selectedKb} onError={flash} />}
        </div>}
      </section> : <div className={`ask-split ${viewer ? 'with-viewer' : ''}`}>
        <section className="ask">
          <header className="view-header">
            <button className="btn btn-ghost btn-icon menu-button" onClick={() => setMobileSidebar(true)} aria-label="Menu"><Menu size={17} /></button>
            <h1 className="thread-title">{activeChat?.title && activeChat.title !== 'New chat' ? activeChat.title : 'New thread'}</h1>
            <label className="scope">Library
              <select className="select" value={selectedChatKb || ''} onChange={event => changeChatLibrary(event.target.value)}>
                <option value="">None, attached files only</option>
                {knowledgeBases.map(kb => <option value={kb.id} key={kb.id}>{kb.name}</option>)}
              </select>
            </label>
          </header>

          <div className="transcript">
            {messages.length === 0 ? <div className="intro">
              {chatKnowledgeBase ? <>
                <h2>{chatKnowledgeBase.name}</h2>
                <p className="intro-meta">{plural(readyDocuments.length, 'document')} ready{kbDocuments.length > readyDocuments.length ? `, ${kbDocuments.length - readyDocuments.length} still indexing` : ''}</p>
                {kbDocuments.length > 0 && <ul className="intro-docs">{kbDocuments.slice(0, 8).map(document => <li key={document.id}><FileText size={13} /><span>{document.filename}</span>{document.page_count ? <small>{plural(document.page_count, 'page')}</small> : null}{document.status !== 'ready' && <StatusTag status={document.status} />}</li>)}</ul>}
                <div className="intro-help">
                  <p>Answers cite the page each claim comes from; click a citation to see it highlighted in the document. Text the model adds on its own is shown separately.</p>
                  <p>Start a message with <code>diagram:</code> to pull a figure from the documents, or have one drawn if none matches.</p>
                </div>
              </> : <>
                <h2>No library selected</h2>
                <p className="intro-meta">Pick a library above, or attach files to this thread with the paperclip.</p>
                {knowledgeBases.length === 0 && <button className="btn btn-primary" onClick={() => setDialog('create')}><Plus size={14} />New library</button>}
              </>}
            </div> : <div className="exchanges">
              {messages.map(message => message.role === 'user'
                ? <div className="question" key={message.id}><p>{message.content}</p></div>
                : <article className="answer" key={message.id}>
                  {renderAssistant(message)}
                  {message.citations?.length > 0 && !message.error && <div className="sources"><div className="sources-label">Sources</div><SourceList citations={message.citations} onOpen={openCitation} /></div>}
                  {message.content && !message.error && !(sending && message.id === lastId) && <div className="answer-foot">
                    {message.confidence && <ConfidenceBadge level={message.confidence} />}
                    <time>{shortDate(message.created_at)}</time>
                  </div>}
                </article>)}
              <div ref={messageEnd} />
            </div>}
          </div>

          <div className="composer-area">
            {chatDocuments.length > 0 && <div className="attachments">{chatDocuments.map(document => <span className="attachment" key={document.id}><FileText size={12} /><span title={document.filename}>{document.filename}</span><StatusTag status={document.status} error={document.error_message} /><button onClick={() => confirmDeleteDocument(document)} aria-label="Remove attachment"><X size={12} /></button></span>)}</div>}
            <form className="composer" onSubmit={event => void sendMessage(event)}>
              <textarea ref={composer} value={input} rows={1} disabled={sending}
                placeholder={chatKnowledgeBase ? `Ask about ${chatKnowledgeBase.name}` : 'Ask about the attached files'}
                onChange={event => { setInput(event.target.value); event.target.style.height = 'auto'; event.target.style.height = `${Math.min(event.target.scrollHeight, 200)}px` }}
                onKeyDown={onComposerKeyDown} />
              <div className="composer-bar">
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => chatFileInput.current?.click()} title="Attach files to this thread only"><Paperclip size={14} />Attach</button>
                <input ref={chatFileInput} type="file" multiple accept={ACCEPT} hidden onChange={event => void uploadFiles(event.target.files, 'chat')} />
                <span className="composer-hint">Enter to send · Shift+Enter for a new line</span>
                <button className="btn btn-primary btn-sm" disabled={!input.trim() || sending}>{sending ? <LoaderCircle className="spin" size={14} /> : <ArrowUp size={14} />}Ask</button>
              </div>
            </form>
            {modelOffline && <p className="composer-warning">Ollama isn't reachable, so questions will fail. Start it with <code>ollama serve</code>.</p>}
          </div>
        </section>
        {viewer && <Suspense fallback={<aside className="viewer-pane"><p className="viewer-message">Opening viewer…</p></aside>}><PdfViewer key={viewer.documentId} target={viewer} onClose={() => setViewer(null)} /></Suspense>}
      </div>}
    </main>

    {dialog === 'create' && <FormDialog title="New library" submitLabel="Create library" onSubmit={createKnowledgeBase} onClose={() => setDialog(null)} canSubmit={Boolean(newKbName.trim())}>
      <label className="field">Name<input autoFocus value={newKbName} onChange={event => setNewKbName(event.target.value)} placeholder="Orion power subsystem" maxLength={120} required /></label>
      <label className="field">Description <span className="optional">optional</span><textarea value={newKbDescription} onChange={event => setNewKbDescription(event.target.value)} placeholder="Regulator candidates for the 3.3 V rail" rows={3} maxLength={500} /></label>
    </FormDialog>}
    {dialog === 'invite' && activeKb && <FormDialog title={`Invite to ${activeKb.name}`} submitLabel="Invite" onSubmit={inviteMember} onClose={() => setDialog(null)} canSubmit={Boolean(inviteEmail.trim())}>
      <label className="field">Email<input autoFocus type="email" value={inviteEmail} onChange={event => setInviteEmail(event.target.value)} required /><small>They need a Datum account on this server first. Members can read, ask and upload; only you can delete the library.</small></label>
    </FormDialog>}
    {pending && <ConfirmDialog title={pending.title} body={pending.body} action={pending.action} onConfirm={pending.run} onClose={() => setPending(null)} />}
    {source && <SourceDialog citation={source} onClose={() => setSource(null)} />}
    {toast && <div className="toast" role="status">{toast}</div>}
  </div>
}

export default App
