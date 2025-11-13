import { useEffect, useState } from 'react'
import { api } from '../api/client'

const SUMMARY_KEYS: Array<[string, string]> = [
  ['host', 'Hôte'],
  ['port', 'Port'],
  ['llm_provider', 'Fournisseur LLM'],
  ['llm_model_path', 'Chemin modèle local'],
  ['tensorrt_llm_base_url', 'TensorRT base URL'],
  ['tensorrt_llm_model', 'TensorRT modèle'],
  ['chat_system_prompt', 'Prompt système'],
  ['duckduckgo_max_results', 'Résultats DuckDuckGo'],
  ['scheduler_tz', 'Fuseau horaire'],
]

export default function ConfigPage() {
  const [loading, setLoading] = useState(true)
  const [settings, setSettings] = useState<Record<string, any> | null>(null)
  const [cfgText, setCfgText] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  async function load() {
    setMessage(null)
    try {
      setLoading(true)
      const cfg = await api.getConfig()
      setSettings(cfg || {})
      setCfgText(JSON.stringify(cfg, null, 2))
    } catch (err) {
      if (err instanceof Error && err.message === '401') {
        setMessage('Authentification requise pour consulter la configuration.')
      } else {
        setMessage("Impossible de récupérer la configuration")
      }
      setSettings(null)
      setCfgText('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function save() {
    setMessage(null)
    try {
      const payload = JSON.parse(cfgText)
      const res = await api.updateConfig(payload)
      setSettings(res || {})
      setCfgText(JSON.stringify(res, null, 2))
      setMessage('Configuration mise à jour (à chaud)')
    } catch (err) {
      if (err instanceof Error && err.message === '401') {
        setMessage('Authentification requise pour modifier la configuration.')
      } else {
        setMessage('Échec de la mise à jour (JSON invalide ou erreur serveur)')
      }
    }
  }

  return (
    <section className="config-page">
      <h2>Configuration</h2>
      {loading ? (
        <p>Chargement…</p>
      ) : (
        <>
          {settings ? (
            <div className="config-summary">
              <h3>Résumé</h3>
              <dl>
                {SUMMARY_KEYS.map(([key, label]) => (
                  <div key={key} className="config-summary-row">
                    <dt>{label}</dt>
                    <dd>{String(settings?.[key] ?? '—')}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
          <p className="muted">
            La zone ci-dessous correspond au contenu de <code>config.json</code>. Modifiez puis enregistrez pour appliquer immédiatement.
          </p>
          <textarea
            value={cfgText}
            onChange={e => setCfgText(e.target.value)}
            rows={28}
            style={{ width: '100%', fontFamily: 'monospace' }}
            aria-label="Configuration JSON"
          />
          <div className="row">
            <button onClick={save}>Sauvegarder</button>
            <button onClick={load}>Recharger</button>
            {message ? <span>{message}</span> : null}
          </div>
        </>
      )}
    </section>
  )
}
