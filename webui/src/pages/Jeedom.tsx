import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'

interface JeedomStatus {
  configured?: boolean
  base_url?: string | null
  reachable?: boolean
  status?: string | number
  error?: string
  status_code?: number
  body_preview?: string
  note?: string
}

interface JeedomEquipments {
  count?: number
  items?: any[]
  objects?: any[]
  objects_count?: number
  object_map?: Record<string, string>
  status_code?: number
  raw_preview?: string
  error?: string
  source?: string
}

interface JeedomCommands {
  count?: number
  items?: any[]
  status_code?: number
  raw_preview?: string
  error?: string
  source?: string
}

type CommandValueMap = Record<string, string>
type CommandLoadingMap = Record<string, boolean>

export default function JeedomPage() {
  const [status, setStatus] = useState<JeedomStatus>({})
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')

  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loadingData, setLoadingData] = useState(false)
  const [loadingAll, setLoadingAll] = useState(false)

  const [equipments, setEquipments] = useState<JeedomEquipments | null>(null)
  const [commands, setCommands] = useState<JeedomCommands | null>(null)

  const [filterTerm, setFilterTerm] = useState('')

  const [commandValues, setCommandValues] = useState<CommandValueMap>({})
  const [commandLoading, setCommandLoading] = useState<CommandLoadingMap>({})
  const [lastCommandDebug, setLastCommandDebug] = useState<string | null>(null)

  const [scenarioId, setScenarioId] = useState('')
  const [scenarioAction, setScenarioAction] = useState<'start' | 'stop' | 'enable' | 'disable'>('start')
  const [scenarioLoading, setScenarioLoading] = useState(false)
  const [scenarioMessage, setScenarioMessage] = useState<string | null>(null)
  const [intentQuery, setIntentQuery] = useState('')
  const [intentResult, setIntentResult] = useState<any | null>(null)
  const [intentLoading, setIntentLoading] = useState(false)
  const [intents, setIntents] = useState<any[] | null>(null)
  const [intentsLoading, setIntentsLoading] = useState(false)
  const [newIntentQuery, setNewIntentQuery] = useState('')
  const [newIntentCmd, setNewIntentCmd] = useState('')
  const [newIntentSaving, setNewIntentSaving] = useState(false)
  const [autoIntentInstructions, setAutoIntentInstructions] = useState('')
  const [autoIntentLoading, setAutoIntentLoading] = useState(false)
  const [autoIntentResult, setAutoIntentResult] = useState<any | null>(null)
  const [autoLimit, setAutoLimit] = useState(200)
  const [autoOffset, setAutoOffset] = useState(0)
  const [autoTargetCmdIds, setAutoTargetCmdIds] = useState('')
  const [autoMaxIntents, setAutoMaxIntents] = useState(30)
  const [resolveDebug, setResolveDebug] = useState<any | null>(null)
  const [resolveExec, setResolveExec] = useState<string | null>(null)

  async function loadStatus() {
    setTesting(true)
    setError(null)
    try {
      const res = await api.jeedomStatus()
      setStatus(res || {})
      setBaseUrl(String(res?.base_url ?? ''))
      return res || {}
    } catch {
      setError('Impossible de contacter Jeedom')
      return null
    } finally {
      setTesting(false)
    }
  }

  async function loadData(showMessage = false) {
    setLoadingData(true)
    setError(null)
    try {
      const [eq, cmds] = await Promise.all([api.jeedomEquipments(), api.jeedomCommands()])
      setEquipments(eq || {})
      setCommands(cmds || {})
      if (showMessage) {
        setMessage('Équipements et commandes actualisés.')
      }
    } catch {
      setError('Impossible de récupérer équipements/commandes.')
    } finally {
      setLoadingData(false)
    }
  }

  async function refreshAll() {
    setLoadingAll(true)
    const res = await loadStatus()
    if (res?.configured) {
      await loadData()
    }
    setLoadingAll(false)
  }

  useEffect(() => {
    refreshAll().catch(() => setError('Impossible de charger le statut Jeedom'))
    loadIntents().catch(() => null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function saveConfig() {
    setSaving(true)
    setMessage(null)
    setError(null)
    try {
      const payload: Record<string, unknown> = { jeedom_base_url: baseUrl.trim() }
      if (apiKey.trim()) {
        payload.jeedom_api_key = apiKey.trim()
      }
      await api.updateConfig(payload)
      setMessage('Configuration Jeedom mise à jour. Test en cours...')
      setApiKey('')
      await refreshAll()
    } catch (err) {
      if ((err as any)?.status === 401) {
        setError('Authentification requise pour modifier la configuration Jeedom.')
      } else {
        setError('Impossible de mettre à jour la configuration Jeedom.')
      }
    } finally {
      setSaving(false)
    }
  }

  const groupedData = useMemo(() => {
    const term = filterTerm.trim().toLowerCase()
    const objects = equipments?.objects ?? []
    const eqs = equipments?.items ?? []
    const cmds = commands?.items ?? []

    const eqByObject: Record<string, any[]> = {}
    for (const eq of eqs) {
      const oid = eq?.object_id != null ? String(eq.object_id) : 'sans_objet'
      if (!eqByObject[oid]) eqByObject[oid] = []
      eqByObject[oid].push(eq)
    }

    const cmdByEq: Record<string, any[]> = {}
    for (const cmd of cmds) {
      const eqId =
        cmd?.eq_id != null
          ? String(cmd.eq_id)
          : cmd?.eqId != null
            ? String(cmd.eqId)
            : cmd?.eqLogic_id != null
              ? String(cmd.eqLogic_id)
              : ''
      if (!eqId) continue
      if (!cmdByEq[eqId]) cmdByEq[eqId] = []
      cmdByEq[eqId].push(cmd)
    }

    const match = (value: any) => {
      if (!term) return true
      return String(value ?? '').toLowerCase().includes(term)
    }

    const objectList = objects.length ? objects : [{ id: 'sans_objet', name: 'Autres' }]
    const result = []

    for (const obj of objectList) {
      const objId = obj?.id != null ? String(obj.id) : 'sans_objet'
      const eqList = eqByObject[objId] ?? []
      const filteredEquipments = eqList
        .map((eq: any) => {
          const eqId = eq?.id != null ? String(eq.id) : ''
          const eqMatches =
            match(eq.name) ||
            match(eq.eqType_name) ||
            match(eq.id) ||
            match(eq.logicalId) ||
            match(eq.object_id)

          const eqCommandsAll = cmdByEq[eqId] ?? []
          const eqCommands =
            !term || eqMatches
              ? eqCommandsAll
              : eqCommandsAll.filter((cmd: any) => {
                  return (
                    match(cmd.name) ||
                    match(cmd.type) ||
                    match(cmd.subType) ||
                    match(cmd.eq_name) ||
                    match(cmd.eq_id) ||
                    match(cmd.logicalId)
                  )
                })

          if (term && !eqMatches && eqCommands.length === 0) {
            return null
          }
          return { eq, commands: eqCommands }
        })
        .filter(Boolean) as { eq: any; commands: any[] }[]

      const objMatches = match(obj.name) || match(obj.id)

      if (!term || objMatches || filteredEquipments.length > 0) {
        result.push({ object: obj, equipments: filteredEquipments })
      }
    }

    return {
      objectsCount: objects.length || Object.keys(eqByObject).length,
      equipmentCount: eqs.length,
      commandCount: cmds.length,
      groups: result,
    }
  }, [commands, equipments, filterTerm])

  const configured = !!status.configured
  const reachable = status.reachable === true
  const summaryStats = {
    objects: groupedData.objectsCount,
    equipments: groupedData.equipmentCount,
    commands: groupedData.commandCount,
  }

  async function runCommand(cmdId: string, forcedValue?: string | number | null) {
    if (!cmdId) return
    setError(null)
    setMessage(null)
    setCommandLoading((prev) => ({ ...prev, [cmdId]: true }))
    try {
      const value = forcedValue !== undefined ? forcedValue : commandValues[cmdId]
      setLastCommandDebug(
        JSON.stringify(
          {
            id: cmdId,
            value,
            note: 'request (avant réponse)',
          },
          null,
          2,
        ),
      )
      const res = await api.jeedomRunCommand(cmdId, value ?? null)
      if (!res || typeof res !== 'object') {
        const debug = { id: cmdId, value, response: res }
        console.warn('[Jeedom] run command (réponse inattendue)', debug)
        setLastCommandDebug(JSON.stringify(debug, null, 2))
        setError('Réponse inattendue du serveur.')
        return
      }

      const debug = {
        id: cmdId,
        value,
        status: res?.status_code ?? 'n/a',
        raw_preview: res?.raw_preview ?? '',
        params: res?.params ?? {},
        url: res?.url ?? '',
        safe_url: res?.safe_url ?? '',
      }
      console.info('[Jeedom] run command', debug)
      setLastCommandDebug(JSON.stringify(debug, null, 2))
      // Recharge les états pour mettre à jour les infos/commandes
      await loadData()
      setMessage(
        `Commande ${cmdId} envoyée.` +
          (res?.status_code ? ` Status ${res.status_code}.` : '') +
          (res?.raw_preview ? ` Réponse: ${res.raw_preview}` : '') +
          (res?.params ? ` Params: ${JSON.stringify(res.params)}` : ''),
      )
    } catch (err) {
      console.error('[Jeedom] command error', err)
      const statusCode = (err as any)?.status
      if (statusCode === 401) {
        setError('Authentification requise pour piloter cette commande.')
      } else {
        setError('Impossible d’exécuter la commande.')
      }
      setLastCommandDebug(
        JSON.stringify(
          {
            id: cmdId,
            value: forcedValue !== undefined ? forcedValue : commandValues[cmdId],
            error: (err as any)?.message ?? 'unknown',
            status: statusCode,
            detail: (err as any)?.detail,
          },
          null,
          2,
        ),
      )
    } finally {
      setCommandLoading((prev) => ({ ...prev, [cmdId]: false }))
    }
  }

  async function triggerScenario() {
    setScenarioMessage(null)
    setError(null)
    if (!scenarioId.trim()) {
      setError('Indiquez un ID de scénario.')
      return
    }
    setScenarioLoading(true)
    try {
      await api.jeedomScenarioAction(scenarioId.trim(), scenarioAction)
      setScenarioMessage(`Scénario ${scenarioId} (${scenarioAction}) exécuté.`)
    } catch (err) {
      const statusCode = (err as any)?.status
      if (statusCode === 401) {
        setError('Authentification requise pour piloter un scénario.')
      } else {
        setError("Impossible d'exécuter le scénario.")
      }
    } finally {
      setScenarioLoading(false)
    }
  }

  async function resolveIntent(execute = false) {
    if (!intentQuery.trim()) {
      setError('Indiquez une phrase/intention à résoudre.')
      return
    }
    setIntentLoading(true)
    setIntentResult(null)
    setError(null)
    try {
      const res = await api.jeedomResolve({ query: intentQuery.trim(), execute })
      setIntentResult(res)
      setResolveDebug(res)
      if (res?.executed?.status_code) {
        setResolveExec(`Exec cmd ${res.executed.id} status ${res.executed.status_code} source=${res.executed.source ?? '?'}`)
        setMessage(`Intent exécuté (cmd ${res.executed.id}) status ${res.executed.status_code}`)
        await loadData()
      } else {
        setResolveExec('Aucune exécution')
      }
    } catch (err) {
      console.error('[Jeedom] resolve error', err)
      const statusCode = (err as any)?.status
      if (statusCode === 401) setError('Authentification requise pour resolve.')
      else setError('Resolve Jeedom impossible.')
      setResolveDebug((err as any)?.detail ?? err)
    } finally {
      setIntentLoading(false)
    }
  }

  async function loadIntents() {
    setIntentsLoading(true)
    try {
      const res = await api.jeedomIntents()
      setIntents(res?.items ?? [])
    } catch {
      setError('Impossible de charger les intentions mémorisées.')
    } finally {
      setIntentsLoading(false)
    }
  }

  async function deleteIntent(cmdId?: string, query?: string) {
    setError(null)
    try {
      await api.jeedomIntentDelete(cmdId, query)
      await loadIntents()
    } catch {
      setError("Impossible de supprimer l'intention.")
    }
  }

  async function clearIntents() {
    setError(null)
    try {
      await api.jeedomIntentsClear()
      setIntents([])
    } catch {
      setError('Impossible de vider les intentions.')
    }
  }

  async function addIntent() {
    if (!newIntentQuery.trim() || !newIntentCmd.trim()) {
      setError('Indiquez une phrase et un cmd_id.')
      return
    }
    setNewIntentSaving(true)
    setError(null)
    try {
      await api.jeedomIntentAdd({ query: newIntentQuery.trim(), cmd_id: newIntentCmd.trim() })
      setNewIntentQuery('')
      setNewIntentCmd('')
      await loadIntents()
    } catch {
      setError("Impossible d'ajouter l'intention.")
    } finally {
      setNewIntentSaving(false)
    }
  }

  async function autoGenerateIntents() {
    setAutoIntentLoading(true)
    setAutoIntentResult(null)
    setError(null)
    try {
      const res = await api.jeedomIntentsAuto({
        instructions: autoIntentInstructions.trim() || undefined,
        limit_cmds: autoLimit,
        offset_cmds: autoOffset,
        target_cmd_ids: autoTargetCmdIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        max_intents: autoMaxIntents,
      })
      setAutoIntentResult(res)
      await loadIntents()
      setMessage(`Intentions générées: ${res?.added ?? 0} ajoutées.`)
    } catch {
      setError('Génération auto impossible (LLM). Vérifiez le modèle local.')
    } finally {
      setAutoIntentLoading(false)
    }
  }

  return (
    <div className="jeedom-page">
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <h1 style={{ margin: 0 }}>Jeedom</h1>
          <span
            style={{
              padding: '0.2rem 0.6rem',
              borderRadius: 999,
              fontSize: '0.85rem',
              background: reachable ? '#d7f6e5' : '#ffe4e4',
              color: reachable ? '#0f7b3c' : '#b30000',
              border: `1px solid ${reachable ? '#7ad1a1' : '#e48f8f'}`,
            }}
          >
            {reachable ? 'Connecté' : configured ? 'Hors ligne' : 'Non configuré'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button onClick={refreshAll} disabled={loadingAll}>
            {loadingAll ? 'Recharge…' : 'Recharger statut + données'}
          </button>
          <button onClick={() => loadData(true)} disabled={!configured || loadingData || loadingAll}>
            {loadingData ? 'Maj données…' : 'Maj équipements/commandes'}
          </button>
        </div>
      </header>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
        <span className="muted" style={{ padding: '0.35rem 0.6rem', border: '1px solid #e0e6ed', borderRadius: 8 }}>
          Objets : <strong>{summaryStats.objects}</strong>
        </span>
        <span className="muted" style={{ padding: '0.35rem 0.6rem', border: '1px solid #e0e6ed', borderRadius: 8 }}>
          Équipements : <strong>{summaryStats.equipments}</strong>
        </span>
        <span className="muted" style={{ padding: '0.35rem 0.6rem', border: '1px solid #e0e6ed', borderRadius: 8 }}>
          Commandes : <strong>{summaryStats.commands}</strong>
        </span>
        {lastCommandDebug ? (
          <button
            onClick={() => setLastCommandDebug(null)}
            style={{ marginLeft: 'auto', background: '#f6f7f9', color: '#4a5668' }}
          >
            Masquer debug
          </button>
        ) : null}
      </div>

      {lastCommandDebug ? (
        <pre
          style={{
            background: '#0b16230d',
            border: '1px solid #0b162333',
            padding: '0.5rem',
            fontSize: '0.85rem',
            whiteSpace: 'pre-wrap',
            borderRadius: 8,
            marginTop: '0.35rem',
          }}
        >
          {lastCommandDebug}
        </pre>
      ) : null}
      {resolveExec ? <p className="success" style={{ marginTop: '0.35rem' }}>{resolveExec}</p> : null}
      {resolveDebug ? (
        <pre
          style={{
            background: '#f5f2ff',
            border: '1px solid #d6ccf5',
            padding: '0.5rem',
            fontSize: '0.85rem',
            whiteSpace: 'pre-wrap',
            borderRadius: 8,
            marginTop: '0.35rem',
          }}
        >
          {JSON.stringify(resolveDebug, null, 2)}
        </pre>
      ) : null}

      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {scenarioMessage ? <p className="success">{scenarioMessage}</p> : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1rem',
          marginTop: '1rem',
        }}
      >
        <div className="card">
          <h3>Connexion</h3>
          <p>
            Statut :{' '}
            <strong style={{ color: configured ? '#0a7a2f' : '#b30000' }}>
              {configured ? 'Configuration détectée' : 'Non configurée'}
            </strong>
          </p>
          {status.base_url ? <p>Instance : {status.base_url}</p> : <p className="muted">URL non définie.</p>}
          <p>
            Connexion :{' '}
            <strong style={{ color: reachable ? '#0a7a2f' : '#b30000' }}>
              {reachable ? 'OK (pong)' : 'KO'}
            </strong>{' '}
            {status.status ? <span className="muted">({String(status.status)})</span> : null}
            {status.note ? <span className="muted" style={{ marginLeft: 4 }}>{status.note}</span> : null}
          </p>
          {status.error ? <p className="error">Erreur: {status.error}</p> : null}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button onClick={loadStatus} disabled={testing || loadingAll}>
              {testing ? 'Test…' : 'Tester la connexion'}
            </button>
            <button onClick={() => loadData(true)} disabled={!configured || loadingData || loadingAll}>
              {loadingData ? 'Chargement…' : 'Rafraîchir équipements/commandes'}
            </button>
            <button onClick={refreshAll} disabled={loadingAll}>
              {loadingAll ? 'Rafraîchissement…' : 'Recharger tout'}
            </button>
          </div>
        </div>

        <div className="card">
          <h3>Configurer Jeedom</h3>
          <label>
            URL Jeedom
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://192.168.1.10"
            />
          </label>
          <label>
            Clé API Jeedom
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Saisir la clé (masquée)"
            />
          </label>
          <p className="muted">La clé API est stockée côté serveur et ne sera pas ré-affichée ici.</p>
          <button onClick={saveConfig} disabled={saving}>
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>Scénarios</h3>
            <span className="muted">Piloter un scénario par ID</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <label style={{ flex: '1 1 200px' }}>
              ID scénario
              <input
                type="text"
                value={scenarioId}
                onChange={(e) => setScenarioId(e.target.value)}
                placeholder="ex: 12"
              />
            </label>
            <label>
              Action
              <select value={scenarioAction} onChange={(e) => setScenarioAction(e.target.value as any)}>
                <option value="start">start</option>
                <option value="stop">stop</option>
                <option value="enable">enable</option>
                <option value="disable">disable</option>
              </select>
            </label>
            <button onClick={triggerScenario} disabled={scenarioLoading || !configured}>
              {scenarioLoading ? 'Exécution…' : 'Lancer'}
            </button>
          </div>
          <p className="muted" style={{ marginTop: -8 }}>
            Indiquez l'ID du scénario Jeedom puis choisissez l'action à envoyer.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>Intent → Commande (LLM)</h3>
            <span className="muted">Résolution et apprentissage local</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="text"
              value={intentQuery}
              onChange={(e) => setIntentQuery(e.target.value)}
              placeholder="ex: allume bureau"
              style={{ flex: '1 1 240px' }}
            />
            <button onClick={() => resolveIntent(false)} disabled={intentLoading || !configured}>
              {intentLoading ? 'Recherche…' : 'Chercher'}
            </button>
            <button onClick={() => resolveIntent(true)} disabled={intentLoading || !configured}>
              {intentLoading ? 'Exécution…' : 'Chercher + exécuter si unique'}
            </button>
          </div>
          {intentResult ? (
            <div className="muted" style={{ fontSize: '0.9rem' }}>
              {intentResult.memory_hit ? (
                <div>
                  <strong>Mémoire :</strong> {JSON.stringify(intentResult.memory_hit)}
                </div>
              ) : null}
              <div>
                <strong>Matches ({intentResult.matched_count}):</strong>{' '}
                {intentResult.matched
                  ? intentResult.matched
                      .slice(0, 5)
                      .map(
                        (m: any) =>
                          `${m.name ?? '?'} (id=${m.id}, eq=${m.eq_name ?? m.eq_id ?? '?'}, score=${m.score})`,
                      )
                      .join(' | ')
                  : ' - '}
              </div>
              {intentResult.executed ? (
                <div>
                  <strong>Exécuté :</strong>{' '}
                  {`cmd ${intentResult.executed.id}, status ${intentResult.executed.status_code}, source ${intentResult.executed.source ?? '?'}`}
                  {intentResult.executed.raw_preview ? ` · ${intentResult.executed.raw_preview}` : ''}
                </div>
              ) : (
                <div>Exécution : aucune (matches multiples ou execute=false).</div>
              )}
            </div>
          ) : (
            <p className="muted" style={{ marginTop: -8 }}>
              Saisissez une phrase type “allume bureau” ou “off salon”, puis lancez une recherche ou l’exécution directe.
            </p>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>Intentions mémorisées</h3>
            <span className="muted">Table locale query → cmd_id (jeedom_intents.json)</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <button onClick={loadIntents} disabled={intentsLoading || !configured}>
              {intentsLoading ? 'Chargement…' : 'Charger'}
            </button>
            <button onClick={clearIntents} disabled={intentsLoading || !configured}>
              Vider
            </button>
            <button onClick={autoGenerateIntents} disabled={autoIntentLoading || !configured}>
              {autoIntentLoading ? 'Auto (LLM)…' : 'Auto (LLM)'}
            </button>
            <span className="muted">Ajouter :</span>
            <input
              type="text"
              placeholder="phrase ex: allume bureau"
              value={newIntentQuery}
              onChange={(e) => setNewIntentQuery(e.target.value)}
              style={{ minWidth: 200 }}
            />
            <input
              type="text"
              placeholder="cmd_id ex: 1616"
              value={newIntentCmd}
              onChange={(e) => setNewIntentCmd(e.target.value)}
              style={{ width: 120 }}
            />
            <button onClick={addIntent} disabled={newIntentSaving || intentsLoading || !configured}>
              {newIntentSaving ? 'Ajout…' : 'Ajouter'}
            </button>
          </div>
          <label>
            Instructions LLM (optionnel)
            <textarea
              rows={2}
              placeholder="Ex: privilégie les lumières et les commandes on/off"
              value={autoIntentInstructions}
              onChange={(e) => setAutoIntentInstructions(e.target.value)}
            />
          </label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <label>
              Limit
              <input
                type="number"
                min={10}
                max={400}
                value={autoLimit}
                onChange={(e) => setAutoLimit(Number(e.target.value))}
                style={{ width: 90 }}
              />
            </label>
            <label>
              Offset
              <input
                type="number"
                min={0}
                value={autoOffset}
                onChange={(e) => setAutoOffset(Number(e.target.value))}
                style={{ width: 90 }}
              />
            </label>
            <label style={{ flex: '1 1 220px' }}>
              Cmd IDs ciblés (optionnel, virgule)
              <input
                type="text"
                placeholder="ex: 1616,1615"
                value={autoTargetCmdIds}
                onChange={(e) => setAutoTargetCmdIds(e.target.value)}
              />
            </label>
            <label>
              Max intents
              <input
                type="number"
                min={5}
                max={200}
                value={autoMaxIntents}
                onChange={(e) => setAutoMaxIntents(Number(e.target.value))}
                style={{ width: 90 }}
              />
            </label>
            <span className="muted">Traite par lots (ex: offset 0, 200, 400...).</span>
          </div>
          {autoIntentResult ? (
            <div className="muted" style={{ fontSize: '0.9rem' }}>
              <div>
                Généré : {autoIntentResult?.generated?.length ?? 0} · Ajoutés : {autoIntentResult?.added ?? 0}
              </div>
              {autoIntentResult.raw_model_output ? (
                <div>LLM preview: {autoIntentResult.raw_model_output}</div>
              ) : null}
            </div>
          ) : null}
          {intents && intents.length > 0 ? (
            <div className="table-like" style={{ marginTop: '0.25rem' }}>
              <div className="table-row header">
                <span>Query</span>
                <span>Cmd ID</span>
                <span>Source</span>
                <span>TS</span>
                <span>Action</span>
              </div>
              {intents.slice(0, 40).map((it: any) => (
                <div key={`${it.query}-${it.cmd_id}-${it.ts}`} className="table-row">
                  <span>{it.query}</span>
                  <span>{it.cmd_id}</span>
                  <span>{it.source ?? '-'}</span>
                  <span>{it.ts ?? '-'}</span>
                  <span>
                    <button onClick={() => deleteIntent(it.cmd_id, it.query)} disabled={intentsLoading}>
                      Supprimer
                    </button>
                  </span>
                </div>
              ))}
              {intents.length > 40 ? (
                <div className="table-row">
                  <span className="muted">+{intents.length - 40} supplémentaires…</span>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="muted" style={{ marginTop: -4 }}>Aucune intention mémorisée.</p>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>Objets → Équipements → Commandes</h3>
          <span className="muted">
            {groupedData.objectsCount} objets · {groupedData.equipmentCount} équipements · {groupedData.commandCount}{' '}
            commandes
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="text"
            value={filterTerm}
            onChange={(e) => setFilterTerm(e.target.value)}
            placeholder="Filtrer par nom/ID/équipement/commande…"
            style={{ minWidth: 260 }}
          />
          <span className="muted">Filtre appliqué sur objets, équipements et commandes.</span>
        </div>
        {equipments?.error ? <p className="error">{equipments.error}</p> : null}
        {commands?.error ? <p className="error">{commands.error}</p> : null}

        <div style={{ display: 'grid', gap: '0.75rem', marginTop: '0.75rem' }}>
          {groupedData.groups.map(({ object, equipments }) => (
            <div
              key={object.id ?? Math.random()}
              className="card"
              style={{ background: '#0b1a2a10', color: '#0b1623' }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: '0.5rem',
                  marginBottom: '0.35rem',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{object.name ?? 'Sans nom'}</div>
                  <div className="muted">
                    Objet ID {object.id ?? '-'} · {equipments.length} équipements
                  </div>
                </div>
                {object.position ? <span className="muted">Position {object.position}</span> : null}
              </div>

              {equipments.length === 0 ? (
                <p className="muted">Aucun équipement correspondant.</p>
              ) : (
                <div style={{ display: 'grid', gap: '0.5rem' }}>
                  {equipments.map(({ eq, commands }) => (
                    <div
                      key={eq.id ?? Math.random()}
                      className="card"
                      style={{ background: '#ffffff', color: '#0b1623' }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          gap: '0.5rem',
                          alignItems: 'baseline',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 600 }}>
                            {eq.name ?? 'Équipement'}
                            {eq.id ? <span className="muted"> · #{eq.id}</span> : null}
                          </div>
                          <div className="muted">
                            {eq.eqType_name ?? 'type ?'} · objet {eq.object_id ?? '-'}
                          </div>
                        </div>
                        {commands.length ? (
                          <span className="muted">{commands.length} commandes</span>
                        ) : (
                          <span className="muted">0 commande</span>
                        )}
                      </div>

                      {commands.length === 0 ? (
                        <p className="muted" style={{ marginTop: '0.25rem' }}>
                          Aucune commande pour cet équipement.
                        </p>
                      ) : (
                        <div className="table-like" style={{ marginTop: '0.4rem' }}>
                          <div className="table-row header">
                            <span>ID</span>
                            <span>Nom</span>
                            <span>Type</span>
                            <span>Valeur / Action</span>
                          </div>
                          {commands.slice(0, 80).map((cmd: any) => {
                            const isAction = (cmd.type || '').toLowerCase() === 'action'
                            const cmdId = String(cmd.id ?? '')
                            const state = cmd.state ?? cmd.value ?? cmd.display ?? '-'
                            const stateDisplay = state === undefined || state === null ? '-' : String(state)
                            const nameLower = (cmd.name || '').toLowerCase()
                            const isOnAction = nameLower.includes('on')
                            const isOffAction = nameLower.includes('off')

                            return (
                              <div key={cmd.id ?? `${cmd.eq_id}-${cmd.name}-${Math.random()}`} className="table-row">
                                <span>{cmd.id ?? '-'}</span>
                                <span>{cmd.name ?? '-'}</span>
                                <span>
                                  {cmd.type ?? '-'}
                                  {cmd.subType ? ` (${cmd.subType})` : ''}
                                </span>
                                <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                                  {!isAction ? (
                                    <span
                                      className="muted"
                                      style={{
                                        padding: '2px 6px',
                                        borderRadius: 4,
                                        background: '#0b16230d',
                                        border: '1px solid #0b162333',
                                      }}
                                    >
                                      {stateDisplay}
                                    </span>
                                  ) : isOnAction || isOffAction ? (
                                    <button onClick={() => runCommand(cmdId, null)} disabled={commandLoading[cmdId]}>
                                      {isOnAction ? 'ON' : isOffAction ? 'OFF' : cmd.name ?? 'Action'}
                                    </button>
                                  ) : (
                                    <>
                                      <input
                                        type="text"
                                        placeholder="valeur"
                                        value={commandValues[cmdId] ?? ''}
                                        onChange={(e) =>
                                          setCommandValues((prev) => ({
                                            ...prev,
                                            [cmdId]: e.target.value,
                                          }))
                                        }
                                        style={{ width: 90 }}
                                      />
                                      <button onClick={() => runCommand(cmdId)} disabled={commandLoading[cmdId]}>
                                        {commandLoading[cmdId] ? '…' : 'Exécuter'}
                                      </button>
                                    </>
                                  )}
                                </span>
                              </div>
                            )
                          })}
                          {commands.length > 80 ? (
                            <div className="table-row">
                              <span className="muted">+{commands.length - 80} supplémentaires (affinez le filtre).</span>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
