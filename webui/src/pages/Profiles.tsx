import { useCallback, useMemo, useState } from 'react';

import { api } from '../api/client';
import RadarChart, { RadarMetric, RadarSeries } from '../components/RadarChart';

type ProfileRun = {
  latency_ms: number;
  speculative: boolean;
  text?: string;
  usage?: Record<string, unknown> | null;
};

type ProfileResult = {
  name: string;
  description?: string | null;
  applied_settings?: Record<string, unknown> | null;
  applied_options?: Record<string, unknown> | null;
  samples: number;
  runs: ProfileRun[];
  errors: string[];
};

type ProfilesResponse = {
  prompt: string;
  profiles: ProfileResult[];
};

type OptionFields = {
  temperature: string;
  top_p: string;
  top_k: string;
  repeat_penalty: string;
  max_tokens: string;
};

type SettingFields = {
  llm_model_path: string;
  llm_speculative_model_path: string;
  llm_context_tokens: string;
  llm_n_gpu_layers: string;
  llm_speculative_context_tokens: string;
  llm_speculative_n_gpu_layers: string;
  chat_system_prompt: string;
};

type ProfileForm = {
  id: string;
  name: string;
  description: string;
  samples: string;
  speculative: boolean;
  options: OptionFields;
  settings: SettingFields;
};

type HistoryRow = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
};

type ProfileStats = {
  averageLatency: number;
  minLatency: number;
  maxLatency: number;
  stdLatency: number;
  averagePromptTokens: number;
  averageCompletionTokens: number;
  averageTotalTokens: number;
  runs: number;
};

type ProfileSummary = {
  profile: ProfileResult;
  stats: ProfileStats;
};

type AutoStep = {
  parameter: string;
  value: string;
  stats: ProfileStats;
  success: boolean;
  errors: string[];
  improvement: number;
};

type AutoSummary = {
  baseline: ProfileSummary;
  best: ProfileSummary;
  steps: AutoStep[];
};

type CandidateRecord = {
  profile: ProfileResult;
  stats: ProfileStats;
  profileForm: ProfileForm;
  parameter: string;
  value: string;
  prompt: string;
};

type VariationDefinition = {
  key: string;
  label: string;
  values: string[];
};

type AutoHistoryEntry = {
  timestamp: string;
  prompt: string;
  summary: AutoSummary;
};

type AutoTuneResult = {
  prompt: string;
  summary: AutoSummary;
  bestProfileForm: ProfileForm;
  bestParameters: Record<string, string>;
  candidates: CandidateRecord[];
  steps: AutoStep[];
  response: ProfilesResponse;
};

const MAX_AUTO_PROFILES = 24;
const DEFAULT_GENERATOR_MATRIX = 'temperature=0.6,0.8\nmax_tokens=256,512\nspeculative=false,true';
const FINE_STEPS = [1, 0.5, 0.25, 0.1, 0.05, 0.01];

const OPTION_KEYS: (keyof OptionFields)[] = ['temperature', 'top_p', 'top_k', 'repeat_penalty', 'max_tokens'];
const SETTING_KEYS: (keyof SettingFields)[] = [
  'llm_model_path',
  'llm_speculative_model_path',
  'llm_context_tokens',
  'llm_n_gpu_layers',
  'llm_speculative_context_tokens',
  'llm_speculative_n_gpu_layers',
  'chat_system_prompt',
];

const createId = () =>
  typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

const emptyOptions = (): OptionFields => ({
  temperature: '',
  top_p: '',
  top_k: '',
  repeat_penalty: '',
  max_tokens: '',
});

const emptySettings = (): SettingFields => ({
  llm_model_path: '',
  llm_speculative_model_path: '',
  llm_context_tokens: '',
  llm_n_gpu_layers: '',
  llm_speculative_context_tokens: '',
  llm_speculative_n_gpu_layers: '',
  chat_system_prompt: '',
});

const createProfile = (partial?: Partial<ProfileForm>): ProfileForm => ({
  id: createId(),
  name: partial?.name ?? '',
  description: partial?.description ?? '',
  samples: partial?.samples ?? '1',
  speculative: partial?.speculative ?? false,
  options: { ...emptyOptions(), ...(partial?.options ?? {}) },
  settings: { ...emptySettings(), ...(partial?.settings ?? {}) },
});

const parseFloatLoose = (value: string): number | undefined => {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const parseIntLoose = (value: string): number | undefined => {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : undefined;
};

const normalizeKey = (key: string): string => key.trim().toLowerCase();

const coerceBoolean = (value: string): boolean => {
  const lowered = value.trim().toLowerCase();
  if (['1', 'true', 'oui', 'yes', 'on'].includes(lowered)) return true;
  if (['0', 'false', 'non', 'no', 'off'].includes(lowered)) return false;
  throw new Error(`Valeur booleenne invalide: "${value}"`);
};

const normaliseSamples = (value: string): number => {
  const parsed = parseIntLoose(value);
  if (parsed === undefined || parsed < 1) return 1;
  if (parsed > 5) return 5;
  return parsed;
};

const parseVariationInput = (raw: string): VariationDefinition[] => {
  const lines = raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const result: VariationDefinition[] = [];
  for (const line of lines) {
    const [rawKey, rawValues] = line.split('=');
    if (!rawKey || rawValues === undefined) {
      throw new Error(`Ligne invalide: "${line}" (format cle=val1,val2,...)`);
    }
    const values = rawValues
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean);
    if (!values.length) {
      throw new Error(`Aucune valeur specifiee pour "${rawKey.trim()}"`);
    }
    result.push({ key: normalizeKey(rawKey), label: rawKey.trim(), values });
  }
  return result;
};

