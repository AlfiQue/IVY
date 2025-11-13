import React, { useEffect, useMemo, useState, FormEvent, ChangeEvent } from "react";
import { api } from "../api/client";

type QAItem = {
  id: number;
  question: string;
  answer: string;
  is_variable: boolean;
  origin: string;
  usage_count?: number;
  last_used?: string | null;
  updated_at?: string;
  metadata?: Record<string, unknown> | null;
};

type ClassifyResult = {
  is_variable: boolean;
  needs_search?: boolean;
  raw?: string | null;
  provider?: string | null;
  details?: unknown;
};

function normaliseClassification(payload: unknown): ClassifyResult | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const candidate = payload as Record<string, unknown>;
  const result = {
    is_variable: Boolean(candidate.is_variable),
    needs_search: candidate.needs_search as boolean | undefined,
    raw: typeof candidate.raw === "string"
      ? candidate.raw
      : candidate.raw != null
        ? JSON.stringify(candidate.raw, null, 2)
        : null,
    provider: (typeof candidate.provider === "string" ? candidate.provider : null),
    details: candidate.details,
  } satisfies ClassifyResult;

  return result;
}

export default function MemoryPage(): JSX.Element {
  const [items, setItems] = useState<QAItem[]>([]);
  const [selected, setSelected] = useState<QAItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [classify, setClassify] = useState<ClassifyResult | null>(null);

  async function loadMemory(selectLatest = false) {
    try {
      setLoading(true);
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
      setStatus("Lecture mémoire impossible");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMemory(true).catch(() => setStatus("Lecture mémoire impossible"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function applySearch(e: FormEvent) {
    e.preventDefault();
    await loadMemory();
  }

  async function handleSave() {
    if (!selected) return;

    try {
      setLoading(true);
      await api.memoryUpdate(selected.id, {
        question: selected.question,
        answer: selected.answer,
        is_variable: selected.is_variable,
        origin: selected.origin,
        metadata: selected.metadata,
      });
      await loadMemory();
      setStatus("Entrée enregistrée");
    } catch (err) {
      setStatus("Échec de la mise à jour");
    } finally {
      setLoading(false);
    }
  }

  async function removeItem(id: number) {
    if (!window.confirm("Supprimer cette entrée ?")) return;
    try {
      await api.memoryDelete(id);
      if (selected?.id === id) setSelected(null);
      setStatus("Entrée supprimée");
      await loadMemory();
    } catch (err) {
      setStatus("Suppression impossible");
    }
  }

  async function testLLM(id: number, update = false) {
    try {
      const result = await api.memoryClassifyLLM(id, update);
      const payload = (result && typeof result === "object" && "classification" in result)
        ? (result as { classification?: unknown }).classification
        : result;
      setClassify(normaliseClassification(payload));
      if (update) {
        if (result && typeof result === "object" && (result as { qa?: QAItem }).qa) {
          setSelected({ ...(result as { qa: QAItem }).qa });
        }
        await loadMemory();
      }
    } catch (err) {
      setStatus("Échec classification LLM");
    }
  }

  async function testHeuristic(id: number, update = false) {
    try {
      const result = await api.memoryClassifyHeuristic(id, update);
      const payload = (result && typeof result === "object" && "classification" in result)
        ? (result as { classification?: unknown }).classification
        : result;
      setClassify(normaliseClassification(payload));
      if (update) {
        if (result && typeof result === "object" && (result as { qa?: QAItem }).qa) {
          setSelected({ ...(result as { qa: QAItem }).qa });
        }
        await loadMemory();
      }
    } catch (err) {
      setStatus("Échec classification heuristique");
    }
  }

  async function handleExport() {
    const data = await api.memoryExport();
    const items = JSON.stringify(data?.items ?? [], null, 2);
    const blob = new Blob([items], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "memory-export.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  async function handleImport(evt: ChangeEvent<HTMLInputElement>) {
    const file = evt.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const array = Array.isArray(parsed) ? parsed : parsed?.items;
      if (!Array.isArray(array)) throw new Error("format invalide");
      await api.memoryImport(array);
      await loadMemory();
      setStatus("Import réussi");
    } catch (err) {
      setStatus("Import impossible");
    }
  }

  const sortedItems = useMemo(() => (
    items.slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
  ), [items]);

  function selectRow(item: QAItem) {
    setClassify(null);
    setStatus(null);
    setSelected({ ...item });
  }

  return (
    <div className="memory-layout">
      <section className="memory-list">
        <header>
          <h1>Mémoire</h1>
          <form onSubmit={applySearch} className="memory-search">
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Recherche..." />
            <button type="submit">Filtrer</button>
          </form>
          <div className="memory-actions">
            <button onClick={handleExport}>Exporter</button>
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
              <th>Modifiée</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map(item => (
              <tr key={item.id} className={selected?.id === item.id ? 'selected' : ''}>
                <td onClick={() => selectRow(item)}>{item.question.slice(0, 80)}{item.question.length > 80 ? '…' : ''}</td>
                <td>{item.origin}</td>
                <td>{item.is_variable ? 'Oui' : 'Non'}</td>
                <td>{item.usage_count ?? 0}</td>
                <td>{item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}</td>
                <td>
                  <button onClick={() => testLLM(item.id, false)}>Tester LLM</button>
                  <button onClick={() => testHeuristic(item.id, false)}>Tester logique</button>
                  <button onClick={() => removeItem(item.id)}>Supprimer</button>
                </td>
              </tr>
            ))}
            {!sortedItems.length && (
              <tr><td colSpan={6} className="muted">Aucune entrée</td></tr>
            )}
          </tbody>
        </table>
      </section>
      <section className="memory-editor">
        {selected ? (
          <div>
            <h2>Édition</h2>
            <label>Question
              <textarea value={selected.question} onChange={e => setSelected({ ...selected, question: e.target.value })} rows={4} />
            </label>
            <label>Réponse
              <textarea value={selected.answer} onChange={e => setSelected({ ...selected, answer: e.target.value })} rows={6} />
            </label>
            <label>Origine
              <input value={selected.origin} onChange={e => setSelected({ ...selected, origin: e.target.value })} />
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={selected.is_variable} onChange={e => setSelected({ ...selected, is_variable: e.target.checked })} />
              Réponse variable
            </label>
            <div className="memory-editor-actions">
              <button onClick={handleSave} disabled={loading}>Enregistrer</button>
              <button onClick={() => testLLM(selected.id, true)}>Tester + mettre à jour (LLM)</button>
              <button onClick={() => testHeuristic(selected.id, true)}>Tester + mettre à jour (logique)</button>
            </div>
            {classify ? (
              <aside className="memory-classify">
                <h3>Dernière classification</h3>
                <pre>{JSON.stringify(classify, null, 2)}</pre>
              </aside>
            ) : null}
          </div>
        ) : (
          <p className="muted">Sélectionnez une entrée pour l’éditer.</p>
        )}
      </section>
      {status ? <p className="status-bar">{status}</p> : null}
    </div>
  )
}
