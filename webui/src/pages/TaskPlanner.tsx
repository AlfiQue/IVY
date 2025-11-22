import { useEffect, useState } from 'react'
import { api } from '../api/client'

type JobItem = {
  id: string
  type: string
  status: string
  attempts?: number
  success_count?: number
  failure_count?: number
  next_run?: string | null
  last_run?: string | null
  description?: string | null
  tag?: string | null
}

type JobDetail = JobItem & {
  params?: any
  schedule?: any
  last_error?: string | null
  last_error_at?: string | null
}

type ScheduleMode = 'interval' | 'daily'

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

export default function TaskPlannerPage(): JSX.Element {
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<JobDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [mode, setMode] = useState<ScheduleMode>('interval')
  const [intervalMinutes, setIntervalMinutes] = useState(60)
  const [dailyHour, setDailyHour] = useState(3)
  const [dailyMinute, setDailyMinute] = useState(0)

  async function loadJobs() {
    const data = await api.jobs()
    const items = Array.isArray(data?.jobs) ? data.jobs : []
    setJobs(items)
    if (!selectedId && items.length) {
      selectJob(items[0].id)
    }
  }

  async function selectJob(id: string) {
    setSelectedId(id)
    setSelected(null)
    setMessage(null)
    setError(null)
    try {
      const data = await api.getJob(id)
      setSelected(data as JobDetail)
      const schedule = data?.schedule || {}
      const trig = schedule.trigger || 'cron'
      if (trig === 'interval') {
        setMode('interval')
        const interval = schedule.interval || {}
        let minutes = 60
        if (typeof interval.minutes === 'number') {
          minutes = interval.minutes
        } else if (typeof interval.seconds === 'number') {
          minutes = interval.seconds / 60
        } else if (typeof interval.hours === 'number') {
          minutes = interval.hours * 60
        }
        setIntervalMinutes(Math.max(1, Math.round(minutes)))
      } else {
        setMode('daily')
        setDailyHour(clamp(parseInt(schedule.cron?.hour ?? 3, 10) || 3, 0, 23))
        setDailyMinute(clamp(parseInt(schedule.cron?.minute ?? 0, 10) || 0, 0, 59))
      }
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Impossible de charger la tache.')
    }
  }

  async function refreshAll() {
    setLoading(true)
    try {
      await loadJobs()
      if (selectedId) {
        await selectJob(selectedId)
      }
      setMessage('Rafraichi')
    } catch (err: any) {
      setError(err?.message || 'Echec rafraichissement.')
    } finally {
      setLoading(false)
    }
  }

  function buildSchedule() {
    if (mode === 'interval') {
      return {
        trigger: 'interval',
        interval: { minutes: Math.max(1, intervalMinutes) },
      }
    }
    return {
      trigger: 'cron',
      cron: { hour: clamp(dailyHour, 0, 23), minute: clamp(dailyMinute, 0, 59) },
    }
  }

  async function saveSchedule() {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      await api.updateJob(selectedId, { schedule: buildSchedule() })
      setMessage('Planification mise à jour.')
      await selectJob(selectedId)
      await loadJobs()
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Echec mise à jour.')
    } finally {
      setLoading(false)
    }
  }

  async function runNow() {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      await api.runJobNow(selectedId)
      setMessage("Execution demandée.")
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Impossible de lancer la tâche.')
    } finally {
      setLoading(false)
    }
  }

  async function cancelJob() {
    if (!selectedId) return
    setLoading(true)
    setError(null)
    try {
      await api.cancelJob(selectedId)
      setMessage("Annulation demandée.")
      await selectJob(selectedId)
      await loadJobs()
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Echec annulation.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadJobs()
  }, [])

  return (
    <section>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
        <h2>Planification des tâches</h2>
        <button type="button" onClick={refreshAll} disabled={loading}>
          Rafraichir
        </button>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="grid" style={{ gridTemplateColumns: 'minmax(320px, 1fr) 2fr', gap: '1.5rem' }}>
        <div className="card" aria-label="Liste des tâches planifiées">
          <h3>Tâches</h3>
          {jobs.length ? (
            <ul className="task-list">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className={job.id === selectedId ? 'selected' : ''}
                  onClick={() => selectJob(job.id)}
                >
                  <div>
                    <strong>{job.description || job.tag || job.id}</strong>
                    <div className="muted">
                      {job.type} · statut {job.status.toLowerCase()}
                    </div>
                  </div>
                  <div className="muted small">
                    prochaine : {job.next_run ? new Date(job.next_run).toLocaleString() : 'n/a'}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Aucune tâche configurée.</p>
          )}
        </div>

        <div className="card" aria-label="Détails de la tâche sélectionnée">
          <h3>Détails</h3>
          {!selected ? (
            <p className="muted">Sélectionnez une tâche pour afficher les détails.</p>
          ) : (
            <>
              <p>
                <strong>ID :</strong> {selected.id}
              </p>
              <p>
                <strong>Type :</strong> {selected.type}
              </p>
              <p>
                <strong>Statut :</strong> {selected.status}
              </p>
              <p className="muted">
                Dernier run : {selected.last_run ? new Date(selected.last_run).toLocaleString() : 'n/a'} · Prochain :{' '}
                {selected.next_run ? new Date(selected.next_run).toLocaleString() : 'n/a'}
              </p>
              <p className="muted">
                Succès : {selected.success_count ?? 0} · Échecs : {selected.failure_count ?? 0}
              </p>
              {selected.last_error ? (
                <p className="error">
                  Dernière erreur ({selected.last_error_at || 'n/a'}) : {selected.last_error}
                </p>
              ) : null}
              <div className="divider" />
              <h4>Planification</h4>
              <div className="row" style={{ gap: '.75rem', flexWrap: 'wrap' }}>
                <label style={{ flex: '1 0 160px' }}>
                  Mode
                  <select value={mode} onChange={(e) => setMode(e.target.value as ScheduleMode)}>
                    <option value="interval">Intervalle régulier</option>
                    <option value="daily">Tous les jours à heure fixe</option>
                  </select>
                </label>
                {mode === 'interval' ? (
                  <label style={{ flex: '1 0 160px' }}>
                    Minutes
                    <input
                      type="number"
                      min={1}
                      value={intervalMinutes}
                      onChange={(e) => setIntervalMinutes(parseInt(e.target.value || '1', 10))}
                    />
                  </label>
                ) : (
                  <div className="row" style={{ gap: '.5rem' }}>
                    <label>
                      Heure
                      <input
                        type="number"
                        min={0}
                        max={23}
                        value={dailyHour}
                        onChange={(e) => setDailyHour(clamp(parseInt(e.target.value || '0', 10) || 0, 0, 23))}
                      />
                    </label>
                    <label>
                      Minutes
                      <input
                        type="number"
                        min={0}
                        max={59}
                        value={dailyMinute}
                        onChange={(e) =>
                          setDailyMinute(clamp(parseInt(e.target.value || '0', 10) || 0, 0, 59))
                        }
                      />
                    </label>
                  </div>
                )}
              </div>
              <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap', marginTop: '.75rem' }}>
                <button type="button" onClick={saveSchedule} disabled={loading}>
                  Enregistrer
                </button>
                <button type="button" onClick={runNow} disabled={loading}>
                  Exécuter maintenant
                </button>
                <button type="button" onClick={cancelJob} disabled={loading}>
                  Annuler la prochaine exécution
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
