import { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function SystemPage() {
  const [health, setHealth] = useState<any>(null)
  useEffect(()=>{ api.health().then(setHealth).catch(()=>setHealth(null)) },[])
  return (
    <section>
      <h2>Système</h2>
      {!health ? <p>Chargement...</p> : (
        <>
          <div className="grid">
            <div className="card"><strong>Statut</strong><div>{health.status}</div></div>
            <div className="card"><strong>DB</strong><div>{health.db_ok? 'OK':'KO'}</div></div>
            <div className="card"><strong>FAISS</strong><div>{health.faiss_ok? 'OK':'KO'}</div></div>
            <div className="card"><strong>GPU</strong><div>{health.gpu? 'Oui':'Non'}</div></div>
            <div className="card"><strong>Version</strong><div>{health.version}</div></div>
            <div className="card"><strong>Conversations</strong><div>{health.conversations_total}</div></div><div className="card"><strong>Q/R mémorisées</strong><div>{health.qa_total}</div></div>
          </div>
          <div className="grid" style={{marginTop:'.5rem'}}>
            <div className="card"><strong>CPU</strong><div>{health.cpu_percent!=null? `${Number(health.cpu_percent).toFixed(1)}%`:'-'}</div></div>
            <div className="card"><strong>Mémoire</strong><div>{health.mem_percent!=null? `${Number(health.mem_percent).toFixed(1)}%`:'-'}</div></div>
            <div className="card"><strong>RAM totale</strong><div>{health.mem_total!=null? `${Math.round(Number(health.mem_total)/ (1024*1024*1024))} Go`:'-'}</div></div>
            <div className="card"><strong>RAM dispo</strong><div>{health.mem_available!=null? `${Math.round(Number(health.mem_available)/ (1024*1024*1024))} Go`:'-'}</div></div>
          </div>
        </>
      )}
    </section>
  )
}



