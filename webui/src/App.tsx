import { useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate } from 'react-router-dom'
import { Nav } from './components/Nav'
import { ThemeToggle } from './components/ThemeToggle'
import { useAuth } from './hooks/useAuth'

import ChatPage from './pages/Chat'
import MemoryPage from './pages/Memory'
import ProfilesPage from './pages/Profiles'
import DebugPage from './pages/Debug'
import JeedomPage from './pages/Jeedom'
import ConfigPage from './pages/Config'
import BackupsPage from './pages/Backups'
import JobsPage from './pages/Jobs'
import TaskHubPage from './pages/TaskHub'
import TaskPlannerPage from './pages/TaskPlanner'
import HistoryPage from './pages/History'
import APIKeysPage from './pages/APIKeys'
import PluginsPage from './pages/Plugins'
import LLMConsole from './pages/LLMConsole'
import SystemPage from './pages/System'
import SessionsPage from './pages/Sessions'
import VoiceCommand from './pages/VoiceCommand'

export default function App() {
  const { logged, login, logout, loading } = useAuth()
  const [user, setUser] = useState('admin')
  const [pass, setPass] = useState('admin')

  useEffect(() => {
    document.title = 'IVY'
  }, [])

  return (
    <div>
      <header className="toolbar" role="banner">
        <Link to="/">IVY</Link>
        {logged ? <Nav /> : null}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '.5rem', alignItems: 'center' }}>
          <ThemeToggle />
          {logged ? (
            <button onClick={logout} aria-label="Se déconnecter">
              Se déconnecter
            </button>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault()
                await login(user, pass)
              }}
              aria-label="Formulaire de connexion"
            >
              <input
                value={user}
                onChange={(e) => setUser(e.target.value)}
                placeholder="admin"
                aria-label="Utilisateur"
              />
              <input
                value={pass}
                onChange={(e) => setPass(e.target.value)}
                type="password"
                placeholder="mot de passe"
                aria-label="Mot de passe"
              />
              <button disabled={loading}>Connexion</button>
            </form>
          )}
        </div>
      </header>
      <main>
        {!logged ? <p className="muted">Connectez-vous pour accéder aux fonctionnalités.</p> : null}
        <Routes>
          <Route path="/" element={<Navigate to="/chat" />} />
          <Route path="/chat" element={<ChatPage logged={logged} />} />
          <Route path="/memory" element={<MemoryPage logged={logged} />} />
          <Route path="/profiles" element={<ProfilesPage />} />
          <Route path="/debug" element={<DebugPage />} />
          <Route path="/jeedom" element={<JeedomPage />} />
          <Route path="/plugins" element={<PluginsPage />} />
          <Route path="/llm" element={<LLMConsole />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/task-hub" element={<TaskHubPage />} />
          <Route path="/tasks" element={<TaskPlannerPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/config" element={<ConfigPage />} />
          <Route path="/backups" element={<BackupsPage />} />
          <Route path="/apikeys" element={<APIKeysPage />} />
          <Route path="/voice" element={<VoiceCommand />} />
        </Routes>
      </main>
    </div>
  )
}
