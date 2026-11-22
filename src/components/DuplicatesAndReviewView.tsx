import { GitMerge, RotateCcw, Search, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type { BusinessRecord, DuplicateCandidate, MergeHistoryItem, WilayaSummary } from '../types';
import { StatusLabel } from './StatusLabel';

interface DuplicatesViewProps {
  mode: 'duplicates' | 'verification' | 'review';
  wilayas: WilayaSummary[];
  t: Translations;
  onInspectBusiness: (id: number) => void;
  onDataChanged: () => void;
}

export function DuplicatesAndReviewView({
  mode,
  wilayas,
  t,
  onInspectBusiness,
  onDataChanged,
}: DuplicatesViewProps) {
  const [candidates, setCandidates] = useState<DuplicateCandidate[]>([]);
  const [mergeHistory, setMergeHistory] = useState<MergeHistoryItem[]>([]);
  const [reviewRecords, setReviewRecords] = useState<BusinessRecord[]>([]);
  const [dupTab, setDupTab] = useState<'pending' | 'history'>('pending');
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState('');

  const loadData = useCallback(async () => {
    const [cands, hist, rev] = await Promise.all([
      api.get<DuplicateCandidate[]>('/api/duplicates/candidates?status=pending'),
      api.get<MergeHistoryItem[]>('/api/merges/history'),
      api.get<{ items: BusinessRecord[] }>(
        mode === 'verification'
          ? '/api/businesses?page_size=100'
          : '/api/businesses?needs_review_only=true&page_size=100',
      ),
    ]);
    setCandidates(cands);
    setMergeHistory(hist);
    setReviewRecords(rev.items);
  }, [mode]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleResolveCandidate = async (
    id: number,
    decision: 'merge_into_a' | 'merge_into_b' | 'reject_separate',
  ) => {
    setBusy(true);
    try {
      await api.post(`/api/duplicates/candidates/${id}/resolve`, { decision, notes: 'Manual panel resolution' });
      await loadData();
      onDataChanged();
    } finally {
      setBusy(false);
    }
  };

  const handleRevertMerge = async (mergeId: number) => {
    setBusy(true);
    try {
      await api.post(`/api/merges/${mergeId}/revert`);
      setBanner(`Merge #${mergeId} reverted successfully.`);
      await loadData();
      onDataChanged();
    } finally {
      setBusy(false);
    }
  };

  const handleScanDuplicates = async () => {
    setBusy(true);
    try {
      const res = await api.post<{ new_candidates_created: number }>('/api/duplicates/scan');
      setBanner(`Duplicate scan completed: ${res.new_candidates_created} new candidate pair(s) surfaced.`);
      await loadData();
    } finally {
      setBusy(false);
    }
  };

  const handleBatchVerify = async (checkOnline: boolean) => {
    setBusy(true);
    try {
      const res = await api.post<{ processed: number; status_breakdown: Record<string, number> }>(
        `/api/verification/run-batch?check_urls_online=${checkOnline}`,
      );
      setBanner(
        `Verified ${res.processed} records: ${res.status_breakdown.VERIFIED || 0} VERIFIED, ${res.status_breakdown.UNVERIFIED || 0} UNVERIFIED, ${res.status_breakdown.NEEDS_REVIEW || 0} NEEDS_REVIEW.`,
      );
      await loadData();
      onDataChanged();
    } finally {
      setBusy(false);
    }
  };

  const handleQuickStatus = async (bizId: number, status: string, wilayaCode?: number) => {
    await api.patch(`/api/businesses/${bizId}`, {
      verification_status: status,
      ...(wilayaCode ? { wilaya_code: wilayaCode } : {}),
      review_notes: `Quick review action -> ${status}`,
    });
    await loadData();
    onDataChanged();
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            {mode === 'duplicates'
              ? t.nav.duplicates
              : mode === 'verification'
                ? t.nav.verification
                : t.nav.review}
          </h1>
          <p className="text-xs text-slate-600 mt-0.5">
            {mode === 'duplicates'
              ? 'Compare suspected duplicates side-by-side. Every merge is snapshot-logged and reversible.'
              : mode === 'verification'
                ? 'Evidence-based verification checks name, Algerian phone format, coordinates, commune/wilaya consistency, and multi-source agreement.'
                : 'Resolve uncertain locations, assign wilayas, update statuses, or inspect suspected duplicates.'}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {mode === 'duplicates' && (
            <button
              type="button"
              disabled={busy}
              onClick={handleScanDuplicates}
              className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 disabled:opacity-50 whitespace-nowrap"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Scan for Duplicates</span>
            </button>
          )}
          {mode === 'verification' && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => handleBatchVerify(false)}
                className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-white bg-teal-700 rounded-lg hover:bg-teal-800 disabled:opacity-50 whitespace-nowrap"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Run Offline Verification</span>
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => handleBatchVerify(true)}
                className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 disabled:opacity-50 whitespace-nowrap"
              >
                <span>Verify + Check Websites</span>
              </button>
            </>
          )}
        </div>
      </div>

      {banner && (
        <div className="bg-teal-50 border border-teal-200 text-teal-900 text-xs rounded-lg px-4 py-2.5">{banner}</div>
      )}

      {mode === 'duplicates' && (
        <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-lg w-fit text-xs">
          <button
            type="button"
            onClick={() => setDupTab('pending')}
            className={`px-3 py-1.5 rounded-md font-medium whitespace-nowrap ${dupTab === 'pending' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            Pending Candidates ({candidates.length})
          </button>
          <button
            type="button"
            onClick={() => setDupTab('history')}
            className={`px-3 py-1.5 rounded-md font-medium whitespace-nowrap ${dupTab === 'history' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            Merge History ({mergeHistory.length})
          </button>
        </div>
      )}

      {/* Side-by-Side Duplicate Comparison */}
      {(mode === 'duplicates' || mode === 'review') && dupTab === 'pending' && (
        <div className="space-y-4">
          {candidates.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-lg p-6 text-xs text-slate-500">
              No pending suspected duplicates in queue.
            </div>
          ) : (
            candidates.map((cand) => (
              <div key={cand.id} className="bg-white border border-slate-200 rounded-lg p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                  <div className="text-xs text-slate-700">
                    <span className="font-semibold text-slate-900">Candidate Pair #{cand.id}</span>
                    <span className="mx-2 text-slate-300">·</span>
                    <span className="font-mono-tabular">Match Score: {Math.round(cand.overall_score * 100)}%</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleResolveCandidate(cand.id, 'merge_into_a')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-700 text-white rounded hover:bg-teal-800 whitespace-nowrap"
                    >
                      <GitMerge className="w-3.5 h-3.5" />
                      <span>Merge into A</span>
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleResolveCandidate(cand.id, 'merge_into_b')}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-white rounded hover:bg-slate-900 whitespace-nowrap"
                    >
                      <GitMerge className="w-3.5 h-3.5" />
                      <span>Merge into B</span>
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => handleResolveCandidate(cand.id, 'reject_separate')}
                      className="px-3 py-1.5 border border-slate-200 text-slate-700 rounded hover:bg-slate-50 whitespace-nowrap"
                    >
                      Keep Separate
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                  {[
                    { label: 'Record A', b: cand.business_a },
                    { label: 'Record B', b: cand.business_b },
                  ].map(({ label, b }) => (
                    <div key={b.id} className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-900">
                          {label}: #{b.id} · {b.primary_name}
                        </span>
                        <button
                          type="button"
                          onClick={() => onInspectBusiness(b.id)}
                          className="text-teal-700 hover:underline"
                        >
                          Inspect
                        </button>
                      </div>
                      {b.name_ar && <div className="text-slate-600" dir="rtl">{b.name_ar}</div>}
                      <div className="font-mono-tabular text-slate-700">Phone: {b.primary_phone || '—'}</div>
                      <div className="text-slate-700">Address: {b.full_address || '—'}</div>
                      <div className="text-slate-600">
                        Location: {b.wilaya_name || '—'} / {b.commune_name || '—'}
                        {b.lat !== null && b.lon !== null && (
                          <span className="font-mono-tabular text-slate-500 ml-1.5">
                            ({b.lat.toFixed(4)}, {b.lon.toFixed(4)})
                          </span>
                        )}
                      </div>
                      <div className="text-slate-500">
                        Sources: {b.sources.map((s) => s.name).join(', ') || '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Merge History with Reversible Restore */}
      {mode === 'duplicates' && dupTab === 'history' && (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
              <tr>
                <th className="py-2.5 px-3 text-left font-medium">Merge ID</th>
                <th className="py-2.5 px-3 text-left font-medium">Target Business</th>
                <th className="py-2.5 px-3 text-left font-medium">Merged Business</th>
                <th className="py-2.5 px-3 text-left font-medium">Type</th>
                <th className="py-2.5 px-3 text-right font-medium">Score</th>
                <th className="py-2.5 px-3 text-left font-medium">Date</th>
                <th className="py-2.5 px-3 text-right font-medium">{t.common.actions}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {mergeHistory.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No merge history recorded yet.
                  </td>
                </tr>
              ) : (
                mergeHistory.map((m) => (
                  <tr key={m.id} className="h-10">
                    <td className="px-3 py-2 font-mono-tabular text-slate-500">#{m.id}</td>
                    <td className="px-3 py-2 font-medium text-slate-900">
                      #{m.target_business_id} · {m.target_name}
                    </td>
                    <td className="px-3 py-2 text-slate-700">
                      #{m.source_business_id} · {m.source_name}
                    </td>
                    <td className="px-3 py-2 font-mono-tabular text-slate-600">{m.merge_type}</td>
                    <td className="px-3 py-2 text-right font-mono-tabular">{Math.round(m.confidence_score * 100)}%</td>
                    <td className="px-3 py-2 font-mono-tabular text-slate-500">{m.created_at.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-3 py-2 text-right">
                      {m.is_reverted ? (
                        <span className="text-slate-400">Reverted</span>
                      ) : (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleRevertMerge(m.id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 border border-slate-200 rounded text-slate-700 hover:bg-slate-50"
                        >
                          <RotateCcw className="w-3 h-3" />
                          <span>Restore</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Records Queue for Verification & Manual Review */}
      {(mode === 'review' || mode === 'verification') && (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-200 text-xs font-semibold text-slate-900">
            {mode === 'review'
              ? `Records Requiring Review (${reviewRecords.length})`
              : `Verification Ledger (${reviewRecords.length})`}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
                <tr>
                  <th className="py-2 px-3 text-left font-medium">Agency</th>
                  <th className="py-2 px-3 text-left font-medium">Wilaya</th>
                  <th className="py-2 px-3 text-left font-medium">Phone</th>
                  <th className="py-2 px-3 text-left font-medium">Status</th>
                  <th className="py-2 px-3 text-left font-medium">Notes</th>
                  <th className="py-2 px-3 text-right font-medium">{t.common.actions}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {reviewRecords.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-500">
                      No records in this queue.
                    </td>
                  </tr>
                ) : (
                  reviewRecords.map((r) => (
                    <tr key={r.id} className="h-11">
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => onInspectBusiness(r.id)}
                          className="font-medium text-teal-800 hover:underline text-left"
                        >
                          {r.primary_name}
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={r.wilaya_code || ''}
                          onChange={(e) =>
                            e.target.value && handleQuickStatus(r.id, r.verification_status, Number(e.target.value))
                          }
                          className="px-2 py-1 border border-slate-200 rounded bg-white text-xs"
                        >
                          <option value="">Unassigned</option>
                          {wilayas.map((w) => (
                            <option key={w.code} value={w.code}>
                              {w.code_str} · {w.name_fr}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2 font-mono-tabular text-slate-700">{r.primary_phone || '—'}</td>
                      <td className="px-3 py-2">
                        <StatusLabel status={r.verification_status} label={t.statuses[r.verification_status]} />
                      </td>
                      <td className="px-3 py-2 text-slate-600 max-w-xs truncate">{r.verification_notes || '—'}</td>
                      <td className="px-3 py-2 text-right space-x-1.5 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => handleQuickStatus(r.id, 'VERIFIED')}
                          className="px-2 py-1 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded hover:bg-emerald-100"
                        >
                          Verify
                        </button>
                        <button
                          type="button"
                          onClick={() => handleQuickStatus(r.id, 'CLOSED')}
                          className="px-2 py-1 bg-rose-50 text-rose-800 border border-rose-200 rounded hover:bg-rose-100"
                        >
                          Close
                        </button>
                        <button
                          type="button"
                          onClick={() => onInspectBusiness(r.id)}
                          className="px-2 py-1 border border-slate-200 rounded text-slate-700 hover:bg-slate-50"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
