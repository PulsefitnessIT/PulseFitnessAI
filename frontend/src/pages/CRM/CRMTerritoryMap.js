/**
 * CRMTerritoryMap.js (iter 216h278)
 *
 * Interactive UK map for visualising sales-coverage areas. Admins click
 * a county or postcode area to assign Sales Managers / Engineers,
 * pick colours from each rep's palette, and download a PNG of any
 * rep's patch for handover.
 *
 * Data:
 *   /maps/uk_counties.topojson    — 74 ceremonial counties (covers GB + NI)
 *   /maps/uk_postcodes.topojson   — 120 postcode areas (AB, AL, B, …)
 *
 * Architecture: each region maps 1:1 to a row in `crm_territories`
 * (region_type + region_code keyed), so the existing auto-assign +
 * rollup pipelines keep working unchanged. Postcode-area territories
 * carry priority 100, county territories priority 10 — postcode wins
 * on cross-overs, matching the brief.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { ComposableMap, Geographies, Geography, Marker } from 'react-simple-maps';
import { geoCentroid } from 'd3-geo';
import { feature } from 'topojson-client';
import {
  Map as MapIcon, Layers, Download, RefreshCw, X, Search, UserCog, Hammer, CheckCircle2,
  Flame, Zap, Paintbrush, Building2, Users,
} from 'lucide-react';
import OfficesPanel from './CRMTerritoryOffices';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => { const _t = localStorage.getItem('crm_token'); return { headers: _t ? { Authorization: `Bearer ${_t}` } : {} }; };

const DEFAULT_PALETTE = [
  // Territory swatch palette — these are visual data, not theme tokens.
  // The palette must stay stable so saved colour assignments don't shift.
  /* eslint-disable gymaxis/no-inline-hex -- swatch literals, not theme styling */
  '#2563EB', '#DB2777', '#059669', '#D97706', '#7C3AED', '#DC2626',
  '#0891B2', '#65A30D', '#EA580C', '#9333EA', '#0EA5E9', '#16A34A',
  /* eslint-enable gymaxis/no-inline-hex */
];

const ROLE_LABELS = { sales_manager: 'Sales Manager', engineer: 'Engineer', both: 'Manager + Engineer' };
const ROLE_ICONS = { sales_manager: UserCog, engineer: Hammer, both: UserCog };

