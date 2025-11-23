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
        <h3>Scénarios</h3>
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
        <p className="muted" style={{ marginTop: 4 }}>
          Indiquez l'ID du scénario Jeedom puis choisissez l'action à envoyer.
        </p>
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
