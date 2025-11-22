import { NavLink } from 'react-router-dom'

const links: Array<[string, string]> = [
  ['/chat', 'Chat'],
  ['/memory', 'MÃ©moire'],
  ['/profiles', 'Profils LLM'],
  ['/debug', 'Debug'],
  ['/jeedom', 'Jeedom'],
  ['/plugins', 'Plugins'],
  ['/llm', 'Console LLM'],
  ['/history', 'Historique'],
  ['/jobs', 'Taches'],
  ['/task-hub', 'Taches & Prog.'],
  ['/tasks', 'Planification'],
  ['/sessions', 'Sessions'],
  ['/system', 'SystÃ¨me'],
  ['/config', 'Configuration'],
  ['/backups', 'Sauvegardes'],
  ['/apikeys', 'ClÃ©s API'],
  ['/voice', 'Commande vocale'],
]

export function Nav(): JSX.Element {
  return (
    <nav aria-label="Navigation principale">
      {links.map(([to, label]) => (
        <NavLink key={to} to={to}>
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

