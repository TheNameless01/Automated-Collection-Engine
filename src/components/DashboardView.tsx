import { Play, RefreshCw } from 'lucide-react';
import type { Translations } from '../i18n/translations';
import type { DashboardSummary, NavSection } from '../types';

interface DashboardViewProps {
  summary: DashboardSummary | null;
  loading: boolean;
  t: Translations;
  onRefresh: () => void;
  onNavigate: (section: NavSection) => void;
}

export function DashboardView({ summary, loading, t, onRefresh, onNavigate }: DashboardViewProps) {
  if (loading && !summary) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, idx) => (
            <div key={idx} className="h-24 bg-white border border-slate-200 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const s = summary;
  const maxWilayaCount = Math.max(1, ...(s?.by_wilaya.map((w) => w.total_count) || [1]));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t.dashboard.title}</h1>
          <p className="text-sm text-slate-600 mt-0.5">{t.dashboard.subtitle}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={onRefresh}
            className="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors whitespace-nowrap shrink-0"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>{t.common.refresh}</span>
          </button>
          <button
            type="button"
            onClick={() => onNavigate('collect')}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 transition-colors whitespace-nowrap shrink-0"
          >
            <Play className="w-3.5 h-3.5" />
            <span>{t.dashboard.startCollectionCta}</span>
          </button>
        </div>
      </div>

      {s && s.total_businesses === 0 && (
        <div className="bg-white border border-slate-200 rounded-lg p-5 flex flex-wrap items-center justify-between gap-4">
          <p className="text-sm text-slate-700 max-w-3xl">{t.dashboard.emptyNotice}</p>
          <button
            type="button"
            onClick={() => onNavigate('collect')}
            className="px-4 py-2 text-xs font-medium text-teal-800 bg-teal-50 border border-teal-200 rounded-lg hover:bg-teal-100 whitespace-nowrap shrink-0"
          >
            {t.dashboard.startCollectionCta}
          </button>
        </div>
      )}

      {/* Primary KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.totalBusinesses}</div>
          <div className="text-2xl font-semibold text-slate-900 mt-1 font-mono-tabular">
            {s?.total_businesses ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.verified}</div>
          <div className="text-2xl font-semibold text-emerald-700 mt-1 font-mono-tabular">
            {s?.verified_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.unverified}</div>
          <div className="text-2xl font-semibold text-slate-700 mt-1 font-mono-tabular">
            {s?.unverified_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.needsReview}</div>
          <div className="text-2xl font-semibold text-amber-700 mt-1 font-mono-tabular">
            {s?.review_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.suspectedDuplicates}</div>
          <div className="text-2xl font-semibold text-amber-700 mt-1 font-mono-tabular">
            {s?.suspected_duplicates_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.closed}</div>
          <div className="text-2xl font-semibold text-rose-700 mt-1 font-mono-tabular">
            {s?.closed_count ?? 0}
          </div>
        </div>
      </div>

      {/* Data Quality & Run Summary Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.collectionRuns}</div>
          <div className="text-lg font-semibold text-slate-900 mt-1 font-mono-tabular">
            {s?.collection_runs_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.lastCollection}</div>
          <div className="text-sm font-medium text-slate-800 mt-1.5 font-mono-tabular truncate">
            {s?.last_collection_run?.started_at ? s.last_collection_run.started_at.slice(0, 16).replace('T', ' ') : '—'}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.missingPhone}</div>
          <div className="text-lg font-semibold text-slate-800 mt-1 font-mono-tabular">
            {s?.missing_phone_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.missingAddress}</div>
          <div className="text-lg font-semibold text-slate-800 mt-1 font-mono-tabular">
            {s?.missing_address_count ?? 0}
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="text-xs text-slate-500">{t.dashboard.missingCoords}</div>
          <div className="text-lg font-semibold text-slate-800 mt-1 font-mono-tabular">
            {s?.missing_coords_count ?? 0}
          </div>
        </div>
      </div>

      {/* Two-column Analytics: Wilaya Breakdown & Source Coverage */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <div className="bg-white border border-slate-200 rounded-lg p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-900">{t.dashboard.byWilayaTitle}</h2>
            <button
              type="button"
              onClick={() => onNavigate('wilayas')}
              className="text-xs font-medium text-teal-700 hover:text-teal-800 whitespace-nowrap shrink-0"
            >
              69 Wilayas →
            </button>
          </div>
          <div className="space-y-2.5 flex-1">
            {(s?.by_wilaya || []).slice(0, 12).map((w) => (
              <div key={w.code} className="grid grid-cols-12 items-center gap-3 text-xs">
                <div className="col-span-5 truncate text-slate-700">
                  <span className="font-mono-tabular text-slate-400 mr-1.5">{w.code_str}</span>
                  <span>{w.name_fr}</span>
                </div>
                <div className="col-span-5 bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-teal-700 h-full rounded-full"
                    style={{ width: `${Math.round((w.total_count / maxWilayaCount) * 100)}%` }}
                  />
                </div>
                <div className="col-span-2 text-right font-mono-tabular text-slate-700">{w.total_count}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-lg p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-900">{t.dashboard.sourceCoverageTitle}</h2>
            <button
              type="button"
              onClick={() => onNavigate('sources')}
              className="text-xs font-medium text-teal-700 hover:text-teal-800 whitespace-nowrap shrink-0"
            >
              {t.nav.sources} →
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-2 text-left font-medium">{t.common.source}</th>
                  <th className="py-2 text-left font-medium">{t.common.status}</th>
                  <th className="py-2 text-right font-medium">Agencies</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(s?.source_coverage || []).map((src) => (
                  <tr key={src.key} className="h-9">
                    <td className="py-2 font-medium text-slate-800">{src.name}</td>
                    <td className="py-2 text-slate-600">{src.enabled ? src.last_status : 'disabled'}</td>
                    <td className="py-2 text-right font-mono-tabular text-slate-800">{src.business_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
