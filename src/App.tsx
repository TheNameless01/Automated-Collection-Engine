import {
  Building2,
  ClipboardCheck,
  Compass,
  Database,
  FileSpreadsheet,
  GitMerge,
  History,
  LayoutDashboard,
  Map as MapIcon,
  Play,
  ScrollText,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import { BusinessesView } from './components/BusinessesView';
import { CollectView } from './components/CollectView';
import { DashboardView } from './components/DashboardView';
import { DuplicatesAndReviewView } from './components/DuplicatesAndReviewView';
import { ExportView } from './components/ExportView';
import { MapView } from './components/MapView';
import { HistoryView, LogsView, SettingsView, SourcesView } from './components/SourcesHistoryLogsSettings';
import { WilayaExplorerView } from './components/WilayaExplorerView';
import { TRANSLATIONS } from './i18n/translations';
import type { AppLang, DashboardSummary, NavSection, SourceItem, WilayaSummary } from './types';

const NAV_ITEMS: Array<{ id: NavSection; icon: typeof LayoutDashboard }> = [
  { id: 'dashboard', icon: LayoutDashboard },
  { id: 'collect', icon: Play },
  { id: 'businesses', icon: Building2 },
  { id: 'wilayas', icon: Compass },
  { id: 'map', icon: MapIcon },
  { id: 'duplicates', icon: GitMerge },
  { id: 'verification', icon: ShieldCheck },
  { id: 'review', icon: ClipboardCheck },
  { id: 'exports', icon: FileSpreadsheet },
  { id: 'sources', icon: Database },
  { id: 'history', icon: History },
  { id: 'logs', icon: ScrollText },
  { id: 'settings', icon: Settings },
];

export default function App() {
  const [section, setSection] = useState<NavSection>('dashboard');
  const [lang, setLang] = useState<AppLang>('fr');
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [wilayas, setWilayas] = useState<WilayaSummary[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [inspectBusinessId, setInspectBusinessId] = useState<number | null>(null);
  const [mapInitialWilaya, setMapInitialWilaya] = useState<number | null>(null);

  const t = TRANSLATIONS[lang];

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  }, [lang]);

  const refreshCore = useCallback(async () => {
    try {
      const [sum, wil, src, appSettings] = await Promise.all([
        api.get<DashboardSummary>('/api/dashboard/summary'),
        api.get<WilayaSummary[]>('/api/wilayas'),
        api.get<SourceItem[]>('/api/sources'),
        api.get<Record<string, unknown>>('/api/settings'),
      ]);
      setSummary(sum);
      setWilayas(wil);
      setSources(src);
      const savedLang = appSettings.language;
      if (savedLang === 'fr' || savedLang === 'ar' || savedLang === 'en') {
        setLang(savedLang);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshCore();
  }, [refreshCore]);

  const handleInspectBusiness = (id: number) => {
    setInspectBusinessId(id);
    setSection('businesses');
  };

  const handleSelectWilayaMap = (wilayaCode: number) => {
    setMapInitialWilaya(wilayaCode);
    setSection('map');
  };

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900">
      {/* Left Navigation Sidebar */}
      <aside className="w-60 shrink-0 bg-white border-e border-slate-200 flex flex-col">
        <div className="h-14 px-5 flex items-center border-b border-slate-200">
          <span className="text-sm font-bold tracking-tight text-slate-900 whitespace-nowrap truncate">
            {t.appName}
          </span>
        </div>

        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ id, icon: Icon }) => {
            const active = section === id;
            const badgeCount =
              id === 'duplicates'
                ? summary?.suspected_duplicates_count
                : id === 'review'
                  ? summary?.review_count
                  : undefined;

            return (
              <button
                key={id}
                type="button"
                onClick={() => {
                  if (id !== 'businesses') setInspectBusinessId(null);
                  setSection(id);
                }}
                className={`w-full flex items-center justify-between gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors whitespace-nowrap ${
                  active
                    ? 'bg-teal-50 text-teal-900'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <span className="flex items-center gap-2.5 min-w-0">
                  <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-teal-700' : 'text-slate-400'}`} />
                  <span className="truncate">{t.nav[id]}</span>
                </span>
                {badgeCount !== undefined && badgeCount > 0 && (
                  <span className="font-mono-tabular text-[11px] text-amber-700 shrink-0">{badgeCount}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="p-3 border-t border-slate-200 text-[11px] text-slate-500 flex items-center justify-between">
          <span className="font-mono-tabular">69 Wilayas</span>
          <span className="font-mono-tabular">SQLite Local</span>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 bg-white border-b border-slate-200 px-6 flex items-center justify-between gap-8 shrink-0">
          <div className="text-xs font-medium text-slate-600 whitespace-nowrap truncate">
            {t.appName} <span className="mx-1.5 text-slate-300">/</span>{' '}
            <span className="text-slate-900">{t.nav[section]}</span>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <div className="flex items-center gap-1 p-0.5 bg-slate-100 rounded-md text-[11px]">
              {(['fr', 'ar', 'en'] as const).map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => {
                    setLang(l);
                    api.patch('/api/settings', { settings: { language: l } }).catch(() => {});
                  }}
                  className={`px-2 py-1 rounded font-medium uppercase whitespace-nowrap ${
                    lang === l ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {l}
                </button>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setSection('exports')}
              className="px-3.5 py-1.5 text-xs font-medium text-white bg-slate-900 rounded-lg hover:bg-slate-800 whitespace-nowrap shrink-0"
            >
              {t.nav.exports}
            </button>
          </div>
        </header>

        <main className="flex-1 p-6 max-w-[1400px] w-full mx-auto">
          {section === 'dashboard' && (
            <DashboardView
              summary={summary}
              loading={loading}
              t={t}
              onRefresh={refreshCore}
              onNavigate={setSection}
            />
          )}
          {section === 'collect' && (
            <CollectView
              wilayas={wilayas}
              sources={sources}
              activeRunId={summary?.active_run_id ?? null}
              t={t}
              onRunChange={refreshCore}
            />
          )}
          {section === 'businesses' && (
            <BusinessesView
              wilayas={wilayas}
              sources={sources}
              t={t}
              initialInspectId={inspectBusinessId}
            />
          )}
          {section === 'wilayas' && (
            <WilayaExplorerView
              wilayas={wilayas}
              t={t}
              onSelectWilayaMap={handleSelectWilayaMap}
            />
          )}
          {section === 'map' && (
            <MapView
              wilayas={wilayas}
              sources={sources}
              t={t}
              initialWilayaCode={mapInitialWilaya}
              onInspectBusiness={handleInspectBusiness}
            />
          )}
          {(section === 'duplicates' || section === 'verification' || section === 'review') && (
            <DuplicatesAndReviewView
              mode={section}
              wilayas={wilayas}
              t={t}
              onInspectBusiness={handleInspectBusiness}
              onDataChanged={refreshCore}
            />
          )}
          {section === 'exports' && <ExportView wilayas={wilayas} t={t} />}
          {section === 'sources' && <SourcesView sources={sources} t={t} onRefresh={refreshCore} />}
          {section === 'history' && <HistoryView t={t} onResumed={refreshCore} />}
          {section === 'logs' && <LogsView t={t} />}
          {section === 'settings' && <SettingsView lang={lang} onLangChange={setLang} t={t} />}
        </main>
      </div>
    </div>
  );
}
