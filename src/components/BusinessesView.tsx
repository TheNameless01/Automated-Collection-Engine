import { ExternalLink, Plus, ShieldCheck, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type {
  BusinessDetailResponse,
  BusinessRecord,
  CommuneItem,
  SourceItem,
  VerificationStatus,
  WilayaSummary,
} from '../types';
import { StatusLabel } from './StatusLabel';

interface BusinessesViewProps {
  wilayas: WilayaSummary[];
  sources: SourceItem[];
  t: Translations;
  initialInspectId?: number | null;
}

export function BusinessesView({ wilayas, sources, t, initialInspectId }: BusinessesViewProps) {
  const [items, setItems] = useState<BusinessRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [wilayaCode, setWilayaCode] = useState('');
  const [communeId, setCommuneId] = useState('');
  const [communes, setCommunes] = useState<CommuneItem[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [hasPhone, setHasPhone] = useState('');
  const [hasAddress, setHasAddress] = useState('');
  const [hasWebsite, setHasWebsite] = useState('');
  const [hasCoords, setHasCoords] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [sortBy, setSortBy] = useState('updated_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);

  const [detail, setDetail] = useState<BusinessDetailResponse | null>(null);
  const [editDraft, setEditDraft] = useState<Record<string, string>>({});
  const [editCommunes, setEditCommunes] = useState<CommuneItem[]>([]);
  const [saving, setSaving] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    primary_name: '',
    name_ar: '',
    primary_phone: '',
    full_address: '',
    wilaya_code: '',
    website: '',
    google_maps_url: '',
  });

  useEffect(() => {
    if (wilayaCode) {
      api.get<CommuneItem[]>(`/api/wilayas/${wilayaCode}/communes`).then(setCommunes).catch(() => setCommunes([]));
    } else {
      setCommunes([]);
      setCommuneId('');
    }
  }, [wilayaCode]);

  const fetchBusinesses = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: String(page),
      page_size: '25',
      sort_by: sortBy,
      sort_dir: sortDir,
    });
    if (search.trim()) params.set('search', search.trim());
    if (wilayaCode) params.set('wilaya_code', wilayaCode);
    if (communeId) params.set('commune_id', communeId);
    if (statusFilter) params.set('verification_status', statusFilter);
    if (sourceFilter) params.set('source_key', sourceFilter);
    if (hasPhone) params.set('has_phone', hasPhone);
    if (hasAddress) params.set('has_address', hasAddress);
    if (hasWebsite) params.set('has_website', hasWebsite);
    if (hasCoords) params.set('has_coords', hasCoords);
    if (dateFrom) params.set('date_from', dateFrom);

    try {
      const res = await api.get<{ items: BusinessRecord[]; total: number }>(`/api/businesses?${params.toString()}`);
      setItems(res.items);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, sortBy, sortDir, search, wilayaCode, communeId, statusFilter, sourceFilter, hasPhone, hasAddress, hasWebsite, hasCoords, dateFrom]);

  useEffect(() => {
    fetchBusinesses();
  }, [fetchBusinesses]);

  const openDetail = useCallback(async (id: number) => {
    const res = await api.get<BusinessDetailResponse>(`/api/businesses/${id}`);
    setDetail(res);
    const b = res.business;
    setEditDraft({
      primary_name: b.primary_name || '',
      name_ar: b.name_ar || '',
      name_fr: b.name_fr || '',
      name_en: b.name_en || '',
      primary_phone: b.primary_phone || b.primary_phone_raw || '',
      full_address: b.full_address || '',
      wilaya_code: b.wilaya_code ? String(b.wilaya_code) : '',
      commune_id: b.commune_id ? String(b.commune_id) : '',
      lat: b.lat !== null ? String(b.lat) : '',
      lon: b.lon !== null ? String(b.lon) : '',
      website: b.website || '',
      facebook_url: b.facebook_url || '',
      instagram_url: b.instagram_url || '',
      google_maps_url: b.google_maps_url || '',
      verification_status: b.verification_status,
      notes: b.notes || '',
      review_notes: '',
    });
    if (b.wilaya_code) {
      api.get<CommuneItem[]>(`/api/wilayas/${b.wilaya_code}/communes`).then(setEditCommunes).catch(() => setEditCommunes([]));
    } else {
      setEditCommunes([]);
    }
  }, []);

  useEffect(() => {
    if (initialInspectId) {
      openDetail(initialInspectId);
    }
  }, [initialInspectId, openDetail]);

  const handleSaveEdit = async () => {
    if (!detail) return;
    setSaving(true);
    try {
      await api.patch(`/api/businesses/${detail.business.id}`, {
        primary_name: editDraft.primary_name,
        name_ar: editDraft.name_ar,
        name_fr: editDraft.name_fr,
        name_en: editDraft.name_en,
        primary_phone: editDraft.primary_phone,
        full_address: editDraft.full_address,
        wilaya_code: editDraft.wilaya_code ? Number(editDraft.wilaya_code) : null,
        commune_id: editDraft.commune_id ? Number(editDraft.commune_id) : null,
        lat: editDraft.lat ? Number(editDraft.lat) : null,
        lon: editDraft.lon ? Number(editDraft.lon) : null,
        website: editDraft.website,
        facebook_url: editDraft.facebook_url,
        instagram_url: editDraft.instagram_url,
        google_maps_url: editDraft.google_maps_url,
        verification_status: editDraft.verification_status as VerificationStatus,
        notes: editDraft.notes,
        review_notes: editDraft.review_notes,
      });
      await openDetail(detail.business.id);
      await fetchBusinesses();
    } finally {
      setSaving(false);
    }
  };

  const handleVerifyNow = async (checkOnline: boolean) => {
    if (!detail) return;
    await api.post(`/api/businesses/${detail.business.id}/verify?check_urls_online=${checkOnline}`);
    await openDetail(detail.business.id);
    await fetchBusinesses();
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post('/api/businesses', {
      ...createForm,
      wilaya_code: createForm.wilaya_code ? Number(createForm.wilaya_code) : null,
    });
    setShowCreateModal(false);
    setCreateForm({ primary_name: '', name_ar: '', primary_phone: '', full_address: '', wilaya_code: '', website: '', google_maps_url: '' });
    fetchBusinesses();
  };

  const totalPages = Math.max(1, Math.ceil(total / 25));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t.nav.businesses}</h1>
          <p className="text-xs text-slate-500 font-mono-tabular mt-0.5">{total} unique agencies</p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 whitespace-nowrap shrink-0"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Add Agency</span>
        </button>
      </div>

      {/* Filters bar */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 text-xs">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder={t.common.search}
          className="col-span-2 px-3 py-1.5 border border-slate-200 rounded-lg focus:outline-none focus:border-teal-600"
        />
        <select
          value={wilayaCode}
          onChange={(e) => {
            setWilayaCode(e.target.value);
            setPage(1);
          }}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
        >
          <option value="">{t.common.wilaya}: {t.common.all}</option>
          {wilayas.map((w) => (
            <option key={w.code} value={w.code}>
              {w.code_str} · {w.name_fr}
            </option>
          ))}
        </select>
        <select
          value={communeId}
          onChange={(e) => {
            setCommuneId(e.target.value);
            setPage(1);
          }}
          disabled={!wilayaCode}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white disabled:opacity-50"
        >
          <option value="">{t.common.commune}: {t.common.all}</option>
          {communes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_fr}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
        >
          <option value="">{t.common.status}: {t.common.all}</option>
          <option value="VERIFIED">{t.statuses.VERIFIED}</option>
          <option value="UNVERIFIED">{t.statuses.UNVERIFIED}</option>
          <option value="NEEDS_REVIEW">{t.statuses.NEEDS_REVIEW}</option>
          <option value="CLOSED">{t.statuses.CLOSED}</option>
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => {
            setSourceFilter(e.target.value);
            setPage(1);
          }}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
        >
          <option value="">{t.common.source}: {t.common.all}</option>
          {sources.map((s) => (
            <option key={s.key} value={s.key}>
              {s.name}
            </option>
          ))}
        </select>

        <select value={hasPhone} onChange={(e) => { setHasPhone(e.target.value); setPage(1); }} className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white">
          <option value="">Phone: Any</option>
          <option value="true">Has phone</option>
          <option value="false">Missing phone</option>
        </select>
        <select value={hasAddress} onChange={(e) => { setHasAddress(e.target.value); setPage(1); }} className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white">
          <option value="">Address: Any</option>
          <option value="true">Has address</option>
          <option value="false">Missing address</option>
        </select>
        <select value={hasWebsite} onChange={(e) => { setHasWebsite(e.target.value); setPage(1); }} className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white">
          <option value="">Website: Any</option>
          <option value="true">Has website</option>
          <option value="false">Missing website</option>
        </select>
        <select value={hasCoords} onChange={(e) => { setHasCoords(e.target.value); setPage(1); }} className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white">
          <option value="">GPS: Any</option>
          <option value="true">Has GPS</option>
          <option value="false">Missing GPS</option>
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
        />
        <select
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [sb, sd] = e.target.value.split(':');
            setSortBy(sb);
            setSortDir(sd as 'asc' | 'desc');
          }}
          className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
        >
          <option value="updated_at:desc">Sort: Recently updated</option>
          <option value="primary_name:asc">Sort: Name (A–Z)</option>
          <option value="wilaya_code:asc">Sort: Wilaya (01–69)</option>
          <option value="confidence_score:desc">Sort: Highest confidence</option>
        </select>
      </div>

      {/* Data Table */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
              <tr>
                <th className="py-2.5 px-3 text-left font-medium">ID</th>
                <th className="py-2.5 px-3 text-left font-medium">Agency</th>
                <th className="py-2.5 px-3 text-left font-medium">Phone</th>
                <th className="py-2.5 px-3 text-left font-medium">{t.common.wilaya}</th>
                <th className="py-2.5 px-3 text-left font-medium">{t.common.commune}</th>
                <th className="py-2.5 px-3 text-left font-medium">{t.common.status}</th>
                <th className="py-2.5 px-3 text-right font-medium">{t.common.confidence}</th>
                <th className="py-2.5 px-3 text-left font-medium">{t.common.source}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    {t.common.loading}
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-500">
                    {t.common.noData}
                  </td>
                </tr>
              ) : (
                items.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => openDetail(b.id)}
                    className="h-10 hover:bg-slate-50 cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-2 font-mono-tabular text-slate-400">{b.id}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-slate-900">{b.primary_name}</div>
                      {b.name_ar && b.name_ar !== b.primary_name && (
                        <div className="text-[11px] text-slate-500" dir="rtl">
                          {b.name_ar}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono-tabular text-slate-700">{b.primary_phone || '—'}</td>
                    <td className="px-3 py-2 text-slate-700">
                      {b.wilaya_code ? (
                        <span>
                          <span className="font-mono-tabular text-slate-400 mr-1">{String(b.wilaya_code).padStart(2, '0')}</span>
                          {b.wilaya_name}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{b.commune_name || '—'}</td>
                    <td className="px-3 py-2">
                      <StatusLabel status={b.verification_status} label={t.statuses[b.verification_status]} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono-tabular text-slate-700">
                      {Math.round((b.confidence_score || 0) * 100)}%
                    </td>
                    <td className="px-3 py-2 text-slate-500 font-mono-tabular">{(b.source_keys || []).join(' · ')}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 text-xs text-slate-600">
          <span className="font-mono-tabular">
            Page {page} / {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1 border border-slate-200 rounded disabled:opacity-40 hover:bg-slate-50"
            >
              Prev
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1 border border-slate-200 rounded disabled:opacity-40 hover:bg-slate-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Record Inspection & Edit Drawer */}
      {detail && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 flex justify-end">
          <div className="w-full max-w-2xl bg-white h-full overflow-y-auto border-s border-slate-200 p-6 space-y-6">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
              <div>
                <div className="text-xs text-slate-400 font-mono-tabular">Agency #{detail.business.id}</div>
                <h2 className="text-lg font-semibold text-slate-900">{detail.business.primary_name}</h2>
                <div className="mt-1 flex items-center gap-3 text-xs text-slate-600">
                  <StatusLabel status={detail.business.verification_status} label={t.statuses[detail.business.verification_status]} />
                  <span>·</span>
                  <span className="font-mono-tabular">Confidence {Math.round(detail.business.confidence_score * 100)}%</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDetail(null)}
                className="p-1.5 text-slate-500 hover:text-slate-900 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Quick Verification & Manual Google Maps Check */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => handleVerifyNow(false)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-teal-800 bg-teal-50 border border-teal-200 rounded-lg hover:bg-teal-100"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Re-evaluate Verification</span>
              </button>
              <a
                href={
                  detail.business.google_maps_url ||
                  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                    `${detail.business.primary_name} ${detail.business.wilaya_name || 'Algeria'}`,
                  )}`
                }
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-50"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Manual Google Maps Verify</span>
              </a>
            </div>

            {detail.business.verification_notes && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-slate-700">
                {detail.business.verification_notes}
              </div>
            )}

            {/* Edit Form */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Primary Name</span>
                <input
                  value={editDraft.primary_name || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, primary_name: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Arabic Name</span>
                <input
                  dir="rtl"
                  value={editDraft.name_ar || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, name_ar: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Primary Phone</span>
                <input
                  value={editDraft.primary_phone || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, primary_phone: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono-tabular"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Status</span>
                <select
                  value={editDraft.verification_status || 'UNVERIFIED'}
                  onChange={(e) => setEditDraft({ ...editDraft, verification_status: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded bg-white"
                >
                  <option value="VERIFIED">{t.statuses.VERIFIED}</option>
                  <option value="UNVERIFIED">{t.statuses.UNVERIFIED}</option>
                  <option value="NEEDS_REVIEW">{t.statuses.NEEDS_REVIEW}</option>
                  <option value="CLOSED">{t.statuses.CLOSED}</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">{t.common.wilaya}</span>
                <select
                  value={editDraft.wilaya_code || ''}
                  onChange={(e) => {
                    const wc = e.target.value;
                    setEditDraft({ ...editDraft, wilaya_code: wc, commune_id: '' });
                    if (wc) {
                      api.get<CommuneItem[]>(`/api/wilayas/${wc}/communes`).then(setEditCommunes);
                    }
                  }}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded bg-white"
                >
                  <option value="">Unassigned</option>
                  {wilayas.map((w) => (
                    <option key={w.code} value={w.code}>
                      {w.code_str} · {w.name_fr}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">{t.common.commune}</span>
                <select
                  value={editDraft.commune_id || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, commune_id: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded bg-white"
                >
                  <option value="">Unassigned</option>
                  {editCommunes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name_fr}
                    </option>
                  ))}
                </select>
              </label>
              <label className="sm:col-span-2 space-y-1">
                <span className="text-slate-600 font-medium">Full Address</span>
                <input
                  value={editDraft.full_address || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, full_address: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Latitude</span>
                <input
                  value={editDraft.lat || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, lat: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono-tabular"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Longitude</span>
                <input
                  value={editDraft.lon || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, lon: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono-tabular"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Website</span>
                <input
                  value={editDraft.website || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, website: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
              <label className="space-y-1">
                <span className="text-slate-600 font-medium">Google Maps URL</span>
                <input
                  value={editDraft.google_maps_url || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, google_maps_url: e.target.value })}
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
              <label className="sm:col-span-2 space-y-1">
                <span className="text-slate-600 font-medium">Audit Note for this Edit</span>
                <input
                  value={editDraft.review_notes || ''}
                  onChange={(e) => setEditDraft({ ...editDraft, review_notes: e.target.value })}
                  placeholder="Optional reason recorded in audit history"
                  className="w-full px-2.5 py-1.5 border border-slate-200 rounded"
                />
              </label>
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={saving}
                className="px-4 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 disabled:opacity-50"
              >
                {saving ? t.common.loading : t.common.save}
              </button>
            </div>

            {/* Source Provenance */}
            <div className="border-t border-slate-200 pt-4 space-y-2">
              <h3 className="text-xs font-semibold text-slate-900">Source Provenance ({detail.source_records.length})</h3>
              <div className="space-y-2">
                {detail.source_records.map((sr) => (
                  <div key={sr.id} className="p-3 bg-slate-50 border border-slate-200 rounded text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-800">{sr.source_name}</span>
                      <span className="font-mono-tabular text-slate-500">{sr.collected_at.slice(0, 10)}</span>
                    </div>
                    <div className="text-slate-600">{sr.raw_name} · {sr.raw_address || 'No address'}</div>
                    {sr.source_url && (
                      <a href={sr.source_url} target="_blank" rel="noreferrer" className="text-teal-700 hover:underline break-all block">
                        {sr.source_url}
                      </a>
                    )}
                    <div className="text-[11px] text-slate-500">{sr.attribution_text}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Audit History */}
            <div className="border-t border-slate-200 pt-4 space-y-2">
              <h3 className="text-xs font-semibold text-slate-900">Audit History ({detail.audit_logs.length})</h3>
              <div className="space-y-1.5 text-xs">
                {detail.audit_logs.map((al) => (
                  <div key={al.id} className="flex items-center justify-between text-slate-600 border-b border-slate-100 pb-1">
                    <span>
                      <span className="font-medium text-slate-800">{al.action}</span> by {al.actor}
                    </span>
                    <span className="font-mono-tabular text-slate-400">{al.created_at.slice(0, 19).replace('T', ' ')}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Manual Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 flex items-center justify-center p-4">
          <form onSubmit={handleCreate} className="bg-white border border-slate-200 rounded-lg max-w-lg w-full p-5 space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">Add Agency Manually</h2>
              <button type="button" onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                required
                placeholder="Business Name *"
                value={createForm.primary_name}
                onChange={(e) => setCreateForm({ ...createForm, primary_name: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded"
              />
              <input
                dir="rtl"
                placeholder="الاسم بالعربية"
                value={createForm.name_ar}
                onChange={(e) => setCreateForm({ ...createForm, name_ar: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded"
              />
              <input
                placeholder="Phone (+213 / 0...)"
                value={createForm.primary_phone}
                onChange={(e) => setCreateForm({ ...createForm, primary_phone: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded"
              />
              <select
                value={createForm.wilaya_code}
                onChange={(e) => setCreateForm({ ...createForm, wilaya_code: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded bg-white"
              >
                <option value="">Select Wilaya</option>
                {wilayas.map((w) => (
                  <option key={w.code} value={w.code}>
                    {w.code_str} · {w.name_fr}
                  </option>
                ))}
              </select>
              <input
                placeholder="Full Address"
                value={createForm.full_address}
                onChange={(e) => setCreateForm({ ...createForm, full_address: e.target.value })}
                className="sm:col-span-2 px-3 py-2 border border-slate-200 rounded"
              />
              <input
                placeholder="Website URL"
                value={createForm.website}
                onChange={(e) => setCreateForm({ ...createForm, website: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded"
              />
              <input
                placeholder="Google Maps URL (manual)"
                value={createForm.google_maps_url}
                onChange={(e) => setCreateForm({ ...createForm, google_maps_url: e.target.value })}
                className="px-3 py-2 border border-slate-200 rounded"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreateModal(false)} className="px-3 py-2 border border-slate-200 rounded">
                {t.common.cancel}
              </button>
              <button type="submit" className="px-4 py-2 bg-teal-700 text-white rounded font-medium hover:bg-teal-800">
                {t.common.save}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
