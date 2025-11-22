import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { api } from '../api/client';

type QAItem = {
  id: number;
  question: string;
  answer: string;
  is_variable: boolean;
  origin: string;
  usage_count?: number;
  last_used?: string | null;
  updated_at?: string | null;
  metadata?: Record<string, unknown> | null;
};

type ClassifyResult = {
  is_variable: boolean;
  needs_search?: boolean;
  refresh_interval_days?: number | null;
  raw?: string | null;
  provider?: string | null;
  details?: unknown;
};

const parseRefresh = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) return Math.trunc(value);
  if (typeof value === 'string') {
    const parsed = Number(value.trim());
    if (Number.isFinite(parsed) && parsed >= 0) return Math.trunc(parsed);
  }
  return undefined;
};

const readRefreshInterval = (meta?: Record<string, unknown> | null): number | undefined => {
  if (!meta) return undefined;
  return parseRefresh(meta['refresh_interval_days']);
};

const readLastRefreshed = (meta?: Record<string, unknown> | null): string | undefined => {
  if (!meta) return undefined;
  const raw = meta['last_refreshed_at'];
  return typeof raw === 'string' && raw ? raw : undefined;
};

function normaliseClassification(payload: unknown): ClassifyResult | null {
  if (!payload || typeof payload !== 'object') return null;
  const candidate = payload as Record<string, unknown>;
  const rawValue = candidate.raw;
  let raw: string | null = null;
  if (typeof rawValue === 'string') {
    raw = rawValue;
  } else if (rawValue !== undefined) {
    try {
      raw = JSON.stringify(rawValue, null, 2);
    } catch {
      raw = String(rawValue);
    }
  }
  return {
    is_variable: Boolean(candidate.is_variable),
    needs_search: typeof candidate.needs_search === 'boolean' ? candidate.needs_search : undefined,
    refresh_interval_days: parseRefresh(candidate.refresh_interval_days),
    raw,
    provider: typeof candidate.provider === 'string' ? candidate.provider : null,
    details: candidate.details,
  };
}

interface MemoryPageProps {
  logged?: boolean;
}

