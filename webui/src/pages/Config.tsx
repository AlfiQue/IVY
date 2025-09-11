import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function ConfigPage() {
  const [health, setHealth] = useState<any>(null)
  useEffect(()=>{ api.health().then(setHealth).catch(()=>{}) },[])
  return (
    <section>
      <h2>Configuration</h2>
      {!health ? <p>Chargement…</p> : (
        <div className="grid">
          <div className="card"><strong>Hôte/Port</strong><div>{location.hostname}:{location.port}</div></div>
          <div className="card"><strong>Rate limit</strong><div>voir config serveur</div></div>
          <div className="card"><strong>Allowlist</strong><div>config.json (ex: open-meteo.com, duckduckgo.com)</div></div>
          <div className="card"><strong>RAG</strong><div>Index: app/data/faiss_index</div></div>
          <div className="card"><strong>LLM</strong><div>LLM_MODEL_PATH via env</div></div>
          <div className="card"><strong>Logs</strong><div>Rotation: config serveur</div></div>
          <div className="card"><strong>Reset admin</strong><div>Créer le fichier reset_admin.flag (via serveur)</div></div>
        </div>
      )}
    </section>
  )
}

