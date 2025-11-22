import { FormEvent, useState } from "react";
import { api } from "../api/client";

type SearchResult = {
  title?: string;
  href?: string;
  body?: string;
};

type SearchMeta = {
  backend?: string | null;
  status?: string;
  errors?: { backend?: string | null; error?: string | null }[];
  count?: number;
  query?: string;
};

type SearchResponse = {
  items?: SearchResult[];
  meta?: SearchMeta;
};

type LearningInsights = {
  top_queries?: any[];
  unresolved_queries?: any[];
  recent_events?: any[];
  recent_prompts?: { prompt?: string; count?: number; last_used?: string }[];
  favorite_prompts?: { prompt?: string; count?: number; last_used?: string }[];
  top_jobs?: { id?: string; description?: string; tag?: string; type?: string; success?: number; failure?: number }[];
  suggestions?: { question?: string; occurrences?: number; action?: string; reason?: string }[];
};

export default function DebugPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [meta, setMeta] = useState<SearchMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastInfo, setLastInfo] = useState<string | null>(null);
  const [insights, setInsights] = useState<LearningInsights | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState<string | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setResults([]);
    setMeta(null);
    setLastInfo(`Requete envoyee a ${new Date().toLocaleTimeString()}.`);

    try {
      const data = (await api.debugSearch(trimmed, 5)) as SearchResponse;
      const items = Array.isArray(data?.items) ? data.items : [];
      setResults(items);
      setMeta(data?.meta ?? null);

      const backendLabel = data?.meta?.backend ? ` via backend "${data.meta.backend}"` : "";
      setLastInfo(`Reponse recue (${items.length} resultat${items.length > 1 ? "s" : ""}${backendLabel}).`);

      if (!items.length && data?.meta?.errors?.length) {
        setError("DuckDuckGo a refuse la requete (ratelimit). Reessayez plus tard.");
      }
    } catch (err) {
      if (err instanceof Error && err.message === "401") {
        setError("Authentification requise pour la recherche web.");
      } else {
        setError("Recherche impossible : verifiez la configuration reseau / allowlist.");
      }
      setLastInfo(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleInsights() {
    setInsightsError(null);
    setInsightsLoading(true);
    try {
      const payload = (await api.learningInsights(10)) as LearningInsights;
      setInsights(payload);
    } catch (err) {
      setInsightsError(`Impossible de charger les insights (code ${(err as any)?.status ?? "?"}).`);
    } finally {
      setInsightsLoading(false);
    }
  }

  const metaErrors = meta?.errors
    ?.filter((entry) => entry.error)
    .map((entry, index) => (
      <li key={`${entry.backend ?? "unknown"}-${index}`}>
        {entry.backend ? `Backend ${entry.backend}` : "Backend inconnu"} : {entry.error ?? "Erreur"}
      </li>
    ));

  return (
    <section className="debug-page">
      <h1>Debug recherche web</h1>
      <form onSubmit={handleSearch} className="debug-form">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Requete DuckDuckGo"
          aria-label="Requete de recherche"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Recherche..." : "Chercher"}
        </button>
      </form>
      {lastInfo ? <p className="muted">{lastInfo}</p> : null}
      {meta?.backend ? <p className="muted">Backend utilise : {meta.backend}</p> : null}
      {metaErrors?.length ? <ul className="error-list">{metaErrors}</ul> : null}
      {error ? <p className="error">{error}</p> : null}
      <ul className="debug-results">
        {results.map((item, index) => (
          <li key={`${item.href ?? item.title ?? index}-${index}`}>
            <h3>{item.title || "Sans titre"}</h3>
            {item.href ? (
              <a href={item.href} target="_blank" rel="noreferrer" aria-label={`Ouvrir ${item.href}`}>
                {item.href}
              </a>
            ) : null}
            {item.body ? <p>{item.body}</p> : null}
          </li>
        ))}
        {!loading && !error && !results.length ? (
          <li className="muted">Aucun resultat pour cette requete.</li>
        ) : null}
      </ul>

      <hr style={{ margin: "2rem 0" }} />

      <section>
        <h2>Insights auto-learning</h2>
        <p className="muted">
          Visualise les requetes frequentes, les recherches non resolues et les evenements recents exploites
          par le moteur d auto-apprentissage.
        </p>
        <button type="button" onClick={handleInsights} disabled={insightsLoading}>
          {insightsLoading ? "Chargement..." : "Charger les insights"}
        </button>
        {insightsError ? <p className="error">{insightsError}</p> : null}

        {insights ? (
          <>
            <div className="insights-grid">
              <div>
                <h3>Prompts recents</h3>
                {insights.recent_prompts?.length ? (
                  <ul>
                    {insights.recent_prompts.map((item) => (
                      <li key={`recent-${item.prompt}`}>
                        <strong>{item.prompt}</strong>
                        <div className="muted">Utilisations : {item.count ?? 1}</div>
                        <div className="muted small">
                          {item.last_used ? new Date(item.last_used).toLocaleString() : "n/a"}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Aucune donnee.</p>
                )}
              </div>
              <div>
                <h3>Favoris</h3>
                {insights.favorite_prompts?.length ? (
                  <ul>
                    {insights.favorite_prompts.map((item) => (
                      <li key={`fav-${item.prompt}`}>
                        <strong>{item.prompt}</strong>
                        <div className="muted">Occurrences : {item.count ?? 0}</div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Pas encore de favoris.</p>
                )}
              </div>
              <div>
                <h3>Jobs fiables</h3>
                {insights.top_jobs?.length ? (
                  <ul>
                    {insights.top_jobs.map((job, idx) => (
                      <li key={`job-${job.id}-${idx}`}>
                        <strong>{job.description || job.tag || job.id}</strong>
                        <div className="muted small">
                          {job.type} — {job.success ?? 0} succes / {job.failure ?? 0} echecs
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Stats non disponibles.</p>
                )}
              </div>
              <div>
                <h3>Suggestions</h3>
                {insights.suggestions?.length ? (
                  <ul>
                    {insights.suggestions.map((suggestion, idx) => (
                      <li key={`suggest-${idx}`}>
                        <strong>{suggestion.question}</strong>
                        <div className="muted small">
                          {suggestion.occurrences ?? 0} occurrences, action : {suggestion.action}
                        </div>
                        {suggestion.reason ? <div className="muted small">{suggestion.reason}</div> : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Aucune recommandation pour l'instant.</p>
                )}
              </div>
            </div>

            <div className="insights-grid" style={{ marginTop: "1.25rem" }}>
              <div>
                <h3>Top requetes</h3>
                {insights.top_queries?.length ? (
                  <ul>
                    {insights.top_queries.map((item: any) => (
                      <li key={item.query}>
                        <strong>{item.query}</strong> — {item.occurrences} occurrences
                        {typeof item.search_success === "number" ? ` (succes ${item.search_success})` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Aucune donnee.</p>
                )}
              </div>
              <div>
                <h3>Requetes non resolues</h3>
                {insights.unresolved_queries?.length ? (
                  <ul>
                    {insights.unresolved_queries.map((item: any) => (
                      <li key={item.query}>
                        {item.query} — {item.occurrences} fois
                        {item.last_seen ? ` (dernier ${item.last_seen})` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Rien a signaler.</p>
                )}
              </div>
              <div>
                <h3>Evenements recents</h3>
                {insights.recent_events?.length ? (
                  <ul>
                    {insights.recent_events.slice(0, 5).map((entry: any, idx: number) => (
                      <li key={`${entry.created_at}-${idx}`}>
                        <strong>{entry.question}</strong>
                        <div className="muted">query : {entry.normalized_query || "n/a"}</div>
                        <div className="muted">resultats : {entry.search_results_count ?? 0}</div>
                        <div className="muted">
                          latence : {entry.latency_ms ? `${Math.round(entry.latency_ms)} ms` : "n/a"}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Pas encore d evenements.</p>
                )}
              </div>
            </div>
          </>
        ) : null}
      </section>
    </section>
  );
}
