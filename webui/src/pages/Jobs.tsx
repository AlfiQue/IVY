import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

type Job = { id: string, type: string, status: string, attempts?: number, next_run?: string|null, last_run?: string|null, description?: string|null, tag?: string|null }
type JobDetail = Job & { params: any, schedule: any, last_error?: string|null, cancel_requested?: boolean }

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<JobDetail | null>(null)
  const timer = useRef<number | null>(null)

  async function load() {
    const data = await api.jobs()
    setJobs(data.jobs)
  }
  async function open(id: string) {
    const d = await api.getJob(id)
    setSelected(d as JobDetail)
  }
  async function cancel(id: string) {
    await api.cancelJob(id); await open(id); await load()
  }
  async function runNow(id: string) {
    await api.runJobNow(id); await open(id); await load()
  }
  useEffect(()=>{ load(); return ()=>{ if (timer.current) window.clearInterval(timer.current) } },[])
  useEffect(()=>{
    if (!selected) return
    if (timer.current) window.clearInterval(timer.current)
    timer.current = window.setInterval(()=> open(selected.id), 1500)
    return ()=>{ if (timer.current) window.clearInterval(timer.current) }
  }, [selected?.id])

  return (
    <section>
      <h2>Tâches</h2>
      <div className="grid">
        {jobs.map(j => (
          <div key={j.id} className="card">
            <div className="row" style={{justifyContent:'space-between'}}>
              <strong>{j.type}</strong>
              <span className={j.status==='SUCCESS'?'success':j.status==='FAILED'?'danger':'warn'}>{j.status}</span>
            </div>
            <div className="muted">id: {j.id}</div>
            <div className="muted">prochaine: {j.next_run || '—'}</div>
            <div className="row">
              <button onClick={()=>open(j.id)}>Détails</button>
              <button onClick={()=>runNow(j.id)}>Lancer</button>
              <button onClick={()=>cancel(j.id)}>Annuler</button>
            </div>
          </div>
        ))}
      </div>
      {selected && (
        <div className="card" style={{marginTop:'1rem'}} aria-live="polite">
          <h3>Détails</h3>
          <div>id: {selected.id}</div>
          <div>type: {selected.type}</div>
          <div>status: {selected.status} {selected.cancel_requested ? '(annulation demandée)' : ''}</div>
          <div>prochaine exécution: {selected.next_run || '—'}</div>
          <div>dernière exécution: {selected.last_run || '—'}</div>
          {selected.last_error && <div className="danger">erreur: {selected.last_error}</div>}
          <pre style={{whiteSpace:'pre-wrap'}}>params: {JSON.stringify(selected.params, null, 2)}</pre>
          <pre style={{whiteSpace:'pre-wrap'}}>schedule: {JSON.stringify(selected.schedule, null, 2)}</pre>
          <div className="row">
            <button onClick={()=>runNow(selected.id)}>Lancer</button>
            <button onClick={()=>cancel(selected.id)}>Annuler</button>
          </div>
        </div>
      )}
    </section>
  )
}

