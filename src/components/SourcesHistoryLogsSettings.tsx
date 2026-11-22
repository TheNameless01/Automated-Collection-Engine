import { Database, Download, Play, RotateCcw, Shield, Wifi } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type { AppLang, CollectionRun, SourceItem } from '../types';

export function SourcesView({
  sources,
  t,
  onRefresh,
}: {
  sources: SourceItem[];
  t: Translations;
  onRefresh: () => void;
}) {
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string }>>({});
  const [testingKey, setTestingKey] = useState('');

  const handleToggle = async (src: SourceItem) => {
    await api.patch(`/api/sources/${src.key}`, { enabled: !src.enabled });
    onRefresh();
  };

  const handleTest = async (key: string) => {
    setTestingKey(key);
    try {
      const res = await api.post<{ ok: boolean; message: string }>(`/api/sources/${key}/test`);
      setTestResults((prev) => ({ ...prev, [key]: res }));
    } finally {
      setTestingKey('');
    }
  };

  const handleDownloadPbf = async () => {
    await api.post('/api/sources/osm-pbf/download');
    onRefresh();
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t.nav.sources}</h1>
        <p className="text-xs text-slate-600 mt-0.5">
          Configure, test, enable, or disable modular data adapters. All sources enforce rate limits and robots.txt rules.
        </p>
      </div>

      <div className="space-y-3">
        {sources.map((src) => {
          const testRes = testResults[src.key];
          return (
            <div key={src.key} className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <h2 className="text-sm font-semibold text-slate-900">{src.name}</h2>
                    <span className="text-xs font-mono-tabular text-slate-500">{src.source_type}</span>
                  </div>
                  <div className="text-xs text-slate-600">{src.license_info}</div>
                  {src.base_url && <div className="text-[11px] font-mono-tabular text-slate-400">{src.base_url}</div>}
                </div>

                <div className="flex items-center gap-2 shrink-0 text-xs">
                  <button
                    type="button"
                    onClick={() => handleTest(src.key)}
                    disabled={testingKey === src.key}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50"
                  >
                    <Wifi className="w-3.5 h-3.5" />
                    <span>{testingKey === src.key ? t.common.loading : 'Test Source'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggle(src)}
                    className={`px-3 py-1.5 rounded-lg font-medium border ${
                      src.enabled
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                        : 'bg-slate-100 border-slate-200 text-slate-600'
                    }`}
                  >
                    {src.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                </div>
              </div>

              {src.key === 'osm_pbf' && (
                <div className="bg-slate-50 border border-slate-200 rounded p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div>
                    <span className="font-medium text-slate-800">Local PBF Status: </span>
                    <span className="font-mono-tabular text-slate-600">
                      {src.pbf_local_exists
                        ? `Ready (${src.pbf_local_size_mb} MB in data/raw/algeria-latest.osm.pbf)`
                        : src.pbf_download_state?.downloading
                          ? `Downloading (${Math.round((src.pbf_download_state.downloaded_bytes / 1048576) * 10) / 10} MB)`
                          : 'Not downloaded yet (~302 MB)'}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleDownloadPbf}
                    disabled={Boolean(src.pbf_download_state?.downloading)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-700 text-white rounded hover:bg-teal-800 disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>{src.pbf_local_exists ? 'Check / Update PBF' : 'Download Algeria PBF'}</span>
                  </button>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-500 font-mono-tabular">
                <span>Rate limit: {src.rate_limit_seconds}s</span>
                <span>·</span>
                <span>Last status: {src.last_status}</span>
                {src.last_run_at && (
                  <>
                    <span>·</span>
                    <span>Last run: {src.last_run_at.slice(0, 19).replace('T', ' ')}</span>
                  </>
                )}
              </div>

              {testRes && (
                <div
                  className={`text-xs px-3 py-2 rounded border ${
                    testRes.ok
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-amber-50 border-amber-200 text-amber-900'
                  }`}
                >
                  {testRes.message}
                </div>
              )}
              {src.last_error && (
                <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">
                  {src.last_error}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function HistoryView({
  t,
  onResumed,
}: {
  t: Translations;
  onResumed: () => void;
}) {
  const [runs, setRuns] = useState<CollectionRun[]>([]);
  const load = useCallback(() => {
    api.get<CollectionRun[]>('/api/collections').then(setRuns);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleResume = async (id: number) => {
    await api.post(`/api/collections/${id}/resume`);
    load();
    onResumed();
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t.nav.history}</h1>
        <p className="text-xs text-slate-600 mt-0.5">
          All automated collection runs. Interrupted or cancelled runs can be resumed from their last saved checkpoint.
        </p>
      </div>
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-2.5 px-3 text-left font-medium">Run</th>
              <th className="py-2.5 px-3 text-left font-medium">Status</th>
              <th className="py-2.5 px-3 text-left font-medium">Started</th>
              <th className="py-2.5 px-3 text-right font-medium">Tasks</th>
              <th className="py-2.5 px-3 text-right font-medium">Discovered</th>
              <th className="py-2.5 px-3 text-right font-medium">New</th>
              <th className="py-2.5 px-3 text-right font-medium">Merged</th>
              <th className="py-2.5 px-3 text-right font-medium">Errors</th>
              <th className="py-2.5 px-3 text-right font-medium">{t.common.actions}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {runs.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-500">
                  No collection runs yet.
                </td>
              </tr>
            ) : (
              runs.map((r) => (
                <tr key={r.id} className="h-10">
                  <td className="px-3 py-2 font-mono-tabular font-medium text-slate-900">#{r.id}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-700">{r.status}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-500">{r.started_at.slice(0, 19).replace('T', ' ')}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular">
                    {r.completed_tasks}/{r.total_tasks}
                  </td>
                  <td className="px-3 py-2 text-right font-mono-tabular">{r.discovered_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-emerald-700">{r.new_businesses_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-teal-700">{r.merged_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-rose-700">{r.error_count}</td>
                  <td className="px-3 py-2 text-right">
                    {(r.status === 'cancelled' || r.status === 'paused' || r.status === 'failed') && (
                      <button
                        type="button"
                        onClick={() => handleResume(r.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-teal-50 text-teal-800 border border-teal-200 rounded hover:bg-teal-100"
                      >
                        <Play className="w-3 h-3" />
                        <span>Resume</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function LogsView({ t }: { t: Translations }) {
  const [tab, setTab] = useState<'app' | 'audit'>('app');
  const [level, setLevel] = useState('');
  const [appLogs, setAppLogs] = useState<Array<{ id: number; level: string; logger_name: string; message: string; created_at: string }>>([]);
  const [auditLogs, setAuditLogs] = useState<Array<{ id: number; action: string; entity_type: string; entity_id: number; actor: string; details_json: string; created_at: string }>>([]);

  useEffect(() => {
    api.get<typeof appLogs>(`/api/logs?level=${level}`).then(setAppLogs);
    api.get<typeof auditLogs>('/api/audit-logs').then(setAuditLogs);
  }, [level]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-semibold text-slate-900">{t.nav.logs}</h1>
        <div className="flex items-center gap-2 text-xs">
          <div className="flex p-1 bg-slate-100 rounded-lg">
            <button
              type="button"
              onClick={() => setTab('app')}
              className={`px-3 py-1 rounded font-medium ${tab === 'app' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
            >
              System Logs
            </button>
            <button
              type="button"
              onClick={() => setTab('audit')}
              className={`px-3 py-1 rounded font-medium ${tab === 'audit' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
            >
              Audit History
            </button>
          </div>
          {tab === 'app' && (
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
            >
              <option value="">All Levels</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {tab === 'app' ? (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
              <tr>
                <th className="py-2 px-3 text-left font-medium">Time</th>
                <th className="py-2 px-3 text-left font-medium">Level</th>
                <th className="py-2 px-3 text-left font-medium">Logger</th>
                <th className="py-2 px-3 text-left font-medium">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {appLogs.map((l) => (
                <tr key={l.id}>
                  <td className="px-3 py-2 font-mono-tabular text-slate-400 whitespace-nowrap">{l.created_at.slice(0, 19).replace('T', ' ')}</td>
                  <td className="px-3 py-2 font-mono-tabular font-medium text-slate-700">{l.level}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-500">{l.logger_name}</td>
                  <td className="px-3 py-2 text-slate-800">{l.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
              <tr>
                <th className="py-2 px-3 text-left font-medium">Time</th>
                <th className="py-2 px-3 text-left font-medium">Action</th>
                <th className="py-2 px-3 text-left font-medium">Entity</th>
                <th className="py-2 px-3 text-left font-medium">Actor</th>
                <th className="py-2 px-3 text-left font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {auditLogs.map((a) => (
                <tr key={a.id}>
                  <td className="px-3 py-2 font-mono-tabular text-slate-400 whitespace-nowrap">{a.created_at.slice(0, 19).replace('T', ' ')}</td>
                  <td className="px-3 py-2 font-medium text-slate-800">{a.action}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-600">
                    {a.entity_type} #{a.entity_id}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{a.actor}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-500 max-w-md truncate">{a.details_json}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function SettingsView({
  lang,
  onLangChange,
  t,
}: {
  lang: AppLang;
  onLangChange: (newLang: AppLang) => void;
  t: Translations;
}) {
  const [settingsMap, setSettingsMap] = useState<Record<string, unknown>>({});
  const [backups, setBackups] = useState<Array<{ filename: string; size_bytes: number; created_at: string }>>([]);
  const [integrity, setIntegrity] = useState<{ ok: boolean; integrity_messages: string[] } | null>(null);
  const [notice, setNotice] = useState('');

  const loadAll = useCallback(async () => {
    const [s, b] = await Promise.all([
      api.get<Record<string, unknown>>('/api/settings'),
      api.get<Array<{ filename: string; size_bytes: number; created_at: string }>>('/api/backups'),
    ]);
    setSettingsMap(s);
    setBackups(b);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleSaveSettings = async (next: Record<string, unknown>) => {
    const updated = await api.patch<Record<string, unknown>>('/api/settings', { settings: next });
    setSettingsMap(updated);
    setNotice('Settings saved.');
  };

  const handleCreateBackup = async () => {
    const res = await api.post<{ filename: string }>('/api/backups/create');
    setNotice(`Backup created: ${res.filename}`);
    loadAll();
  };

  const handleRestoreBackup = async (filename: string) => {
    await api.post('/api/backups/restore', { filename });
    setNotice(`Database restored from ${filename} (pre-restore safety snapshot saved).`);
    loadAll();
  };

  const handleIntegrity = async () => {
    const res = await api.get<{ ok: boolean; integrity_messages: string[] }>('/api/database/integrity');
    setIntegrity(res);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t.nav.settings}</h1>
        <p className="text-xs text-slate-600 mt-0.5">Language preferences, deduplication thresholds, and SQLite backup management.</p>
      </div>

      {notice && (
        <div className="bg-teal-50 border border-teal-200 text-teal-900 text-xs rounded-lg px-4 py-2.5">{notice}</div>
      )}

      {/* Language & Thresholds */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-5 text-xs">
        <div className="space-y-2">
          <div className="font-semibold text-slate-900">Interface Language / اللغة / Langue</div>
          <div className="flex gap-2 max-w-md">
            {([
              { id: 'fr', label: 'Français' },
              { id: 'ar', label: 'العربية (RTL)' },
              { id: 'en', label: 'English' },
            ] as const).map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  onLangChange(opt.id);
                  handleSaveSettings({ language: opt.id });
                }}
                className={`flex-1 py-2 px-3 border rounded-lg font-medium ${
                  lang === opt.id ? 'bg-teal-50 border-teal-600 text-teal-900' : 'border-slate-200 text-slate-700'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 border-t border-slate-100">
          <label className="space-y-1">
            <span className="font-medium text-slate-700">Auto-Merge Threshold</span>
            <input
              type="number"
              step="0.02"
              min="0.7"
              max="0.99"
              value={String(settingsMap.auto_merge_threshold ?? 0.88)}
              onChange={(e) => setSettingsMap({ ...settingsMap, auto_merge_threshold: Number(e.target.value) })}
              className="w-full px-3 py-1.5 border border-slate-200 rounded font-mono-tabular"
            />
          </label>
          <label className="space-y-1">
            <span className="font-medium text-slate-700">Review Threshold</span>
            <input
              type="number"
              step="0.02"
              min="0.3"
              max="0.85"
              value={String(settingsMap.review_threshold ?? 0.58)}
              onChange={(e) => setSettingsMap({ ...settingsMap, review_threshold: Number(e.target.value) })}
              className="w-full px-3 py-1.5 border border-slate-200 rounded font-mono-tabular"
            />
          </label>
          <label className="space-y-1">
            <span className="font-medium text-slate-700">Branch Separation Guard (km)</span>
            <input
              type="number"
              step="0.5"
              min="0.5"
              max="25"
              value={String(settingsMap.max_branch_distance_km ?? 1.5)}
              onChange={(e) => setSettingsMap({ ...settingsMap, max_branch_distance_km: Number(e.target.value) })}
              className="w-full px-3 py-1.5 border border-slate-200 rounded font-mono-tabular"
            />
          </label>
        </div>

        <button
          type="button"
          onClick={() =>
            handleSaveSettings({
              auto_merge_threshold: Number(settingsMap.auto_merge_threshold ?? 0.88),
              review_threshold: Number(settingsMap.review_threshold ?? 0.58),
              max_branch_distance_km: Number(settingsMap.max_branch_distance_km ?? 1.5),
            })
          }
          className="px-4 py-2 bg-teal-700 text-white rounded-lg font-medium hover:bg-teal-800"
        >
          {t.common.save}
        </button>
      </div>

      {/* SQLite Backup & Integrity */}
      <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-4 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="font-semibold text-slate-900 flex items-center gap-2">
            <Database className="w-4 h-4 text-slate-600" />
            <span>SQLite Backups & Integrity</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleIntegrity}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50"
            >
              <Shield className="w-3.5 h-3.5" />
              <span>Run Integrity Check</span>
            </button>
            <button
              type="button"
              onClick={handleCreateBackup}
              className="px-3.5 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-800"
            >
              Create Backup Now
            </button>
          </div>
        </div>

        {integrity && (
          <div
            className={`px-3 py-2 rounded border ${
              integrity.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-rose-50 border-rose-200 text-rose-800'
            }`}
          >
            SQLite Integrity Check: {integrity.integrity_messages.join(', ')}
          </div>
        )}

        <table className="w-full text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-2 px-3 text-left font-medium">Backup File</th>
              <th className="py-2 px-3 text-right font-medium">Size</th>
              <th className="py-2 px-3 text-left font-medium">Created</th>
              <th className="py-2 px-3 text-right font-medium">{t.common.actions}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {backups.map((b) => (
              <tr key={b.filename} className="h-9">
                <td className="px-3 py-2 font-mono-tabular text-slate-800">{b.filename}</td>
                <td className="px-3 py-2 text-right font-mono-tabular text-slate-600">{(b.size_bytes / 1024).toFixed(1)} KB</td>
                <td className="px-3 py-2 font-mono-tabular text-slate-500">{b.created_at.slice(0, 19).replace('T', ' ')}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => handleRestoreBackup(b.filename)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 border border-slate-200 rounded hover:bg-slate-50"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Restore</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
