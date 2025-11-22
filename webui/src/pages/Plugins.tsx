import { useEffect, useState } from 'react'
import { api } from '../api/client'

type PluginItem = { name: string; state: string; meta: any }

export default function PluginsPage(): JSX.Element {
  const [items, setItems] = useState<PluginItem[]>([])
  const [file, setFile] = useState<File | null>(null)

  async function load() {
    const data = await api.plugins()
    setItems(data.plugins ?? [])
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function action(name: string, act: 'enable' | 'disable' | 'start' | 'stop' | 'reload') {
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
      <div className="row" style={{ gap: '.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="file"
          accept=".zip"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          aria-label="Sélectionner un fichier ZIP"
        />
        <button onClick={upload} disabled={!file}>
          Téléverser le ZIP
        </button>
      </div>
      <div className="grid" style={{ marginTop: '1rem' }}>
        {items.length ? (
          items.map((plugin) => (
            <div key={plugin.name} className="card" aria-label={`Plugin ${plugin.name}`}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>{plugin.name}</strong>
                <span
                  className={
                    plugin.state === 'running' ? 'success' : plugin.state === 'disabled' ? 'muted' : 'warn'
                  }
                >
                  {plugin.state}
                </span>
              </div>
              {plugin.meta?.description ? <p className="muted">{plugin.meta.description}</p> : null}
              <div className="row" style={{ flexWrap: 'wrap', gap: '.5rem' }}>
                <button onClick={() => action(plugin.name, 'enable')}>Activer</button>
                <button onClick={() => action(plugin.name, 'disable')}>Désactiver</button>
                <button onClick={() => action(plugin.name, 'start')}>Démarrer</button>
                <button onClick={() => action(plugin.name, 'stop')}>Arrêter</button>
                <button onClick={() => action(plugin.name, 'reload')}>Recharger</button>
              </div>
            </div>
          ))
        ) : (
          <p className="muted">Aucun plugin détecté pour le moment.</p>
        )}
      </div>
    </section>
  )
}
