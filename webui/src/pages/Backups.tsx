import { useState } from 'react'
import { api } from '../api/client'

export default function BackupsPage() {
  const [msg, setMsg] = useState('')
  const [file, setFile] = useState<File|null>(null)
  const [dry, setDry] = useState(true)
  const [downloading, setDownloading] = useState(false)

  async function exportNow() {
    // crée un job backup à exécution immédiate
    const { id } = await api.addJob({ type:'backup', params:{}, schedule:{ trigger:'date' } })
    await api.runJobNow(id)
    setMsg('Export planifié. Consultez app/data/backups/')
  }

  async function downloadExport() {
    setDownloading(true)
    try {
      const blob = await api.exportBackup()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'ivy-backup.zip'; a.click()
      URL.revokeObjectURL(url)
    } catch { setMsg('Échec export') } finally { setDownloading(false) }
  }

  return (
    <section>
      <h2>Sauvegardes</h2>
      <div className="row">
        <button onClick={exportNow}>Exporter (via Job)</button>
        <button onClick={downloadExport} disabled={downloading}>Télécharger export (ZIP)</button>
      </div>
      {msg && <p>{msg}</p>}
      <h3>Importer</h3>
      <div className="row">
        <input type="file" accept=".zip" onChange={e=>setFile(e.target.files?.[0]||null)} aria-label="ZIP à importer" />
        <label><input type="checkbox" checked={dry} onChange={e=>setDry(e.target.checked)} /> Dry-run</label>
        <button onClick={async ()=>{ if(!file) return; const res = await api.importBackup(file, dry); setMsg(JSON.stringify(res)) }}>Importer</button>
      </div>
    </section>
  )
}
