import { useEffect, useState } from 'react'
import { api } from '../api/client'

type PluginItem = { name: string, state: string, meta: any }

export default function PluginsPage() {
  const [items, setItems] = useState<PluginItem[]>([])
  const [file, setFile] = useState<File|null>(null)
  async function load() {
    const data = await api.plugins()
    setItems(data.plugins)
  }
  useEffect(()=>{ load() },[])
  async function action(name: string, act: 'enable'|'disable'|'start'|'stop'|'reload') {
    await api.pluginAction(name, act)
    await load()
  }
  async function upload() {
    if (!file) return
    await api.pluginUpload(file)
    setFile(null)
    await load()
  }
  return (
    <section>
      <h2>Plugins</h2>
      <div className="toolbar">
        <input type="file" accept=".zip" onChange={e=>setFile(e.target.files?.[0] || null)} aria-label="Sélectionner un ZIP" />
        <button onClick={upload} disabled={!file}>Uploader ZIP</button>
      </div>
      <div className="grid">
        {items.map(p=> (
          <div key={p.name} className="card" aria-label={`Plugin ${p.name}`}>
            <div className="row" style={{justifyContent:'space-between'}}>
              <strong>{p.name}</strong>
              <span className={p.state==='running'?'success':p.state==='disabled'?'muted':'warn'}>{p.state}</span>
            </div>
            <p className="muted">{p.meta?.description || ''}</p>
            <div className="row">
              <button onClick={()=>action(p.name,'enable')}>Activer</button>
              <button onClick={()=>action(p.name,'disable')}>Désactiver</button>
              <button onClick={()=>action(p.name,'start')}>Démarrer</button>
              <button onClick={()=>action(p.name,'stop')}>Arrêter</button>
              <button onClick={()=>action(p.name,'reload')}>Recharger</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

