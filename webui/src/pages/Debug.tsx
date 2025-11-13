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

export default function DebugPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [meta, setMeta] = useState<SearchMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastInfo, setLastInfo] = useState<string | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setResults([]);
    setMeta(null);
    setLastInfo(`Requête envoyée à ${new Date().toLocaleTimeString()} …`);

    try {
      const data = (await api.debugSearch(trimmed, 5)) as SearchResponse;
      const items = Array.isArray(data?.items) ? data.items : [];
      setResults(items);
      setMeta(data?.meta ?? null);

      const backendLabel = data?.meta?.backend ? ` via backend “${data.meta.backend}”` : "";
      setLastInfo(`Réponse reçue (${items.length} résultat${items.length > 1 ? 's' : ''}${backendLabel}).`);

      if (!items.length && data?.meta?.errors?.length) {
        setError(
          "DuckDuckGo a refusé la requête (ratelimit). Les services sont probablement saturés – réessayez plus tard."
        );
      }
    } catch (err) {
      if (err instanceof Error && err.message === "401") {
        setError("Authentification requise pour la recherche web (désactivez la sécurité ou connectez-vous).");
      } else {
        setError("Recherche impossible : vérifiez la configuration réseau / allowlist.");
      }
      setLastInfo(null);
    } finally {
      setLoading(false);
    }
  }

  const metaErrors = meta?.errors?.filter((entry) => entry.error).map((entry, index) => (
    <li key={`${entry.backend ?? 'unknown'}-${index}`}>
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
          placeholder="Requête DuckDuckGo"
          aria-label="Requête de recherche"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Recherche…" : "Chercher"}
        </button>
      </form>
      {lastInfo ? <p className="muted">{lastInfo}</p> : null}
      {meta?.backend ? <p className="muted">Backend utilisé : {meta.backend}</p> : null}
      {metaErrors?.length ? (
        <ul className="error-list">
          {metaErrors}
        </ul>
      ) : null}
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
          <li className="muted">Aucun résultat pour cette requête.</li>
        ) : null}
      </ul>
    </section>
  );
}