const cartesianProduct = (defs: VariationDefinition[]): Array<Record<string, string>> => {
  if (!defs.length) return [{}];
  return defs.reduce<Array<Record<string, string>>>((acc, def) => {
    const next: Array<Record<string, string>> = [];
    for (const combo of acc) {
      for (const value of def.values) {
        next.push({ ...combo, [def.key]: value });
      }
    }
    return next;
  }, [{}]);
};

const cloneProfile = (profile: ProfileForm): ProfileForm => ({
  id: createId(),
  name: profile.name,
  description: profile.description,
  samples: profile.samples,
  speculative: profile.speculative,
  options: { ...profile.options },
  settings: { ...profile.settings },
});

const applyOverrides = (profile: ProfileForm, overrides: Record<string, string>, nameSuffix?: string): ProfileForm => {
  const next = cloneProfile(profile);
  if (nameSuffix) {
    next.name = `${profile.name || 'Profil'} ${nameSuffix}`;
  }
  Object.entries(overrides).forEach(([rawKey, rawValue]) => {
    const key = normalizeKey(rawKey);
    const value = rawValue.trim();
    if (!value.length) return;
    if (key === 'speculative') {
      next.speculative = coerceBoolean(value);
      return;
    }
    if (key === 'samples') {
      next.samples = String(normaliseSamples(value));
      return;
    }
    if (OPTION_KEYS.includes(key as keyof OptionFields)) {
      next.options = { ...next.options, [key]: value } as OptionFields;
      return;
    }
    if (SETTING_KEYS.includes(key as keyof SettingFields)) {
      next.settings = { ...next.settings, [key]: value } as SettingFields;
      return;
    }
    throw new Error(`Champ inconnu: "${rawKey}"`);
  });
  return next;
};

const readToken = (usage: Record<string, unknown> | null | undefined, key: string): number => {
  if (!usage) return 0;
  const value = usage[key];
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

const computeStats = (profile: ProfileResult): ProfileStats => {
  const latencies = profile.runs.map((run) => run.latency_ms).filter((value) => Number.isFinite(value));
  const runs = latencies.length;
  const averageLatency = runs ? latencies.reduce((sum, value) => sum + value, 0) / runs : 0;
  const minLatency = runs ? Math.min(...latencies) : 0;
  const maxLatency = runs ? Math.max(...latencies) : 0;
  const variance =
    runs > 1 ? latencies.reduce((sum, value) => sum + (value - averageLatency) ** 2, 0) / (runs - 1) : 0;
  const stdLatency = Math.sqrt(variance);

  let promptTokens = 0;
  let completionTokens = 0;
  let totalTokens = 0;
  profile.runs.forEach((run) => {
    promptTokens += readToken(run.usage, 'prompt_tokens');
    completionTokens += readToken(run.usage, 'completion_tokens');
    totalTokens += readToken(run.usage, 'total_tokens');
  });

  return {
    averageLatency,
    minLatency,
    maxLatency,
    stdLatency,
    averagePromptTokens: runs ? promptTokens / runs : 0,
    averageCompletionTokens: runs ? completionTokens / runs : 0,
    averageTotalTokens: runs ? totalTokens / runs : 0,
    runs,
  };
};

const formatLatency = (value: number | undefined): string => {
  if (!value || Number.isNaN(value)) return '-';
  return value >= 1000 ? `${value.toFixed(1)} ms` : `${Math.round(value)} ms`;
};

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '-';
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 }).format(value);
};

const formatDateTime = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
};

const prettyKV = (data?: Record<string, unknown> | null): string[] => {
  if (!data) return [];
  return Object.entries(data).map(([key, value]) => `${key}=${value}`);
};

const normalizeValueKey = (value: string): string => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toString() : value.trim();
};

const extractParameters = (profile: ProfileForm, keys: string[]): Record<string, string> => {
  const record: Record<string, string> = {};
  keys.forEach((key) => {
    if (key === 'speculative') {
      record[key] = profile.speculative ? 'true' : 'false';
    } else if (key === 'samples') {
      record[key] = profile.samples;
    } else if (OPTION_KEYS.includes(key as keyof OptionFields)) {
      record[key] = profile.options[key as keyof OptionFields] ?? '';
    } else if (SETTING_KEYS.includes(key as keyof SettingFields)) {
      record[key] = profile.settings[key as keyof SettingFields] ?? '';
    }
  });
  return record;
};

const buildHistoryPayload = (history: HistoryRow[]) =>
  history
    .map((row) => ({ role: row.role, content: row.content.trim() }))
    .filter((row) => row.content.length > 0);

const profileFormToDescriptor = (profile: ProfileForm, index: number) => {
  const settings: Record<string, unknown> = {
    llm_speculative_enabled: profile.speculative,
  };
  const modelPath = profile.settings.llm_model_path.trim();
  if (modelPath) settings.llm_model_path = modelPath;
  const draftPath = profile.settings.llm_speculative_model_path.trim();
  if (draftPath) settings.llm_speculative_model_path = draftPath;

  const ctx = parseIntLoose(profile.settings.llm_context_tokens);
  if (ctx !== undefined) settings.llm_context_tokens = ctx;
  const gpu = parseIntLoose(profile.settings.llm_n_gpu_layers);
  if (gpu !== undefined) settings.llm_n_gpu_layers = gpu;
  const draftCtx = parseIntLoose(profile.settings.llm_speculative_context_tokens);
  if (draftCtx !== undefined) settings.llm_speculative_context_tokens = draftCtx;
  const draftGpu = parseIntLoose(profile.settings.llm_speculative_n_gpu_layers);
  if (draftGpu !== undefined) settings.llm_speculative_n_gpu_layers = draftGpu;
  const customSystem = profile.settings.chat_system_prompt.trim();
  if (customSystem) settings.chat_system_prompt = customSystem;

  const options: Record<string, unknown> = {};
  const temperature = parseFloatLoose(profile.options.temperature);
  if (temperature !== undefined) options.temperature = temperature;
  const topP = parseFloatLoose(profile.options.top_p);
  if (topP !== undefined) options.top_p = topP;
  const topK = parseIntLoose(profile.options.top_k);
  if (topK !== undefined) options.top_k = topK;
  const repeatPenalty = parseFloatLoose(profile.options.repeat_penalty);
  if (repeatPenalty !== undefined) options.repeat_penalty = repeatPenalty;
  const maxTokens = parseIntLoose(profile.options.max_tokens);
  if (maxTokens !== undefined) options.max_tokens = maxTokens;

  return {
    name: profile.name.trim() || `Profil ${index + 1}`,
    description: profile.description.trim() || undefined,
    samples: normaliseSamples(profile.samples),
    settings,
    options,
  };
};

