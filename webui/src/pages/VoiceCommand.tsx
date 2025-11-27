import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

export default function VoiceCommand() {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [text, setText] = useState('')
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [resolveRes, setResolveRes] = useState<any | null>(null)
  const recRef = useRef<any>(null)

  useEffect(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (SR) {
      setSupported(true)
      const rec = new SR()
      rec.lang = 'fr-FR'
      rec.interimResults = false
      rec.onresult = (e: any) => {
        const last = e.results?.[e.results.length - 1]
        if (!last) return
        if (last.isFinal) {
          const transcript = (last[0]?.transcript || '').trim()
          if (transcript) {
            setText((prev) => (transcript !== prev ? transcript : prev))
          }
        }
      }
      rec.onend = () => setListening(false)
      recRef.current = rec
    }
  }, [])

  function start() {
    try {
      recRef.current?.start()
      setListening(true)
      setError(null)
    } catch (e: any) {
      setError(e?.message || 'Impossible de démarrer la reconnaissance.')
    }
  }

  function stop() {
    try {
      recRef.current?.stop()
      setListening(false)
    } catch (e: any) {
      setError(e?.message || "Impossible d'arrêter la reconnaissance.")
    }
  }

  async function send() {
    if (!text.trim()) return
    try {
      const res = await api.jeedomResolve({ query: text.trim(), execute: true })
      setResolveRes(res)
      if (res?.executed?.status_code) {
        setAnswer(`Exec cmd ${res.executed.id} status ${res.executed.status_code} source=${res.executed.source ?? '?'}`)
      } else {
        setAnswer('Aucune exécution')
      }
      setError(null)
    } catch (e: any) {
      setError(e?.message || String(e))
    }
  }

  return (
    <section>
      <h2>Commande vocale</h2>
      {!supported ? (
        <p className="muted">Reconnaissance vocale non supportée sur ce navigateur.</p>
      ) : (
        <div className="row">
          {!listening ? (
            <button onClick={start} aria-label="Démarrer l’écoute">Démarrer</button>
          ) : (
            <button onClick={stop} aria-label="Arrêter l’écoute">Arrêter</button>
          )}
          <button onClick={send} disabled={!text.trim()}>Envoyer</button>
        </div>
      )}
      {error ? <p className="danger">{error}</p> : null}
      <p>{text}</p>
      {answer ? (
        <div className="panel" style={{ marginTop: '.5rem' }}>
          <strong>Réponse</strong>
          <p>{answer}</p>
        </div>
      ) : null}
      {resolveRes ? (
        <pre
          style={{
            background: '#f5f2ff',
            border: '1px solid #d6ccf5',
            padding: '0.5rem',
            fontSize: '0.85rem',
            whiteSpace: 'pre-wrap',
            marginTop: '0.5rem',
          }}
        >
          {JSON.stringify(resolveRes, null, 2)}
        </pre>
      ) : null}
    </section>
  )
}
