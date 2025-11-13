import { useState } from 'react'
import { api } from '../api/client'

export default function LLMConsole() {
  const [prompt, setPrompt] = useState('Bonjour !')
  const [answer, setAnswer] = useState('')
  const [origin, setOrigin] = useState<string | undefined>(undefined)
  const [classification, setClassification] = useState<any>(null)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function runQuery() {
    if (!prompt.trim()) return
    setLoading(true)
    setError(null)
    setAnswer('')
    setOrigin(undefined)
    setClassification(null)
    setSearchResults([])
    try {
      const data = await api.chatQuery(prompt.trim())
      setAnswer(String(data.answer ?? data.answer_message?.content ?? ''))
      setOrigin(typeof data.origin === 'string' ? data.origin : data.answer_message?.origin)
      if (data.classification) setClassification(data.classification)
      if (Array.isArray(data.search_results)) setSearchResults(data.search_results)
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section>
      <h2>Console LLM (via /chat/query)</h2>
      <textarea
        value={prompt}
        onChange={e => setPrompt(e.target.value)}
        rows={6}
        style={{ width: '100%' }}
        aria-label="Invite"
      />
      <div className="row" style={{ marginTop: '.75rem', gap: '.5rem' }}>
        <button onClick={runQuery} disabled={loading}>
          {loading ? 'En cours…' : 'Envoyer'}
        </button>
        <span className="muted">Streaming temps réel désactivé (utiliser la page Chat).</span>
      </div>
      {error ? <p className="danger">{error}</p> : null}
      {origin ? <p className="muted">Provenance : {origin}</p> : null}
      <pre aria-live="polite" style={{ whiteSpace: 'pre-wrap', minHeight: '6rem' }}>{answer}</pre>
      {classification ? (
        <details style={{ marginTop: '.5rem' }}>
          <summary>Classification</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(classification, null, 2)}</pre>
        </details>
      ) : null}
      {searchResults.length ? (
        <details style={{ marginTop: '.5rem' }}>
          <summary>Résultats web ({searchResults.length})</summary>
          <ol>
            {searchResults.map((item, idx) => (
              <li key={idx}>
                <strong>{item.title || 'Sans titre'}</strong>
                {item.href ? (
                  <div><a href={item.href} target="_blank" rel="noreferrer">{item.href}</a></div>
                ) : null}
                <div className="muted">{item.body}</div>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  )
}
