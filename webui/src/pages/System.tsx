import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function SystemPage() {
  const [health, setHealth] = useState<any>(null)
  useEffect(()=>{ api.health().then(setHealth).catch(()=>setHealth(null)) },[])
  return (
    <section>
      <h2>Système</h2>
      {!health ? <p>Chargement…</p> : (
        <div className="grid">
          <div className="card"><strong>Statut</strong><div>{health.status}</div></div>
          <div className="card"><strong>DB</strong><div>{health.db_ok? 'OK':'KO'}</div></div>
          <div className="card"><strong>FAISS</strong><div>{health.faiss_ok? 'OK':'KO'}</div></div>
          <div className="card"><strong>GPU</strong><div>{health.gpu? 'Oui':'Non'}</div></div>
          <div className="card"><strong>Version</strong><div>{health.version}</div></div>
          <div className="card"><strong>Plugins</strong><div>{health.plugins_count}</div></div>
        </div>
      )}
    </section>
  )
}

