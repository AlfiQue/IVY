import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { api } from '../api/client'

const SUMMARY_KEYS: Array<[string, string]> = [
  ['host', 'Hôte'],
  ['port', 'Port'],
  ['llm_provider', 'Fournisseur LLM'],
  ['llm_model_path', 'Chemin du modèle local'],
  ['llm_context_tokens', 'Jetons de contexte LLM'],
  ['llm_max_output_tokens', 'Jetons de sortie max'],
  ['llm_temperature', 'Température'],
  ['llm_speculative_enabled', 'Décodage spéculatif'],
  ['llm_speculative_model_path', 'Modèle spéculatif'],
  ['llm_speculative_max_draft_tokens', 'Jetons brouillon max'],
  ['llm_speculative_context_tokens', 'Contexte spéculatif'],
  ['llm_speculative_n_gpu_layers', 'Couches GPU spéculatives'],
  ['tensorrt_llm_model', 'Modèle TensorRT'],
  ['tensorrt_llm_base_url', 'Base URL TensorRT'],
  ['tensorrt_llm_chat_endpoint', 'Endpoint TensorRT'],
  ['duckduckgo_max_results', 'Résultats DuckDuckGo'],
  ['scheduler_tz', 'Fuseau horaire'],
  ['voice_tts_voice', 'Voix TTS'],
  ['voice_tts_length_scale', 'Vitesse TTS'],
  ['voice_tts_pitch', 'Pitch TTS'],
]

const TTS_PRESETS: Array<{ label: string; value: string }> = [
  { label: 'UPMC (medium)', value: 'fr-FR-piper-high/fr/fr_FR/upmc/medium' },
  { label: 'Jessica UPMC (high)', value: 'fr-FR-piper-high/fr/fr_FR/jessica/high' },
]

type SettingsPayload = Record<string, unknown>

