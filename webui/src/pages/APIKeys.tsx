import { useEffect, useState } from 'react'
import { api } from '../api/client'

type KeyItem = { id: string, name: string, created_at: string, last_used_at?: string|null, scopes: string[] }

export default function APIKeysPage() {
  const [items, setItems] = useState<KeyItem[]>([])
  const [name, setName] = useState('client')
  const [scopes, setScopes] = useState<string[]>(['llm'])
  const [created, setCreated] = useState<{id:string,name:string,key:string,scopes:string[],created_at:string}|null>(null)

  async function load() {
    try {
      const res = await api.listKeys()
      setItems((res.keys || []) as KeyItem[])
    } catch (_e) { /* ignore */ }
  }

  useEffect(()=>{ load() },[])

  const toggleScope = (s: string) => {
    setScopes(prev => prev.includes(s) ? prev.filter(x=>x!==s) : [...prev, s])
  }

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.createKey({ name, scopes })
      setCreated(res)
      await load()
    } catch (_e) { /* ignore */ }
  }

  const onDelete = async (id: string) => {
    try { await api.deleteKey(id); await load() } catch (_e) { /* ignore */ }
  }

  const scopeList = ['chat','memory','debug','jobs','history']

  return (
    <section>
      <h2>API Keys</h2>
      <form onSubmit={onCreate} className="row">
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="Nom de la clé" aria-label="Nom de la clé" />
        <div>
          {scopeList.map(s => (
            <label key={s} style={{marginRight: '1rem'}}>
              <input type="checkbox" checked={scopes.includes(s)} onChange={()=>toggleScope(s)} /> {s}
            </label>
          ))}
        </div>
        <button>Créer</button>
      </form>

      {created ? (
        <div className="alert">
          <strong>Nouvelle clé:</strong> {created.key} <small>(copiez-la maintenant, elle ne sera plus visible)</small>
        </div>
      ) : null}

      <table>
        <thead>
          <tr><th>Nom</th><th>Scopes</th><th>Créée</th><th>Dernier usage</th><th></th></tr>
        </thead>
        <tbody>
          {items.map(it => (
            <tr key={it.id}>
              <td>{it.name}</td>
              <td>{it.scopes?.join(', ')}</td>
              <td>{it.created_at}</td>
              <td>{it.last_used_at || '-'}</td>
              <td><button onClick={()=>onDelete(it.id)}>Supprimer</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