function StaffRow({ s, onColour, onRole, focused, onFocus }) {
  const Icon = ROLE_ICONS[s.territory_role] || UserCog;
  return (
    <div
      onClick={() => onFocus(focused ? null : s.id)}
      className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer border ${focused ? 'border-zinc-900 bg-zinc-50 dark:bg-zinc-800 dark:border-zinc-200 shadow-sm' : 'border-transparent hover:bg-zinc-50 dark:hover:bg-zinc-800/60'}`}
      data-testid={`staff-row-${s.id}`}
    >
      <input
        type="color"
        value={s.colour_hex}
        onChange={(e) => onColour(s.id, e.target.value)}
        onClick={(e) => e.stopPropagation()}
        className="w-7 h-7 rounded border border-zinc-200 dark:border-zinc-700 cursor-pointer bg-transparent"
        title="Pick colour"
        data-testid={`staff-colour-${s.id}`}
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{s.full_name || s.email}</p>
        <p className="text-[10px] text-zinc-500 truncate flex items-center gap-1">
          <Icon size={10} /> {ROLE_LABELS[s.territory_role]}
        </p>
      </div>
      <select
        value={s.territory_role}
        onChange={(e) => onRole(s.id, e.target.value)}
        onClick={(e) => e.stopPropagation()}
        className="text-[11px] border border-zinc-200 dark:border-zinc-700 rounded px-1 py-0.5 bg-white dark:bg-zinc-900"
        data-testid={`staff-role-${s.id}`}
      >
        <option value="sales_manager">Manager</option>
        <option value="engineer">Engineer</option>
        <option value="both">Both</option>
      </select>
    </div>
  );
}

function RegionDrawer({ region, staff, coverage, offices = [], onClose, onSave }) {
  const current = coverage[region?.code] || [];
  const [selected, setSelected] = useState(() => current.map((m) => m.user_id));
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  useEffect(() => { setSelected(current.map((m) => m.user_id)); }, [region]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (uid) => setSelected((cur) => (cur.includes(uid) ? cur.filter((x) => x !== uid) : [...cur, uid]));
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return staff;
    return staff.filter((s) => (s.full_name || s.email || '').toLowerCase().includes(q));
  }, [staff, query]);

  // Nearest office to this region — great-circle distance (miles) from the
  // region centroid to every pinned office. Helps planners pick the
  // closest depot when allocating coverage.
  const nearest = useMemo(() => {
    if (!region?.centroid || !offices.length) return null;
    const [lng, lat] = region.centroid;
    const R = 3958.8; // Earth radius, miles
    const toRad = (d) => (d * Math.PI) / 180;
    let best = null;
    offices.forEach((o) => {
      if (typeof o.lat !== 'number' || typeof o.lng !== 'number') return;
      const dLat = toRad(o.lat - lat);
      const dLng = toRad(o.lng - lng);
      const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat)) * Math.cos(toRad(o.lat)) * Math.sin(dLng / 2) ** 2;
      const dist = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      if (!best || dist < best.dist) best = { office: o, dist };
    });
    return best;
  }, [region, offices]);

  if (!region) return null;
  const save = async () => {
    setSaving(true);
    try {
      await onSave(region, selected);
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] bg-white dark:bg-zinc-900 border-l border-zinc-200 dark:border-zinc-800 shadow-xl flex flex-col" data-testid="region-drawer">
      <div className="px-5 py-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
        <div className="min-w-0">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">
            {region.type === 'county' ? 'County' : 'Postcode area'}
          </p>
          <h3 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 truncate">{region.label}</h3>
        </div>
        <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100" data-testid="region-drawer-close">
          <X size={18} />
        </button>
      </div>
      <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-2.5 text-zinc-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter people..."
            className="w-full pl-7 pr-2 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
            data-testid="region-drawer-search"
          />
        </div>
        <p className="mt-2 text-[11px] text-zinc-500">
          {selected.length} assigned · click anyone to toggle them on or off this region.
        </p>
        {nearest && (
          <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold text-zinc-700 dark:text-zinc-300" data-testid="region-nearest-office">
            <Building2 size={12} className="text-zinc-500" />
            Nearest office:
            <span className="inline-flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full border border-zinc-300" style={{ backgroundColor: nearest.office.colour_hex }} />
              {nearest.office.name}
            </span>
            <span className="text-zinc-400 font-normal">· {Math.round(nearest.dist)} mi</span>
          </div>
        )}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        {visible.length === 0 && <p className="text-sm text-zinc-400 text-center py-6">No matching people.</p>}
        {visible.map((s) => {
          const on = selected.includes(s.id);
          const Icon = ROLE_ICONS[s.territory_role] || UserCog;
          return (
            <button
              type="button"
              key={s.id}
              onClick={() => toggle(s.id)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md border text-left ${on ? 'border-zinc-900 bg-zinc-50 dark:bg-zinc-800 dark:border-zinc-200' : 'border-transparent hover:bg-zinc-50 dark:hover:bg-zinc-800/60'}`}
              data-testid={`region-drawer-staff-${s.id}`}
            >
              <span className="w-3 h-3 rounded border border-zinc-300" style={{ backgroundColor: s.colour_hex }} />
              <span className="flex-1 min-w-0">
                <span className="block text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{s.full_name || s.email}</span>
                <span className="block text-[10px] text-zinc-500 flex items-center gap-1">
                  <Icon size={9} /> {ROLE_LABELS[s.territory_role]}
                </span>
              </span>
              {on && <CheckCircle2 size={15} className="text-emerald-600" />}
            </button>
          );
        })}
      </div>
      <div className="px-5 py-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center gap-3 bg-zinc-50 dark:bg-zinc-900/60">
        <button
          onClick={() => onSave(region, [])}
          disabled={saving || current.length === 0}
          className="px-3 py-2 text-xs font-bold text-rose-700 hover:bg-rose-50 rounded-md disabled:opacity-40"
          data-testid="region-drawer-clear"
        >
          Clear region
        </button>
        <div className="flex-1" />
        <button onClick={onClose} className="px-3 py-2 text-sm font-bold text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-md" data-testid="region-drawer-cancel">
          Cancel
        </button>
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 text-sm font-bold text-white rounded-md disabled:opacity-50"
          style={{ background: 'var(--color-brand-blue, #2563EB)' }}
          data-testid="region-drawer-save"
        >
          {saving ? 'Saving…' : 'Save assignment'}
        </button>
      </div>
    </div>
  );
}

