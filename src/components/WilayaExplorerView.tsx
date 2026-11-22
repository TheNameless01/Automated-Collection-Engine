import { useState } from 'react';
import type { Translations } from '../i18n/translations';
import type { WilayaSummary } from '../types';

interface WilayaExplorerViewProps {
  wilayas: WilayaSummary[];
  t: Translations;
  onSelectWilayaMap?: (wilayaCode: number) => void;
}

export function WilayaExplorerView({ wilayas, t, onSelectWilayaMap }: WilayaExplorerViewProps) {
  const [search, setSearch] = useState('');
  const [groupFilter, setGroupFilter] = useState<'all' | '1_58' | '59_69'>('all');

  const filtered = wilayas.filter((w) => {
    if (groupFilter === '1_58' && w.code > 58) return false;
    if (groupFilter === '59_69' && w.code < 59) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return w.name_fr.toLowerCase().includes(q) || w.name_ar.includes(q) || w.code_str.includes(q);
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t.nav.wilayas}</h1>
          <p className="text-xs text-slate-600 mt-0.5">
            Official 69-wilaya registry (Law 84-09, Law 19-12, Law 26-06). Raw discovery counts do not imply complete market coverage.
          </p>
        </div>
        <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg text-xs">
          <button
            type="button"
            onClick={() => setGroupFilter('all')}
            className={`px-3 py-1.5 rounded-md font-medium whitespace-nowrap ${groupFilter === 'all' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            All (69)
          </button>
          <button
            type="button"
            onClick={() => setGroupFilter('1_58')}
            className={`px-3 py-1.5 rounded-md font-medium whitespace-nowrap ${groupFilter === '1_58' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            01–58
          </button>
          <button
            type="button"
            onClick={() => setGroupFilter('59_69')}
            className={`px-3 py-1.5 rounded-md font-medium whitespace-nowrap ${groupFilter === '59_69' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            59–69 (New)
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t.common.search}
          className="w-full max-w-md px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-teal-600"
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
              <tr>
                <th className="py-2.5 px-3 text-left font-medium">Code</th>
                <th className="py-2.5 px-3 text-left font-medium">Wilaya (FR / AR)</th>
                <th className="py-2.5 px-3 text-right font-medium">Discovered</th>
                <th className="py-2.5 px-3 text-right font-medium">{t.statuses.VERIFIED}</th>
                <th className="py-2.5 px-3 text-right font-medium">{t.statuses.UNVERIFIED}</th>
                <th className="py-2.5 px-3 text-right font-medium">{t.statuses.NEEDS_REVIEW}</th>
                <th className="py-2.5 px-3 text-right font-medium">Communes</th>
                <th className="py-2.5 px-3 text-left font-medium">Sources Used</th>
                <th className="py-2.5 px-3 text-left font-medium">Collection Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((w) => (
                <tr
                  key={w.code}
                  onClick={() => onSelectWilayaMap?.(w.code)}
                  className="h-9 hover:bg-slate-50 cursor-pointer"
                >
                  <td className="px-3 py-2 font-mono-tabular font-medium text-slate-500">{w.code_str}</td>
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-900">{w.name_fr}</span>
                    <span className="text-slate-400 mx-1.5">·</span>
                    <span className="text-slate-600" dir="rtl">
                      {w.name_ar}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono-tabular font-semibold text-slate-900">
                    {w.discovered_count}
                  </td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-emerald-700">{w.verified_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-slate-600">{w.unverified_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-amber-700">{w.review_count}</td>
                  <td className="px-3 py-2 text-right font-mono-tabular text-slate-700">
                    {w.communes_covered} / {w.total_communes}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{w.sources_used.join(' · ') || '—'}</td>
                  <td className="px-3 py-2 font-mono-tabular text-slate-600">{w.collection_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
