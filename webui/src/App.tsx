import { useState, useEffect } from 'react'
import { Routes, Route, Link, Navigate } from 'react-router-dom'
import { Nav } from './components/Nav'
import { useAuth } from './hooks/useAuth'
import { ThemeToggle } from './components/ThemeToggle'
import ChatPage from './pages/Chat'
import MemoryPage from './pages/Memory'
import DebugPage from './pages/Debug'
import JeedomPage from './pages/Jeedom'
import ConfigPage from './pages/Config'
import BackupsPage from './pages/Backups'
import JobsPage from './pages/Jobs'
import HistoryPage from './pages/History'
import APIKeysPage from './pages/APIKeys'

export default function App() {
  const { logged, login, logout, loading } = useAuth()
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')

  useEffect(() => {
    document.title = 'IVY'
  }, [])

  return (
    <div>
      <header className="toolbar" role="banner">
        <Link to="/">IVY</Link>
        <Nav />
        <div style={{marginLeft:'auto', display:'flex', gap:'.5rem'}}>
          <ThemeToggle />
          {logged ? (
            <button onClick={logout} aria-label="Se déconnecter">Se déconnecter</button>
          ) : (
            <form onSubmit={async (e)=>{ e.preventDefault(); await login(user, pass) }} aria-label="Formulaire de connexion">
              <input value={user} onChange={e=>setUser(e.target.value)} placeholder="Identifiant" aria-label="Utilisateur" />
              <input value={pass} onChange={e=>setPass(e.target.value)} type="password" placeholder="mot de passe" aria-label="Mot de passe" />
              <button disabled={loading || !user.trim() || !pass.trim()}>Connexion</button>
            </form>
          )}
        </div>
      </header>
      <main style={{padding:'1rem'}}>
        {!logged ? (
          <p className="muted">Connectez-vous pour accéder aux fonctionnalités.</p>
        ) : null}
        <Routes>
          <Route path="/" element={<Navigate to="/chat" />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/debug" element={<DebugPage />} />
          <Route path="/jeedom" element={<JeedomPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/backups" element={<BackupsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/apikeys" element={<APIKeysPage />} />
        </Routes>
      </main>
    </div>
  )
}