export default function CRMTerritoryMap() {
  const [layer, setLayer] = useState('county'); // 'county' | 'postcode_area'
  const [counties, setCounties] = useState([]);
  const [postcodes, setPostcodes] = useState([]);
  const [coverage, setCoverage] = useState({ counties: {}, postcode_areas: {} });
  const [heatmap, setHeatmap] = useState({ counties: {}, postcode_areas: {} });
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [roleFilter, setRoleFilter] = useState('all'); // 'all' | 'sales_manager' | 'engineer'
  const [offices, setOffices] = useState([]);
  const [showOffices, setShowOffices] = useState(true);
  const [autoAssigning, setAutoAssigning] = useState(false);
  const [staff, setStaff] = useState([]);
  const [focusedUser, setFocusedUser] = useState(null);
  const [activeRegion, setActiveRegion] = useState(null);
  const [loading, setLoading] = useState(true);
  const svgRef = useRef(null);

  // ── Data loading ─────────────────────────────────────────────────
  const loadCoverage = useCallback(async () => {
    try {
      const [cov, palette, heat] = await Promise.all([
        axios.get(`${API}/crm/territories/coverage-map`, auth()),
        axios.get(`${API}/crm/territories/staff-palette`, auth()),
        axios.get(`${API}/crm/territories/coverage-heatmap`, auth()).catch(() => ({ data: { counties: {}, postcode_areas: {} } })),
      ]);
      setCoverage({
        counties: cov.data.counties || {},
        postcode_areas: cov.data.postcode_areas || {},
      });
      setHeatmap({
        counties: heat.data.counties || {},
        postcode_areas: heat.data.postcode_areas || {},
      });
      // Auto-assign default colours to staff who haven't picked one.
      const pal = (palette.data.staff || []).map((s, i) => ({
        ...s,
        colour_hex: s.colour_hex && s.colour_hex !== '#94A3B8' ? s.colour_hex : DEFAULT_PALETTE[i % DEFAULT_PALETTE.length],
      }));
      setStaff(pal);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load coverage');
    }
  }, []);

  const loadOffices = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/territories/offices`, auth());
      setOffices(r.data.offices || []);
    } catch (e) { /* offices are optional; ignore load errors */ }
  }, []);

  const loadMaps = useCallback(async () => {
    setLoading(true);
    try {
      const [c, p] = await Promise.all([
        fetch('/maps/uk_counties.topojson').then((r) => r.json()),
        fetch('/maps/uk_postcodes.topojson').then((r) => r.json()),
      ]);
      const countiesFC = feature(c, c.objects.eng_ceremonial);
      const postcodesFC = feature(p, p.objects.uk_postcode_areas);
      setCounties(countiesFC.features || []);
      setPostcodes(postcodesFC.features || []);
    } catch (e) {
      toast.error('Could not load UK map data');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadMaps();
    loadCoverage();
    loadOffices();
  }, [loadMaps, loadCoverage, loadOffices]);

  // ── Save handlers ─────────────────────────────────────────────────
  const saveRegion = async (region, assignedIds) => {
    try {
      await axios.put(
        `${API}/crm/territories/region/${region.type}/${encodeURIComponent(region.code)}`,
        { assigned_rep_ids: assignedIds },
        auth(),
      );
      toast.success(assignedIds.length === 0 ? `Cleared ${region.label}` : `Saved ${region.label}`);
      setActiveRegion(null);
      loadCoverage();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    }
  };

  // Iter 220ea·41 — "paint mode": once a staff member is selected in the
  // sidebar (focusedUser), clicking a county/postcode area directly
  // allocates them to it (paints their colour) — or removes them if they
  // already cover it. No drawer needed. Optimistic + auto-saved. This is
  // the intuitive "pick a person, click the map to allocate" flow.
  const paintRegion = async (region, uid) => {
    const key = region.type === 'county' ? 'counties' : 'postcode_areas';
    const current = coverage[key][region.code] || [];
    const has = current.some((m) => m.user_id === uid);
    const nextIds = has
      ? current.filter((m) => m.user_id !== uid).map((m) => m.user_id)
      : [...current.map((m) => m.user_id), uid];
    const s = staffById[uid];
    const optimistic = has
      ? current.filter((m) => m.user_id !== uid)
      : [...current, { user_id: uid, full_name: s?.full_name, colour_hex: s?.colour_hex, role: s?.territory_role }];
    // Optimistically recolour the region so painting feels instant.
    setCoverage((cur) => ({ ...cur, [key]: { ...cur[key], [region.code]: optimistic } }));
    try {
      await axios.put(
        `${API}/crm/territories/region/${region.type}/${encodeURIComponent(region.code)}`,
        { assigned_rep_ids: nextIds },
        auth(),
      );
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save assignment');
      loadCoverage(); // revert to server truth on failure
    }
  };

  const saveStaffColour = async (uid, hex) => {
    setStaff((cur) => cur.map((s) => (s.id === uid ? { ...s, colour_hex: hex.toUpperCase() } : s)));
    try {
      await axios.put(`${API}/crm/territories/staff/${uid}/style`, { colour_hex: hex }, auth());
      loadCoverage();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save colour');
    }
  };

  const saveStaffRole = async (uid, role) => {
    setStaff((cur) => cur.map((s) => (s.id === uid ? { ...s, territory_role: role } : s)));
    try {
      await axios.put(`${API}/crm/territories/staff/${uid}/style`, { territory_role: role }, auth());
      loadCoverage();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not save role');
    }
  };

  // Iter 216h279 — push every region's coverage onto unassigned
  // companies + opportunities + tenders in one click. Heaviest write
  // op on this page so we lock the button + show a spinner; the
  // backend already short-circuits on records that already carry a
  // territory_id so re-runs are cheap and idempotent.
  const runAutoAssign = async () => {
    setAutoAssigning(true);
    try {
      const r = await axios.post(
        `${API}/crm/territories/map-auto-assign`,
        { dry_run: false, only_unassigned: true },
        auth(),
      );
      const tot = r.data?.totals || {};
      toast.success(
        `Auto-assigned ${r.data.total} records · ${tot.company || 0} companies · ${tot.opportunity || 0} deals · ${tot.tender || 0} tenders`,
      );
      loadCoverage();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Auto-assign failed');
    } finally { setAutoAssigning(false); }
  };

  // ── Region fill resolver — colour-mix when N reps cover the same area ──
  const staffById = useMemo(() => Object.fromEntries(staff.map((s) => [s.id, s])), [staff]);
  // Role filter: a member with role 'both' always matches. This lets an
  // admin view Engineer coverage and Sales-Manager coverage independently
  // while allowing the two to overlap on the same region.
  const roleMatch = useCallback(
    (r) => roleFilter === 'all' || r === roleFilter || r === 'both',
    [roleFilter],
  );
  const membersFor = useCallback((type, code) => {
    const list = (type === 'county' ? coverage.counties : coverage.postcode_areas)[code] || [];
    return list.filter((m) => roleMatch(m.role));
  }, [coverage, roleMatch]);
  const visibleStaff = useMemo(
    () => staff.filter((s) => roleMatch(s.territory_role)),
    [staff, roleMatch],
  );
  // Pre-compute the heatmap normalisation range for the active layer so
  // opacity scales sensibly across whatever range the org has.
  const heatRange = useMemo(() => {
    const vals = Object.values(heatmap[layer === 'county' ? 'counties' : 'postcode_areas']).filter((v) => v > 0);
    if (!vals.length) return { max: 0 };
    return { max: Math.max(...vals) };
  }, [heatmap, layer]);
  const fillForRegion = useCallback((type, code) => {
    const list = membersFor(type, code);
    const focusList = focusedUser ? list.filter((m) => m.user_id === focusedUser) : list;
    if (!focusList.length) return (focusedUser || roleFilter !== 'all') ? '#F1F5F9' : '#FFFFFF';
    const first = staffById[focusList[0].user_id] || focusList[0];
    return first.colour_hex || '#94A3B8';
  }, [membersFor, focusedUser, roleFilter, staffById]);
  const opacityForRegion = useCallback((type, code) => {
    if (!showHeatmap) return 1;
    if (!heatRange.max) return 0.18;
    const v = (heatmap[type === 'county' ? 'counties' : 'postcode_areas'][code]) || 0;
    if (!v) return 0.18; // empty regions stay readable, never invisible
    return 0.2 + 0.8 * (v / heatRange.max);
  }, [showHeatmap, heatmap, heatRange]);

  // ── Geometries to render ─────────────────────────────────────────
  const features = layer === 'county' ? counties : postcodes;
  const regionFor = (geo) => {
    const code = layer === 'county' ? geo.properties.county : geo.properties.area;
    return { type: layer, code, label: code };
  };

  const downloadPng = async () => {
    if (!svgRef.current) return;
    const svg = svgRef.current.querySelector('svg');
    if (!svg) return;
    const xml = new window.XMLSerializer().serializeToString(svg);
    const blob = new Blob([xml], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const stamp = new Date().toISOString().slice(0, 10);
    a.href = url; a.download = `uk-territory-coverage-${stamp}.svg`;
    a.click(); URL.revokeObjectURL(url);
  };

  // ── Render ───────────────────────────────────────────────────────
  const focusedCount = focusedUser ? (() => {
    let n = 0;
    Object.values(coverage[layer === 'county' ? 'counties' : 'postcode_areas']).forEach((list) => {
      if (list.some((m) => m.user_id === focusedUser)) n += 1;
    });
    return n;
  })() : null;

  return (
    <div className="max-w-7xl mx-auto px-4 py-3 space-y-3" data-testid="crm-territory-map">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="inline-flex border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-900" data-testid="layer-toggle">
            <button
              type="button"
              onClick={() => setLayer('county')}
              className={`px-3 py-1.5 text-xs font-bold inline-flex items-center gap-1.5 ${layer === 'county' ? 'seg-active' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800/60'}`}
              data-testid="layer-county"
            >
              <MapIcon size={12} /> Counties
            </button>
            <button
              type="button"
              onClick={() => setLayer('postcode_area')}
              className={`px-3 py-1.5 text-xs font-bold inline-flex items-center gap-1.5 ${layer === 'postcode_area' ? 'seg-active' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800/60'}`}
              data-testid="layer-postcode"
            >
              <Layers size={12} /> Postcode areas
            </button>
          </div>
          {focusedUser && (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-blue-600 border border-blue-700 px-2 py-1 rounded-md shadow-sm" data-testid="focus-indicator" title={`Click any county or postcode area to allocate it to ${staffById[focusedUser]?.full_name || 'this person'}. Click an allocated area again to remove them.`}>
              <Paintbrush size={12} /> Painting: {staffById[focusedUser]?.full_name || '?'} · {focusedCount} {layer === 'county' ? 'counties' : 'areas'}
              <button onClick={() => setFocusedUser(null)} className="ml-1 text-blue-100 hover:text-white" data-testid="focus-clear">
                <X size={11} />
              </button>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-900" data-testid="role-filter">
            {[
              { v: 'all', label: 'All roles', Icon: Users },
              { v: 'sales_manager', label: 'Managers', Icon: UserCog },
              { v: 'engineer', label: 'Engineers', Icon: Hammer },
            ].map(({ v, label, Icon }) => (
              <button
                key={v}
                type="button"
                onClick={() => setRoleFilter(v)}
                className={`px-3 py-1.5 text-xs font-bold inline-flex items-center gap-1.5 ${roleFilter === v ? 'seg-active' : 'text-zinc-900 dark:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800/60'}`}
                data-testid={`role-filter-${v}`}
              >
                <Icon size={12} /> {label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowOffices((v) => !v)}
            className={`px-3 py-1.5 text-xs font-bold border rounded-md inline-flex items-center gap-1.5 ${showOffices ? 'seg-active' : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'}`}
            title="Show or hide office pins on the map."
            data-testid="map-offices-toggle"
          >
            <Building2 size={12} /> Offices
          </button>
          <button
            onClick={runAutoAssign}
            disabled={autoAssigning}
            className="px-3 py-1.5 text-xs font-bold border border-zinc-200 dark:border-zinc-800 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/60 inline-flex items-center gap-1.5 disabled:opacity-50"
            title="Push every region's coverage onto unassigned companies, deals and tenders."
            data-testid="map-auto-assign"
          >
            <Zap size={12} className={autoAssigning ? 'animate-pulse' : ''} /> {autoAssigning ? 'Assigning…' : 'Auto-assign'}
          </button>
          <button
            onClick={() => setShowHeatmap((v) => !v)}
            className={`px-3 py-1.5 text-xs font-bold border rounded-md inline-flex items-center gap-1.5 ${showHeatmap ? 'bg-amber-500 border-amber-500 text-white' : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/60'}`}
            title="Shade regions by open pipeline + tender value."
            data-testid="map-heatmap-toggle"
          >
            <Flame size={12} /> {showHeatmap ? 'Heatmap on' : 'Heatmap'}
          </button>
          <button
            onClick={loadCoverage}
            className="px-3 py-1.5 text-xs font-bold border border-zinc-200 dark:border-zinc-800 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/60 inline-flex items-center gap-1.5"
            data-testid="map-refresh"
          >
            <RefreshCw size={12} /> Refresh
          </button>
          <button
            onClick={downloadPng}
            className="px-3 py-1.5 text-xs font-bold border border-zinc-200 dark:border-zinc-800 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/60 inline-flex items-center gap-1.5"
            data-testid="map-download"
          >
            <Download size={12} /> Export SVG
          </button>
        </div>
      </header>

      <div className="grid lg:grid-cols-[1fr_320px] gap-4">
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden" ref={svgRef} data-testid="territory-map-svg">
          {loading ? (
            <div className="h-[600px] flex items-center justify-center text-zinc-400 text-sm">Loading map…</div>
          ) : (
            <ComposableMap
              projection="geoMercator"
              projectionConfig={{ center: [-3.5, 54.5], scale: 2400 }}
              width={720} height={780}
              style={{ width: '100%', height: 'auto' }}
            >
              <Geographies geography={{ type: 'FeatureCollection', features }}>
                {({ geographies }) => geographies.map((geo) => {
                  const region = regionFor(geo);
                  const fill = fillForRegion(region.type, region.code);
                  const list = membersFor(region.type, region.code);
                  const hasAssignees = list.length > 0;
                  const tooltip = hasAssignees
                    ? `${region.label} — ${list.map((m) => m.full_name).join(', ')}`
                    : region.label;
                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onClick={() => { if (focusedUser) paintRegion(region, focusedUser); else setActiveRegion({ ...region, centroid: geoCentroid(geo) }); }}
                      style={{
                        // SVG stroke colours — visual data, not theme tokens.
                        /* eslint-disable gymaxis/no-inline-hex -- SVG stroke literals */
                        default:  { fill, fillOpacity: opacityForRegion(region.type, region.code), stroke: '#94A3B8', strokeWidth: 0.4, outline: 'none', cursor: 'pointer' },
                        hover:    { fill: hasAssignees ? fill : '#E2E8F0', fillOpacity: 1, stroke: '#1E293B', strokeWidth: 0.9, outline: 'none', cursor: 'pointer' },
                        pressed:  { fill, fillOpacity: 1, stroke: '#0F172A', strokeWidth: 1.1, outline: 'none' },
                        /* eslint-enable gymaxis/no-inline-hex */
                      }}
                      data-testid={`region-${region.type}-${region.code}`}
                    >
                      <title>{tooltip}</title>
                    </Geography>
                  );
                })}
              </Geographies>
              {showOffices && offices.map((o) => (
                <Marker key={o.id} coordinates={[o.lng, o.lat]} data-testid={`office-marker-${o.id}`}>
                  <g style={{ pointerEvents: 'none' }}>
                    <circle r={5} fill={o.colour_hex || '#0F172A'} stroke="#FFFFFF" strokeWidth={1.4} />
                    <text textAnchor="middle" y={-9} fontSize={9} fontWeight="700" fill="#0F172A" stroke="#FFFFFF" strokeWidth={2.4} paintOrder="stroke">{o.name}</text>
                  </g>
                </Marker>
              ))}
            </ComposableMap>
          )}
        </div>

        <aside className="space-y-3">
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-bold">Sales team · {staff.length}</p>
              {focusedUser && (
                <button onClick={() => setFocusedUser(null)} className="text-[10px] text-blue-600 hover:underline font-semibold" data-testid="clear-focus-side">
                  Clear focus
                </button>
              )}
            </div>
            <p className="text-[11px] text-zinc-500 mb-2">
              Click a person to select them, then click counties or postcode areas on the map to allocate that area to them. Click an allocated area again to remove it. Click a colour swatch to recolour a person.
            </p>
            <div className="space-y-1 max-h-[520px] overflow-y-auto" data-testid="staff-list">
              {visibleStaff.length === 0 && <p className="text-xs text-zinc-400 italic py-2">{staff.length === 0 ? 'No CRM users yet — add reps in People first.' : 'No people match this role filter.'}</p>}
              {visibleStaff.map((s) => (
                <StaffRow
                  key={s.id}
                  s={s}
                  focused={focusedUser === s.id}
                  onFocus={(uid) => setFocusedUser(uid)}
                  onColour={saveStaffColour}
                  onRole={saveStaffRole}
                />
              ))}
            </div>
          </div>
          <OfficesPanel offices={offices} onChange={loadOffices} />
          <div className="rounded-xl border border-dashed border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-900/60 p-3 text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed">
            <p className="font-semibold text-zinc-700 dark:text-zinc-300 mb-1">How coverage resolves</p>
            <p>
              Postcode-area assignments override county assignments — so you can paint Greater London to
              one manager, then override SW1 to a different engineer for that single postcode area.
            </p>
          </div>
        </aside>
      </div>

      <RegionDrawer
        region={activeRegion}
        staff={staff}
        offices={offices}
        coverage={layer === 'county' ? coverage.counties : coverage.postcode_areas}
        onClose={() => setActiveRegion(null)}
        onSave={saveRegion}
      />
    </div>
  );
}
