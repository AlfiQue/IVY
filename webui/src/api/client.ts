const API_URL = (import.meta as any).env?.VITE_API_URL || window.location.origin
const API_BASE = () => API_URL

let csrfToken: string | null = null
export function setCsrfToken(token: string) { csrfToken = token }
export function getCsrfToken() { return csrfToken }

async function req(path: string, opts: RequestInit = {}) {
  const url = API_BASE() + path
  const headers: Record<string,string> = { 'Accept': 'application/json' }
  if (opts.method && opts.method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  if (opts.body && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const res = await fetch(url, { credentials: 'include', headers, ...opts })
  if (!res.ok) throw new Error(`${res.status}`)
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? res.json() : res.text()
}

export const api = {
  // Auth
  login: async (user: string, password: string) => {
    const data = await req('/auth/login', { method:'POST', body: JSON.stringify({ user, password }) })
    setCsrfToken(data.csrf_token)
    return data
  },
  logout: () => req('/auth/logout', { method:'POST' }),

  // Plugins
  plugins: () => req('/plugins'),
  pluginAction: (name: string, action: 'enable'|'disable'|'start'|'stop'|'reload') => req(`/plugins/${encodeURIComponent(name)}/${action}`, { method:'POST' }),
  pluginUpload: (file: File) => { const fd = new FormData(); fd.append('file', file); return req('/plugins/upload', { method:'POST', body: fd })},

  // LLM
  infer: (prompt: string, options?: any) => req('/llm/infer', { method:'POST', body: JSON.stringify({ prompt, options }) }),

  // RAG
  ragReindex: (full=true) => req('/rag/reindex', { method:'POST', body: JSON.stringify({ full }) }),
  ragQuery: (query: string, top_k=5) => req('/rag/query', { method:'POST', body: JSON.stringify({ query, top_k }) }),

  // Jobs
  jobs: () => req('/jobs'),
  addJob: (payload: any) => req('/jobs/add', { method:'POST', body: JSON.stringify(payload) }),
  runJobNow: (id: string) => req(`/jobs/${id}/run-now`, { method:'POST' }),
  cancelJob: (id: string) => req(`/jobs/${id}/cancel`, { method:'POST' }),
  deleteJob: (id: string) => req(`/jobs/${id}`, { method:'DELETE' }),
  getJob: (id: string) => req(`/jobs/${id}`),
  updateJob: (id: string, payload: any) => req(`/jobs/${id}/update`, { method:'POST', body: JSON.stringify(payload) }),

  // Health
  health: () => req('/health'),

  // History (replay)
  historyReplay: () => req('/history/replay', { method:'POST' }),
  historyList: (params: any = {}) => {
    const q = new URLSearchParams(params)
    return req(`/history?${q.toString()}`)
  },

  // Sessions
  sessions: () => req('/sessions'),
  terminateSession: (id: string) => req(`/sessions/${id}/terminate`, { method:'POST' }),

  // Backup
  exportBackup: async () => {
    const res = await fetch(API_BASE() + '/backup/export', { credentials:'include' })
    if (!res.ok) throw new Error('export failed')
    return await res.blob()
  },
  importBackup: (file: File, dry_run=true) => { const fd = new FormData(); fd.append('file', file); return req(`/backup/import?dry_run=${dry_run?'true':'false'}`, { method:'POST', body: fd })},
}

export function connectLLMStream(prompt: string, options?: any) {
  const api = new URL(API_URL)
  const proto = api.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${api.host}/llm/stream`
  const ws = new WebSocket(url)
  const req = { type: 'request', req_id: Date.now().toString(), source: 'webui', event: 'start', payload: { prompt, options }, ts: Date.now() }
  return {
    ws,
    start(onToken: (t: string) => void, onEnd: () => void, onError: (e: any) => void) {
      ws.onopen = () => ws.send(JSON.stringify(req))
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.event === 'token') onToken(data.payload)
          if (data.event === 'end') onEnd()
          if (data.event === 'error') onError(data.payload)
        } catch { /* ignore */ }
      }
      ws.onerror = onError
    },
    close() { try { ws.close() } catch {} }
  }
}