export default function ConfigPage(): JSX.Element {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const [ttsSaving, setTtsSaving] = useState(false)
  const [settings, setSettings] = useState<SettingsPayload | null>(null)
  const [cfgText, setCfgText] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const [ttsVoice, setTtsVoice] = useState('')
  const [ttsSpeed, setTtsSpeed] = useState(0.92)
  const [ttsPitch, setTtsPitch] = useState(0.85)

  async function load() {
    setMessage(null)
    try {
      setLoading(true)
      const cfg = await api.getConfig()
      setSettings(cfg || {})
      setCfgText(JSON.stringify(cfg ?? {}, null, 2))
      setTtsVoice(String(cfg?.voice_tts_voice ?? ''))
      setTtsSpeed(Number(cfg?.voice_tts_length_scale ?? 0.92))
      setTtsPitch(Number(cfg?.voice_tts_pitch ?? 0.85))
    } catch (err) {
      if (err instanceof Error && err.message === '401') {
        setMessage('Authentification requise pour consulter la configuration.')
      } else {
        setMessage('Impossible de récupérer la configuration.')
      }
      setSettings(null)
      setCfgText('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => setMessage('Impossible de récupérer la configuration.'))
  }, [])

  async function save() {
    setSaving(true)
    setMessage(null)
    try {
      const payload = JSON.parse(cfgText)
      const res = await api.updateConfig(payload)
      setSettings(res || {})
      setCfgText(JSON.stringify(res ?? payload, null, 2))
      setMessage('Configuration mise à jour (à chaud).')
    } catch (err) {
      if (err instanceof Error && err.message === '401') {
        setMessage('Authentification requise pour modifier la configuration.')
      } else {
        setMessage('Échec de la mise à jour (JSON invalide ou erreur serveur).')
      }
    } finally {
      setSaving(false)
    }
  }

  function openFileDialog() {
    fileInputRef.current?.click()
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setImporting(true)
    setMessage(null)
    try {
      const result = await api.importConfig(file)
      const cfg = (result as any)?.config ?? result ?? {}
      setSettings(cfg)
      setCfgText(JSON.stringify(cfg, null, 2))
      setTtsVoice(String(cfg?.voice_tts_voice ?? ''))
      setTtsSpeed(Number(cfg?.voice_tts_length_scale ?? 0.92))
      setTtsPitch(Number(cfg?.voice_tts_pitch ?? 0.85))
      setMessage('Configuration importée. Pensez à redémarrer le serveur pour tout appliquer.')
    } catch (err) {
      const detail = (err as any)?.detail
      if ((err as any)?.status === 401) {
        setMessage('Authentification requise pour importer un fichier.')
      } else if (detail?.error?.message) {
        setMessage(`Import impossible : ${detail.error.message}.`)
      } else if (typeof detail === 'string' && detail) {
        setMessage(`Import impossible : ${detail}`)
      } else {
        setMessage('Import impossible (fichier invalide ou erreur serveur).')
      }
    } finally {
      setImporting(false)
    }
  }

  async function restart() {
    setRestarting(true)
    setMessage('Redémarrage programmé – la connexion va se couper quelques secondes.')
    try {
      await api.restartServer()
    } catch (err) {
      if ((err as any)?.status === 401) {
        setMessage('Authentification requise pour redémarrer le serveur.')
      } else if ((err as any)?.status === 403) {
        setMessage('Protection CSRF manquante : rechargez la page puis réessayez.')
      } else {
        setMessage('Impossible de redémarrer automatiquement le serveur.')
      }
    } finally {
      setRestarting(false)
    }
  }

  async function applyTTS() {
    setTtsSaving(true)
    setMessage(null)
    try {
      const payload = {
        voice_tts_voice: ttsVoice,
        voice_tts_length_scale: Number(ttsSpeed),
        voice_tts_pitch: Number(ttsPitch),
      }
      const res = await api.updateConfig(payload)
      setSettings(res || {})
      setCfgText(JSON.stringify(res ?? payload, null, 2))
      setMessage('Paramètres TTS mis à jour.')
    } catch (err) {
      if ((err as any)?.status === 401) {
        setMessage('Authentification requise pour modifier les paramètres TTS.')
      } else {
        setMessage('Impossible de mettre à jour les paramètres TTS.')
      }
    } finally {
      setTtsSaving(false)
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
                    <dd>{String(settings?.[key] ?? '-')}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}

          <div className="card">
            <h3>Réglages TTS (console vocale)</h3>
            <div className="row" style={{ gap: '1rem', flexWrap: 'wrap' }}>
              <label style={{ flex: '1 0 240px' }}>
                Voix Piper
                <select value={ttsVoice} onChange={(e) => setTtsVoice(e.target.value)}>
                  <option value="">-- personnalisée --</option>
                  {TTS_PRESETS.map((preset) => (
                    <option key={preset.value} value={preset.value}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ flex: '1 0 160px' }}>
                Vitesse (0.5 - 1.5)
                <input
                  type="number"
                  min={0.5}
                  max={1.5}
                  step={0.01}
                  value={ttsSpeed}
                  onChange={(e) => setTtsSpeed(Number(e.target.value))}
                />
              </label>
              <label style={{ flex: '1 0 160px' }}>
                Pitch (0.1 - 2.0)
                <input
                  type="number"
                  min={0.1}
                  max={2}
                  step={0.01}
                  value={ttsPitch}
                  onChange={(e) => setTtsPitch(Number(e.target.value))}
                />
              </label>
            </div>
            <p className="muted">
              Ces paramètres sont stockés dans <code>config.json</code>. Les clients vocaux ou scripts Piper peuvent
              s’y référer pour appliquer une voix “Jessica” ou ajuster la vitesse/pitch par défaut.
            </p>
            <button type="button" onClick={applyTTS} disabled={ttsSaving}>
              Appliquer les réglages TTS
            </button>
          </div>

          <p className="muted">
            La zone ci-dessous correspond au contenu de <code>config.json</code>. Modifiez puis enregistrez pour appliquer
            immédiatement.
          </p>
          <textarea
            value={cfgText}
            onChange={(e) => setCfgText(e.target.value)}
            rows={28}
            style={{ width: '100%', fontFamily: 'monospace' }}
            aria-label="Configuration JSON"
          />
          <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <button onClick={save} disabled={saving}>
              Sauvegarder
            </button>
            <button onClick={load} disabled={loading}>
              Recharger
            </button>
            <button type="button" onClick={openFileDialog} disabled={importing}>
              Importer un fichier
            </button>
            <button type="button" onClick={restart} disabled={restarting}>
              Redémarrer le serveur
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json"
              onChange={handleImport}
              style={{ display: 'none' }}
            />
          </div>
          {message ? <p className="status-bar">{message}</p> : null}
        </>
      )}
    </section>
  )
}
