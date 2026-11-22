import { Play, Square, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type { CommuneItem, SourceItem, WilayaSummary } from '../types';

interface CollectViewProps {
  wilayas: WilayaSummary[];
  sources: SourceItem[];
  activeRunId: number | null;
  t: Translations;
  onRunChange: () => void;
}

interface RunDetailPayload {
  run: {
    id: number;
    status: string;
    total_tasks: number;
    completed_tasks: number;
    discovered_count: number;
    processed_count: number;
    new_businesses_count: number;
    merged_count: number;
    rejected_count: number;
    review_required_count: number;
    error_count: number;
  };
  wilaya_progress: Array<{
    wilaya_code: number;
    code_str: string;
    name_fr: string;
    source_key: string;
    coverage_status: string;
    discovered_count: number;
    processed_count: number;
    rejected_count: number;
    review_count: number;
    error_message: string;
  }>;
  is_actively_running: boolean;
}

export function CollectView({ wilayas, sources, activeRunId, t, onRunChange }: CollectViewProps) {
  const [selectedWilayas, setSelectedWilayas] = useState<number[]>([]);
  const [selectedCommunes, setSelectedCommunes] = useState<number[]>([]);
  const [communes, setCommunes] = useState<CommuneItem[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>(['osm_overpass', 'pagesmaghreb']);
  const [searchDepth, setSearchDepth] = useState<'quick' | 'standard' | 'deep'>('standard');
  const [wilayaSearch, setWilayaSearch] = useState('');
  const [currentRunId, setCurrentRunId] = useState<number | null>(activeRunId);
  const [runDetail, setRunDetail] = useState<RunDetailPayload | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [importResult, setImportResult] = useState<string>('');
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (activeRunId) {
      setCurrentRunId(activeRunId);
    }
  }, [activeRunId]);

  // Load communes when exactly 1 wilaya is selected
  useEffect(() => {
    if (selectedWilayas.length === 1) {
      api
        .get<CommuneItem[]>(`/api/wilayas/${selectedWilayas[0]}/communes`)
        .then(setCommunes)
        .catch(() => setCommunes([]));
    } else {
      setCommunes([]);
      setSelectedCommunes([]);
    }
  }, [selectedWilayas]);

  // Poll active collection run progress
  useEffect(() => {
    if (!currentRunId) return;
    let active = true;
    const poll = async () => {
      try {
        const detail = await api.get<RunDetailPayload>(`/api/collections/${currentRunId}`);
        if (!active) return;
        setRunDetail(detail);
        if (!detail.is_actively_running && detail.run.status !== 'running') {
          onRunChange();
        }
      } catch {
        // ignore transient polling errors
      }
    };
    poll();
    const timer = setInterval(poll, 1800);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [currentRunId, onRunChange]);

  const automatedSources = sources.filter((s) => s.source_type !== 'manual_import');

  const toggleWilaya = (code: number) => {
    setSelectedWilayas((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  };

  const toggleSource = (key: string) => {
    setSelectedSources((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const handleStart = async () => {
    setErrorMsg('');
    try {
      const res = await api.post<{ run_id: number }>('/api/collections/start', {
        wilaya_codes: selectedWilayas,
        commune_ids: selectedCommunes,
        source_keys: selectedSources,
        search_depth: searchDepth,
      });
      setCurrentRunId(res.run_id);
      onRunChange();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to start collection');
    }
  };

  const handleStop = async () => {
    if (!currentRunId) return;
    await api.post(`/api/collections/${currentRunId}/stop`);
    onRunChange();
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setImportResult('');
    setErrorMsg('');
    try {
      const res = await api.upload<{
        total_rows: number;
        new: number;
        auto_merged: number;
        review_candidate: number;
        rejected: number;
      }>('/api/imports/upload', file);
      setImportResult(
        `Imported ${res.total_rows} rows: ${res.new} new, ${res.auto_merged} auto-merged, ${res.review_candidate} needing review, ${res.rejected} rejected.`,
      );
      onRunChange();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const filteredWilayas = wilayas.filter((w) => {
    const q = wilayaSearch.trim().toLowerCase();
    if (!q) return true;
    return w.name_fr.toLowerCase().includes(q) || w.name_ar.includes(q) || w.code_str.includes(q);
  });

  const isRunning = Boolean(runDetail?.is_actively_running || runDetail?.run.status === 'running');
  const pct =
    runDetail && runDetail.run.total_tasks > 0
      ? Math.round((runDetail.run.completed_tasks / runDetail.run.total_tasks) * 100)
      : 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t.collect.title}</h1>
          <p className="text-sm text-slate-600 mt-0.5">{t.collect.subtitle}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {isRunning ? (
            <button
              type="button"
              onClick={handleStop}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-rose-600 rounded-lg hover:bg-rose-700 whitespace-nowrap shrink-0"
            >
              <Square className="w-3.5 h-3.5" />
              <span>{t.collect.stopRun}</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStart}
              disabled={selectedSources.length === 0}
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 disabled:opacity-50 whitespace-nowrap shrink-0"
            >
              <Play className="w-3.5 h-3.5" />
              <span>{t.collect.startRun}</span>
            </button>
          )}
        </div>
      </div>

      {errorMsg && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-lg px-4 py-3">{errorMsg}</div>
      )}

      {/* Configuration Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Wilaya selector */}
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-lg p-5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-900">
              {t.collect.selectWilayas} (
              <span className="font-mono-tabular">
                {selectedWilayas.length === 0 ? '69 / 69' : `${selectedWilayas.length} / 69`}
              </span>
              )
            </h2>
            <div className="flex items-center gap-2 text-xs">
              <button
                type="button"
                onClick={() => setSelectedWilayas([])}
                className="px-2.5 py-1 border border-slate-200 rounded hover:bg-slate-50 whitespace-nowrap shrink-0"
              >
                {t.collect.all69Wilayas}
              </button>
              <button
                type="button"
                onClick={() => setSelectedWilayas(wilayas.filter((w) => w.code >= 59).map((w) => w.code))}
                className="px-2.5 py-1 border border-slate-200 rounded hover:bg-slate-50 whitespace-nowrap shrink-0"
              >
                {t.collect.new11Wilayas}
              </button>
              {selectedWilayas.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedWilayas([])}
                  className="px-2.5 py-1 text-slate-600 hover:text-slate-900 whitespace-nowrap shrink-0"
                >
                  {t.collect.clearSelection}
                </button>
              )}
            </div>
          </div>

          <input
            type="text"
            value={wilayaSearch}
            onChange={(e) => setWilayaSearch(e.target.value)}
            placeholder={t.common.search}
            className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-teal-600"
          />

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1.5 max-h-60 overflow-y-auto pr-1">
            {filteredWilayas.map((w) => {
              const checked = selectedWilayas.includes(w.code);
              return (
                <button
                  key={w.code}
                  type="button"
                  onClick={() => toggleWilaya(w.code)}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs text-left border transition-colors ${
                    checked
                      ? 'bg-teal-50 border-teal-600 text-teal-900 font-medium'
                      : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span className="font-mono-tabular text-slate-400 shrink-0">{w.code_str}</span>
                  <span className="truncate">{w.name_fr}</span>
                </button>
              );
            })}
          </div>

          {selectedWilayas.length === 1 && communes.length > 0 && (
            <div className="pt-2 border-t border-slate-100">
              <div className="text-xs font-medium text-slate-700 mb-1.5">
                {t.common.commune} ({selectedCommunes.length || 'all'} / {communes.length})
              </div>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto">
                {communes.map((c) => {
                  const active = selectedCommunes.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() =>
                        setSelectedCommunes((prev) =>
                          prev.includes(c.id) ? prev.filter((id) => id !== c.id) : [...prev, c.id],
                        )
                      }
                      className={`px-2 py-1 text-xs rounded border ${
                        active ? 'bg-teal-50 border-teal-600 text-teal-900' : 'border-slate-200 text-slate-600'
                      }`}
                    >
                      {c.name_fr}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Sources & Depth */}
        <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-5">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 mb-2.5">{t.collect.selectSources}</h2>
            <div className="space-y-2">
              {automatedSources.map((src) => (
                <label
                  key={src.key}
                  className="flex items-start gap-2.5 p-2 rounded border border-slate-200 cursor-pointer hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    checked={selectedSources.includes(src.key)}
                    disabled={!src.enabled}
                    onChange={() => toggleSource(src.key)}
                    className="mt-0.5 accent-teal-700"
                  />
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-slate-800">{src.name}</div>
                    <div className="text-[11px] text-slate-500 truncate">{src.attribution}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-semibold text-slate-900 mb-2">{t.collect.searchDepth}</h2>
            <div className="grid grid-cols-3 gap-1.5 p-1 bg-slate-100 rounded-lg">
              {(['quick', 'standard', 'deep'] as const).map((depth) => (
                <button
                  key={depth}
                  type="button"
                  onClick={() => setSearchDepth(depth)}
                  className={`py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                    searchDepth === depth ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'
                  }`}
                >
                  {depth === 'quick'
                    ? t.collect.depthQuick
                    : depth === 'standard'
                      ? t.collect.depthStandard
                      : t.collect.depthDeep}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Live Run Progress */}
      {runDetail && (
        <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              {isRunning && <span className="w-2 h-2 rounded-full bg-teal-600 animate-pulse" />}
              <h2 className="text-sm font-semibold text-slate-900">
                Run #{runDetail.run.id} · {runDetail.run.status}
              </h2>
            </div>
            <div className="text-xs font-mono-tabular text-slate-600">
              {runDetail.run.completed_tasks} / {runDetail.run.total_tasks} tasks ({pct}%)
            </div>
          </div>

          <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden">
            <div className="bg-teal-700 h-full transition-all" style={{ width: `${pct}%` }} />
          </div>

          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs">
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">Discovered</div>
              <div className="font-mono-tabular font-semibold text-slate-900 text-base">
                {runDetail.run.discovered_count}
              </div>
            </div>
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">Processed</div>
              <div className="font-mono-tabular font-semibold text-slate-900 text-base">
                {runDetail.run.processed_count}
              </div>
            </div>
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">New</div>
              <div className="font-mono-tabular font-semibold text-emerald-700 text-base">
                {runDetail.run.new_businesses_count}
              </div>
            </div>
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">Auto-Merged</div>
              <div className="font-mono-tabular font-semibold text-teal-700 text-base">
                {runDetail.run.merged_count}
              </div>
            </div>
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">Rejected</div>
              <div className="font-mono-tabular font-semibold text-slate-700 text-base">
                {runDetail.run.rejected_count}
              </div>
            </div>
            <div className="p-2.5 bg-slate-50 rounded border border-slate-200">
              <div className="text-slate-500">Needs Review</div>
              <div className="font-mono-tabular font-semibold text-amber-700 text-base">
                {runDetail.run.review_required_count}
              </div>
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto border border-slate-200 rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 sticky top-0">
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 px-3 text-left font-medium">{t.common.wilaya}</th>
                  <th className="py-2 px-3 text-left font-medium">{t.common.source}</th>
                  <th className="py-2 px-3 text-left font-medium">{t.common.status}</th>
                  <th className="py-2 px-3 text-right font-medium">Discovered</th>
                  <th className="py-2 px-3 text-right font-medium">Processed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runDetail.wilaya_progress.slice(0, 120).map((wp, i) => (
                  <tr key={`${wp.wilaya_code}-${wp.source_key}-${i}`} className="h-8">
                    <td className="px-3 py-1.5 text-slate-800">
                      <span className="font-mono-tabular text-slate-400 mr-1.5">{wp.code_str}</span>
                      {wp.name_fr}
                    </td>
                    <td className="px-3 py-1.5 font-mono-tabular text-slate-600">{wp.source_key}</td>
                    <td className="px-3 py-1.5 text-slate-700">{wp.coverage_status}</td>
                    <td className="px-3 py-1.5 text-right font-mono-tabular">{wp.discovered_count}</td>
                    <td className="px-3 py-1.5 text-right font-mono-tabular">{wp.processed_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Manual Import Panel */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{t.collect.manualImportTitle}</h2>
          <p className="text-xs text-slate-600 mt-0.5">{t.collect.manualImportDesc}</p>
          {importResult && <p className="text-xs text-emerald-700 font-medium mt-2">{importResult}</p>}
        </div>
        <label className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-slate-800 bg-slate-50 border border-slate-300 rounded-lg hover:bg-slate-100 cursor-pointer whitespace-nowrap shrink-0">
          <Upload className="w-3.5 h-3.5" />
          <span>{uploading ? t.common.loading : t.collect.uploadFile}</span>
          <input type="file" accept=".csv,.xlsx,.xlsm,.json,.geojson" onChange={handleFileUpload} className="hidden" />
        </label>
      </div>
    </div>
  );
}
