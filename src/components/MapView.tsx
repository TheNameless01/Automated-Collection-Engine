import L from 'leaflet';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { Translations } from '../i18n/translations';
import type { SourceItem, WilayaSummary } from '../types';

interface MapBusinessPoint {
  id: number;
  primary_name: string;
  name_ar: string;
  primary_phone: string;
  full_address: string;
  commune_name: string;
  wilaya_code: number | null;
  wilaya_name: string;
  lat: number;
  lon: number;
  verification_status: string;
  confidence_score: number;
  website: string;
}

interface MapViewProps {
  wilayas: WilayaSummary[];
  sources: SourceItem[];
  t: Translations;
  initialWilayaCode?: number | null;
  onInspectBusiness: (id: number) => void;
}

const STATUS_COLORS: Record<string, string> = {
  VERIFIED: '#16a34a',
  UNVERIFIED: '#475569',
  NEEDS_REVIEW: '#d97706',
  CLOSED: '#dc2626',
};

export function MapView({ wilayas, sources, t, initialWilayaCode, onInspectBusiness }: MapViewProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);

  const [wilayaCode, setWilayaCode] = useState(initialWilayaCode ? String(initialWilayaCode) : '');
  const [statusFilter, setStatusFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [points, setPoints] = useState<MapBusinessPoint[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;
    const map = L.map(mapContainerRef.current).setView([28.0339, 1.6596], 5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);
    layerGroupRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      layerGroupRef.current = null;
    };
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (wilayaCode) params.set('wilaya_code', wilayaCode);
    if (statusFilter) params.set('verification_status', statusFilter);
    if (sourceFilter) params.set('source_key', sourceFilter);

    api
      .get<MapBusinessPoint[]>(`/api/map/businesses?${params.toString()}`)
      .then((pts) => setPoints(pts))
      .finally(() => setLoading(false));
  }, [wilayaCode, statusFilter, sourceFilter]);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerGroupRef.current;
    if (!map || !group) return;

    group.clearLayers();
    const bounds: L.LatLngTuple[] = [];

    for (const p of points) {
      const color = STATUS_COLORS[p.verification_status] || '#475569';
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 7,
        fillColor: color,
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.9,
      });

      const container = document.createElement('div');
      container.className = 'text-xs space-y-1';
      const titleEl = document.createElement('div');
      titleEl.className = 'font-semibold text-slate-900';
      titleEl.textContent = p.primary_name;
      container.appendChild(titleEl);

      const metaEl = document.createElement('div');
      metaEl.className = 'text-slate-600';
      metaEl.textContent = `${p.wilaya_name || ''} ${p.commune_name ? '· ' + p.commune_name : ''}`;
      container.appendChild(metaEl);

      if (p.primary_phone) {
        const phoneEl = document.createElement('div');
        phoneEl.className = 'font-mono text-slate-700';
        phoneEl.textContent = p.primary_phone;
        container.appendChild(phoneEl);
      }

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mt-1 px-2.5 py-1 bg-teal-700 text-white rounded text-[11px] font-medium';
      btn.textContent = 'Inspect Agency';
      btn.onclick = () => onInspectBusiness(p.id);
      container.appendChild(btn);

      marker.bindPopup(container);
      marker.addTo(group);
      bounds.push([p.lat, p.lon]);
    }

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    } else if (wilayaCode) {
      const w = wilayas.find((item) => item.code === Number(wilayaCode));
      if (w) {
        map.setView([w.center_lat, w.center_lon], 9);
      }
    }
  }, [points, wilayaCode, wilayas, onInspectBusiness]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t.nav.map}</h1>
          <p className="text-xs text-slate-600 mt-0.5">
            Displaying {points.length} agencies with verified GPS coordinates (businesses without coordinates are never fabricated on the map).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={wilayaCode}
            onChange={(e) => setWilayaCode(e.target.value)}
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
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
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
            onChange={(e) => setSourceFilter(e.target.value)}
            className="px-2.5 py-1.5 border border-slate-200 rounded-lg bg-white"
          >
            <option value="">{t.common.source}: {t.common.all}</option>
            {sources.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden relative">
        {loading && (
          <div className="absolute top-3 right-3 z-[400] bg-white border border-slate-200 px-3 py-1 rounded text-xs text-slate-600 shadow-sm">
            {t.common.loading}
          </div>
        )}
        <div ref={mapContainerRef} className="w-full h-[600px]" />
      </div>
    </div>
  );
}
