import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface JeedomStatus {
  configured?: boolean
  base_url?: string | null
}

export default function JeedomPage() {
  const [status, setStatus] = useState<JeedomStatus>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.jeedomStatus().then(setStatus).catch(() => setError('Impossible de contacter Jeedom'))
  }, [])

  return (
    <div className="jeedom-page">
      <h1>Jeedom</h1>
      {error ? <p className="error">{error}</p> : null}
      <p>Statut: <strong>{status.configured ? 'Configuration détectée' : 'Non configuré'}</strong></p>
      {status.base_url ? <p>Instance: {status.base_url}</p> : <p className="muted">Définissez l’URL et la clé API dans la configuration.</p>}
      <p className="muted">Cette section servira à piloter Jeedom (à venir).</p>
    </div>
  )
}
