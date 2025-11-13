export default function PluginsPage() {
  return (
    <section>
      <h2>Historique des plugins</h2>
      <p className="muted">
        Le système de plugins Python a été retiré. Utilisez désormais la mémoire conversationnelle, les pages Chat/Mémoire et les
        intégrations dédiées (DuckDuckGo, Ollama, Jeedom) pour étendre IVY.
      </p>
      <p>
        Consultez <code>docs/PLUGINS.md</code> pour une description de la nouvelle architecture mémoire et des points d’extension.
      </p>
    </section>
  )
}
