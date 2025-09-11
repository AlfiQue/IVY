import { useEffect, useState } from 'react'
import { api } from '../api/client'

type Session = { id: string, client: string, start_ts: string, last_activity: string, active: boolean }

export default function SessionsPage() {
  const [list, setList] = useState<Session[]>([])
  async function load() {
    const data = await api.sessions()
    setList(data.sessions)
  }
  useEffect(()=>{ load() },[])
  async function terminate(id: string) { await api.terminateSession(id); await load() }
  return (
    <section>
      <h2>Sessions</h2>
      <div className="grid">
        {list.map(s => (
          <div key={s.id} className="card">
            <div><strong>{s.client}</strong> <span className="muted">{s.id}</span></div>
            <div className="muted">Début: {s.start_ts}</div>
            <div className="muted">Dernière activité: {s.last_activity}</div>
            <div className="row"><button onClick={()=>terminate(s.id)}>Terminer</button></div>
          </div>
        ))}
      </div>
    </section>
  )
}
