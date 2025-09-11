import { useEffect, useState } from 'react'
import { api } from '../api/client'

type Entry = { id: number, type: string, created_at: string, payload: any }

export default function HistoryPage() {
  const [items, setItems] = useState<Entry[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [plugin, setPlugin] = useState('')
  const [limit, setLimit] = useState(20)
  const [offset, setOffset] = useState(0)
  const [msg, setMsg] = useState('')

  async function load() {
    const res = await api.historyList({ q, plugin, limit, offset })
    setItems(res.items || [])
    setTotal(res.total || 0)
  }
  useEffect(()=>{ load() }, [q, plugin, limit, offset])

  async function replay(n=30) {
    try { await api.historyReplay(); setMsg(`Relecture demandée (N=${n}).`) } catch { setMsg('Échec relecture') }
  }

  return (
    <section>
      <h2>Historique</h2>
      <div className="row">
        <input placeholder="Recherche" value={q} onChange={e=>{setQ(e.target.value); setOffset(0)}} aria-label="Filtre texte" />
        <input placeholder="Plugin" value={plugin} onChange={e=>{setPlugin(e.target.value); setOffset(0)}} aria-label="Filtre plugin" />
        <button onClick={()=>replay(30)}>Rejouer N=30</button>
        {msg && <span className="muted">{msg}</span>}
      </div>
      <div className="muted">Total: {total}</div>
      <div className="grid">
        {items.map(e => (
          <div key={e.id} className="card">
            <div className="row" style={{justifyContent:'space-between'}}>
              <strong>{e.type}</strong>
              <span className="muted">{e.created_at}</span>
            </div>
            <pre style={{whiteSpace:'pre-wrap',maxHeight:'12rem',overflow:'auto'}}>{JSON.stringify(e.payload, null, 2)}</pre>
          </div>
        ))}
      </div>
      <div className="row" style={{marginTop:'.5rem'}}>
        <button disabled={offset===0} onClick={()=>setOffset(Math.max(0, offset - limit))}>Précédent</button>
        <button disabled={offset+limit>=total} onClick={()=>setOffset(offset + limit)}>Suivant</button>
        <select value={limit} onChange={e=>{setLimit(parseInt(e.target.value)); setOffset(0)}} aria-label="Taille page">
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </div>
    </section>
  )
}
