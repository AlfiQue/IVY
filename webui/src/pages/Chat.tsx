import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'

interface Conversation {
  id: number
  title?: string | null
  created_at?: string
  updated_at?: string
  last_message?: string | null
}

interface Message {
  id: number
  role: string
  content: string
  origin: string
  is_variable?: boolean
  metadata?: any
  created_at?: string
}

function formatLabel(name?: string | null, fallback?: string) {
  if (name && name.trim().length) return name.trim()
  return fallback || 'Conversation'
}

function originLabel(origin: string) {
  if (origin === 'database') return 'Mémoire'
  if (origin === 'internet') return 'Internet'
  if (origin === 'llm' || origin === 'tensorrt_llm') return 'LLM'
  if (origin === 'user') return 'Utilisateur'
  return origin
}

function originClass(origin: string | undefined) {
  if (!origin) return 'origin-unknown'
  return `origin-${origin.toLowerCase().replace(/[^a-z0-9_-]+/g, '-')}`
}

function messageClasses(msg: Message) {
  const classes = ['chat-msg', msg.role === 'user' ? 'user' : 'bot']
  if (msg.origin) classes.push(originClass(msg.origin))
  if (msg.is_variable) classes.push('variable')
  return classes.join(' ')
}

function formatLatency(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '-';
  const seconds = value / 1000;
  const formatted = seconds >= 10 ? seconds.toFixed(1) : seconds.toFixed(2);
  return `${formatted} s`;
}

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const endRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!messages.length) return
    const cleanup = window.setTimeout(() => {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }, 10)
    return () => window.clearTimeout(cleanup)
  }, [messages])

  async function loadConversations(selectFirst = false) {
    try {
      setRefreshing(true)
      const data = await api.chatConversations(50, 0)
      const items = Array.isArray(data?.items) ? data.items : []
      setConversations(items)
      if (selectFirst && items.length && selectedId == null) {
        await handleSelect(items[0].id)
      }
    } catch (err) {
      setStatus('Impossible de charger les conversations')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadConversations(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function fetchMessages(convId: number) {
    try {
      const data = await api.conversationMessages(convId, 200)
      const items = Array.isArray(data?.items) ? data.items : []
      setMessages(items)
    } catch (err) {
      setMessages([])
      setStatus('Impossible de charger les messages')
    }
  }

  async function handleSelect(id: number) {
    setSelectedId(id)
    setStatus(null)
    await fetchMessages(id)
  }

  async function handleSend() {
    if (!question.trim()) return
    if (loading) return
    setLatencyMs(null)
    const startedAt = performance.now()
    try {
      setLoading(true)
      setStatus(null)
      const result = await api.chatQuery(question.trim(), selectedId ?? undefined)
      setLatencyMs(performance.now() - startedAt)
      const convId = result?.conversation_id
      setQuestion('')
      if (convId != null) {
        setSelectedId(convId)
        await fetchMessages(convId)
        await loadConversations()
      }
    } catch (err) {
      if (err instanceof Error) {
        if (err.message === '503') {
          setStatus('LLM indisponible : vérifiez `llm_model_path` ou TensorRT-LLM.')
        } else if (err.message === '401') {
          setStatus('Authentification requise pour interroger le LLM.')
        } else {
          setStatus(`Échec de la requête LLM (${err.message})`)
        }
      } else {
        setStatus('Échec de la requête LLM')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleNewConversation() {
    try {
      const conv = await api.createConversation(null)
      const convId = Number(conv?.id)
      if (!Number.isNaN(convId)) {
        await loadConversations()
        await handleSelect(convId)
      }
    } catch (err) {
      setStatus('Impossible de créer la conversation')
    }
  }

  const conversationName = useMemo(() => {
    const conv = conversations.find(c => c.id === selectedId)
    return formatLabel(conv?.title, conv ? `Conversation #${conv.id}` : undefined)
  }, [conversations, selectedId])

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <h2>Conversations</h2>
          <button onClick={handleNewConversation}>Nouvelle</button>
        </div>
        <div className="chat-list" aria-label="Liste des conversations">
          {conversations.map(conv => (
            <button
              key={conv.id}
              className={conv.id === selectedId ? 'chat-list-item active' : 'chat-list-item'}
              onClick={() => handleSelect(conv.id)}
            >
              <span>{formatLabel(conv.title, `Conversation #${conv.id}`)}</span>
              {conv.updated_at ? <small>{new Date(conv.updated_at).toLocaleString()}</small> : null}
            </button>
          ))}
          {!conversations.length && <p className="muted">Aucune conversation enregistrée.</p>}
        </div>
        <button className="chat-refresh" onClick={() => loadConversations()}>Rafraîchir</button>
        {refreshing && <small className="muted">Mise à jour…</small>}
      </aside>
      <section className="chat-main">
        <header className="chat-header">
          <h1>{conversationName}</h1>
        </header>
        <div className="chat-messages" aria-live="polite">
          {messages.map(msg => (
            <article key={msg.id} className={messageClasses(msg)}>
              <div className="chat-msg-header">
                <span className="chat-msg-role">{msg.role === 'user' ? 'Vous' : 'Assistant'}</span>
                <span className={`chat-msg-origin ${originClass(msg.origin)}`}>{originLabel(msg.origin)}</span>
                {msg.is_variable ? <span className="chat-msg-flag">Variable</span> : null}
              </div>
              <p>{msg.content}</p>
              {msg.metadata?.classification ? (
                <details>
                  <summary>Classification</summary>
                  <pre>{JSON.stringify(msg.metadata.classification, null, 2)}</pre>
                </details>
              ) : null}
              {msg.metadata?.search_results_count ? (
                <small className="muted">Résultats web utilisés : {msg.metadata.search_results_count}</small>
              ) : null}
            </article>
          ))}
          <div ref={endRef} />
          {!messages.length && <p className="muted">Sélectionnez une conversation ou posez une question.</p>}
        </div>
        <footer className="chat-input">
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="Posez votre question..."
            rows={3}
            aria-label="Question"
          />
          <button onClick={handleSend} disabled={loading || !question.trim()}>
            {loading ? 'Envoi…' : 'Envoyer'}
          </button>
        </footer>
        {latencyMs != null ? (<p className="chat-latency muted">Réponse en {formatLatency(latencyMs)}</p>) : null}
        {status ? <p className="error">{status}</p> : null}
      </section>
    </div>
  )
}
