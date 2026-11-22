import { Download, FileSpreadsheet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type { ExportFileItem, WilayaSummary } from '../types';

interface ExportViewProps {
  wilayas: WilayaSummary[];
  t: Translations;
}

export function ExportView({ wilayas, t }: ExportViewProps) {
  const [format, setFormat] = useState<'xlsx' | 'csv'>('xlsx');
  const [scope, setScope] = useState<'all' | 'selected_wilayas' | 'verified_only' | 'review_required'>('all');
  const [selectedWilayas, setSelectedWilayas] = useState<number[]>([]);
  const [exportsList, setExportsList] = useState<ExportFileItem[]>([]);
  const [generating, setGenerating] = useState(false);
  const [latestFile, setLatestFile] = useState<ExportFileItem | null>(null);

  const loadExports = async () => {
    const items = await api.get<ExportFileItem[]>('/api/exports');
    setExportsList(items);
  };

  useEffect(() => {
    loadExports();
  }, []);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const created = await api.post<ExportFileItem>('/api/exports', {
        format,
        scope,
        wilaya_codes: scope === 'selected_wilayas' ? selectedWilayas : [],
      });
      setLatestFile(created);
      await loadExports();
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t.nav.exports}</h1>
        <p className="text-xs text-slate-600 mt-0.5">
          Export unique businesses to Excel (.xlsx with MASTER, STATISTICS, SOURCES, REVIEW_REQUIRED + 69 wilaya sheets) or UTF-8 BOM CSV.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
          <div className="space-y-2">
            <div className="font-semibold text-slate-900">Format</div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setFormat('xlsx')}
                className={`flex-1 py-2.5 px-3 border rounded-lg font-medium ${
                  format === 'xlsx' ? 'bg-teal-50 border-teal-600 text-teal-900' : 'border-slate-200 text-slate-700'
                }`}
              >
                Excel Workbook (.xlsx · 73 sheets)
              </button>
              <button
                type="button"
                onClick={() => setFormat('csv')}
                className={`flex-1 py-2.5 px-3 border rounded-lg font-medium ${
                  format === 'csv' ? 'bg-teal-50 border-teal-600 text-teal-900' : 'border-slate-200 text-slate-700'
                }`}
              >
                CSV (UTF-8 with BOM)
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="font-semibold text-slate-900">Export Scope</div>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as typeof scope)}
              className="w-full px-3 py-2.5 border border-slate-200 rounded-lg bg-white"
            >
              <option value="all">Export Everything (All Unique Businesses)</option>
              <option value="verified_only">Verified Businesses Only</option>
              <option value="review_required">Records Requiring Review</option>
              <option value="selected_wilayas">Selected Wilayas</option>
            </select>
          </div>
        </div>

        {scope === 'selected_wilayas' && (
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-1.5 max-h-48 overflow-y-auto border border-slate-200 rounded-lg p-3 text-xs">
            {wilayas.map((w) => {
              const checked = selectedWilayas.includes(w.code);
              return (
                <button
                  key={w.code}
                  type="button"
                  onClick={() =>
                    setSelectedWilayas((prev) =>
                      prev.includes(w.code) ? prev.filter((c) => c !== w.code) : [...prev, w.code],
                    )
                  }
                  className={`px-2 py-1 rounded text-left truncate border ${
                    checked ? 'bg-teal-50 border-teal-600 text-teal-900' : 'border-slate-200 text-slate-700'
                  }`}
                >
                  {w.code_str} {w.name_fr}
                </button>
              );
            })}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-100">
          <div className="text-xs text-slate-500">
            Saved locally to <span className="font-mono-tabular text-slate-700">exports/</span>
          </div>
          <button
            type="button"
            disabled={generating || (scope === 'selected_wilayas' && selectedWilayas.length === 0)}
            onClick={handleGenerate}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 disabled:opacity-50"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>{generating ? t.common.loading : 'Generate Export'}</span>
          </button>
        </div>

        {latestFile && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 flex items-center justify-between text-xs">
            <span className="text-emerald-900 font-medium">Generated: {latestFile.filename}</span>
            <a
              href={latestFile.download_url}
              download={latestFile.filename}
              className="inline-flex items-center gap-1.5 font-medium text-emerald-800 hover:underline"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{t.common.download}</span>
            </a>
          </div>
        )}
      </div>

      {/* Previously generated exports */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-200 text-xs font-semibold text-slate-900">
          Generated Files ({exportsList.length})
        </div>
        <table className="w-full text-xs">
          <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
            <tr>
              <th className="py-2 px-3 text-left font-medium">Filename</th>
              <th className="py-2 px-3 text-left font-medium">Format</th>
              <th className="py-2 px-3 text-right font-medium">Size</th>
              <th className="py-2 px-3 text-left font-medium">Created</th>
              <th className="py-2 px-3 text-right font-medium">{t.common.download}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {exportsList.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-slate-500">
                  No export files generated yet.
                </td>
              </tr>
            ) : (
              exportsList.map((f) => (
                <tr key={f.filename} className="h-9">
                  <td className="px-3 py-2 font-mono-tabular text-slate-800">{f.filename}</td>
                  <td className="px-3 py-2 uppercase font-mono-tabular text-slate-600">{f.format}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-slate-600">
                    {(f.size_bytes / 1024).toFixed(1)} KB
                  </td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-500">{f.created_at.slice(0, 19).replace('T', ' ')}</td>
                  <td className="px-3 py-2 text-right">
                    <a
                      href={f.download_url}
                      download={f.filename}
                      className="inline-flex items-center gap-1 text-teal-700 hover:underline font-medium"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>{t.common.download}</span>
                    </a>
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
