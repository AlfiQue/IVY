import { useState } from 'react'
import { Routes, Route, Link, Navigate } from 'react-router-dom'
import { Nav } from './components/Nav'
import { useAuth } from './hooks/useAuth'
import PluginsPage from './pages/Plugins'
import HistoryPage from './pages/History'
import LLMConsole from './pages/LLMConsole'
import SystemPage from './pages/System'
import JobsPage from './pages/Jobs'
import SessionsPage from './pages/Sessions'
import ConfigPage from './pages/Config'
import BackupsPage from './pages/Backups'
import VoiceCommand from './pages/VoiceCommand'

export default function App() {
  const { logged, login, logout, loading } = useAuth()
  const [user, setUser] = useState('admin')
  const [pass, setPass] = useState('admin')
  return (
    <div>
      <header className="toolbar" role="banner">
        <Link to="/">IVY</Link>
        <Nav />
        <div style={{marginLeft:'auto'}}>
          {logged ? (
            <button onClick={logout} aria-label="Se déconnecter">Se déconnecter</button>
          ) : (
            <form onSubmit={async (e)=>{ e.preventDefault(); await login(user, pass) }} aria-label="Formulaire de connexion">
              <input value={user} onChange={e=>setUser(e.target.value)} placeholder="admin" aria-label="Utilisateur" />
              <input value={pass} onChange={e=>setPass(e.target.value)} type="password" placeholder="mot de passe" aria-label="Mot de passe" />
              <button disabled={loading}>Connexion</button>
            </form>
          )}
        </div>
      </header>
      <main style={{padding:'1rem'}}>
        {!logged ? (
          <p className="muted">Connectez‑vous pour accéder aux fonctionnalités.</p>
        ) : null}
        <Routes>
          <Route path="/" element={<Navigate to="/plugins" />} />
          <Route path="/plugins" element={<PluginsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/llm" element={<LLMConsole />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/backups" element={<BackupsPage />} />
          <Route path="/voice" element={<VoiceCommand />} />
        </Routes>
      </main>
    </div>
  )
}
