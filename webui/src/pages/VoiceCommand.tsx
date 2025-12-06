import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

export default function VoiceCommand() {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [text, setText] = useState('')
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [resolveRes, setResolveRes] = useState<any | null>(null)
  const [status, setStatus] = useState<{ configured: boolean; reachable: boolean; message?: string; status_code?: number } | null>(null)
  const [cmdId, setCmdId] = useState('')
  const [cmdValue, setCmdValue] = useState('')
  const [cmdResult, setCmdResult] = useState<string | null>(null)
  const [savingIntent, setSavingIntent] = useState(false)
  const [showActionsOnly, setShowActionsOnly] = useState(false)
  const [simulateOnly, setSimulateOnly] = useState(false)
  const recRef = useRef<any>(null)

  useEffect(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (!SR) return
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
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const st = await api.jeedomStatus()
        setStatus(st)
      } catch {
        setStatus(null)
      }
    })()
  }, [])

  function start() {
    try {
      recRef.current?.start()
      setListening(true)
      setError(null)
      setInfo(null)
    } catch (e: any) {
      setError(e?.message || 'Impossible de demarrer la reconnaissance.')
    }
  }

  function stop() {
    try {
      recRef.current?.stop()
      setListening(false)
    } catch (e: any) {
      setError(e?.message || "Impossible d'arreter la reconnaissance.")
    }
  }

  async function copyToClipboard(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value)
      setInfo(`Copie ${label} ok`)
    } catch (e: any) {
      setError(e?.message || 'Copie impossible')
    }
  }

  async function send() {
    if (!text.trim()) return
    try {
      const res = await api.jeedomResolve({ query: text.trim(), execute: !simulateOnly })
      setResolveRes(res)
      const parts: string[] = []
      if (res?.executed?.status_code) {
        parts.push(`Cmd ${res.executed.id} -> ${res.executed.status_code} (source ${res.executed.source ?? '?'})`)
      } else {
        parts.push('Aucune execution')
      }
      if (typeof res?.matched_count === 'number') {
        parts.push(`candidats=${res.matched_count}`)
      }
      if (res?.status_code && res.status_code !== 200) {
        parts.push(`Jeedom a repondu ${res.status_code}`)
      }
      if (res?.error) {
        parts.push(`Erreur API: ${res.error}`)
      }
      setAnswer(parts.join(' | '))
      setError(null)
      setInfo(null)
    } catch (e: any) {
      const detail = e?.detail
      if (detail?.error?.message) {
        setError(`${e.status || ''} ${detail.error.message}`)
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(e?.message || String(e))
      }
    }
  }

  async function preview() {
    if (!text.trim()) return
    try {
      const res = await api.jeedomResolve({ query: text.trim(), execute: false })
      setResolveRes(res)
      const best = Array.isArray(res?.matched) && res.matched.length > 0 ? res.matched[0] : null
      const parts: string[] = []
      parts.push(`Apercu: ${res?.matched_count ?? 0} candidat(s)`)
      if (best?.score) {
        parts.push(`meilleur score=${best.score}`)
      }
      if (best?.name) {
        parts.push(`cmd=${best.name}`)
      }
      if (best?.eq_name) {
        parts.push(`equipement=${best.eq_name}`)
      }
      setAnswer(parts.join(' | '))
      setError(null)
      setInfo(null)
    } catch (e: any) {
      const detail = e?.detail
      if (detail?.error?.message) {
        setError(`${e.status || ''} ${detail.error.message}`)
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(e?.message || String(e))
      }
    }
  }

  async function saveIntent() {
    if (savingIntent) return
    const targetId =
      resolveRes?.executed?.id ||
      (Array.isArray(resolveRes?.matched) && resolveRes.matched[0]?.id) ||
      ''
    if (!text.trim() || !targetId) {
      setInfo("Aucune commande a enregistrer")
      return
    }
    try {
      setSavingIntent(true)
      await api.jeedomIntentAdd({ query: text.trim(), cmd_id: String(targetId) })
      setInfo('Intent enregistre')
    } catch (e: any) {
      const detail = e?.detail
      if (detail?.error?.message) {
        setError(`${e.status || ''} ${detail.error.message}`)
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(e?.message || String(e))
      }
    } finally {
      setSavingIntent(false)
    }
  }

  function clearAll() {
    setText('')
    setAnswer('')
    setResolveRes(null)
    setInfo(null)
    setError(null)
    setCmdResult(null)
    setSavingIntent(false)
  }

  async function runCommandById() {
    if (!cmdId.trim()) return
    try {
      const res = await api.jeedomRunCommand(cmdId.trim(), cmdValue ? cmdValue : undefined)
      setCmdResult(`Cmd ${cmdId.trim()} -> ${res.status_code ?? 'ok'} | ${res.raw_preview ?? ''}`)
      setError(null)
    } catch (e: any) {
      const detail = e?.detail
      if (detail?.error?.message) {
        setError(`${e.status || ''} ${detail.error.message}`)
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(e?.message || String(e))
      }
    }
  }

  const matches = Array.isArray(resolveRes?.matched) ? resolveRes.matched : []
  const filteredMatches = showActionsOnly ? matches.filter((m: any) => (m?.type || '').toLowerCase() === 'action') : matches
  const bestMatch = filteredMatches[0] || matches[0] || null
  const confidence = bestMatch?.score

  return (
    <section>
      <h2>Console vocale</h2>

      <div className="row" style={{ gap: '.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {supported ? (
          !listening ? (
            <button onClick={start} aria-label="Demarrer l'ecoute">Demarrer</button>
          ) : (
            <button onClick={stop} aria-label="Arreter l'ecoute" className="secondary">Arreter</button>
          )
        ) : (
          <span className="muted">Reconnaissance vocale non supportee sur ce navigateur.</span>
        )}
        <button onClick={send} disabled={!text.trim()}>Envoyer</button>
        <button onClick={preview} disabled={!text.trim()} className="secondary">Apercu (sans exec)</button>
        <button onClick={clearAll} className="ghost">Effacer</button>
      </div>
      <div className="row" style={{ gap: '.5rem', alignItems: 'center', flexWrap: 'wrap', marginTop: '.35rem' }}>
        <label className="checkbox" style={{ gap: '.35rem', alignItems: 'center' }}>
          <input type="checkbox" checked={simulateOnly} onChange={(e) => setSimulateOnly(e.target.checked)} />
          Mode simulation (aucune execution)
        </label>
      </div>

      <div style={{ marginTop: '.35rem' }}>
        {status ? (
          <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap', alignItems: 'center', margin: '0' }}>
            <span className="pill">{status.configured ? 'Jeedom configure' : 'Jeedom non configure'}</span>
            <span className={`pill ${status.reachable ? 'success' : 'warning'}`}>
              {status.reachable ? 'Jeedom joignable' : 'Jeedom non joignable'}
            </span>
            {status.message ? <span className="muted">{status.message}</span> : null}
          </div>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Statut Jeedom indisponible (connectez-vous ?).</p>
        )}
      </div>

      <div style={{ marginTop: '.75rem' }}>
        <label style={{ display: 'block', fontWeight: 600, marginBottom: '.25rem' }}>
          Texte a envoyer (dictation ou saisie)
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Dictez ou saisissez une commande Jeedom (ex: allume lumiere bureau)..."
          rows={5}
          style={{
            width: '100%',
            fontFamily: 'inherit',
            padding: '.5rem',
            resize: 'vertical',
            minHeight: '160px',
            lineHeight: '1.5',
            fontSize: '1rem',
          }}
        />
        <div className="row" style={{ gap: '.5rem', marginTop: '.25rem', flexWrap: 'wrap' }}>
          <span className="muted">Etat: {listening ? 'En ecoute micro' : supported ? 'Pret' : 'Non supporte'}</span>
          {navigator.clipboard ? (
            <button
              type="button"
              className="ghost"
              onClick={() => copyToClipboard(text, 'texte')}
              disabled={!text.trim()}
            >
              Copier le texte
            </button>
          ) : null}
        </div>
      </div>

      {error ? <p className="danger">{error}</p> : null}
      {info ? <p className="info">{info}</p> : null}

      {text.trim() ? (
        <div className="panel" style={{ marginTop: '.75rem' }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem' }}>
            <strong>Derniere question</strong>
            {navigator.clipboard ? (
              <button className="ghost" onClick={() => copyToClipboard(text, 'question')}>Copier la question</button>
            ) : null}
          </div>
          <pre
            style={{
              marginTop: '.35rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: '1.55',
              background: '#f7f7fb',
              border: '1px solid #e5e7eb',
              borderRadius: '6px',
              padding: '.75rem',
              fontFamily: 'var(--font-mono, monospace)',
              maxHeight: '30vh',
              overflowY: 'auto',
              fontSize: '1rem',
            }}
          >
            {text}
          </pre>
        </div>
      ) : null}

      {answer ? (
        <div className="panel" style={{ marginTop: '.75rem' }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>Reponse</strong>
            {navigator.clipboard ? (
              <button className="ghost" onClick={() => copyToClipboard(answer, 'reponse')}>Copier</button>
            ) : null}
          </div>
          <pre
            style={{
              marginTop: '.35rem',
              fontFamily: 'var(--font-mono, monospace)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: '1.6',
              background: '#0d101c',
              color: '#e6edf7',
              padding: '.8rem',
              borderRadius: '6px',
              maxHeight: '32vh',
              overflowY: 'auto',
              fontSize: '1rem',
            }}
          >
            {answer}
          </pre>
        </div>
      ) : null}

      {resolveRes ? (
        <div className="panel" style={{ marginTop: '.75rem' }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem' }}>
            <div>
              <strong>Resultat detaille</strong>
              <p className="muted" style={{ margin: 0 }}>
                Exec: {resolveRes.executed ? `${resolveRes.executed.id} (${resolveRes.executed.status_code ?? 'err'})` : 'aucune'}
                {' | '}Matches: {resolveRes.matched_count ?? 0}
                {' | '}Top: {bestMatch ? `${bestMatch.name ?? bestMatch.id ?? 'inconnu'} (score ${bestMatch.score ?? '?'})` : 'n/a'}
                {bestMatch?.eq_name ? ` | Eq: ${bestMatch.eq_name}` : ''}
                {bestMatch?.object_name ? ` | Objet: ${bestMatch.object_name}` : ''}
                {resolveRes.need_confirmation ? ' | Confirmation requise' : ''}
              </p>
            </div>
            {navigator.clipboard ? (
              <button
                className="ghost"
                onClick={() => copyToClipboard(JSON.stringify(resolveRes, null, 2), 'resultat')}
              >
                Copier le JSON
              </button>
            ) : null}
          </div>
          <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '.35rem' }}>
            <label className="checkbox" style={{ gap: '.35rem', alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={showActionsOnly}
                onChange={(e) => setShowActionsOnly(e.target.checked)}
              />
              Actions uniquement
            </label>
            {confidence ? <span className="pill">{`Confiance ${confidence}`}</span> : null}
            <button onClick={saveIntent} disabled={!text.trim() || (!resolveRes?.executed && !bestMatch?.id) || savingIntent}>
              {savingIntent ? 'Enregistrement...' : 'Enregistrer cette phrase'}
            </button>
          </div>
          <pre
            style={{
              background: '#0d101c',
              color: '#e6edf7',
              padding: '0.85rem',
              fontSize: '0.95rem',
              whiteSpace: 'pre-wrap',
              marginTop: '.5rem',
              borderRadius: '6px',
              overflow: 'auto',
              maxHeight: '420px',
            }}
          >
            {JSON.stringify(resolveRes, null, 2)}
          </pre>
        </div>
      ) : null}

      <div className="panel" style={{ marginTop: '.75rem' }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem' }}>
          <strong>Tester une commande par ID</strong>
          {cmdResult ? <span className="muted">{cmdResult}</span> : null}
        </div>
        <div className="row" style={{ gap: '.5rem', marginTop: '.35rem', flexWrap: 'wrap' }}>
          <input
            value={cmdId}
            onChange={(e) => setCmdId(e.target.value)}
            placeholder="id Jeedom (ex: 1234)"
            style={{ minWidth: '160px' }}
          />
          <input
            value={cmdValue}
            onChange={(e) => setCmdValue(e.target.value)}
            placeholder="valeur/slider (optionnel)"
            style={{ minWidth: '160px' }}
          />
          <button onClick={runCommandById} disabled={!cmdId.trim()}>Executer</button>
        </div>
        <p className="muted" style={{ marginTop: '.25rem' }}>
          Utile pour verifier rapidement la connexion Jeedom sans reconnaissance vocale.
        </p>
      </div>
    </section>
  )
}
