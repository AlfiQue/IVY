const API_URL = (import.meta as any).env?.VITE_API_URL || window.location.origin
const API_BASE = () => API_URL

let csrfToken: string | null = null
export function setCsrfToken(token: string) { csrfToken = token }
export function getCsrfToken() { return csrfToken }

async function req(path: string, opts: RequestInit = {}) {
  const url = API_BASE() + path
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opts.method && opts.method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  if (opts.body && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const res = await fetch(url, { credentials: 'include', headers, ...opts })
  const ct = res.headers.get('content-type') || ''
  const raw = await res.text()
  if (!res.ok) {
    let detail: unknown = raw
    if (ct.includes('application/json')) {
      try { detail = raw ? JSON.parse(raw) : null } catch { detail = raw }
    }
    const error: any = new Error(String(res.status))
    error.status = res.status
    error.detail = detail
    throw error
  }
  if (!raw) return null
  if (ct.includes('application/json')) {
    try { return JSON.parse(raw) } catch { return raw }
  }
  return raw
}

function qs(params: Record<string, any>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    search.append(k, String(v))
  })
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  login: async (user: string, password: string) => {
    const data = await req('/auth/login', { method:'POST', body: JSON.stringify({ user, password }) })
    setCsrfToken(data.csrf_token)
    return data
  },
  logout: () => req('/auth/logout', { method:'POST' }),

  chatQuery: (question: string, conversation_id?: number | null) => req('/chat/query', { method:'POST', body: JSON.stringify({ question, conversation_id }) }),
  chatConversations: (limit = 20, offset = 0) => req(`/chat/conversations${qs({ limit, offset })}`),
  createConversation: (title?: string | null) => req('/chat/conversations', { method:'POST', body: JSON.stringify({ title }) }),
  renameConversation: (id: number, title?: string | null) => req(`/chat/conversations/${id}`, { method:'PATCH', body: JSON.stringify({ title }) }),
  deleteConversation: (id: number) => req(`/chat/conversations/${id}`, { method:'DELETE' }),
  conversationMessages: (id: number, limit = 100, before_id?: number) => req(`/chat/conversations/${id}/messages${qs({ limit, before_id })}`),

  memoryList: (limit = 50, offset = 0, search?: string) => req(`/memory/qa${qs({ limit, offset, search })}`),
  memoryUpdate: (id: number, payload: any) => req(`/memory/qa/${id}`, { method:'PATCH', body: JSON.stringify(payload) }),
  memoryDelete: (id: number) => req(`/memory/qa/${id}`, { method:'DELETE' }),
  memoryClassifyLLM: (id: number, update_flag = false) => req(`/memory/qa/${id}/classify/llm${qs({ update_flag })}`, { method:'POST' }),
  memoryClassifyHeuristic: (id: number, update_flag = false) => req(`/memory/qa/${id}/classify/heuristic${qs({ update_flag })}`, { method:'POST' }),
  memoryExport: () => req('/memory/qa/export'),
  memoryImport: (items: any[]) => req('/memory/qa/import', { method:'POST', body: JSON.stringify({ items }) }),


  debugSearch: (q: string, limit = 5) => req(`/debug/search${qs({ q, limit })}`),
  jeedomStatus: () => req('/jeedom/status'),

  getConfig: () => req('/config'),
  updateConfig: (patch: any) => req('/config', { method:'PUT', body: JSON.stringify(patch) }),
  listKeys: () => req('/apikeys'),
  createKey: (name: string, scopes: string[]) => req('/apikeys', { method:'POST', body: JSON.stringify({ name, scopes }) }),
  deleteKey: (id: string) => req(`/apikeys/${encodeURIComponent(id)}`, { method:'DELETE' }),
  jobs: () => req('/jobs'),
  addJob: (payload: any) => req('/jobs/add', { method:'POST', body: JSON.stringify(payload) }),
  runJobNow: (id: string) => req(`/jobs/${id}/run-now`, { method:'POST' }),
    cancelJob: (id: string) => req(`/jobs/${id}/cancel`, { method:'POST' }),
    deleteJob: (id: string) => req(`/jobs/${id}`, { method:'DELETE' }),
    getJob: (id: string) => req(`/jobs/${id}`),
    jobRuns: (id: string, limit = 10) => req(`/jobs/${id}/runs?limit=${encodeURIComponent(String(limit))}`),
  updateJob: (id: string, payload: any) => req(`/jobs/${id}/update`, { method:'POST', body: JSON.stringify(payload) }),
  health: () => req('/health'),
  historyList: (params: any = {}) => req(`/history${qs(params)}`),
  sessions: () => req('/sessions'),
  terminateSession: (id: string) => req(`/sessions/${id}/terminate`, { method:'POST' }),
  exportBackup: async () => {
    const res = await fetch(API_BASE() + '/backup/export', { credentials:'include' })
    if (!res.ok) throw new Error('export failed')
    return await res.blob()
  },
  importBackup: (file: File, dry_run=true) => { const fd = new FormData(); fd.append('file', file); return req(`/backup/import?dry_run=${dry_run?'true':'false'}`, { method:'POST', body: fd })},
}

export function connectLLMStream() {
  throw new Error('Le streaming LLM n’est plus supporté. Utilisez chatQuery.')
}
