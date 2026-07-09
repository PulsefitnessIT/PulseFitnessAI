/**
 * EngineerQueue — iter 216h147 (Phase 5 follow-on).
 *
 * Org-wide unassigned-jobs queue. Any field engineer in the org can
 * scan this list and "Allocate to me" — the backend uses an atomic
 * find_one_and_update so two engineers racing on the same job get a
 * graceful 409 (the loser sees who took it).
 *
 *   /svc/engineer/queue
 *
 * Header strip shows the org's open / P1 / SLA-due counters so the
 * engineer can decide whether to step in.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, RefreshCw, Loader2, AlertTriangle, Clock, MapPin,
  Hand, CheckCircle2, X, ShieldCheck, Navigation, Crosshair,
  Wrench, Building2, Camera, FileText, PoundSterling,
} from 'lucide-react';
import { List } from 'react-window';
import { notify } from '@/components/notifications';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';
import { warmEngineerCache } from '@/utils/swEngineerWarmer';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIO = {
  P1: 'bg-red-500',
  P2: 'bg-amber-500',
  P3: 'bg-cyan-500',
  P4: 'bg-slate-400',
};

const fmtRelative = (iso) => {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
};

const fmtSLA = (iso) => {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  if (!breached && !atRisk) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
      breached ? 'text-red-700 bg-red-50' : 'text-amber-700 bg-amber-50'
    }`}>
      {breached ? <AlertTriangle size={10} /> : <Clock size={10} />}
      {breached ? 'SLA BREACHED' : 'SLA AT RISK'}
    </span>
  );
};

// ── Claim modal ──────────────────────────────────────────────
const ClaimModal = ({ job, onClose, onConfirm, busy }) => {
  const [when, setWhen] = useState('');
  // Iter 220dt — Hours + Minutes dropdowns instead of a single
  // free-text minutes field. Engineers think in hours, not 90
  // minutes, and the typing pad was awkward on mobile.
  const initialMins = job?.estimated_minutes || 60;
  const [hours, setHours] = useState(() => Math.floor(initialMins / 60));
  const [mins, setMins] = useState(() => initialMins % 60);
  const totalMins = (Number(hours) || 0) * 60 + (Number(mins) || 0);
  if (!job) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center bg-black/50"
      onClick={onClose}
      data-testid="claim-modal"
    >
      <div
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              {job.reference} · {job.priority || 'P3'}
            </p>
            <h2 className="text-lg font-bold text-slate-900">{job.title}</h2>
            <p className="text-xs text-slate-500">{job.site_name || job.customer_name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            data-testid="claim-modal-close"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Take this job. You can leave the schedule blank and set it later.
        </p>
        <div className="space-y-3">
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Schedule for (optional)
            </span>
            <input
              type="datetime-local"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="claim-time-input"
            />
          </label>
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Estimated time
            </span>
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <select
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                  data-testid="claim-hours-input"
                  aria-label="Hours"
                >
                  {Array.from({ length: 11 }, (_, h) => (
                    <option key={h} value={h}>{h} {h === 1 ? 'hour' : 'hours'}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <select
                  value={mins}
                  onChange={(e) => setMins(Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                  data-testid="claim-minutes-input"
                  aria-label="Minutes"
                >
                  {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                    <option key={m} value={m}>{m} mins</option>
                  ))}
                </select>
              </label>
            </div>
            <p className="text-[10px] text-slate-500 mt-1" data-testid="claim-total-minutes">
              Total · {totalMins} mins
            </p>
          </div>
        </div>
        <div className="flex gap-2 mt-4">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 border border-slate-300 rounded-lg py-2 text-sm font-semibold"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy || totalMins < 15}
            onClick={() =>
              onConfirm({
                scheduled_at: when ? new Date(when).toISOString() : null,
                estimated_minutes: Math.max(15, Math.min(600, totalMins)),
              })
            }
            className="flex-1 bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-300 text-white rounded-lg py-2 text-sm font-bold flex items-center justify-center gap-2"
            data-testid="claim-submit"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Hand size={14} />}
            Allocate to me
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Iter 220cj — Preview an unassigned job before claiming ──────────
// Mobile-first detail sheet. Tap "View details" on a queue row to
// pull richer context (site address, equipment lines, potential value
// from any open quote, photo/event count) before deciding to claim.
const PreviewModal = ({ job, onClose, onClaim }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!job?.id) { setData(null); return; }
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const r = await axios.get(
          `${API}/svc/engineer/queue/${job.id}/preview`, auth(),
        );
        if (!cancelled) setData(r.data);
      } catch (e) {
        if (!cancelled) {
          setError(e?.response?.data?.detail || e?.message || 'Failed to load');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [job?.id]);

  if (!job) return null;
  const c = data?.case || job;
  const equipment = data?.site_equipment || [];
  const potential = data?.potential_value;
  const fmtGbp = (n) => new Intl.NumberFormat('en-GB', {
    style: 'currency', currency: potential?.currency || 'GBP',
    maximumFractionDigits: 0,
  }).format(Number(n) || 0);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center p-0 sm:p-4"
      data-testid="queue-preview-modal"
    >
      <div className="bg-white w-full sm:max-w-lg max-h-[92vh] sm:rounded-2xl rounded-t-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-200 flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              {c.reference || job.reference} · {c.priority || job.priority || 'P3'}
            </p>
            <h2 className="text-base font-bold text-slate-900 truncate">{c.title || job.title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            aria-label="Close"
            data-testid="queue-preview-close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-slate-400">
              <Loader2 size={14} className="animate-spin mr-2" /> Loading job…
            </div>
          ) : error ? (
            <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-xs text-rose-700 flex items-start gap-2" data-testid="queue-preview-error">
              <AlertTriangle size={12} className="mt-0.5" />
              <p>{error}</p>
            </div>
          ) : (
            <>
              {/* Site */}
              <div className="bg-slate-50 rounded-xl p-3 border border-slate-200">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Site</p>
                <p className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <Building2 size={12} /> {c.site_name || c.customer_name || 'Site TBC'}
                </p>
                {(c.site_address || c.site_postcode) && (
                  <p className="text-xs text-slate-600 mt-0.5 flex items-start gap-1">
                    <MapPin size={11} className="mt-0.5 flex-shrink-0" />
                    <span className="leading-snug">
                      {c.site_address}{c.site_address && c.site_postcode ? ', ' : ''}{c.site_postcode}
                    </span>
                  </p>
                )}
              </div>

              {/* Potential value */}
              {potential && potential.total > 0 ? (
                <div className="bg-emerald-50 rounded-xl p-3 border border-emerald-200" data-testid="queue-preview-potential-value">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-700">Potential value</p>
                  <p className="text-lg font-bold text-emerald-800 flex items-center gap-1">
                    <PoundSterling size={14} /> {fmtGbp(potential.total)}
                  </p>
                  <p className="text-[11px] text-emerald-700 mt-0.5">
                    Open quote · {potential.quote_status}
                  </p>
                </div>
              ) : null}

              {/* Fault description */}
              {c.description ? (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Fault description</p>
                  <p className="text-sm text-slate-800 whitespace-pre-wrap leading-snug">{c.description}</p>
                </div>
              ) : null}

              {/* Asset */}
              {(c.asset_name || c.asset_serial) ? (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Reported asset</p>
                  <p className="text-sm text-slate-800 flex items-center gap-1">
                    <Wrench size={12} /> {c.asset_name || ''} {c.asset_serial ? <span className="font-mono text-xs text-slate-500">· SN {c.asset_serial}</span> : null}
                  </p>
                </div>
              ) : null}

              {/* Site equipment lines */}
              {equipment.length > 0 ? (
                <div data-testid="queue-preview-site-equipment">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Site equipment ({equipment.length})
                  </p>
                  <ul className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
                    {equipment.slice(0, 6).map((eq) => (
                      <li key={eq.id} className="px-3 py-1.5 text-xs flex items-center gap-2">
                        <Wrench size={11} className="text-slate-400 flex-shrink-0" />
                        <span className="truncate">
                          <span className="font-semibold text-slate-800">{eq.name}</span>
                          {eq.manufacturer ? <span className="text-slate-500"> · {eq.manufacturer}</span> : null}
                          {eq.model ? <span className="text-slate-500"> {eq.model}</span> : null}
                        </span>
                        {eq.serial_number ? <span className="font-mono text-[10px] text-slate-400 ml-auto truncate">SN {eq.serial_number}</span> : null}
                      </li>
                    ))}
                    {equipment.length > 6 ? (
                      <li className="px-3 py-1.5 text-[11px] text-slate-500">+ {equipment.length - 6} more after claiming</li>
                    ) : null}
                  </ul>
                </div>
              ) : null}

              {/* Meta strip */}
              <div className="flex items-center gap-2 flex-wrap text-[11px] text-slate-500">
                {c.estimated_minutes ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 bg-white">
                    <Clock size={10} /> Est. {Math.floor(c.estimated_minutes / 60)}h{c.estimated_minutes % 60 ? ` ${c.estimated_minutes % 60}m` : ''}
                  </span>
                ) : null}
                {(data?.photos_count || 0) > 0 ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 bg-white">
                    <Camera size={10} /> {data.photos_count} photo{data.photos_count === 1 ? '' : 's'}
                  </span>
                ) : null}
                {(data?.events_count || 0) > 0 ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 bg-white">
                    <FileText size={10} /> {data.events_count} note{data.events_count === 1 ? '' : 's'}
                  </span>
                ) : null}
                {c.intake_channel ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 bg-white">
                    via {c.intake_channel}
                  </span>
                ) : null}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-slate-200 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 border border-slate-300 rounded-xl py-2 text-sm font-semibold"
            data-testid="queue-preview-cancel"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => onClaim?.(job)}
            className="flex-1 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl py-2 text-sm font-bold inline-flex items-center justify-center gap-1.5"
            data-testid="queue-preview-allocate"
          >
            <Hand size={12} /> Allocate to me
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Row ──────────────────────────────────────────────────────
// Iter 216h176 — Row signature adapted for react-window v2.
// react-window calls `rowComponent({ index, style, ariaAttributes, ...rowProps })`
// for each visible row; we accept the full props bag, look up the
// job by index from the `jobs` array, and apply the absolute-positioned
// `style` the windowing engine hands us.
const Row = ({ index, style, ariaAttributes, jobs, onClaim, onPreview, onOpen, viewMode, showDistance }) => {
  const job = jobs[index];
  if (!job) return null;
  // Iter 220p — "My gyms" rows are supplier_cases routed via the
  // public supplier-portal token flow; the engineer doesn't claim
  // them through this queue (they're already dispatched). The row's
  // CTA opens the token page instead.
  const isMyGymRow = viewMode === 'my-gyms';
  const rowKey = job.reference || job.id || `row-${index}`;
  return (
  <div
    style={style}
    {...ariaAttributes}
    className="p-3 sm:p-4 flex items-start gap-3 border-b border-slate-100 bg-white"
    data-testid={`queue-row-${rowKey}`}
  >
    <span
      className={`w-1.5 self-stretch rounded-full ${PRIO[job.priority] || PRIO.P3} flex-shrink-0`}
      aria-hidden
    />
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-extrabold text-white ${PRIO[job.priority] || PRIO.P3}`}>
          {job.priority || 'P3'}
        </span>
        <p className="text-[11px] font-bold text-slate-500 tabular-nums truncate">
          {job.reference || (job.issue_id ? `#${String(job.issue_id).slice(0, 8)}` : '')}
        </p>
        {/* Iter 220p — provenance badge: this fault came from a gym
            the engineer referred (auto-attached as supplier on signup). */}
        {job.from_referred_gym ? (
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider inline-flex items-center gap-1 border"
            style={{ background: 'rgba(14,116,144,0.08)', borderColor: 'rgba(14,116,144,0.3)', color: '#0e7490' }}
            data-testid={`queue-row-referred-${rowKey}`}
            title="From a gym you referred. You're their primary auto-dispatched supplier."
          >
            <span aria-hidden>★</span> Referred
          </span>
        ) : null}
        {fmtSLA(job.sla_resolve_at)}
        {showDistance ? (
          <span className="ml-auto inline-flex items-center gap-1" data-testid={`queue-row-near-${rowKey}`}>
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums bg-emerald-50 text-emerald-700"
              data-testid={`queue-row-distance-${rowKey}`}
            >
              <Navigation size={10} />
              {job.distance_km != null ? `${job.distance_km} km` : '—'}
            </span>
            {job.eta_minutes != null ? (
              <span
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums bg-slate-100 text-slate-700"
                data-testid={`queue-row-eta-${rowKey}`}
                title="Estimated drive time at 50 km/h average"
              >
                <Clock size={10} />
                ~{job.eta_minutes < 60
                  ? `${job.eta_minutes}m`
                  : `${Math.floor(job.eta_minutes / 60)}h${job.eta_minutes % 60 ? ` ${job.eta_minutes % 60}m` : ''}`}
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-[10px] text-slate-400 ml-auto tabular-nums">
            {fmtRelative(job.created_at)} ago
          </span>
        )}
      </div>
      <p className="text-sm font-semibold text-slate-900 truncate">{job.title}</p>
      <p className="text-xs text-slate-500 mt-0.5 truncate flex items-center gap-1.5">
        <MapPin size={10} />
        {job.site_name || job.customer_name || job.organization_name || 'Site TBC'}
        {job.site_postcode ? ` · ${job.site_postcode}` : ''}
        {job.intake_channel ? <span className="text-slate-400">· {job.intake_channel}</span> : null}
      </p>
      {job.description ? (
        <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-snug">{job.description}</p>
      ) : null}
    </div>
    {isMyGymRow ? (
      <a
        href={job.supplier_case_token ? `/supplier/case/${job.supplier_case_token}` : '#'}
        target="_blank"
        rel="noreferrer"
        className="bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5 flex-shrink-0"
        data-testid={`queue-open-supplier-case-${rowKey}`}
      >
        Open ticket
      </a>
    ) : job.assigned_engineer_id ? (
      <div className="flex flex-col gap-1.5 items-end flex-shrink-0">
        <span
          className="px-2 py-1 rounded-lg text-[10px] font-bold bg-slate-100 text-slate-600 inline-flex items-center gap-1 max-w-[130px]"
          data-testid={`queue-assigned-${rowKey}`}
          title={job.assigned_engineer_name || 'Assigned'}
        >
          <ShieldCheck size={11} className="flex-shrink-0" />
          <span className="truncate">{job.assigned_engineer_name ? `Assigned · ${job.assigned_engineer_name}` : 'Assigned'}</span>
        </span>
        <button
          type="button"
          onClick={() => onOpen && onOpen(job)}
          className="text-cyan-700 hover:bg-cyan-50 text-[11px] font-bold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
          data-testid={`queue-open-${rowKey}`}
        >
          View →
        </button>
      </div>
    ) : (
      <div className="flex flex-col gap-1.5 items-end flex-shrink-0">
        <button
          type="button"
          onClick={() => onClaim && onClaim(job)}
          className="bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5"
          data-testid={`queue-claim-${rowKey}`}
        >
          <Hand size={12} /> Allocate to me
        </button>
        <button
          type="button"
          onClick={() => onPreview && onPreview(job)}
          className="text-cyan-700 hover:bg-cyan-50 text-[11px] font-bold px-2.5 py-1 rounded-md inline-flex items-center gap-1"
          data-testid={`queue-preview-${rowKey}`}
        >
          View details →
        </button>
      </div>
    )}
  </div>
  );
};

// ── Main page ──────────────────────────────────────────────
export default function EngineerQueue() {
  const orgBrand = useEngineerOrgBrand();
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState({ total: 0, p1: 0, sla_breached_or_due: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [claimFor, setClaimFor] = useState(null);
  const [previewFor, setPreviewFor] = useState(null);
  const [claimBusy, setClaimBusy] = useState(false);
  const [sortMode, setSortMode] = useState('default');   // 'default' | 'nearest'
  const [origin, setOrigin] = useState(null);            // { lat, lon } | { postcode }
  const [originSource, setOriginSource] = useState(null); // 'geolocation' | 'postcode' | null
  const [locating, setLocating] = useState(false);
  // Iter 220p — "My gyms" view. When toggled on, swap data source
  // from org-wide /queue/unassigned to /queue/my-gyms (supplier_cases
  // dispatched directly to this engineer from the gyms they referred).
  const [viewMode, setViewMode] = useState('queue'); // 'queue' | 'my-gyms'
  const [myGyms, setMyGyms] = useState({ jobs: [], total: 0, gyms_count: 0, is_partner_engineer: null });

  const load = useCallback(async (sortOverride, originOverride) => {
    setLoading(true);
    try {
      const effectiveSort = sortOverride ?? sortMode;
      const effectiveOrigin = originOverride !== undefined ? originOverride : origin;
      const params = {};
      if (effectiveSort === 'nearest' && effectiveOrigin) {
        params.sort = 'nearest';
        if (effectiveOrigin.lat != null && effectiveOrigin.lon != null) {
          params.lat = effectiveOrigin.lat;
          params.lon = effectiveOrigin.lon;
        } else if (effectiveOrigin.postcode) {
          params.postcode = effectiveOrigin.postcode;
        }
      }
      const [j, g] = await Promise.all([
        axios.get(`${API}/svc/engineer/queue/territory`, { ...auth(), params }),
        // Iter 220p — fetch "My gyms" alongside for the pill badge count.
        axios.get(`${API}/svc/engineer/queue/my-gyms`, auth())
          .catch(() => ({ data: { jobs: [], total: 0, is_partner_engineer: null } })),
      ]);
      const tjobs = j.data?.jobs || [];
      setJobs(tjobs);
      setOriginSource(null);
      // Territory view computes its own stat strip from the returned cases.
      const p1 = tjobs.filter((x) => (x.priority || '').toUpperCase() === 'P1').length;
      const slaRisk = tjobs.filter((x) => {
        if (!x.sla_resolve_at) return false;
        return (new Date(x.sla_resolve_at) - Date.now()) < 2 * 3600 * 1000;
      }).length;
      setStats({ total: tjobs.length, p1, sla_breached_or_due: slaRisk });
      setMyGyms(g.data || { jobs: [], total: 0, is_partner_engineer: null });
      // Iter 216h176 — Warm the engineer's "active week" cache so the
      // diary + notifications survive going offline. Throttled to once
      // every 5 minutes; no-op if the SW isn't installed.
      warmEngineerCache();
    } catch (e) {
      notify.error('Failed to load queue', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [sortMode, origin]); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 30s so race-with-other-engineers doesn't show stale jobs.
  useEffect(() => {
    const t = setInterval(() => load(), 30000);
    return () => clearInterval(t);
  }, [load]);

  // ── Nearest-to-me handler ────────────────────────────────
  const enableNearest = useCallback(async () => {
    if (sortMode === 'nearest') {
      // Toggle off
      setSortMode('default');
      setOrigin(null);
      setOriginSource(null);
      load('default', null);
      return;
    }
    setLocating(true);
    // Try browser geolocation first
    const tryGeo = () => new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 7000, maximumAge: 60_000 },
      );
    });
    const coords = await tryGeo();
    let nextOrigin = null;
    if (coords) {
      nextOrigin = { lat: coords.lat, lon: coords.lon };
    } else {
      // Fallback: fetch engineer profile postcode
      try {
        const me = await axios.get(`${API}/svc/engineer/me`, auth());
        const pc = me.data?.engineer?.home_address?.postcode
                || me.data?.home_address?.postcode
                || me.data?.postcode;
        if (pc) nextOrigin = { postcode: pc };
      } catch (_) { /* ignore */ }
    }
    setLocating(false);
    if (!nextOrigin) {
      notify.error('Location unavailable',
        'Grant location access or set a postcode on your engineer profile to sort by distance.');
      return;
    }
    setSortMode('nearest');
    setOrigin(nextOrigin);
    load('nearest', nextOrigin);
  }, [sortMode, load]);

  const filtered = useMemo(() => {
    // Iter 220p — when viewing "My gyms", show the engineer's
    // supplier_cases. These aren't claimable through the normal queue
    // (they came via the supplier portal token flow), so the row
    // component routes the user to the supplier_case page instead.
    if (viewMode === 'my-gyms') return myGyms.jobs || [];
    if (filter === 'all') return jobs;
    if (filter === 'p1') return jobs.filter((j) => (j.priority || '').toUpperCase() === 'P1');
    if (filter === 'risk') return jobs.filter((j) => {
      if (!j.sla_resolve_at) return false;
      const ms = new Date(j.sla_resolve_at) - Date.now();
      return ms < 2 * 3600 * 1000;
    });
    return jobs;
  }, [jobs, filter, viewMode, myGyms.jobs]);

  const onClaim = async (payload) => {
    if (!claimFor) return;
    setClaimBusy(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/queue/${claimFor.id}/claim`,
        payload,
        auth(),
      );
      notify.success(`Allocated ${r.data.reference}`);
      setClaimFor(null);
      // Iter 220dn — pass `from=queue` so the job-detail back button
      // returns the engineer to Up-for-grabs instead of dumping them
      // on Engineer Home. Fixes the "the job disappeared" feedback —
      // the queue now visibly re-renders without the claimed row.
      navigate(`/svc/engineer/jobs/${r.data.case_id}?from=queue`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409) {
        const msg = (typeof detail === 'object' ? detail.detail : null) ||
                    'Sorry — that job has just been taken by another engineer.';
        notify.error('Already claimed', msg);
        setClaimFor(null);
        load();
      } else {
        notify.error('Allocate failed', (typeof detail === 'object' ? JSON.stringify(detail) : detail) || e.message);
      }
    } finally {
      setClaimBusy(false);
    }
  };

  const Stat = ({ label, value, accent }) => (
    <div className={`flex-1 rounded-xl border p-3 ${accent || 'bg-white border-slate-200'}`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="text-2xl font-extrabold text-slate-900 tabular-nums leading-tight">{value}</p>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-queue">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="queue-back"
              aria-label="Back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-700">
                {orgBrand.label}
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <Hand size={20} /> Territory jobs
              </h1>
            </div>
          </div>
          <button
            type="button"
            onClick={load}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
            data-testid="queue-refresh"
            aria-label="Refresh"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-4 space-y-3">
        {/* Stat strip */}
        <section className="flex gap-2" data-testid="queue-stats">
          <Stat label="Open" value={stats.total} />
          <Stat label="P1" value={stats.p1} accent={stats.p1 ? 'bg-red-50 border-red-200' : ''} />
          <Stat label="SLA risk" value={stats.sla_breached_or_due} accent={stats.sla_breached_or_due ? 'bg-amber-50 border-amber-200' : ''} />
        </section>

        {/* Iter 220p — view mode switcher: org-wide queue ↔ My gyms.
            The "My gyms" pill is only shown for Partner Engineers (i.e.
            users we've found a partner_engineers row for). For everyone
            else it stays hidden so the queue UX is unchanged. */}
        {myGyms.is_partner_engineer ? (
          <div className="flex items-center gap-2" data-testid="queue-view-switcher">
            <button
              type="button"
              onClick={() => setViewMode('queue')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
                viewMode === 'queue'
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-50'
              }`}
              data-testid="queue-view-org"
            >
              Territory jobs{jobs.length ? ` · ${jobs.length}` : ''}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('my-gyms')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors inline-flex items-center gap-1.5 ${
                viewMode === 'my-gyms'
                  ? 'text-white shadow-sm'
                  : 'bg-white border text-slate-700 hover:bg-slate-50'
              }`}
              style={viewMode === 'my-gyms'
                ? { background: 'linear-gradient(135deg, #0891b2 0%, #0e7490 100%)' }
                : { borderColor: '#0e749033' }
              }
              data-testid="queue-view-my-gyms"
              title="Faults from gyms where you're the auto-dispatched supplier"
            >
              <span aria-hidden>★</span>
              My gyms{myGyms.total ? ` · ${myGyms.total}` : ''}
              {myGyms.gyms_count ? (
                <span className={`ml-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${
                  viewMode === 'my-gyms' ? 'bg-white/20 text-white' : 'bg-teal-50 text-teal-700'
                }`}>
                  {myGyms.gyms_count} gym{myGyms.gyms_count === 1 ? '' : 's'}
                </span>
              ) : null}
            </button>
          </div>
        ) : null}

        {/* Filters */}
        <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 flex items-center gap-1 flex-wrap">
          {[
            { k: 'all',  label: `All${jobs.length ? ` · ${jobs.length}` : ''}` },
            { k: 'p1',   label: `P1${stats.p1 ? ` · ${stats.p1}` : ''}` },
            { k: 'risk', label: `SLA risk${stats.sla_breached_or_due ? ` · ${stats.sla_breached_or_due}` : ''}` },
          ].map((opt) => (
            <button
              key={opt.k}
              type="button"
              onClick={() => setFilter(opt.k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                filter === opt.k ? 'bg-cyan-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
              data-testid={`queue-filter-${opt.k}`}
            >
              {opt.label}
            </button>
          ))}
          <span className="flex-1" />
          <button
            type="button"
            onClick={enableNearest}
            disabled={locating}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 ${
              sortMode === 'nearest'
                ? 'bg-emerald-600 text-white'
                : 'text-slate-700 border border-slate-300 hover:bg-slate-50'
            }`}
            data-testid="queue-sort-nearest"
            title="Sort jobs by distance from your current location"
          >
            {locating ? <Loader2 size={12} className="animate-spin" /> : <Crosshair size={12} />}
            {sortMode === 'nearest' ? 'Sorted: nearest' : 'Nearest to me'}
          </button>
        </div>

        {sortMode === 'nearest' && originSource ? (
          <p className="text-[11px] text-slate-500 px-1" data-testid="queue-origin-source">
            Distances from your{' '}
            {originSource === 'geolocation' ? 'current location' : 'home postcode'};
            ETA assumes a 50 km/h field-service average. Sites without a postcode appear last.
          </p>
        ) : null}

        {/* List */}
        {!loading && filtered.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center" data-testid="queue-empty">
            <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-semibold text-slate-700">
              {viewMode === 'my-gyms' ? 'No open jobs from your gyms' : 'No jobs in your area'}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {viewMode === 'my-gyms'
                ? (myGyms.no_gyms_yet
                    ? "You haven't been added as a supplier yet. Share your referral link to onboard gyms."
                    : "Your gyms are all clear right now. New faults will appear here automatically.")
                : "No open cases logged in your territory right now. We refresh this every 30 seconds."}
            </p>
          </div>
        ) : (
          // Iter 216h176 — Virtualised list. For ≤30 jobs we fall back
          // to the static <ul> so very short queues don't pay the
          // windowing overhead. Above that, react-window only mounts
          // ~10 rows at a time which keeps scroll smooth at 60 fps
          // even with 200+ jobs in the engineer's region.
          filtered.length <= 30 ? (
            <ul className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
              {filtered.map((j, idx) => (
                <Row
                  key={j.id}
                  index={idx}
                  style={{ position: 'relative' }}
                  ariaAttributes={{}}
                  jobs={filtered}
                  onClaim={viewMode === 'my-gyms' ? null : setClaimFor}
                  onPreview={viewMode === 'my-gyms' ? null : setPreviewFor}
                  onOpen={(j) => navigate(`/svc/engineer/jobs/${j.id}?from=queue`)}
                  viewMode={viewMode}
                  showDistance={sortMode === 'nearest'}
                />
              ))}
            </ul>
          ) : (
            <div
              className="bg-white border border-slate-200 rounded-2xl overflow-hidden"
              data-testid="queue-virtualised"
              style={{ height: 'calc(100vh - 320px)', minHeight: 360 }}
            >
              <List
                rowCount={filtered.length}
                rowHeight={132}
                rowComponent={Row}
                rowProps={{
                  jobs: filtered,
                  onClaim: viewMode === 'my-gyms' ? null : setClaimFor,
                  onPreview: viewMode === 'my-gyms' ? null : setPreviewFor,
                  onOpen: (j) => navigate(`/svc/engineer/jobs/${j.id}?from=queue`),
                  viewMode,
                  showDistance: sortMode === 'nearest',
                }}
                overscanCount={3}
              />
            </div>
          )
        )}

        {/* Footer hint */}
        <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-3 text-xs text-cyan-900 flex items-start gap-2">
          <ShieldCheck size={14} className="mt-0.5 flex-shrink-0" />
          <p>
            Two engineers can't grab the same job — first tap wins. If you see "already claimed",
            just refresh and pick the next one.
          </p>
        </div>
      </main>

      <ClaimModal
        job={claimFor}
        onClose={() => setClaimFor(null)}
        onConfirm={onClaim}
        busy={claimBusy}
      />
      <PreviewModal
        job={previewFor}
        onClose={() => setPreviewFor(null)}
        onClaim={(j) => { setPreviewFor(null); setClaimFor(j); }}
      />
    </div>
  );
}
