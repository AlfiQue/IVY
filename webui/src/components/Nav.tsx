import { NavLink } from 'react-router-dom'

export function Nav() {
  return (
    <nav aria-label="Navigation principale">
      <NavLink to="/chat">Chat</NavLink>
      <NavLink to="/memory">Mémoire</NavLink>
      <NavLink to="/debug">Debug</NavLink>
      <NavLink to="/jeedom">Jeedom</NavLink>
      <NavLink to="/jobs">Tâches</NavLink>
      <NavLink to="/history">Historique</NavLink>
      <NavLink to="/config">Configuration</NavLink>
      <NavLink to="/backups">Sauvegardes</NavLink>
      <NavLink to="/apikeys">API Keys</NavLink>
    </nav>
  )
}
