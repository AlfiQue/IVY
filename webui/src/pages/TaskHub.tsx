import { FormEvent, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { useToast } from '../components/Toast'

type HubJob = {
  id: string
  type: string
  status: string
  description?: string | null
  tag?: string | null
  next_run?: string | null
  last_run?: string | null
  success_count?: number | null
  failure_count?: number | null
}

type PromptEntry = {
  prompt?: string
  count?: number
  last_used?: string
}

type TopJob = HubJob & {
  success?: number
  failure?: number
  success_rate?: number
}

type Suggestion = {
  question?: string
  occurrences?: number
  action?: string
  reason?: string
}

type LearningInsights = {
  recent_prompts?: PromptEntry[]
  favorite_prompts?: PromptEntry[]
  top_jobs?: TopJob[]
  suggestions?: Suggestion[]
  top_queries?: Array<{ query?: string; occurrences?: number; search_success?: number }>
  unresolved_queries?: Array<{ query?: string; occurrences?: number; last_seen?: string }>
  recent_events?: Array<{ question?: string; normalized_query?: string; created_at?: string }>
  job_recommendations?: Array<{ query?: string; occurrences?: number; needs_search_hits?: number; last_seen?: string }>
}

export default function TaskHubPage(): JSX.Element {
  const [jobs, setJobs] = useState<HubJob[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [insights, setInsights] = useState<LearningInsights | null>(null)
  const [insightError, setInsightError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<string>('')
  const [filterStatus, setFilterStatus] = useState<string>('')
  const [filterText, setFilterText] = useState<string>('')
  const [runsJobId, setRunsJobId] = useState<string | null>(null)
  const [jobRuns, setJobRuns] = useState<Array<{ status?: string; timestamp?: string; detail?: string }>>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const { show, Toast } = useToast()

  const currentFilters = () => ({
    job_type: filterType || null,
    status: filterStatus || null,
    q: filterText || null,
  })

  useEffect(() => {
    void Promise.all([loadJobs(currentFilters()), loadInsights()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadJobs(params?: { job_type?: string | null; status?: string | null; q?: string | null }) {
    setLoading(true)
    setError(null)
    try {
      const data = await api.jobs(params)
      setJobs(Array.isArray(data?.jobs) ? data.jobs : [])
    } catch (err) {
      const detail = (err as any)?.detail?.error?.message || (err as Error)?.message
      setError(detail || "Impossible de recuperer les taches.")
    } finally {
      setLoading(false)
    }
  }

  async function loadInsights() {
    setInsightError(null)
    try {
      const payload = (await api.learningInsights(10)) as LearningInsights
      setInsights(payload)
    } catch (err) {
      const status = (err as any)?.status ?? '?'
      setInsightError(`Impossible de recuperer les suggestions (code ${status}).`)
    }
  }

  async function handleFilter(event: FormEvent) {
    event.preventDefault()
    await loadJobs(currentFilters())
  }

  async function handleRun(jobId: string) {
    try {
      await api.runJobNow(jobId)
      show({ message: `Job ${jobId} planifie.`, type: 'success' })
      await loadJobs(currentFilters())
    } catch (err) {
      const status = (err as any)?.status ?? '?'
      show({ message: `Execution impossible (code ${status}).`, type: 'error' })
    }
  }

  async function handleCancel(jobId: string) {
    try {
      await api.cancelJob(jobId)
      show({ message: `Annulation enfilée pour ${jobId}.`, type: 'success' })
      await loadJobs(currentFilters())
    } catch (err) {
      const status = (err as any)?.status ?? '?'
      show({ message: `Annulation impossible (code ${status}).`, type: 'error' })
    }
  }

  const pending = useMemo(
    () => jobs.filter((job) => job.status === 'PENDING' || job.status === 'RUNNING'),
    [jobs],
  )
  const failedCount = useMemo(() => jobs.filter((job) => job.status === 'FAILED').length, [jobs])
  const byType = useMemo(() => {
    const base: Record<string, number> = { llm: 0, rag: 0, backup: 0, plugin: 0 }
    jobs.forEach((job) => {
      if (job.type in base) base[job.type] += 1
    })
    return base
  }, [jobs])
  const upcoming = useMemo(
    () =>
      jobs
        .filter((job) => job.next_run)
        .sort((a, b) => (a.next_run || '').localeCompare(b.next_run || ''))
        .slice(0, 5),
    [jobs],
  )

  const topRagJobs = useMemo(
    () =>
      jobs
        .filter((job) => job.type === 'rag')
        .sort((a, b) => (b.success_count ?? 0) - (a.success_count ?? 0))
        .slice(0, 4),
    [jobs],
  )

  async function openRuns(jobId: string) {
    setRunsJobId(jobId)
    setRunsLoading(true)
    try {
      const data = await api.jobRuns(jobId, 15)
      setJobRuns(Array.isArray(data?.items) ? data.items : [])
    } catch (err) {
      const status = (err as any)?.status ?? '?'
      show({ message: `Impossible de charger l'historique (${status}).`, type: 'error' })
      setJobRuns([])
    } finally {
      setRunsLoading(false)
    }
  }

  async function adoptPrompt(text: string, favorite = false) {
    if (!text) return
    try {
      await api.saveJobPrompt(text, favorite)
      show({ type: 'success', message: favorite ? 'Ajoute aux favoris.' : 'Memorise.' })
      await loadInsights()
    } catch (err) {
      const status = (err as any)?.status ?? '?'
      show({ message: `Impossible d'enregistrer le prompt (${status}).`, type: 'error' })
    }
  }

  function fmtDate(value?: string | null) {
    if (!value) return 'n/a'
    try {
      return new Date(value).toLocaleString()
    } catch {
      return value
    }
  }

  function label(job: HubJob) {
    return job.description || job.tag || job.id
  }

  return (
    <section>
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <h2>Taches & Programmation</h2>
          <p className="muted">Tableau de bord des jobs, planifications et apprentissages automatiques.</p>
        </div>
        <div className="row" style={{ gap: '.5rem', flexWrap: 'wrap' }}>
          <button onClick={() => void loadInsights()} disabled={loading}>
            Rafraichir les suggestions
          </button>
          <button onClick={() => void loadJobs()} disabled={loading}>
            Rafraichir les jobs
          </button>
        </div>
      </header>
      {error ? <p className="danger">{error}</p> : null}

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: '1rem' }}>
        <div className="card">
          <h3>Filtres</h3>
          <form className="row" style={{ gap: '.5rem', flexWrap: 'wrap' }} onSubmit={handleFilter}>
            <label>
              Type
              <select value={filterType} onChange={(event) => setFilterType(event.target.value)}>
                <option value="">Tous</option>
                <option value="llm">LLM</option>
                <option value="rag">RAG</option>
                <option value="backup">Backup</option>
                <option value="plugin">Plugin</option>
              </select>
            </label>
            <label>
              Statut
              <select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
                <option value="">Tous</option>
                <option value="PENDING">Pending</option>
                <option value="RUNNING">Running</option>
                <option value="FAILED">Failed</option>
                <option value="SUCCESS">Success</option>
              </select>
            </label>
            <label style={{ flex: '1 0 180px' }}>
              Rechercher
              <input
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="Description, tag..."
              />
            </label>
            <button type="submit" disabled={loading}>
              Appliquer
            </button>
          </form>
        </div>

        <div className="card">
          <h3>Jobs rapides</h3>
          <p className="muted">
            Declenchez ou annulez les jobs les plus utilises sans quitter la page. Les actions utilisent les routes
            API protegees (/jobs/*).
          </p>
          <ul className="task-list">
            {jobs.slice(0, 5).map((job) => (
              <li key={job.id}>
                <div className="row" style={{ justifyContent: 'space-between', gap: '.5rem', alignItems: 'center' }}>
                  <div>
                    <strong>{label(job)}</strong>
                    <div className="muted small">
                      {job.type} �?� statut {job.status.toLowerCase()}
                    </div>
                  </div>
                  <div className="row" style={{ gap: '.25rem' }}>
                    <button onClick={() => void handleRun(job.id)} aria-label={`Executer ${job.id}`}>
                      Lancer
                    </button>
                    <button onClick={() => void handleCancel(job.id)} className="ghost-button" aria-label={`Annuler ${job.id}`}>
                      Annuler
                    </button>
                    <button onClick={() => void openRuns(job.id)} className="ghost-button" aria-label={`Historique ${job.id}`}>
                      Runs
                    </button>
                  </div>
                </div>
              </li>
            ))}
            {!jobs.length ? <li className="muted">Aucun job defini.</li> : null}
          </ul>
        </div>

        <div className="card">
          <h3>Historique des runs</h3>
          {runsJobId ? (
            <>
              <p className="muted small">Derniers runs pour {runsJobId}</p>
              {runsLoading ? <p className="muted">Chargement...</p> : null}
              <ul className="insight-list">
                {jobRuns.length
                  ? jobRuns.map((item, idx) => (
                      <li key={`${runsJobId}-${idx}`}>
                        <strong>{item.status || 'n/a'}</strong>
                        <div className="muted small">{item.timestamp ? fmtDate(item.timestamp) : 'n/a'}</div>
                        {item.detail ? <div className="muted small">{item.detail}</div> : null}
                      </li>
                    ))
                  : <li className="muted">Aucune execution recente.</li>}
              </ul>
            </>
          ) : (
            <p className="muted">Cliquez sur “Runs” pour afficher l'historique d'un job dans ce panneau.</p>
          )}
        </div>

        <div className="card">
          <h3>Prochaines executions</h3>
          <p className="muted">Apercu des 5 prochaines occurrences planifiees (tous types confondus).</p>
          <ul className="task-list">
            {upcoming.map((job) => (
              <li key={`next-${job.id}`}>
                <strong>{label(job)}</strong>
                <div className="muted small">Prochaine execution: {fmtDate(job.next_run)}</div>
              </li>
            ))}
            {!upcoming.length ? <li className="muted">Aucune execution programmee.</li> : null}
          </ul>
          <Link to="/tasks" className="ghost-button" style={{ display: 'inline-block', marginTop: '.75rem' }}>
            Ouvrir Planification
          </Link>
        </div>

        <div className="card">
          <h3>Etat rapide</h3>
          <ul className="insight-list">
            <li>
              <div>
                <strong>{jobs.length}</strong>
                <span className="muted small">taches totales</span>
              </div>
              <small className="muted">
                llm {byType.llm} �?� rag {byType.rag} �?� backup {byType.backup} �?� plugin {byType.plugin}
              </small>
            </li>
            <li>
              <div>
                <strong>{pending.length}</strong>
                <span className="muted small">en attente / en cours</span>
              </div>
            </li>
            <li>
              <div>
                <strong>{failedCount}</strong>
                <span className="muted small">en echec</span>
              </div>
            </li>
          </ul>
          <p className="muted small" style={{ marginTop: '.75rem' }}>
            Utilisez cette synthese pour detecter rapidement les jobs sensibles avant un deploy ou une coupure.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.25rem' }}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap' }}>
              <div>
                <h3>Suggestions auto-learning</h3>
                <p className="muted small">
                  Prompts recurrents, favoris, jobs fiables et actions proposees par le module d'apprentissage progressif.
                </p>
              </div>
              <button onClick={() => void loadInsights()} disabled={loading}>
                Rafraichir
              </button>
            </div>
            {insightError ? <p className="danger">{insightError}</p> : null}
            {!insights && !insightError ? <p className="muted">Chargement des suggestions...</p> : null}
            {insights ? (
              <div className="insight-columns">
                <div>
                  <h4>Prompts recents</h4>
                  <ul className="insight-list">
                {insights.recent_prompts?.length
                  ? insights.recent_prompts.map((item) => (
                      <li key={`recent-${item.prompt}`}>
                        <span>{item.prompt}</span>
                        <small className="muted">{item.last_used ? fmtDate(item.last_used) : 'n/a'}</small>
                        <button className="ghost-button" onClick={() => void adoptPrompt(item.prompt || '')}>
                          Utiliser
                        </button>
                      </li>
                    ))
                  : <li className="muted">Aucun prompt recent.</li>}
                  </ul>
                </div>
                <div>
                  <h4>Favoris</h4>
                  <ul className="insight-list">
                {insights.favorite_prompts?.length
                  ? insights.favorite_prompts.map((item) => (
                      <li key={`fav-${item.prompt}`}>
                        <span>{item.prompt}</span>
                        <small className="muted">Utilisations : {item.count ?? 1}</small>
                        <button className="ghost-button" onClick={() => void adoptPrompt(item.prompt || '', true)}>
                          Favori
                        </button>
                      </li>
                    ))
                      : <li className="muted">Pas encore de favoris.</li>}
                  </ul>
                </div>
                <div>
                  <h4>Jobs fiables</h4>
                  <ul className="insight-list">
                    {insights.top_jobs?.length
                      ? insights.top_jobs.map((job) => (
                          <li key={`top-${job.id}`}>
                            <strong>{job.description || job.tag || job.id}</strong>
                            <small className="muted">
                              {job.type} �?� {job.success ?? job.success_count ?? 0} ok / {job.failure ?? job.failure_count ?? 0} ko
                            </small>
                          </li>
                        ))
                      : <li className="muted">Pas encore de statistiques.</li>}
                  </ul>
                </div>
                <div>
                  <h4>Actions suggerees</h4>
                  <ul className="insight-list">
                    {insights.suggestions?.length
                      ? insights.suggestions.map((item, idx) => (
                          <li key={`suggest-${idx}`}>
                            <div>
                              <strong>{item.question || 'Question'}</strong>
                              <small className="muted">Occurrences: {item.occurrences ?? 0}</small>
                            </div>
                            <div className="muted small">
                              {item.action}
                              {item.reason ? ` — ${item.reason}` : ''}
                            </div>
                            {item.question ? (
                              <button className="ghost-button" onClick={() => void adoptPrompt(item.question || '')}>
                                Mémoriser
                              </button>
                            ) : null}
                          </li>
                        ))
                      : <li className="muted">Aucune recommandation.</li>}
                  </ul>
                </div>
              </div>
            ) : null}
          </div>

      <div className="grid" style={{ marginTop: '1.25rem', gridTemplateColumns: 'repeat(auto-fit,minmax(300px,1fr))', gap: '1rem' }}>
        <div className="card">
          <h3>Top requetes web</h3>
          {insights?.top_queries?.length ? (
            <ul className="insight-list">
              {insights.top_queries.map((item, idx) => (
                <li key={`query-${idx}`}>
                  <strong>{item.query}</strong>
                  <div className="muted small">
                    Occurrences {item.occurrences ?? 0}
                    {typeof item.search_success === 'number' ? ` �?� succes ${item.search_success}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Aucune requete significative pour l'instant.</p>
          )}
        </div>

        <div className="card">
          <h3>Requetes non resolues</h3>
          {insights?.unresolved_queries?.length ? (
            <ul className="insight-list">
              {insights.unresolved_queries.map((item, idx) => (
                <li key={`unresolved-${idx}`}>
                  <strong>{item.query}</strong>
                  <div className="muted small">
                    {item.occurrences ?? 0} fois
                    {item.last_seen ? ` (dernier ${fmtDate(item.last_seen)})` : ''}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Rien �� signaler.</p>
          )}
        </div>

        <div className="card">
          <h3>RAG (full / incremental)</h3>
          {topRagJobs.length ? (
            <ul className="insight-list">
              {topRagJobs.map((job) => (
                <li key={`rag-${job.id}`}>
                  <strong>{label(job)}</strong>
                  <div className="muted small">
                    succes {job.success_count ?? 0} / echec {job.failure_count ?? 0}
                    {job.next_run ? ` — prochaine execution ${fmtDate(job.next_run)}` : ''}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Aucun job RAG trouve.</p>
          )}
        </div>

        <div className="card">
          <h3>Sujets à planifier</h3>
          {insights?.job_recommendations?.length ? (
            <ul className="insight-list">
              {insights.job_recommendations.map((item, idx) => (
                <li key={`hot-topic-${idx}`}>
                  <strong>{item.query}</strong>
                  <div className="muted small">
                    {item.occurrences ?? 0} occurrences • recherches web {item.needs_search_hits ?? 0}
                  </div>
                  {item.last_seen ? <div className="muted small">Dernier : {fmtDate(item.last_seen)}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Aucun sujet prioritaire recensé.</p>
          )}
        </div>

        <div className="card">
          <h3>Événements récents</h3>
          {insights?.recent_events?.length ? (
            <ul className="insight-list">
              {insights.recent_events.slice(0, 5).map((item, idx) => (
                <li key={`recent-event-${idx}`}>
                  <strong>{item.question || 'Requête'}</strong>
                  <div className="muted small">Query : {item.normalized_query || 'n/a'}</div>
                  <div className="muted small">{item.created_at ? fmtDate(item.created_at) : 'n/a'}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Pas encore d'événements.</p>
          )}
        </div>
      </div>
      <Toast />
    </section>
  )
}
