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
  const ct = res.headers.get('content-type') || ''
  if (!res.ok) {
    let detail: unknown = null
    try {
      if (ct.includes('application/json')) {
        detail = await res.json()
      } else {
        const text = await res.text()
        detail = text
      }
    } catch {
      detail = null
    }
    const err = new Error(`${res.status}`)
    ;(err as any).status = res.status
    if (detail !== null && detail !== undefined) (err as any).detail = detail
    throw err
  }
  if (ct.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

interface ApiClient {
  [key: string]: (...args: any[]) => any
  login(user: string, password: string): Promise<any>
  logout(): Promise<any>

  plugins(): Promise<any>
  pluginAction(name: string, action: 'enable'|'disable'|'start'|'stop'|'reload'): Promise<any>
  pluginUpload(file: File): Promise<any>

  getConfig(): Promise<any>
  updateConfig(payload: any): Promise<any>
  importConfig(file: File): Promise<any>
  restartServer(): Promise<any>

  chatConversations(limit?: number, offset?: number): Promise<any>
  createConversation(title?: string | null): Promise<any>
  deleteConversation(id: number): Promise<any>
  conversationMessages(id: number, limit?: number, beforeId?: number): Promise<any>
  chatQuery(
    payload:
      | { question: string; conversation_id?: number; user?: string; use_speculative?: boolean }
      | string,
    conversationId?: number | null
  ): Promise<any>

  infer(prompt: string, options?: any): Promise<any>

  ragReindex(full?: boolean): Promise<any>
  ragQuery(query: string, top_k?: number): Promise<any>

  jobs(params?: { job_type?: string | null; status?: string | null; q?: string | null }): Promise<any>
  addJob(payload: any): Promise<any>
  runJobNow(id: string): Promise<any>
  cancelJob(id: string): Promise<any>
  deleteJob(id: string): Promise<any>
  getJob(id: string): Promise<any>
  updateJob(id: string, payload: any): Promise<any>
  duplicateJob(id: string, payload?: any): Promise<any>
  jobRuns(id: string, limit?: number): Promise<any>
  jobPromptsRecent(limit?: number): Promise<any>
  jobPromptsFavorites(limit?: number): Promise<any>
  saveJobPrompt(prompt: string, favorite?: boolean): Promise<any>
  learningInsights(limit?: number): Promise<any>

  listKeys(): Promise<any>
  createKey(payload: any): Promise<any>
  deleteKey(id: string): Promise<any>

  memoryList(limit?: number, offset?: number, search?: string): Promise<any>
  memoryUpdate(id: number, payload: any): Promise<any>
  memoryDelete(id: number): Promise<any>
  memoryClassifyLLM(id: number, updateFlag?: boolean): Promise<any>
  memoryClassifyHeuristic(id: number, updateFlag?: boolean): Promise<any>
  memoryExport(): Promise<any>
  memoryImport(items: any[]): Promise<any>

  health(): Promise<any>

  historyReplay(): Promise<any>
  historyList(params?: Record<string, string | number | boolean | undefined>): Promise<any>
  clearHistory(): Promise<any>

  sessions(): Promise<any>
  terminateSession(id: string): Promise<any>

  exportBackup(): Promise<Blob>
  importBackup(file: File, dry_run?: boolean): Promise<any>

  debugSearch(query: string, limit?: number): Promise<any>
  debugLLMProfiles(payload: any): Promise<any>

  jeedomStatus(): Promise<any>
  jeedomEquipments(): Promise<any>
  jeedomCommands(): Promise<any>
  jeedomRaw(type: string): Promise<any>
  jeedomRunCommand(id: string, value?: string | number | null, params?: Record<string, any>): Promise<any>
  jeedomScenarioAction(id: string, action?: 'start' | 'stop' | 'enable' | 'disable'): Promise<any>
  jeedomResolve(body: { query: string; execute?: boolean }): Promise<any>
  jeedomCatalog(): Promise<any>
  jeedomIntents(): Promise<any>
  jeedomIntentDelete(cmd_id?: string, query?: string): Promise<any>
  jeedomIntentsClear(): Promise<any>
  jeedomIntentAdd(body: { query: string; cmd_id: string }): Promise<any>
  jeedomIntentsAuto(body?: { instructions?: string; limit_cmds?: number; offset_cmds?: number; target_cmd_ids?: string[]; max_intents?: number }): Promise<any>
}

export const api: ApiClient = {
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

  // Config
  getConfig: () => req('/config'),
  updateConfig: (payload: any) => req('/config', { method:'PUT', body: JSON.stringify(payload) }),
  importConfig: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req('/config/import', { method: 'POST', body: fd })
  },
  restartServer: () => req('/config/restart', { method: 'POST' }),

  // Chat
  chatConversations: (limit = 20, offset = 0) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    return req(`/chat/conversations?${params.toString()}`);
  },
  createConversation: (title?: string) => req('/chat/conversations', { method:'POST', body: JSON.stringify({ title }) }),
  deleteConversation: (id: number) => req(`/chat/conversations/${encodeURIComponent(String(id))}`, { method:'DELETE' }),
  conversationMessages: (id: number, limit = 100, beforeId?: number) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (beforeId !== undefined) params.set('before_id', String(beforeId));
    return req(`/chat/conversations/${encodeURIComponent(String(id))}/messages?${params.toString()}`);
  },
  chatQuery: (
    payload:
      | { question: string; conversation_id?: number; user?: string; use_speculative?: boolean }
      | string,
    conversationId?: number | null,
  ) => {
    const body =
      typeof payload === 'string'
        ? {
            question: payload,
            ...(conversationId !== undefined && conversationId !== null
              ? { conversation_id: conversationId }
              : {}),
          }
        : payload
    return req('/chat/query', { method: 'POST', body: JSON.stringify(body) })
  },

  // LLM
  infer: (prompt: string, options?: any) => req('/llm/infer', { method:'POST', body: JSON.stringify({ prompt, options }) }),

  // RAG
  ragReindex: (full=true) => req('/rag/reindex', { method:'POST', body: JSON.stringify({ full }) }),
  ragQuery: (query: string, top_k=5) => req('/rag/query', { method:'POST', body: JSON.stringify({ query, top_k }) }),

  // Jobs
  jobs: (params?: { job_type?: string | null; status?: string | null; q?: string | null }) => {
    const search = new URLSearchParams()
    if (params?.job_type) search.set('job_type', params.job_type)
    if (params?.status) search.set('status', params.status)
    if (params?.q) search.set('q', params.q)
    const suffix = search.toString()
    return req(`/jobs${suffix ? `?${suffix}` : ''}`)
  },
  addJob: (payload: any) => req('/jobs/add', { method:'POST', body: JSON.stringify(payload) }),
  runJobNow: (id: string) => req(`/jobs/${id}/run-now`, { method:'POST' }),
  cancelJob: (id: string) => req(`/jobs/${id}/cancel`, { method:'POST' }),
  deleteJob: (id: string) => req(`/jobs/${id}`, { method:'DELETE' }),
  getJob: (id: string) => req(`/jobs/${id}`),
  updateJob: (id: string, payload: any) => req(`/jobs/${id}/update`, { method:'POST', body: JSON.stringify(payload) }),
  duplicateJob: (id: string, payload?: any) =>
    req(`/jobs/${id}/duplicate`, {
      method: 'POST',
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    }),
  jobRuns: (id: string, limit = 10) =>
    req(`/jobs/${id}/runs?limit=${encodeURIComponent(String(limit))}`),
  jobPromptsRecent: (limit = 10) => req(`/jobs/prompts/recent?limit=${encodeURIComponent(String(limit))}`),
  jobPromptsFavorites: (limit = 10) => req(`/jobs/prompts/favorites?limit=${encodeURIComponent(String(limit))}`),
  saveJobPrompt: (prompt: string, favorite = false) =>
    req('/jobs/prompts/save', { method: 'POST', body: JSON.stringify({ prompt, favorite }) }),
  learningInsights: (limit = 10) => req(`/learning/insights?limit=${encodeURIComponent(String(limit))}`),

  // API Keys
  listKeys: () => req('/apikeys'),
  createKey: (payload: any) => req('/apikeys', { method:'POST', body: JSON.stringify(payload) }),
  deleteKey: (id: string) => req(`/apikeys/${encodeURIComponent(id)}`, { method:'DELETE' }),

  // Memory
  memoryList: (limit = 50, offset = 0, search?: string) => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (search) params.set('search', search)
    return req(`/memory/qa?${params.toString()}`)
  },
  memoryUpdate: (id: number, payload: any) => req(`/memory/qa/${id}`, { method:'PATCH', body: JSON.stringify(payload) }),
  memoryDelete: (id: number) => req(`/memory/qa/${id}`, { method:'DELETE' }),
  memoryClassifyLLM: (id: number, updateFlag = false) =>
    req(`/memory/qa/${id}/classify/llm${updateFlag ? '?update_flag=true' : ''}`, { method:'POST' }),
  memoryClassifyHeuristic: (id: number, updateFlag = false) =>
    req(`/memory/qa/${id}/classify/heuristic${updateFlag ? '?update_flag=true' : ''}`, { method:'POST' }),
  memoryExport: () => req('/memory/qa/export'),
  memoryImport: (items: any[]) => req('/memory/qa/import', { method:'POST', body: JSON.stringify({ items }) }),

  // Health
  health: () => req('/health'),

  // History (replay)
  historyReplay: () => req('/history/replay', { method:'POST' }),
  historyList: (params: any = {}) => {
    const q = new URLSearchParams(params)
    return req(`/history?${q.toString()}`)
  },
  clearHistory: () => req('/history', { method: 'DELETE' }),

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

  // Debug
  debugSearch: (query: string, limit = 5) => {
    const params = new URLSearchParams()
    params.set('q', query)
    params.set('limit', String(limit))
    return req(`/debug/search?${params.toString()}`)
  },
  debugLLMProfiles: (payload: any) => req('/debug/llm-profiles', { method:'POST', body: JSON.stringify(payload) }),

  // Jeedom
  jeedomStatus: () => req('/jeedom/status'),
  jeedomEquipments: () => req('/jeedom/equipments'),
  jeedomCommands: () => req('/jeedom/commands'),
  jeedomRaw: (type: string) => req(`/jeedom/raw?type=${encodeURIComponent(type)}`),
  jeedomRunCommand: (id: string, value?: string | number | null, params?: Record<string, any>) => {
    const qs = `?id=${encodeURIComponent(id)}`
    return req(`/jeedom/command/run${qs}`, { method: 'POST', body: JSON.stringify({ id, value, params }) })
  },
  jeedomScenarioAction: (id: string, action: 'start' | 'stop' | 'enable' | 'disable' = 'start') =>
    req('/jeedom/scenario', { method: 'POST', body: JSON.stringify({ id, action }) }),
  jeedomResolve: (body: { query: string; execute?: boolean }) => {
    const params = new URLSearchParams()
    if (body.query) params.set('query', body.query)
    if (body.execute !== undefined) params.set('execute', body.execute ? 'true' : 'false')
    const suffix = params.toString()
    return req(`/jeedom/resolve${suffix ? `?${suffix}` : ''}`, { method: 'POST', body: JSON.stringify(body) })
  },
  jeedomCatalog: () => req('/jeedom/catalog'),
  jeedomIntents: () => req('/jeedom/intents'),
  jeedomIntentAdd: (body: { query: string; cmd_id: string }) =>
    req('/jeedom/intents', { method: 'POST', body: JSON.stringify(body) }),
  jeedomIntentDelete: (cmd_id?: string, query?: string) => {
    const params = new URLSearchParams()
    if (cmd_id) params.set('cmd_id', cmd_id)
    if (query) params.set('query', query)
    const suffix = params.toString()
    return req(`/jeedom/intents${suffix ? `?${suffix}` : ''}`, { method: 'DELETE' })
  },
  jeedomIntentsClear: () => req('/jeedom/intents/all', { method: 'DELETE' }),
  jeedomIntentsAuto: (body: { instructions?: string; limit_cmds?: number; offset_cmds?: number } = {}) =>
    req('/jeedom/intents/auto', { method: 'POST', body: JSON.stringify(body) }),
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



