import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { api } from '../api/client';

interface Conversation {
  id: number;
  title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_message?: string | null;
}

interface MessageMetadata {
  classification?: unknown;
  search_results_count?: number;
  latency_ms?: number;
  qa_id?: number;
  match?: string;
  speculative?: boolean;
  [key: string]: unknown;
}

interface Message {
  id: number;
  role: string;
  content: string;
  origin: string;
  is_variable?: boolean;
  metadata?: MessageMetadata;
  created_at?: string;
}

const MATCH_LABELS: Record<string, string> = {
  fingerprint: 'empreinte exacte',
  tokens: 'tokens similaires',
  embedding: 'vecteurs proches',
  alias: 'alias enregistré',
};

function formatConversationTitle(name?: string | null, fallback?: string) {
  if (name && name.trim().length) return name.trim();
  return fallback ?? 'Conversation';
}

function originLabel(origin: string | undefined) {
  if (!origin) return 'Origine inconnue';
  switch (origin) {
    case 'database':
      return 'Mémoire';
    case 'alias':
      return 'Mémoire (alias)';
    case 'internet':
      return 'Internet';
    case 'llm':
    case 'tensorrt_llm':
      return 'LLM';
    case 'user':
      return 'Utilisateur';
    default:
      return origin;
  }
}

function originClass(origin: string | undefined) {
  if (!origin) return 'origin-unknown';
  return `origin-${origin.toLowerCase().replace(/[^a-z0-9_-]+/g, '-')}`;
}

function messageClasses(msg: Message) {
  const classes = ['chat-msg', msg.role === 'user' ? 'user' : 'assistant'];
  if (msg.origin) classes.push(originClass(msg.origin));
  if (msg.is_variable) classes.push('variable');
  return classes.join(' ');
}

function formatLatency(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '-';
  const seconds = value / 1000;
  return seconds >= 10 ? `${seconds.toFixed(1)} s` : `${seconds.toFixed(2)} s`;
}

function describeMatch(match: unknown): string | null {
  if (typeof match !== 'string' || !match) return null;
  return MATCH_LABELS[match] ?? match;
}

interface ChatPageProps {
  logged?: boolean;
}

