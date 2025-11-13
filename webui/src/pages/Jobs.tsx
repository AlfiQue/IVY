import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useToast } from '../components/Toast'

type Job = { id: string, type: string, status: string, attempts?: number, next_run?: string|null, last_run?: string|null, description?: string|null, tag?: string|null }
type JobDetail = Job & { params: any, schedule: any, last_error?: string|null, cancel_requested?: boolean }

type SchedulePayload =
  | { trigger: 'immediate' }
  | { trigger: 'interval'; every_minutes: number }
  | { trigger: 'date'; run_date: string }
  | { trigger: 'cron'; cron_hour?: number; cron_minute?: number; day_of_week?: string }

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<JobDetail | null>(null)
  const [newType, setNewType] = useState<'llm'|'backup'>('llm')
  const [llmPrompt, setLlmPrompt] = useState('')
  const [llmOptions, setLlmOptions] = useState('{}')
  const [scheduleMode, setScheduleMode] = useState<'now'|'interval'>('now')
  const [intervalMinutes, setIntervalMinutes] = useState(60)
  const timer = useRef<number | null>(null)
  const { show, Toast } = useToast()

  async function load() {
    const data = await api.jobs()
    setJobs(data.jobs)
  }

  async function open(id: string) {
    const d = await api.getJob(id)
    setSelected(d as JobDetail)
  }

  async function cancel(id: string) {
    if (!window.confirm('Annuler cette tâche ?')) return
    try {
      await api.cancelJob(id)
      show('Annulation demandée', 'ok')
    } catch {
      show('Échec annulation', 'err')
    }
    await open(id)
    await load()
  }

  async function runNow(id: string) {
    if (!window.confirm('Lancer immédiatement ?')) return
    try {
      await api.runJobNow(id)
      show('Lancé', 'ok')
    } catch {
      show('Échec lancement', 'err')
    }
    await open(id)
    await load()
  }

  function buildSchedule(): SchedulePayload {
    if (scheduleMode === 'interval') {
      const minutes = Math.max(1, Number(intervalMinutes) || 1)
      return { trigger: 'interval', every_minutes: minutes }
    }
    return { trigger: 'immediate' }
  }

  async function createJob() {
    try {
      const payload: any = { type: newType, schedule: buildSchedule() }
      if (newType === 'llm') {
        if (!llmPrompt.trim()) {
          show('Prompt requis', 'err')
          return
        }
        let opts: any = {}
        try {
          opts = llmOptions ? JSON.parse(llmOptions) : {}
        } catch {
          show('Options LLM invalides (JSON)', 'err')
          return
        }
        payload.params = { prompt: llmPrompt, options: opts }
      } else {
        payload.params = {}
      }
      const res = await api.addJob(payload)
      const id = res.id
      if (scheduleMode === 'now') {
        try { await api.runJobNow(id) } catch { /* ignore */ }
      }
      show('Tâche créée', 'ok')
      await load()
      setSelected(null)
    } catch {
      show('Échec création', 'err')
    }
  }

  useEffect(() => {
    load()
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [])

  useEffect(() => {
    if (!selected) return
    if (timer.current) window.clearInterval(timer.current)
    timer.current = window.setInterval(() => open(selected.id), 1500)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [selected])

  return (
    <section>
      <h2>Tâches</h2>
      <div className="card" style={{ marginBottom: '.5rem' }}>
        <h3>Créer une tâche</h3>
        <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap' }}>
          <label>Type
            <select value={newType} onChange={e => setNewType(e.target.value as any)}>
              <option value="llm">llm</option>
              <option value="backup">backup</option>
            </select>
          </label>
          {newType === 'llm' && (
            <>
              <input placeholder="prompt" value={llmPrompt} onChange={e => setLlmPrompt(e.target.value)} style={{ minWidth: '18rem' }} />
              <input placeholder="options (JSON)" value={llmOptions} onChange={e => setLlmOptions(e.target.value)} />
            </>
          )}
          <label>Planification
            <select value={scheduleMode} onChange={e => setScheduleMode(e.target.value as any)}>
              <option value="now">immédiat</option>
              <option value="interval">toutes les X minutes</option>
            </select>
          </label>
          {scheduleMode === 'interval' && (
            <input type="number" min={1} value={intervalMinutes} onChange={e => setIntervalMinutes(parseInt(e.target.value || '60', 10))} />
          )}
          <button onClick={createJob}>Créer</button>
        </div>
      </div>
      <div className="grid">
        {jobs.map(j => (
          <div key={j.id} className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{j.type}</strong>
              <span className={j.status === 'SUCCESS' ? 'success' : j.status === 'FAILED' ? 'danger' : 'warn'}>{j.status}</span>
            </div>
            <div className="muted">id: {j.id}</div>
            <div className="muted">prochaine: {j.next_run || '-'}</div>
            <div className="row">
              <button onClick={() => open(j.id)}>Détails</button>
              <button onClick={() => runNow(j.id)}>Lancer</button>
              <button onClick={() => cancel(j.id)}>Annuler</button>
            </div>
          </div>
        ))}
      </div>
      {selected && (
        <div className="card" style={{ marginTop: '1rem' }} aria-live="polite">
          <h3>Détails</h3>
          <div>id: {selected.id}</div>
          <div>type: {selected.type}</div>
          <div>status: {selected.status} {selected.cancel_requested ? '(annulation demandée)' : ''}</div>
          <div>prochaine exécution: {selected.next_run || '-'}</div>
          <div>dernière exécution: {selected.last_run || '-'}</div>
          {selected.last_error && <div className="danger">erreur: {selected.last_error}</div>}
          <pre style={{ whiteSpace: 'pre-wrap' }}>params: {JSON.stringify(selected.params, null, 2)}</pre>
          <pre style={{ whiteSpace: 'pre-wrap' }}>schedule: {JSON.stringify(selected.schedule, null, 2)}</pre>
          <div className="row">
            <button onClick={() => runNow(selected.id)}>Lancer</button>
            <button onClick={() => cancel(selected.id)}>Annuler</button>
          </div>
        </div>
      )}
      <Toast />
    </section>
  )
}
