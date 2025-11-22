import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'

type Entry = { id: number, type: string, created_at: string, payload: any }

const formatDate = (value: string) => {
  try {
    const d = new Date(value)
    if (!Number.isNaN(d.getTime())) return d.toLocaleString()
  } catch {/* ignore */}
  return value
}

export default function HistoryPage() {
  const [items, setItems] = useState<Entry[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Entry | null>(null)
  const [clearing, setClearing] = useState(false)

  const load = useCallback(async () => {
    const res = await api.historyList({ q, limit, offset })
    setItems(res.items || [])
    setTotal(res.total || 0)
  }, [q, limit, offset])

  useEffect(() => {
    load()
  }, [load])

  async function handleClear() {
    if (!window.confirm("Supprimer tout l'historique ?")) return
    try {
      setClearing(true)
      await api.clearHistory()
      setOffset(0)
      setSelected(null)
      await load()
    } finally {
      setClearing(false)
    }
  }

  return (
    <section>
      <h2>Historique</h2>
      <div className="row">
        <input
          placeholder="Recherche"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOffset(0)
          }}
          aria-label="Filtre texte"
        />
        <select
          value={limit}
          onChange={(e) => {
            setLimit(parseInt(e.target.value))
            setOffset(0)
          }}
          aria-label="Taille page"
        >
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
        <div className="muted">Total: {total}</div>
        <button onClick={handleClear} disabled={clearing} aria-label="Purger l'historique complet">
          {clearing ? "Purge..." : "Vider l'historique"}
        </button>
      </div>
      <div>
        {items.map(entry => (
          <div key={entry.id} className="row" style={{borderBottom:'1px solid #222', padding:'.4rem 0', alignItems:'center'}}>
            <div style={{minWidth:'5rem'}} className="muted">#{entry.id}</div>
            <div style={{minWidth:'10rem'}}><strong>{entry.type}</strong></div>
            <div style={{minWidth:'14rem'}} className="muted">{formatDate(entry.created_at)}</div>
            <div style={{flex:1}} className="muted">{JSON.stringify(entry.payload ?? {}).slice(0,80)}</div>
            <button onClick={() => setSelected(entry)}>Voir</button>
          </div>
        ))}
        {!items.length && <p className="muted">Aucun événement</p>}
      </div>
      <div className="row" style={{ marginTop: '.5rem' }}>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Précédent</button>
        <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>Suivant</button>
      </div>
      {selected ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-card" style={{ width: 'min(800px, 95vw)' }}>
            <header className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>Évènement #{selected.id}</h3>
              <button onClick={() => setSelected(null)}>Fermer</button>
            </header>
            <p className="muted" style={{ marginTop: '.25rem' }}>
              {selected.type.toUpperCase()} • {formatDate(selected.created_at)}
            </p>
            <section style={{ marginTop: '1rem' }}>
              <pre className="panel" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(selected.payload ?? {}, null, 2)}</pre>
            </section>
          </div>
        </div>
      ) : null}
    </section>
  )
}