export default function ChatPage({ logged = false }: ChatPageProps): JSX.Element {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!messages.length) return;
    const handle = window.setTimeout(() => {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, 20);
    return () => window.clearTimeout(handle);
  }, [messages]);

  useEffect(() => {
    if (!logged) {
      (true);
      return;
    }
    api.getConfig()
      .then((cfg: any) => {
        if (cfg && typeof cfg.llm_speculative_enabled === 'boolean') {
          (Boolean(cfg.llm_speculative_enabled));
        }
      })
      .catch(() => undefined);
  }, [logged]);


  async function loadConversations(selectFirst = false) {
    if (!logged) {
      return;
    }
    try {
      setRefreshing(true);
      const data = await api.chatConversations(50, 0);
      const items = Array.isArray(data?.items) ? (data.items as Conversation[]) : [];
      setConversations(items);
      setStatus(null);
      if (selectFirst && items.length && selectedId == null) {
        await handleSelect(items[0].id);
      }
    } catch (err) {
      setStatus("Impossible de charger les conversations");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (!logged) {
      setConversations([]);
      setMessages([]);
      setSelectedId(null);
      return;
    }
    void loadConversations(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logged]);

  async function fetchMessages(convId: number) {
    if (!logged) {
      return;
    }
    try {
      const data = await api.conversationMessages(convId, 200);
      const items = Array.isArray(data?.items) ? (data.items as Message[]) : [];
      setMessages(items);
      setStatus(null);
      setTimeout(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
      }, 10);
    } catch (err) {
      setStatus("Impossible de charger les messages");
    }
  }

  async function handleSelect(convId: number) {
    if (!logged) return;
    setSelectedId(convId);
    await fetchMessages(convId);
  }

  async function handleSend() {
    if (!logged || !question.trim()) return;
    const convId = selectedId;
    setLoading(true);
    try {
      const response = await api.chatQuery({
        question: question.trim(),
        conversation_id: convId ?? undefined,
      });
      if (response?.conversation_id) {
        await Promise.all([fetchMessages(response.conversation_id), loadConversations()]);
      }
      setQuestion('');
      setLastLatencyMs(typeof response?.latency_ms === 'number' ? response.latency_ms : null);
      setStatus(null);
      textareaRef.current?.focus();
    } catch (err) {
      const statusCode = typeof (err as any)?.status === 'number' ? (err as any).status : undefined;
      if (statusCode === 503) {
        setStatus('LLM indisponible : vérifiez "llm_model_path" ou TensorRT-LLM');
      } else if (statusCode === 401) {
        setStatus('Authentification requise pour interroger le LLM');
      } else if (err instanceof Error) {
        setStatus(`Échec de la requête LLM (${err.message})`);
      } else {
        setStatus('Échec de la requête LLM');
      }
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter') return;
    if (event.shiftKey) return;
    event.preventDefault();
    void handleSend();
  }

  async function handleNewConversation() {
    try {
      const conv = await api.createConversation();
      const convId = Number(conv?.id);
      if (!Number.isNaN(convId)) {
        await loadConversations();
        await handleSelect(convId);
      }
    } catch (err) {
      setStatus("Impossible de créer la conversation");
    }
  }

  async function handleDelete(convId: number) {
    if (!window.confirm('Supprimer cette conversation ?')) return;
    try {
      await api.deleteConversation(convId);
      if (selectedId === convId) {
        setSelectedId(null);
        setMessages([]);
      }
      await loadConversations(true);
    } catch (err) {
      setStatus("Impossible de supprimer la conversation");
    }
  }

  const conversationName = useMemo(() => {
    const conv = conversations.find(c => c.id === selectedId);
    return formatConversationTitle(conv?.title, conv ? `Conversation #${conv.id}` : undefined);
  }, [conversations, selectedId]);

  return (
    <div className="chat-layout">
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <h2>Conversations</h2>
          <button onClick={handleNewConversation}>Nouvelle</button>
        </div>
        <div className="chat-list" aria-label="Liste des conversations">
          {conversations.map(conv => (
            <div
              key={conv.id}
              className={conv.id === selectedId ? 'chat-list-item active' : 'chat-list-item'}
            >
              <button type="button" onClick={() => handleSelect(conv.id)}>
                <span>{formatConversationTitle(conv.title, `Conversation #${conv.id}`)}</span>
                {conv.updated_at ? <small>{new Date(conv.updated_at).toLocaleString()}</small> : null}
              </button>
              <button
                type="button"
                className="chat-list-delete"
                onClick={event => {
                  event.stopPropagation();
                  void handleDelete(conv.id);
                }}
                aria-label={`Supprimer la conversation ${conv.id}`}
              >
                ✕
              </button>
            </div>
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
          {messages.map(msg => {
            const messageLatency = typeof msg.metadata?.latency_ms === 'number' ? msg.metadata.latency_ms : null;
            const matchLabel = describeMatch(msg.metadata?.match);
            return (
              <article key={msg.id} className={messageClasses(msg)}>
                <div className="chat-msg-header">
                  <span className="chat-msg-role">{msg.role === 'user' ? 'Vous' : 'Assistant'}</span>
                  <span className={`chat-msg-origin ${originClass(msg.origin)}`}>{originLabel(msg.origin)}</span>
                  {msg.is_variable ? <span className="chat-msg-flag">Variable</span> : null}
                  {msg.metadata?.speculative ? <span className="chat-msg-flag">Spéculatif</span> : null}
                </div>
                <p>{msg.content}</p>
                {msg.metadata?.classification ? (
                  <details>
                    <summary>Classification</summary>
                    <pre>{JSON.stringify(msg.metadata.classification, null, 2)}</pre>
                  </details>
                ) : null}
                {typeof msg.metadata?.search_results_count === 'number' && msg.metadata.search_results_count > 0 ? (
                  <small className="muted">Résultats web utilisés : {msg.metadata.search_results_count}</small>
                ) : null}
                {matchLabel ? (
                  <small className="muted">Réutilisation : {matchLabel}</small>
                ) : null}
                {msg.role !== 'user' && messageLatency != null ? (
                  <span className="chat-msg-latency" aria-label="Temps de réponse">Temps de réponse : {formatLatency(messageLatency)}</span>
                ) : null}
              </article>
            );
          })}
          <div ref={endRef} />
          {!messages.length && <p className="muted">Sélectionnez une conversation ou posez une question.</p>}
        </div>
        <footer className="chat-input">
          <label className="chat-spec-toggle">
            <input
              type="checkbox"
              checked={true}
              onChange={event => (event.target.checked)}
            />
            Mode sp�culatif activ�
          </label>
          <textarea
            ref={textareaRef}
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question…"
            rows={3}
            aria-label="Question"
          />
          <button onClick={handleSend} disabled={loading || !question.trim()}>
            {loading ? 'Envoi…' : 'Envoyer'}
          </button>
          <small className="chat-input-hint muted">Entrée pour envoyer • Maj+Entrée pour nouvelle ligne</small>
        
        </footer>

        {lastLatencyMs != null ? (
          <p className="chat-latency muted">Dernière réponse en {formatLatency(lastLatencyMs)}</p>
        ) : null}
        {status ? <p className="error">{status}</p> : null}
      </section>
    </div>
  );
}