const summariseForExport = (summary: ProfileSummary, referenceLatency: number) => ({
  name: summary.profile.name,
  description: summary.profile.description ?? '',
  samples: summary.profile.samples,
  average_latency_ms: summary.stats.averageLatency,
  min_latency_ms: summary.stats.minLatency,
  max_latency_ms: summary.stats.maxLatency,
  std_latency_ms: summary.stats.stdLatency,
  latency_gain_ms: referenceLatency ? referenceLatency - summary.stats.averageLatency : 0,
  average_prompt_tokens: summary.stats.averagePromptTokens,
  average_completion_tokens: summary.stats.averageCompletionTokens,
  average_total_tokens: summary.stats.averageTotalTokens,
  applied_options: summary.profile.applied_options ?? {},
  applied_settings: summary.profile.applied_settings ?? {},
  errors: summary.profile.errors,
});

const ProfilesPage = (): JSX.Element => {
  const [prompt, setPrompt] = useState('');
  const [profiles, setProfiles] = useState<ProfileForm[]>([
    createProfile({
      name: 'Standard',
      description: 'Parametres par defaut',
      speculative: false,
      options: { ...emptyOptions(), temperature: '0.7', top_p: '0.9', max_tokens: '512' },
    }),
  ]);
  const [historyRows, setHistoryRows] = useState<HistoryRow[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ProfilesResponse | null>(null);

  const [generatorBase, setGeneratorBase] = useState<ProfileForm>(() =>
    createProfile({
      name: 'Profil',
      description: 'Base automatique',
      speculative: false,
      options: { ...emptyOptions(), temperature: '0.7', top_p: '0.9', max_tokens: '512' },
    }),
  );
  const [generatorMatrix, setGeneratorMatrix] = useState(DEFAULT_GENERATOR_MATRIX);
  const [generatorError, setGeneratorError] = useState<string | null>(null);

  const [autoPromptsRaw, setAutoPromptsRaw] = useState('');
  const additionalPrompts = useMemo(
    () =>
      autoPromptsRaw
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    [autoPromptsRaw],
  );

  const [autoRunning, setAutoRunning] = useState(false);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [autoSteps, setAutoSteps] = useState<AutoStep[]>([]);
  const [autoSummary, setAutoSummary] = useState<AutoSummary | null>(null);
  const [autoCandidates, setAutoCandidates] = useState<CandidateRecord[]>([]);
  const [autoBestProfile, setAutoBestProfile] = useState<ProfileForm | null>(null);
  const [autoBestParameters, setAutoBestParameters] = useState<Record<string, string>>({});
  const [autoHistory, setAutoHistory] = useState<AutoHistoryEntry[]>([]);
  const [applyStatus, setApplyStatus] = useState<string | null>(null);

  const canSubmit = useMemo(() => prompt.trim().length > 0 && profiles.length > 0, [prompt, profiles.length]);
  const historyPayload = useMemo(() => buildHistoryPayload(historyRows), [historyRows]);

  const summaries = useMemo<ProfileSummary[]>(() => {
    if (!response) return [];
    return response.profiles.map((profile) => ({ profile, stats: computeStats(profile) }));
  }, [response]);

  const referenceLatency = summaries.length ? summaries[0].stats.averageLatency : 0;

  const radarData: { metrics: RadarMetric[]; series: RadarSeries[] } | null = useMemo(() => {
    if (!autoSummary) return null;
    const metrics: RadarMetric[] = [
      { key: 'latency', label: 'Latence (ms)', invert: true },
      { key: 'prompt', label: 'Tokens prompt' },
      { key: 'completion', label: 'Tokens compl.' },
      { key: 'total', label: 'Tokens totaux' },
    ];
    const series: RadarSeries[] = [
      {
        label: autoSummary.baseline.profile.name,
        values: {
          latency: autoSummary.baseline.stats.averageLatency,
          prompt: autoSummary.baseline.stats.averagePromptTokens,
          completion: autoSummary.baseline.stats.averageCompletionTokens,
          total: autoSummary.baseline.stats.averageTotalTokens,
        },
      },
      {
        label: `${autoSummary.best.profile.name} (optimise)`,
        values: {
          latency: autoSummary.best.stats.averageLatency,
          prompt: autoSummary.best.stats.averagePromptTokens,
          completion: autoSummary.best.stats.averageCompletionTokens,
          total: autoSummary.best.stats.averageTotalTokens,
        },
      },
    ];
    return { metrics, series };
  }, [autoSummary]);

  const updateProfile = useCallback((id: string, mutate: (prev: ProfileForm) => ProfileForm) => {
    setProfiles((prev) => prev.map((profile) => (profile.id === id ? mutate(profile) : profile)));
  }, []);

  const addProfile = () => setProfiles((prev) => [...prev, createProfile()]);
  const removeProfile = (id: string) => setProfiles((prev) => (prev.length <= 1 ? prev : prev.filter((profile) => profile.id !== id)));

  const addHistoryRow = () => setHistoryRows((prev) => [...prev, { id: createId(), role: 'user', content: '' }]);
  const removeHistoryRow = (id: string) => setHistoryRows((prev) => prev.filter((row) => row.id !== id));

  const buildPayload = () => {
    const trimmedPrompt = prompt.trim();
    if (!trimmedPrompt) return null;
    const descriptors = profiles.map((profile, index) => profileFormToDescriptor(profile, index));
    if (!descriptors.length) return null;
    return {
      prompt: trimmedPrompt,
      history: historyPayload,
      profiles: descriptors,
    };
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = buildPayload();
    if (!payload) {
      setError('Prompt ou profils manquants.');
      return;
    }
    try {
      setRunning(true);
      setError(null);
      const data = (await api.debugLLMProfiles(payload)) as ProfilesResponse;
      setResponse(data);
    } catch (err: any) {
      setError(err?.detail ?? 'Erreur pendant le benchmark.');
    } finally {
      setRunning(false);
    }
  };

  const handleExportJSON = () => {
    if (!summaries.length || !response) return;
    const exportData = summaries.map((summary) => summariseForExport(summary, referenceLatency));
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'ivy-profils.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportCSV = () => {
    if (!summaries.length || !response) return;
    const rows = summaries.map((summary) => summariseForExport(summary, referenceLatency));
    const headers = [
      'name',
      'description',
      'samples',
      'average_latency_ms',
      'min_latency_ms',
      'max_latency_ms',
      'std_latency_ms',
      'latency_gain_ms',
      'average_prompt_tokens',
      'average_completion_tokens',
      'average_total_tokens',
    ];
    const csv = [
      headers.join(';'),
      ...rows.map((row) => headers.map((header) => String((row as any)[header] ?? '')).join(';')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'ivy-profils.csv';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleApplyProfileToConfig = async (profile: ProfileForm | null) => {
    if (!profile) return;
    const descriptor = profileFormToDescriptor(profile, 0);
    const patch: Record<string, unknown> = {};
    Object.entries(descriptor.settings || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        patch[key] = value;
      }
    });
    if (!Object.keys(patch).length) {
      setApplyStatus('Aucun parametre a appliquer.');
      return;
    }
    try {
      setApplyStatus('Mise a jour en cours...');
      await api.updateConfig(patch);
      setApplyStatus('Configuration mise a jour avec succes.');
    } catch (err: any) {
      setApplyStatus(err?.detail ?? 'Echec de la mise a jour de la configuration.');
    }
  };

  const handleGenerateProfiles = () => {
    try {
      setGeneratorError(null);
      const defs = parseVariationInput(generatorMatrix);
      if (!defs.length) {
        setGeneratorError('Ajoutez au moins un parametre a varier.');
        return;
      }
      const combos = cartesianProduct(defs);
      if (combos.length > MAX_AUTO_PROFILES) {
        setGeneratorError(`Trop de combinaisons (${combos.length}). Limite: ${MAX_AUTO_PROFILES}.`);
        return;
      }
      const generated = combos.map((combo, index) => applyOverrides(generatorBase, combo, String(index + 1)));
      setProfiles(generated);
      setResponse(null);
      setError(null);
    } catch (err: any) {
      setGeneratorError(err?.message ?? "Impossible de generer les profils.");
    }
  };

  const autoTuneSingle = async (targetPrompt: string): Promise<AutoTuneResult> => {
    let defs = parseVariationInput(generatorMatrix);
    if (!defs.find((item) => item.key === 'speculative')) {
      defs = [
        ...defs,
        {
          key: 'speculative',
          label: 'Mode speculatif',
          values: ['false', 'true'],
        },
      ];
    }
    if (!defs.length) {
      throw new Error('Aucun parametre a optimiser');
    }
    const keysForReportSet = new Set<string>(defs.map((def) => def.key));
    keysForReportSet.add('speculative');
    const keysForReport = Array.from(keysForReportSet);

    const baseProfile = cloneProfile(generatorBase);
    const baseDescriptor = profileFormToDescriptor(baseProfile, 0);
    const baselineResponse = (await api.debugLLMProfiles({
      prompt: targetPrompt,
      history: historyPayload,
      profiles: [baseDescriptor],
    })) as ProfilesResponse;
    const baselineResult = baselineResponse.profiles[0];
    const baselineStats = computeStats(baselineResult);

    let bestProfileForm = baseProfile;
    let bestResult = baselineResult;
    let bestStats = baselineStats;

    const steps: AutoStep[] = [];
    const candidateRecords: CandidateRecord[] = [
      {
        profile: baselineResult,
        stats: baselineStats,
        profileForm: baseProfile,
        parameter: 'Baseline',
        value: 'initial',
        prompt: targetPrompt,
      },
    ];

    const evaluateCandidate = async (
      candidateProfile: ProfileForm,
      parameterLabel: string,
      valueLabel: string,
      origin?: string,
    ) => {
      const descriptor = profileFormToDescriptor(candidateProfile, 0);
      const responseCandidate = (await api.debugLLMProfiles({
        prompt: targetPrompt,
        history: historyPayload,
        profiles: [descriptor],
      })) as ProfilesResponse;
      const candidate = responseCandidate.profiles[0];
      const stats = computeStats(candidate);
      const success = candidate.runs.length > 0 && Number.isFinite(stats.averageLatency) && stats.averageLatency > 0;
      const improvement = bestStats.averageLatency - stats.averageLatency;
      steps.push({
        parameter: parameterLabel,
        value: origin ? `${valueLabel} (${origin})` : valueLabel,
        stats,
        success,
        errors: candidate.errors,
        improvement,
      });
      if (success) {
        candidateRecords.push({
          profile: candidate,
          stats,
          profileForm: candidateProfile,
          parameter: parameterLabel,
          value: valueLabel,
          prompt: targetPrompt,
        });
      }
      return { candidate, stats, success };
    };

    for (const def of defs) {
      const label = def.label || def.key;
      const testedValues = new Map<
        string,
        {
          stats: ProfileStats;
          profile: ProfileResult;
          profileForm: ProfileForm;
        }
      >();

      for (const rawValue of def.values) {
        const valueKey = normalizeValueKey(rawValue);
        if (testedValues.has(valueKey)) continue;
        const candidateProfile = applyOverrides(bestProfileForm, { [def.key]: rawValue });
        const result = await evaluateCandidate(candidateProfile, label, rawValue);
        testedValues.set(valueKey, {
          stats: result.stats,
          profile: result.candidate,
          profileForm: candidateProfile,
        });
        if (result.success) {
          if (result.stats.averageLatency < bestStats.averageLatency) {
            bestStats = result.stats;
            bestResult = result.candidate;
            bestProfileForm = candidateProfile;
          }
        }
      }

      const numericValues = Array.from(testedValues.keys())
        .map((value) => Number(value))
        .filter((value) => Number.isFinite(value));
      if (!numericValues.length) continue;

      numericValues.sort((a, b) => a - b);
      let initialStep = 0;
      for (let index = 1; index < numericValues.length; index += 1) {
        const diff = Math.abs(numericValues[index] - numericValues[index - 1]);
        if (diff > 0) {
          initialStep = diff;
          break;
        }
      }
      if (initialStep === 0) {
        const baseValue = Math.abs(numericValues[0]) || 1;
        initialStep = baseValue >= 1 ? 1 : Number((baseValue * 0.5).toFixed(3));
      }

      const stepCandidates = Array.from(new Set([initialStep, initialStep / 2, ...FINE_STEPS])).filter(
        (value) => Number.isFinite(value) && value > 0,
      );

      for (const fineStep of stepCandidates) {
        let improved = true;
        let guard = 0;
        while (improved && guard < 10) {
          guard += 1;
          improved = false;
          const currentBest =
            parseFloatLoose(bestProfileForm.options[def.key as keyof OptionFields] ?? '') ??
            parseFloatLoose(bestProfileForm.settings[def.key as keyof SettingFields] ?? '') ??
            (bestProfileForm.speculative ? 1 : 0);
          if (!Number.isFinite(currentBest)) break;
          for (const direction of [-1, 1]) {
            const candidateValue = currentBest + direction * fineStep;
            if (!Number.isFinite(candidateValue) || candidateValue < 0) continue;
            const decimals = fineStep < 1 ? 3 : 2;
            const formatted = candidateValue.toFixed(decimals);
            const valueKey = normalizeValueKey(formatted);
            if (testedValues.has(valueKey)) continue;
            const candidateProfile = applyOverrides(bestProfileForm, { [def.key]: formatted });
            const origin =
              fineStep === initialStep
                ? direction > 0
                  ? 'voisin +'
                  : 'voisin -'
                : `affinage ${direction > 0 ? '+' : '-'}${fineStep.toFixed(3)}`;
            const result = await evaluateCandidate(candidateProfile, label, formatted, origin);
            testedValues.set(valueKey, {
              stats: result.stats,
              profile: result.candidate,
              profileForm: candidateProfile,
            });
            if (result.success && result.stats.averageLatency < bestStats.averageLatency) {
              bestStats = result.stats;
              bestResult = result.candidate;
              bestProfileForm = candidateProfile;
              improved = true;
              break;
            }
          }
        }
      }
    }

    candidateRecords.sort((a, b) => a.stats.averageLatency - b.stats.averageLatency);
    const uniqueCandidates: CandidateRecord[] = [];
    const seen = new Set<string>();
    candidateRecords.forEach((record) => {
      const key = `${record.prompt}-${record.parameter}-${record.value}-${Math.round(record.stats.averageLatency)}`;
      if (seen.has(key)) return;
      seen.add(key);
      uniqueCandidates.push(record);
    });

    const summary: AutoSummary = {
      baseline: { profile: baselineResult, stats: baselineStats },
      best: { profile: bestResult, stats: bestStats },
      steps,
    };

    return {
      prompt: targetPrompt,
      summary,
      bestProfileForm,
      bestParameters: extractParameters(bestProfileForm, keysForReport),
      candidates: uniqueCandidates,
      steps,
      response: {
        prompt: targetPrompt,
        profiles: [baselineResult, bestResult],
      },
    };
  };

  const runAutoTune = async () => {
    if (autoRunning) return;
    const basePrompt = prompt.trim();
    if (!basePrompt) {
      setAutoError('Saisissez un prompt avant de lancer le mode auto.');
      return;
    }
    const promptsToRun = [basePrompt, ...additionalPrompts.filter((entry) => entry !== basePrompt)];
    if (!promptsToRun.length) {
      setAutoError('Aucun prompt valide pour le mode auto.');
      return;
    }
    try {
      setAutoRunning(true);
      setAutoError(null);
      setAutoSteps([]);
      setAutoCandidates([]);
      setAutoSummary(null);
      setAutoBestParameters({});
      setApplyStatus(null);

      const runResults: Array<AutoTuneResult & { timestamp: string }> = [];
      for (const promptValue of promptsToRun) {
        const result = await autoTuneSingle(promptValue);
        runResults.push({ ...result, timestamp: new Date().toISOString() });
      }

      const combinedSteps = runResults
        .flatMap((entry) =>
          entry.steps.map((step) => ({
            ...step,
            parameter: `${step.parameter} [${entry.prompt}]`,
          })),
        )
        .sort((a, b) => b.improvement - a.improvement);

      const combinedCandidates = runResults
        .flatMap((entry) => entry.candidates)
        .sort((a, b) => a.stats.averageLatency - b.stats.averageLatency);

      const bestRun = runResults.reduce((best, current) =>
        current.summary.best.stats.averageLatency < best.summary.best.stats.averageLatency ? current : best,
      );

      setResponse(bestRun.response);
      setProfiles([bestRun.bestProfileForm]);
      setAutoBestProfile(bestRun.bestProfileForm);
      setAutoBestParameters(bestRun.bestParameters);
      setAutoSteps(combinedSteps);
      setAutoCandidates(combinedCandidates.slice(0, 10));
      setAutoSummary(bestRun.summary);
      setAutoHistory((prev) =>
        [...runResults.map((entry) => ({ timestamp: entry.timestamp, prompt: entry.prompt, summary: entry.summary })), ...prev].slice(
          0,
          10,
        )
      );
    } catch (err: any) {
      setAutoError(err?.detail ?? err?.message ?? 'Erreur pendant le mode auto.');
    } finally {
      setAutoRunning(false);
    }
  };

  return (
    <section className="profiles-page">
      <header>
        <h1>Tests de profils LLM</h1>
        <p className="muted">
          Comparez plusieurs réglages et mesurez la latence. Utilisez la génération automatique ou le mode full-auto pour explorer l’espace
          de paramètres, sur un ou plusieurs prompts.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="profiles-form">
        <label>
          Prompt de test principal
          <textarea
            required
            rows={4}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ex : Résume un article économique en 5 puces."
          />
        </label>

        <label>
          Prompts additionnels (mode auto, un par ligne)
          <textarea
            rows={3}
            value={autoPromptsRaw}
            onChange={(event) => setAutoPromptsRaw(event.target.value)}
            placeholder="Ex :\nAnalyse le code suivant...\nDonne-moi les risques principaux..."
          />
        </label>

        <div className="profiles-history">
          <div className="profiles-history-header">
            <h2>Contexte optionnel</h2>
            <button type="button" onClick={addHistoryRow}>
              Ajouter une entrée
            </button>
          </div>
          {historyRows.length === 0 ? (
            <p className="muted">Aucun historique ajouté.</p>
          ) : (
            historyRows.map((row) => (
              <div key={row.id} className="profiles-history-row">
                <label>
                  Rôle
                  <select
                    value={row.role}
                    onChange={(event) =>
                      setHistoryRows((prev) =>
                        prev.map((item) =>
                          item.id === row.id ? { ...item, role: event.target.value as HistoryRow['role'] } : item,
                        ),
                      )
                    }
                  >
                    <option value="system">system</option>
                    <option value="user">user</option>
                    <option value="assistant">assistant</option>
                  </select>
                </label>
                <label>
                  Contenu
                  <textarea
                    rows={2}
                    value={row.content}
                    onChange={(event) =>
                      setHistoryRows((prev) =>
                        prev.map((item) => (item.id === row.id ? { ...item, content: event.target.value } : item)),
                      )
                    }
                  />
                </label>
                <button type="button" onClick={() => removeHistoryRow(row.id)}>
                  Supprimer
                </button>
              </div>
            ))
          )}
        </div>

        <section className="profiles-generator">
          <div className="profiles-history-header">
            <h2>Génération automatique (profil de base)</h2>
            <button type="button" onClick={handleGenerateProfiles}>
              Générer les profils
            </button>
          </div>
          <p className="muted">
            Définissez un profil de base puis une matrice « champ=val1,val2 ». Toutes les combinaisons seront générées (limite {MAX_AUTO_PROFILES}
            profils).
          </p>
          <div className="profile-card profile-card--mini">
            <div className="profile-card-actions">
              <label>
                Nom de base
                <input
                  value={generatorBase.name}
                  onChange={(event) => setGeneratorBase((prev) => ({ ...prev, name: event.target.value }))}
                />
              </label>
              <label>
                Échantillons
                <input
                  type="number"
                  min={1}
                  max={5}
                  value={generatorBase.samples}
                  onChange={(event) => setGeneratorBase((prev) => ({ ...prev, samples: event.target.value }))}
                />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={generatorBase.speculative}
                  onChange={(event) => setGeneratorBase((prev) => ({ ...prev, speculative: event.target.checked }))}
                />
                Mode spéculatif (base)
              </label>
            </div>
            <label>
              Description
              <input
                value={generatorBase.description}
                onChange={(event) => setGeneratorBase((prev) => ({ ...prev, description: event.target.value }))}
              />
            </label>
            <div className="profile-card-grid">
              <label>
                Température
                <input
                  value={generatorBase.options.temperature}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      options: { ...prev.options, temperature: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                top_p
                <input
                  value={generatorBase.options.top_p}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      options: { ...prev.options, top_p: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                top_k
                <input
                  value={generatorBase.options.top_k}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      options: { ...prev.options, top_k: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                repeat_penalty
                <input
                  value={generatorBase.options.repeat_penalty}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      options: { ...prev.options, repeat_penalty: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                max_tokens
                <input
                  value={generatorBase.options.max_tokens}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      options: { ...prev.options, max_tokens: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                Modèle principal
                <input
                  value={generatorBase.settings.llm_model_path}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_model_path: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                Modèle brouillon
                <input
                  value={generatorBase.settings.llm_speculative_model_path}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_speculative_model_path: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                Contexte (tokens)
                <input
                  value={generatorBase.settings.llm_context_tokens}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_context_tokens: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                GPU layers
                <input
                  value={generatorBase.settings.llm_n_gpu_layers}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_n_gpu_layers: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                Contexte brouillon
                <input
                  value={generatorBase.settings.llm_speculative_context_tokens}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_speculative_context_tokens: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                GPU brouillon
                <input
                  value={generatorBase.settings.llm_speculative_n_gpu_layers}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, llm_speculative_n_gpu_layers: event.target.value },
                    }))
                  }
                />
              </label>
              <label>
                Prompt système
                <input
                  value={generatorBase.settings.chat_system_prompt}
                  onChange={(event) =>
                    setGeneratorBase((prev) => ({
                      ...prev,
                      settings: { ...prev.settings, chat_system_prompt: event.target.value },
                    }))
                  }
                />
              </label>
            </div>
          </div>
          <label>
            Variations (une ligne par paramètre : champ=val1,val2)
            <textarea
              rows={4}
              value={generatorMatrix}
              onChange={(event) => setGeneratorMatrix(event.target.value)}
              placeholder={DEFAULT_GENERATOR_MATRIX}
            />
          </label>
          <p className="muted">
            Champs supportés : temperature, top_p, top_k, repeat_penalty, max_tokens, llm_model_path, llm_speculative_model_path,
            llm_context_tokens, llm_n_gpu_layers, llm_speculative_context_tokens, llm_speculative_n_gpu_layers, chat_system_prompt,
            speculative, samples.
          </p>
          {generatorError ? <p className="error">{generatorError}</p> : null}
        </section>

        <section className="profiles-generator">
          <div className="profiles-history-header">
            <h2>Mode full auto (multi-prompts)</h2>
            <button type="button" onClick={runAutoTune} disabled={autoRunning}>
              {autoRunning ? 'Optimisation en cours...' : 'Lancer le mode auto'}
            </button>
          </div>
          <p className="muted">
            Le mode auto teste chaque prompt, affine les paramètres autour du meilleur candidat avec des pas jusqu’à 0,01 et compare les
            profils spéculatif / non spéculatif.
          </p>
          {autoError ? <p className="error">{autoError}</p> : null}
        </section>

        <div className="profiles-list">
          {profiles.map((profile) => (
            <fieldset key={profile.id} className="profile-card">
              <legend>Profil</legend>
              <div className="profile-card-actions">
                <label>
                  Nom
                  <input
                    value={profile.name}
                    onChange={(event) =>
                      updateProfile(profile.id, (prev) => ({
                        ...prev,
                        name: event.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  Échantillons
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={profile.samples}
                    onChange={(event) =>
                      updateProfile(profile.id, (prev) => ({
                        ...prev,
                        samples: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={profile.speculative}
                    onChange={(event) =>
                      updateProfile(profile.id, (prev) => ({
                        ...prev,
                        speculative: event.target.checked,
                      }))
                    }
                  />
                  Mode spéculatif
                </label>
                <div>
                  <button type="button" onClick={() => removeProfile(profile.id)}>
                    Supprimer
                  </button>
                </div>
              </div>

              <label>
                Description
                <input
                  value={profile.description}
                  onChange={(event) =>
                    updateProfile(profile.id, (prev) => ({
                      ...prev,
                      description: event.target.value,
                    }))
                  }
                />
              </label>

              <div className="profile-card-grid">
                {OPTION_KEYS.map((key) => (
                  <label key={key}>
                    {key}
                    <input
                      value={profile.options[key] ?? ''}
                      onChange={(event) =>
                        updateProfile(profile.id, (prev) => ({
                          ...prev,
                          options: { ...prev.options, [key]: event.target.value },
                        }))
                      }
                    />
                  </label>
                ))}
                {SETTING_KEYS.map((key) => (
                  <label key={key}>
                    {key}
                    <input
                      value={profile.settings[key] ?? ''}
                      onChange={(event) =>
                        updateProfile(profile.id, (prev) => ({
                          ...prev,
                          settings: { ...prev.settings, [key]: event.target.value },
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>

        <div className="profiles-actions">
          <button type="button" onClick={addProfile}>
            Ajouter un profil
          </button>
          <button type="submit" disabled={!canSubmit || running}>
            {running ? 'Calcul en cours...' : 'Lancer les tests'}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
      </form>

      {response && summaries.length ? (
        <section className="profiles-results">
          <div className="profiles-history-header">
            <h2>Résultats</h2>
            <div className="profiles-actions">
              <button type="button" onClick={handleExportJSON}>
                Export JSON
              </button>
              <button type="button" onClick={handleExportCSV}>
                Export CSV
              </button>
            </div>
          </div>
          {summaries.map((summary, index) => {
            const gain = referenceLatency ? referenceLatency - summary.stats.averageLatency : 0;
            return (
              <article key={`${summary.profile.name}-${index}`} className="profile-result">
                <header className="profile-result-header">
                  <div>
                    <h3>{summary.profile.name}</h3>
                    {summary.profile.description ? <p className="muted">{summary.profile.description}</p> : null}
                  </div>
                  <div className="profile-result-meta">
                    <span>Échantillons : {summary.profile.samples}</span>
                    <span>Latence moyenne : {formatLatency(summary.stats.averageLatency)}</span>
                    <span>Gain vs réf. : {formatNumber(gain)} ms</span>
                  </div>
                </header>

                <ul className="profile-options">
                  <li>Latence min : {formatNumber(summary.stats.minLatency)} ms</li>
                  <li>Latence max : {formatNumber(summary.stats.maxLatency)} ms</li>
                  <li>Écart-type : {formatNumber(summary.stats.stdLatency)} ms</li>
                  <li>Tokens prompt : {formatNumber(summary.stats.averagePromptTokens)}</li>
                  <li>Tokens compl. : {formatNumber(summary.stats.averageCompletionTokens)}</li>
                  <li>Tokens totaux : {formatNumber(summary.stats.averageTotalTokens)}</li>
                </ul>

                {prettyKV(summary.profile.applied_options).length ? (
                  <div className="profile-options">
                    {prettyKV(summary.profile.applied_options).map((entry) => (
                      <span key={`${summary.profile.name}-opt-${entry}`}>{entry}</span>
                    ))}
                  </div>
                ) : null}
                {prettyKV(summary.profile.applied_settings).length ? (
                  <div className="profile-options">
                    {prettyKV(summary.profile.applied_settings).map((entry) => (
                      <span key={`${summary.profile.name}-set-${entry}`}>{entry}</span>
                    ))}
                  </div>
                ) : null}

                {summary.profile.errors.length ? (
                  <ul className="profile-errors">
                    {summary.profile.errors.map((item, idx) => (
                      <li key={`${summary.profile.name}-error-${idx}`}>{item}</li>
                    ))}
                  </ul>
                ) : null}

                <div className="profile-runs">
                  {summary.profile.runs.map((run, idx) => (
                    <div key={`${summary.profile.name}-run-${idx}`} className="profile-run">
                      <div className="profile-run-header">
                        <strong>Essai {idx + 1}</strong>
                        <span>{formatLatency(run.latency_ms)}</span>
                        <span>{run.speculative ? 'Spéculatif actif' : 'Standard'}</span>
                      </div>
                      {run.usage ? (
                        <p className="muted">
                          Tokens:{' '}
                          {Object.entries(run.usage)
                            .map(([key, value]) => `${key}=${value}`)
                            .join(' | ')}
                        </p>
                      ) : null}
                      {run.text ? <pre>{run.text}</pre> : <p className="muted">Pas de texte retourné.</p>}
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </section>
      ) : null}

      {autoSteps.length ? (
        <section className="profiles-results">
          <h2>Journal du mode auto</h2>
          <div className="profile-run">
            <table>
              <thead>
                <tr>
                  <th>Paramètre</th>
                  <th>Valeur</th>
                  <th>Latence moyenne (ms)</th>
                  <th>Gain (ms)</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {autoSteps.map((step, idx) => (
                  <tr key={`${step.parameter}-${step.value}-${idx}`}>
                    <td>{step.parameter}</td>
                    <td>{step.value}</td>
                    <td>{formatNumber(step.stats.averageLatency)}</td>
                    <td>{formatNumber(step.improvement)}</td>
                    <td>{step.success ? 'OK' : step.errors.join(', ') || 'Échec'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {autoCandidates.length ? (
        <section className="profiles-results">
          <h2>Meilleurs profils détectés</h2>
          <div className="profile-run">
            {Object.keys(autoBestParameters).length ? (
              <div className="profile-options" style={{ marginBottom: '0.5rem' }}>
                {Object.entries(autoBestParameters).map(([key, value]) => (
                  <span key={key}>
                    {key}={value}
                  </span>
                ))}
              </div>
            ) : null}
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Prompt</th>
                  <th>Paramètre</th>
                  <th>Valeur</th>
                  <th>Latence moyenne (ms)</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {autoCandidates.slice(0, 8).map((record, index) => (
                  <tr key={`${record.prompt}-${record.parameter}-${record.value}-${index}`}>
                    <td>{index + 1}</td>
                    <td>{record.prompt}</td>
                    <td>{record.parameter}</td>
                    <td>{record.value}</td>
                    <td>{formatNumber(record.stats.averageLatency)}</td>
                    <td>{formatNumber(record.stats.minLatency)}</td>
                    <td>{formatNumber(record.stats.maxLatency)}</td>
                    <td>
                      <button type="button" onClick={() => handleApplyProfileToConfig(record.profileForm)}>
                        Appliquer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ marginTop: '0.5rem' }}>
              <button type="button" onClick={() => handleApplyProfileToConfig(autoBestProfile)}>
                Appliquer le meilleur profil global
              </button>
              {applyStatus ? <p className="muted">{applyStatus}</p> : null}
            </div>
          </div>
        </section>
      ) : null}

      {autoSummary && radarData ? (
        <section className="profiles-results">
          <h2>Diagramme de Kiviat (Baseline vs Optimisé)</h2>
          <RadarChart metrics={radarData.metrics} series={radarData.series} />
        </section>
      ) : null}

      {autoHistory.length ? (
        <section className="profiles-results">
          <h2>Historique des optimisations</h2>
          <div className="profile-run">
            <table>
              <thead>
                <tr>
                  <th>Date/heure</th>
                  <th>Prompt</th>
                  <th>Latence baseline (ms)</th>
                  <th>Latence optimisée (ms)</th>
                  <th>Gain (ms)</th>
                </tr>
              </thead>
              <tbody>
                {autoHistory.map((entry, index) => (
                  <tr key={`${entry.prompt}-${entry.timestamp}-${index}`}>
                    <td>{formatDateTime(entry.timestamp)}</td>
                    <td>{entry.prompt}</td>
                    <td>{formatNumber(entry.summary.baseline.stats.averageLatency)}</td>
                    <td>{formatNumber(entry.summary.best.stats.averageLatency)}</td>
                    <td>
                      {formatNumber(
                        entry.summary.baseline.stats.averageLatency - entry.summary.best.stats.averageLatency,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </section>
  );
};

export default ProfilesPage;