export default function MemoryPage({ logged = false }: MemoryPageProps): JSX.Element {
  const [items, setItems] = useState<QAItem[]>([]);
  const [selected, setSelected] = useState<QAItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [classify, setClassify] = useState<ClassifyResult | null>(null);

  const formatDate = (value?: string | null) => {
    if (!value) return '-';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  };

  const loadMemory = async (selectLatest = false) => {
    if (!logged) return;
    try {
      setLoading(true);
      setStatus(null);
      const data = await api.memoryList(100, 0, search || undefined);
      const rows: QAItem[] = Array.isArray(data?.items) ? (data.items as QAItem[]) : [];
      setItems(rows);
      if (selectLatest && rows.length) {
        setSelected({ ...rows[0] });
        return;
      }
      if (selected) {
        const updated = rows.find((item) => item.id === selected.id);
        setSelected(updated ? { ...updated } : null);
      }
    } catch (err) {
      setStatus('Lecture memoire impossible');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!logged) {
      setItems([]);
      setSelected(null);
      setStatus(null);
      return;
    }
    loadMemory(true).catch(() => setStatus('Lecture memoire impossible'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logged]);

  const applySearch = async (event: FormEvent) => {
    event.preventDefault();
    await loadMemory();
  };

  const handleSave = async () => {
    if (!logged || !selected) return;
    try {
      setLoading(true);
      const payload = {
        question: selected.question,
        answer: selected.answer,
        is_variable: selected.is_variable,
        origin: selected.origin,
        metadata: selected.metadata,
      };
      await api.memoryUpdate(selected.id, payload);
      await loadMemory();
      setStatus('Entree enregistree');
    } catch (err) {
      setStatus('Echec de la mise a jour');
    } finally {
      setLoading(false);
    }
  };

  const removeItem = async (id: number) => {
    if (!window.confirm('Supprimer cette entree ?')) return;
    if (!logged) return;
    try {
      await api.memoryDelete(id);
      if (selected?.id === id) setSelected(null);
      setStatus('Entree supprimee');
      await loadMemory();
    } catch (err) {
      setStatus('Suppression impossible');
    }
  };

  const testLLM = async (id: number, update = false) => {
    if (!logged) return;
    try {
      const result = await api.memoryClassifyLLM(id, update);
      const payload = result && typeof result === 'object' && 'classification' in result
        ? (result as { classification?: unknown }).classification
        : result;
      setClassify(normaliseClassification(payload));
      if (update && result && typeof result === 'object' && 'qa' in result) {
        const { qa } = result as { qa?: QAItem };
        if (qa) setSelected({ ...qa });
        await loadMemory();
      }
      setStatus('Test LLM termine');
    } catch (err) {
      setStatus('Test LLM impossible');
    }
  };

  const testHeuristic = async (id: number, update = false) => {
    try {
      const result = await api.memoryClassifyHeuristic(id, update);
      const payload = result && typeof result === 'object' && 'classification' in result
        ? (result as { classification?: unknown }).classification
        : result;
      setClassify(normaliseClassification(payload));
      if (update && result && typeof result === 'object' && 'qa' in result) {
        const { qa } = result as { qa?: QAItem };
        if (qa) setSelected({ ...qa });
        await loadMemory();
      }
      setStatus('Test logique termine');
    } catch (err) {
      setStatus('Test logique impossible');
    }
  };

  const sortedItems = useMemo(
    () => items.slice().sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')),
    [items],
  );

  const selectedRefresh = selected ? readRefreshInterval(selected.metadata) : undefined;
  const selectedLastRefreshed = selected ? readLastRefreshed(selected.metadata) : undefined;

  const handleRefreshChange = (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value.trim();
    setSelected((prev) => {
      if (!prev) return prev;
      const meta = { ...(prev.metadata ?? {}) };
      if (value === '') {
        delete meta['refresh_interval_days'];
      } else {
        const parsed = Number(value);
        if (Number.isFinite(parsed) && parsed >= 0) {
          meta['refresh_interval_days'] = Math.trunc(parsed);
        } else {
          delete meta['refresh_interval_days'];
        }
      }
      const normalizedMeta = Object.keys(meta).length ? meta : null;
      return { ...prev, metadata: normalizedMeta };
    });
  };

  const handleToggleVariable = (checked: boolean) => {
    setSelected((prev) => {
      if (!prev) return prev;
      const meta = { ...(prev.metadata ?? {}) };
      if (!checked) {
        delete meta['refresh_interval_days'];
        delete meta['last_refreshed_at'];
      }
      const normalizedMeta = Object.keys(meta).length ? meta : null;
      return { ...prev, is_variable: checked, metadata: normalizedMeta };
    });
  };

  const handleExport = async () => {
    try {
      const data = await api.memoryExport();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'memory-export.json';
      link.click();
      URL.revokeObjectURL(url);
      setStatus('Export genere');
    } catch (err) {
      setStatus('Export impossible');
    }
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const array = Array.isArray(parsed) ? parsed : parsed?.items;
      if (!Array.isArray(array)) throw new Error('format invalide');
      await api.memoryImport(array);
      await loadMemory();
      setStatus('Import reussi');
    } catch (err) {
      setStatus('Import impossible');
    }
  };

  return (
    <div className="memory-layout">
      <section className="memory-list">
        <header>
          <h1>Memoire</h1>
          <form onSubmit={applySearch} className="memory-search">
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Recherche..."
            />
            <button type="submit">Filtrer</button>
          </form>
          <div className="memory-actions">
            <button type="button" onClick={handleExport}>Exporter</button>
            <label className="import-btn">
              Importer
              <input type="file" accept="application/json" onChange={handleImport} hidden />
            </label>
          </div>
        </header>
        <table>
          <thead>
            <tr>
              <th>Question</th>
              <th>Origine</th>
              <th>Variable</th>
              <th>Utilisations</th>
              <th>Rafraichissement</th>
              <th>Modifiee</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item) => {
              const refresh = readRefreshInterval(item.metadata);
              return (
                <tr key={item.id} className={selected?.id === item.id ? 'selected' : ''}>
                  <td onClick={() => setSelected({ ...item })}>{item.question.slice(0, 80)}{item.question.length > 80 ? '...' : ''}</td>
                  <td>{item.origin}</td>
                  <td>{item.is_variable ? 'Oui' : 'Non'}</td>
                  <td>{item.usage_count ?? 0}</td>
                  <td>{refresh !== undefined ? `${refresh} j` : '-'}</td>
                  <td>{formatDate(item.updated_at)}</td>
                  <td className="memory-row-actions">
                    <button type="button" onClick={() => testLLM(item.id, false)}>Tester LLM</button>
                    <button type="button" onClick={() => testHeuristic(item.id, false)}>Tester logique</button>
                    <button type="button" onClick={() => removeItem(item.id)}>Supprimer</button>
                  </td>
                </tr>
              );
            })}
            {!sortedItems.length && (
              <tr><td colSpan={7} className="muted">Aucune entree</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <section className="memory-editor">
        {selected ? (
          <div>
            <h2>Edition</h2>
            <label>Question
              <textarea
                value={selected.question}
                onChange={(event) => setSelected((prev) => (prev ? { ...prev, question: event.target.value } : prev))}
                rows={4}
              />
            </label>
            <label>Reponse
              <textarea
                value={selected.answer}
                onChange={(event) => setSelected((prev) => (prev ? { ...prev, answer: event.target.value } : prev))}
                rows={6}
              />
            </label>
            <label>Origine
              <input
                value={selected.origin}
                onChange={(event) => setSelected((prev) => (prev ? { ...prev, origin: event.target.value } : prev))}
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={selected.is_variable}
                onChange={(event) => handleToggleVariable(event.target.checked)}
              />
              Reponse variable
            </label>
            {selected.is_variable ? (
              <label>
                Rafraichissement (jours)
                <input
                  type="number"
                  min={0}
                  value={selectedRefresh ?? ''}
                  onChange={handleRefreshChange}
                />
                <small className="muted">0 = jamais de rafraichissement automatique</small>
                {selectedLastRefreshed ? (
                  <small className="muted">Dernier rafraichissement : {formatDate(selectedLastRefreshed)}</small>
                ) : null}
              </label>
            ) : null}
            <div className="memory-editor-actions">
              <button type="button" onClick={handleSave} disabled={loading}>Enregistrer</button>
              <button type="button" onClick={() => testLLM(selected.id, true)}>Tester + maj (LLM)</button>
              <button type="button" onClick={() => testHeuristic(selected.id, true)}>Tester + maj (logique)</button>
            </div>
            {classify ? (
              <aside className="memory-classify">
                <h3>Derniere classification</h3>
                {typeof classify.refresh_interval_days === 'number' ? (
                  <p className="muted">Rafraichissement conseille : {classify.refresh_interval_days} jour(s)</p>
                ) : null}
                <pre>{JSON.stringify(classify, null, 2)}</pre>
              </aside>
            ) : null}
          </div>
        ) : (
          <p className="muted">Selectionnez une entree pour l'editer.</p>
        )}
      </section>
      {status ? <p className="status-bar">{status}</p> : null}
    </div>
  );
}
