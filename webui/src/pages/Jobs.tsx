import { FormEvent, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

type JobType = 'plugin' | 'llm' | 'backup' | 'rag'

type JobItem = {
  id: string
  type: JobType | string
  status: string
  attempts?: number
  success_count?: number | null
  failure_count?: number | null
  next_run?: string | null
  last_run?: string | null
  description?: string | null
  tag?: string | null
}

type JobDetail = JobItem & {
  params?: Record<string, any> | null
  schedule?: Record<string, any> | null
  last_error?: string | null
  last_error_at?: string | null
  cancel_requested?: boolean
}

type PromptEntry = {
  prompt: string
  usage_count?: number
  last_used?: string | null
}

const JOB_TYPE_LABELS: Record<JobType, string> = {
  llm: 'Routine LLM',
  backup: 'Sauvegarde',
  plugin: 'Plugin',
  rag: 'RAG',
}

const RAG_INTERVAL_PRESETS = [15, 30, 60, 120, 240]

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)
const fmtDate = (value?: string | null) => {
  if (!value) return 'n/a'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

const stringify = (payload: any) => {
  try {
    return JSON.stringify(payload ?? {}, null, 2)
  } catch {
    return ''
  }
}

export default function JobsPage(): JSX.Element {
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<JobDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [recentPrompts, setRecentPrompts] = useState<PromptEntry[]>([])
  const [favoritePrompts, setFavoritePrompts] = useState<PromptEntry[]>([])

  const [newType, setNewType] = useState<JobType>('llm')
  const [description, setDescription] = useState('')
  const [tag, setTag] = useState('')
  const [newPrompt, setNewPrompt] = useState('')
  const [llmOptions, setLlmOptions] = useState('')
  const [pluginName, setPluginName] = useState('')
  const [pluginPayload, setPluginPayload] = useState('')
  const [ragMode, setRagMode] = useState<'incremental' | 'full'>('incremental')
  const [scheduleMode, setScheduleMode] = useState<'interval' | 'daily'>('daily')
  const [intervalMinutes, setIntervalMinutes] = useState(60)
  const [dailyHour, setDailyHour] = useState(3)
  const [dailyMinute, setDailyMinute] = useState(0)
  const [formError, setFormError] = useState<string | null>(null)
  const [formBusy, setFormBusy] = useState(false)

  const detailTimer = useRef<number | null>(null)

  useEffect(() => {
    void refreshJobs(true)
    void refreshPrompts()
    return () => {
      if (detailTimer.current) {
        window.clearInterval(detailTimer.current)
        detailTimer.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (detailTimer.current) {
      window.clearInterval(detailTimer.current)
      detailTimer.current = null
    }
    if (!selectedId) return
    detailTimer.current = window.setInterval(() => {
      void loadJobDetail(selectedId, true)
    }, 2000)
    return () => {
      if (detailTimer.current) {
        window.clearInterval(detailTimer.current)
        detailTimer.current = null
      }
    }
  }, [selectedId])

  useEffect(() => {
    if (newType === 'rag') {
      setScheduleMode(ragMode === 'incremental' ? 'interval' : 'daily')
    }
  }, [newType, ragMode])

  async function refreshJobs(forceSelectFirst = false) {
    setLoading(true)
    setError(null)
    try {
      const data = await api.jobs()
      const items = (Array.isArray(data?.jobs) ? data.jobs : []) as JobItem[]
      setJobs(items)
      if (!items.length) {
        setSelectedId(null)
        setSelected(null)
        return
      }
      const hasCurrent = Boolean(!forceSelectFirst && selectedId && items.some((item) => item.id === selectedId))
      const targetId = hasCurrent ? selectedId! : items[0].id
      if (!hasCurrent) {
        setSelectedId(targetId)
      }
      await loadJobDetail(targetId, hasCurrent)
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Impossible de charger les taches.')
    } finally {
      setLoading(false)
    }
  }

  async function loadJobDetail(id: string | null, silent = false) {
    if (!id) return
    try {
      const data = await api.getJob(id)
      setSelected(data as JobDetail)
    } catch (err: any) {
      if (!silent) {
        setError(err?.detail?.error?.message || err?.message || 'Impossible de charger le detail.')
      }
    }
  }

  async function refreshPrompts() {
    try {
      const [recent, favorites] = await Promise.all([api.jobPromptsRecent(8), api.jobPromptsFavorites(8)])
      setRecentPrompts(Array.isArray(recent?.items) ? recent.items : [])
      setFavoritePrompts(Array.isArray(favorites?.items) ? favorites.items : [])
    } catch {
      // silencieux: la page doit rester utilisable meme si la base des prompts est vide
    }
  }

  async function handleSelect(jobId: string) {
    setSelectedId(jobId)
    setMessage(null)
    setError(null)
    await loadJobDetail(jobId)
  }

  async function handleRunNow(jobId: string) {
    setMessage(null)
    setError(null)
    try {
      await api.runJobNow(jobId)
      setMessage('Execution programmee.')
      await loadJobDetail(jobId)
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Impossible de lancer la tache.')
    }
  }

  async function handleCancel(jobId: string) {
    setMessage(null)
    setError(null)
    try {
      await api.cancelJob(jobId)
      setMessage('Annulation demandee.')
      await loadJobDetail(jobId)
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Impossible d annuler la tache.')
    }
  }

  async function handleDelete(jobId: string) {
    if (!window.confirm('Supprimer cette tache ?')) return
    setMessage(null)
    setError(null)
    try {
      await api.deleteJob(jobId)
      setMessage('Tache supprimee.')
      await refreshJobs(true)
    } catch (err: any) {
      setError(err?.detail?.error?.message || err?.message || 'Suppression impossible.')
    }
  }

  function buildSchedule() {
    if (scheduleMode === 'interval') {
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

  async function handleAddJob(event: FormEvent) {
    event.preventDefault()
    if (formBusy) return
    setFormError(null)
    setMessage(null)
    const payload: Record<string, any> = {
      type: newType,
      params: {},
      schedule: buildSchedule(),
    }
    if (description.trim()) payload.description = description.trim()
    if (tag.trim()) payload.tag = tag.trim()
    try {
      if (newType === 'llm') {
        if (!newPrompt.trim()) {
          setFormError('Ajoutez un prompt avant de creer la tache.')
          return
        }
        payload.params = { prompt: newPrompt.trim() }
        if (llmOptions.trim()) {
          payload.params.options = JSON.parse(llmOptions)
        }
      } else if (newType === 'plugin') {
        if (!pluginName.trim()) {
          setFormError('Le champ plugin est requis.')
          return
        }
        payload.params = { name: pluginName.trim() }
        if (pluginPayload.trim()) {
          payload.params.params = JSON.parse(pluginPayload)
        }
      } else if (newType === 'rag') {
        payload.params = { full: ragMode === 'full' }
      } else if (newType === 'backup') {
        payload.params = {}
      }
    } catch (err: any) {
      setFormError(err?.message || 'Impossible de lire les options JSON.')
      return
    }
    try {
      setFormBusy(true)
      const res = await api.addJob(payload)
      setMessage(`Tache creee (${res?.id || 'ok'}).`)
      setFormError(null)
      await refreshJobs(true)
    } catch (err: any) {
      setFormError(err?.detail?.error?.message || err?.message || 'Creation impossible.')
    } finally {
      setFormBusy(false)
    }
  }

  function adoptPrompt(text: string) {
    if (!text) return
    setNewType('llm')
    setNewPrompt(text)
    setMessage('Prompt insere dans le formulaire.')
  }

  const successCount = selected?.success_count ?? 0
  const failureCount = selected?.failure_count ?? 0
  const totalRuns = successCount + failureCount
  const successRate = totalRuns ? Math.round((successCount / totalRuns) * 100) : 0

  return (
    <section className="jobs-page">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
        <h2>Taches planifiees</h2>
        <div className="row" style={{ gap: '.5rem' }}>
          <button type="button" onClick={() => refreshJobs()} disabled={loading}>
            Rafraichir
          </button>
          <button type="button" className="ghost-button" onClick={() => refreshPrompts()}>
            Prompts
          </button>
        </div>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="grid" style={{ gridTemplateColumns: 'minmax(320px, 1fr) 2fr', gap: '1.5rem' }}>
        <div className="card">
          <h3>Vue d ensemble</h3>
          {jobs.length ? (
            <ul className="task-list">
              {jobs.map((job) => {
                const statusLabel = job.status || 'PENDING'
                return (
                  <li key={job.id} className={job.id === selectedId ? 'selected' : ''} onClick={() => handleSelect(job.id)}>
                    <div className="row" style={{ justifyContent: 'space-between', gap: '.5rem' }}>
                      <div>
                        <strong>{job.description || job.tag || job.id}</strong>
                        <div className="muted small">{JOB_TYPE_LABELS[job.type as JobType] || job.type}</div>
                      </div>
                      <span className={`status-pill ${statusLabel.toLowerCase()}`}>{statusLabel}</span>
                    </div>
                    <div className="row" style={{ justifyContent: 'space-between', marginTop: '.35rem', fontSize: '.85rem' }}>
                      <span>Succes&nbsp;: {job.success_count ?? 0}</span>
                      <span>Echecs&nbsp;: {job.failure_count ?? 0}</span>
                    </div>
                    <div className="muted small">
                      Prochaine : {job.next_run ? fmtDate(job.next_run) : 'n/a'} - Derniere :{' '}
                      {job.last_run ? fmtDate(job.last_run) : 'n/a'}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="muted">Aucune tache definie.</p>
          )}
        </div>

        <div className="card">
          <h3>Detail</h3>
          {!selected ? (
            <p className="muted">Selectionnez une tache pour afficher les informations.</p>
          ) : (
            <>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong>{selected.description || selected.tag || selected.id}</strong>
                  <div className="muted small">
                    {JOB_TYPE_LABELS[selected.type as JobType] || selected.type} - ID {selected.id}
                  </div>
                </div>
                <span className={`status-pill ${(selected.status || 'PENDING').toLowerCase()}`}>{selected.status || 'PENDING'}</span>
              </div>
              <div className="job-stats">
                <div>
                  <span className="badge success">{successCount}</span>
                  <small>Succes</small>
                </div>
                <div>
                  <span className="badge warn">{totalRuns ? `${successRate}%` : '--'}</span>
                  <small>Taux reussi</small>
                </div>
                <div>
                  <span className="badge danger">{failureCount}</span>
                  <small>Echecs</small>
                </div>
              </div>
              <p className="muted">
                Dernier run : {selected.last_run ? fmtDate(selected.last_run) : 'n/a'} - Prochain :{' '}
                {selected.next_run ? fmtDate(selected.next_run) : 'n/a'}
              </p>
              <p className="muted">Planification : {describeSchedule(selected.schedule)}</p>
              {selected.cancel_requested ? <p className="warn">Annulation en cours...</p> : null}
              {selected.last_error ? (
                <p className="danger">
                  Derniere erreur ({selected.last_error_at ? fmtDate(selected.last_error_at) : 'n/a'}) :{' '}
                  {selected.last_error}
                </p>
              ) : null}
              <div className="divider" />
              <details open>
                <summary>Parametres</summary>
                <pre>{stringify(selected.params)}</pre>
              </details>
              <details>
                <summary>Planification brute</summary>
                <pre>{stringify(selected.schedule)}</pre>
              </details>
              <div className="job-actions">
                <button type="button" onClick={() => handleRunNow(selected.id)}>
                  Executer
                </button>
                <button type="button" onClick={() => handleCancel(selected.id)}>
                  Annuler
                </button>
                <button type="button" className="ghost-button" onClick={() => handleDelete(selected.id)}>
                  Supprimer
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', gap: '1.5rem', marginTop: '1.5rem' }}>
        <div className="card">
          <h3>Nouvelle tache</h3>
          {formError ? <p className="error">{formError}</p> : null}
          <form onSubmit={handleAddJob} className="job-form">
            <div className="row" style={{ flexWrap: 'wrap' }}>
              <label style={{ flex: '1 0 200px' }}>
                Type
                <select
                  value={newType}
                  onChange={(event) => {
                    const next = event.target.value as JobType
                    setNewType(next)
                    if (next === 'rag') {
                      setRagMode('incremental')
                      setScheduleMode('interval')
                    }
                  }}
                >
                  <option value="llm">Routine LLM</option>
                  <option value="rag">RAG</option>
                  <option value="backup">Sauvegarde</option>
                  <option value="plugin">Plugin</option>
                </select>
              </label>
              <label style={{ flex: '1 0 200px' }}>
                Description
                <input value={description} onChange={(event) => setDescription(event.target.value)} />
              </label>
              <label style={{ flex: '1 0 200px' }}>
                Tag
                <input value={tag} onChange={(event) => setTag(event.target.value)} />
              </label>
            </div>

            {newType === 'llm' ? (
              <>
                <label>
                  Prompt
                  <textarea rows={4} value={newPrompt} onChange={(event) => setNewPrompt(event.target.value)} />
                </label>
                <label>
                  Options LLM (JSON)
                  <textarea
                    rows={2}
                    placeholder='{"temperature":0.2}'
                    value={llmOptions}
                    onChange={(event) => setLlmOptions(event.target.value)}
                  />
                </label>
              </>
            ) : null}

            {newType === 'plugin' ? (
              <div className="row" style={{ flexWrap: 'wrap' }}>
                <label style={{ flex: '1 0 200px' }}>
                  Nom du plugin
                  <input value={pluginName} onChange={(event) => setPluginName(event.target.value)} />
                </label>
                <label style={{ flex: '1 0 200px' }}>
                  Parametres (JSON)
                  <textarea
                    rows={2}
                    value={pluginPayload}
                    placeholder='{"option":true}'
                    onChange={(event) => setPluginPayload(event.target.value)}
                  />
                </label>
              </div>
            ) : null}

            {newType === 'rag' ? (
              <div className="rag-panel">
                <label>
                  Mode de mise a jour
                  <select value={ragMode} onChange={(event) => setRagMode(event.target.value as 'incremental' | 'full')}>
                    <option value="incremental">Incremental (rapide)</option>
                    <option value="full">Full (complet)</option>
                  </select>
                </label>
                {ragMode === 'incremental' ? (
                  <>
                    <p className="muted small">
                      L incremental reindex ajoute uniquement les nouveaux documents. Choisissez un intervalle court pour
                      gagner en fraicheur.
                    </p>
                    <label>
                      Minutes entre deux passes
                      <input
                        type="number"
                        min={1}
                        value={intervalMinutes}
                        onChange={(event) => {
                          const next = parseInt(event.target.value || '1', 10)
                          setIntervalMinutes(Number.isFinite(next) ? Math.max(1, next) : 1)
                        }}
                      />
                    </label>
                    <div className="row" style={{ flexWrap: 'wrap', gap: '.35rem' }}>
                      {RAG_INTERVAL_PRESETS.map((value) => (
                        <button
                          key={value}
                          type="button"
                          className="ghost-button"
                          onClick={() => setIntervalMinutes(value)}
                        >
                          {value} min
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="muted small">
                      Le mode full reconstruit l index complet (plus long). Positionnez une heure calme (nuit).
                    </p>
                    <div className="row" style={{ flexWrap: 'wrap' }}>
                      <label>
                        Heure
                        <input
                          type="number"
                          min={0}
                          max={23}
                          value={dailyHour}
                          onChange={(event) =>
                            setDailyHour(clamp(parseInt(event.target.value || '0', 10) || 0, 0, 23))
                          }
                        />
                      </label>
                      <label>
                        Minute
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={dailyMinute}
                          onChange={(event) =>
                            setDailyMinute(clamp(parseInt(event.target.value || '0', 10) || 0, 0, 59))
                          }
                        />
                      </label>
                    </div>
                  </>
                )}
              </div>
            ) : null}

            {newType !== 'rag' ? (
              <div className="schedule-panel">
                <h4>Planification</h4>
                <div className="row" style={{ flexWrap: 'wrap' }}>
                  <label>
                    Mode
                    <select value={scheduleMode} onChange={(event) => setScheduleMode(event.target.value as 'interval' | 'daily')}>
                      <option value="interval">Intervalle regulier</option>
                      <option value="daily">Tous les jours</option>
                    </select>
                  </label>
                  {scheduleMode === 'interval' ? (
                    <label>
                      Minutes
                      <input
                        type="number"
                        min={1}
                        value={intervalMinutes}
                        onChange={(event) => {
                          const next = parseInt(event.target.value || '1', 10)
                          setIntervalMinutes(Number.isFinite(next) ? Math.max(1, next) : 1)
                        }}
                      />
                    </label>
                  ) : (
                    <div className="row" style={{ flexWrap: 'wrap' }}>
                      <label>
                        Heure
                        <input
                          type="number"
                          min={0}
                          max={23}
                          value={dailyHour}
                          onChange={(event) =>
                            setDailyHour(clamp(parseInt(event.target.value || '0', 10) || 0, 0, 23))
                          }
                        />
                      </label>
                      <label>
                        Minute
                        <input
                          type="number"
                          min={0}
                          max={59}
                          value={dailyMinute}
                          onChange={(event) =>
                            setDailyMinute(clamp(parseInt(event.target.value || '0', 10) || 0, 0, 59))
                          }
                        />
                      </label>
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            <div className="job-actions" style={{ marginTop: '1rem' }}>
              <button type="submit" disabled={formBusy}>
                Ajouter
              </button>
            </div>
          </form>
        </div>

        <div className="card">
          <h3>Prompts utilises</h3>
          <div className="prompt-grid">
            <PromptList title="Recents" items={recentPrompts} onInsert={adoptPrompt} />
            <PromptList title="Favoris" items={favoritePrompts} onInsert={adoptPrompt} />
          </div>
        </div>
      </div>
    </section>
  )
}

type PromptListProps = {
  title: string
  items: PromptEntry[]
  onInsert: (text: string) => void
}

function PromptList({ title, items, onInsert }: PromptListProps) {
  return (
    <div className="prompt-panel">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>{title}</strong>
        <span className="muted small">{items.length} items</span>
      </div>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={`${title}-${item.prompt}`} onClick={() => onInsert(item.prompt)}>
              <div className="prompt-text">{item.prompt}</div>
              <div className="muted small">
                Utilisations : {item.usage_count ?? 1} - Dernier : {item.last_used ? fmtDate(item.last_used) : 'n/a'}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Aucun element.</p>
      )}
    </div>
  )
}

function describeSchedule(schedule?: Record<string, any> | null) {
  if (!schedule) return 'Cron 03:00 par defaut'
  const trigger = schedule.trigger || 'cron'
  if (trigger === 'interval') {
    const interval = schedule.interval || {}
    if (typeof interval.minutes === 'number') {
      return `Intervalle de ${interval.minutes} min`
    }
    if (typeof interval.seconds === 'number') {
      return `Intervalle de ${Math.round(interval.seconds / 60)} min`
    }
    if (typeof interval.hours === 'number') {
      return `Intervalle de ${interval.hours} h`
    }
    return 'Intervalle personnalise'
  }
  if (trigger === 'date') {
    const runDate = schedule.date?.run_date
    return runDate ? `Execution unique le ${fmtDate(runDate)}` : 'Execution unique'
  }
  const cron = schedule.cron || {}
  const hour = cron.hour ?? '03'
  const minute = cron.minute ?? '00'
  return `Tous les jours a ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}
