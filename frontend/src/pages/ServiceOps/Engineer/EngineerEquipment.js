/**
 * EngineerEquipment — Iter 220ci
 *
 * Mobile-first equipment list + create flow for engineers in the field.
 * Lets the engineer log a new machine the moment they spot it on site
 * — the asset flows directly into the operations portal's equipment
 * collection, and (when navigated to from a job) auto-attaches as a
 * machine row on that job's per-machine work report.
 *
 * UX rules (from operator feedback):
 *   - ALL primary fields are mandatory.
 *   - Equipment type + Location + Status are STRICT picklists
 *     (server-validated) so reports stay clean.
 *   - Manufacturer is a curated dropdown sourced from
 *     /api/equipment/manufacturers with an "Other" escape hatch.
 *   - The form is reachable from:
 *       /svc/engineer/equipment                (list view)
 *       /svc/engineer/equipment/new            (blank form)
 *       /svc/engineer/equipment/new?case_id=…  (from a job → auto-attach)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  useNavigate, useSearchParams, Link,
} from 'react-router-dom';
import {
  ArrowLeft, Plus, Loader2, Search, Wrench, MapPin, Building2,
  CheckCircle2, AlertTriangle, RefreshCw, ChevronDown, ChevronUp,
  Sparkles, Camera, FileText, Clock, PoundSterling, QrCode,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import BarcodeScanModal from './BarcodeScanModal';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const STATUS_BADGE = {
  in_service: { label: 'In service', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  out_of_service: { label: 'Out of service', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  awaiting_parts: { label: 'Awaiting parts', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  decommissioned: { label: 'Decommissioned', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
};

// ─────────────────────────────────────────────────────────────────────
// List view
// ─────────────────────────────────────────────────────────────────────

export default function EngineerEquipment() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [search] = useSearchParams();
  const [items, setItems] = useState([]);
  const [picklists, setPicklists] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [siteFilter, setSiteFilter] = useState(search.get('site_id') || '');
  const [q, setQ] = useState('');
  const [scanOpen, setScanOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const qs = new URLSearchParams();
      if (siteFilter) qs.set('site_id', siteFilter);
      if (q.trim()) qs.set('q', q.trim());
      const r = await axios.get(
        `${API}/svc/engineer/equipment${qs.toString() ? `?${qs}` : ''}`,
        auth(),
      );
      setItems(r.data?.equipment || []);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [siteFilter, q]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/equipment/picklists`, auth());
        if (!cancelled) setPicklists(r.data);
      } catch {
        if (!cancelled) setPicklists(null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const sites = picklists?.sites || [];
  const hasMultipleSites = sites.length > 1;

  const caseId = params.get('case_id') || '';
  const newHref = caseId
    ? `/svc/engineer/equipment/new?case_id=${encodeURIComponent(caseId)}`
    : '/svc/engineer/equipment/new';

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-equipment-page">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            data-testid="equipment-back-btn"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900 leading-tight">Equipment</p>
            <p className="text-[11px] text-slate-500 leading-tight">
              {items.length} machine{items.length === 1 ? '' : 's'}
              {caseId ? ' · adding for current job' : ''}
            </p>
          </div>
          <Link
            to={newHref}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700"
            data-testid="equipment-add-btn"
          >
            <Plus size={14} /> Add
          </Link>
        </div>
        <div className="max-w-2xl mx-auto px-4 pb-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search name, serial, model…"
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="equipment-search-input"
            />
          </div>
          {hasMultipleSites && (
            <select
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
              className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white"
              data-testid="equipment-site-filter"
            >
              <option value="">All sites</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={() => setScanOpen(true)}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            data-testid="equipment-scan-btn"
            aria-label="Scan barcode or QR"
            title="Scan barcode or QR"
          >
            <QrCode size={14} />
          </button>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            data-testid="equipment-refresh-btn"
            aria-label="Refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <BarcodeScanModal
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onMatch={(eq) => {
          const code = eq.serial_number || eq.asset_tag || eq.name || '';
          if (code) setQ(code);
        }}
      />

      {/* Body */}
      <div className="max-w-2xl mx-auto px-4 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400">
            <Loader2 size={16} className="animate-spin mr-2" /> Loading equipment…
          </div>
        ) : error ? (
          <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-sm text-rose-700 flex items-start gap-2" data-testid="equipment-error">
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-semibold">Couldn't load equipment</p>
              <p className="text-xs opacity-80 mt-0.5">{error}</p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center" data-testid="equipment-empty">
            <Wrench size={28} className="mx-auto text-slate-300 mb-3" />
            <p className="text-sm font-bold text-slate-900">No equipment yet</p>
            <p className="text-xs text-slate-500 mt-1">
              Log the first machine and it'll flow into Operations and any open job.
            </p>
            <Link
              to={newHref}
              className="mt-4 inline-flex items-center gap-1 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700"
              data-testid="equipment-empty-add-btn"
            >
              <Plus size={14} /> Add equipment
            </Link>
          </div>
        ) : (
          <div className="space-y-2" data-testid="equipment-list">
            {items.map((it) => (
              <EquipmentRow key={it.id} item={it} sites={sites} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EquipmentRow({ item, sites }) {
  const siteName = useMemo(() => {
    if (!item.site_id) return '';
    return (sites.find((s) => s.id === item.site_id) || {}).name || '';
  }, [item.site_id, sites]);
  const badge = STATUS_BADGE[item.status || 'in_service'] || STATUS_BADGE.in_service;
  // Iter 220cm — Service-history rollup (lazy-loaded on expand).
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && history === null && !loading) {
      setLoading(true);
      setError('');
      try {
        const r = await axios.get(
          `${API}/svc/engineer/equipment/${item.id}/service-history`,
          auth(),
        );
        setHistory(r.data);
      } catch (e) {
        setError(e?.response?.data?.detail || e?.message || 'Failed to load');
        setHistory({ visits: [], totals: {} });
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div
      className="bg-white rounded-2xl border border-slate-200 overflow-hidden"
      data-testid={`equipment-row-${item.id}`}
    >
      <button
        type="button"
        onClick={toggle}
        className="w-full text-left p-3 hover:bg-slate-50 transition-colors"
        data-testid={`equipment-row-toggle-${item.id}`}
        aria-expanded={open}
      >
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Wrench size={16} className="text-blue-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900 truncate">
              {item.name}
              <span className="ml-2 text-[11px] font-medium text-slate-500">
                {item.manufacturer ? `${item.manufacturer} ` : ''}{item.model || ''}
              </span>
            </p>
            <div className="mt-1 flex items-center flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
              {item.equipment_type && (
                <span className="inline-flex items-center gap-1">{item.equipment_type}</span>
              )}
              {item.serial_number && (
                <span className="font-mono">SN {item.serial_number}</span>
              )}
              {item.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin size={10} /> {item.location}
                </span>
              )}
              {siteName && (
                <span className="inline-flex items-center gap-1">
                  <Building2 size={10} /> {siteName}
                </span>
              )}
              {item.customer_name && (
                <span className="inline-flex items-center gap-1 text-slate-600 font-semibold">
                  · {item.customer_name}
                </span>
              )}
            </div>
          </div>
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wide ${badge.cls}`}
          >
            {badge.label}
          </span>
          <span className="text-slate-400 ml-1" aria-hidden="true">
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </div>
      </button>

      {open && (
        <div
          className="border-t border-slate-100 bg-slate-50/60 px-3 py-3 space-y-2"
          data-testid={`equipment-history-${item.id}`}
        >
          {loading ? (
            <div className="flex items-center gap-2 text-[11px] text-slate-500">
              <Loader2 size={11} className="animate-spin" /> Loading service history…
            </div>
          ) : error ? (
            <p className="text-[11px] text-rose-600 flex items-center gap-1">
              <AlertTriangle size={11} /> {error}
            </p>
          ) : history && history.visits && history.visits.length > 0 ? (
            <ServiceHistory data={history} />
          ) : (
            <p
              className="text-[11px] text-slate-500 italic"
              data-testid={`equipment-history-empty-${item.id}`}
            >
              No service visits logged for this asset yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Iter 220cm — ServiceHistory panel
// Renders the rollup: counters + a compact timeline of recent visits.
// ─────────────────────────────────────────────────────────────────────

function ServiceHistory({ data }) {
  const totals = data.totals || {};
  const visits = data.visits || [];
  const partsCost = totals.parts_cost || {};
  const fmtDate = (iso) => {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
      });
    } catch {
      return iso.slice(0, 10);
    }
  };
  const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', {
    minimumFractionDigits: 0, maximumFractionDigits: 2,
  })}`;
  const approvedSpend = Number(partsCost.approved_gbp || 0);
  const pendingSpend = Number(partsCost.pending_gbp || 0);
  const hasSpend = approvedSpend > 0 || pendingSpend > 0;

  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <Stat icon={Sparkles} label="Visits" value={totals.visit_count || 0}
              testid="equipment-history-visits" />
        <Stat icon={Wrench} label="Serviced" value={totals.serviced_count || 0}
              testid="equipment-history-serviced" />
        <Stat icon={Clock} label="Last visit"
              value={totals.last_visit ? fmtDate(totals.last_visit) : '—'}
              testid="equipment-history-last" />
      </div>
      {hasSpend && (
        <div
          className="rounded-xl border border-amber-200 bg-amber-50/60 px-2.5 py-2 flex items-center gap-2 flex-wrap"
          data-testid="equipment-history-parts-cost"
        >
          <div className="w-7 h-7 rounded-lg bg-white border border-amber-200 flex items-center justify-center flex-shrink-0">
            <PoundSterling size={12} className="text-amber-700" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase font-bold tracking-wider text-amber-700">
              Parts spend on this machine
            </p>
            <div className="flex items-center flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
              <span
                className="text-sm font-bold text-slate-900 tabular-nums"
                data-testid="equipment-history-parts-cost-approved"
              >
                {fmtGBP(approvedSpend)}
                <span className="ml-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wide">
                  approved
                </span>
              </span>
              {pendingSpend > 0 && (
                <span
                  className="text-[11px] text-amber-800 font-semibold tabular-nums"
                  data-testid="equipment-history-parts-cost-pending"
                >
                  + {fmtGBP(pendingSpend)} pending
                </span>
              )}
              <span className="text-[10px] text-slate-500">
                across {partsCost.request_count || 0}{' '}
                request{(partsCost.request_count || 0) === 1 ? '' : 's'}
              </span>
            </div>
          </div>
        </div>
      )}
      <ol className="mt-1 space-y-1.5" data-testid="equipment-history-timeline">
        {visits.slice(0, 8).map((v) => {
          const visitCost = v.parts_cost || {};
          const visitApproved = Number(visitCost.approved_gbp || 0);
          const visitPending = Number(visitCost.pending_gbp || 0);
          return (
          <li
            key={v.machine_row_id}
            className="bg-white rounded-xl border border-slate-200 p-2"
            data-testid={`equipment-history-visit-${v.machine_row_id}`}
          >
            <div className="flex items-start gap-2">
              <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
                <FileText size={12} className="text-slate-500" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-slate-900 truncate">
                  {v.case_reference || 'Job'}{v.case_title ? ` · ${v.case_title}` : ''}
                </p>
                <div className="mt-0.5 flex items-center flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-slate-500">
                  <span>{fmtDate(v.visit_date)}</span>
                  {v.engineer_name && <span>· {v.engineer_name}</span>}
                  {v.case_status && (
                    <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-bold uppercase tracking-wide">
                      {v.case_status}
                    </span>
                  )}
                  {v.serviced && (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-bold">
                      ✓ Serviced
                    </span>
                  )}
                  {v.cleaned && (
                    <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-bold">
                      ✓ Cleaned
                    </span>
                  )}
                  {(v.photos_count || 0) > 0 && (
                    <span className="inline-flex items-center gap-0.5">
                      <Camera size={10} /> {v.photos_count}
                    </span>
                  )}
                  {visitApproved > 0 && (
                    <span
                      className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 font-bold inline-flex items-center gap-0.5 tabular-nums"
                      data-testid={`equipment-history-visit-cost-${v.machine_row_id}`}
                    >
                      <PoundSterling size={9} />{fmtGBP(visitApproved).replace('£', '')}
                    </span>
                  )}
                  {visitApproved === 0 && visitPending > 0 && (
                    <span
                      className="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 font-bold inline-flex items-center gap-0.5 tabular-nums"
                      data-testid={`equipment-history-visit-cost-pending-${v.machine_row_id}`}
                      title="Parts requested, awaiting admin approval"
                    >
                      <PoundSterling size={9} />{fmtGBP(visitPending).replace('£', '')} pending
                    </span>
                  )}
                </div>
                {v.notes && (
                  <p className="mt-1 text-[11px] text-slate-600 leading-snug line-clamp-2">
                    {v.notes}
                  </p>
                )}
              </div>
            </div>
          </li>
          );
        })}
      </ol>
      {visits.length > 8 && (
        <p className="text-[10px] text-slate-400 italic mt-1">
          + {visits.length - 8} older visit{visits.length - 8 === 1 ? '' : 's'} not shown
        </p>
      )}
    </>
  );
}

function Stat({ icon: Icon, label, value, testid }) {
  return (
    <div
      className="bg-white rounded-lg border border-slate-200 p-2"
      data-testid={testid}
    >
      <div className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
        <Icon size={10} /> {label}
      </div>
      <div className="text-sm font-bold text-slate-900 truncate">{value}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Create form (default export of a sibling file)
// ─────────────────────────────────────────────────────────────────────

export function EngineerEquipmentForm() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const caseId = params.get('case_id') || '';

  const [picklists, setPicklists] = useState(null);
  const [manufacturerList, setManufacturerList] = useState([]);
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    name: '',
    equipment_type: '',
    manufacturer: '',
    manufacturer_other: '',
    model: '',
    location: '',
    site_id: '',
    serial_number: '',
    status: 'in_service',
    notes: '',
  });
  const [errors, setErrors] = useState({});

  // Load picklists + manufacturers in parallel.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingMeta(true);
      try {
        const [p, m] = await Promise.all([
          axios.get(`${API}/svc/engineer/equipment/picklists`, auth()),
          axios.get(`${API}/equipment/manufacturers`, auth()).catch(() => ({ data: { manufacturers: [] } })),
        ]);
        if (cancelled) return;
        setPicklists(p.data);
        setManufacturerList(m.data?.manufacturers || []);
        // Auto-pick site if exactly one.
        if ((p.data?.sites || []).length === 1) {
          setForm((f) => ({ ...f, site_id: p.data.sites[0].id }));
        }
      } catch (e) {
        if (!cancelled) {
          notify.error('Could not load form options', e?.response?.data?.detail || e?.message);
        }
      } finally {
        if (!cancelled) setLoadingMeta(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const sites = picklists?.sites || [];
  const requireSite = sites.length > 1;

  const set = (k) => (e) => {
    const v = typeof e === 'string' ? e : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
    if (errors[k]) setErrors((er) => ({ ...er, [k]: undefined }));
  };

  const validate = () => {
    const er = {};
    if (!form.name.trim()) er.name = 'Required';
    if (!form.equipment_type) er.equipment_type = 'Required';
    const finalManufacturer = (form.manufacturer === '__other__'
      ? form.manufacturer_other
      : form.manufacturer).trim();
    if (!finalManufacturer || finalManufacturer.length < 2) {
      er.manufacturer = 'Required';
    }
    if (!form.model.trim()) er.model = 'Required';
    if (!form.location) er.location = 'Required';
    if (requireSite && !form.site_id) er.site_id = 'Pick a site';
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (!validate()) {
      notify.error('Please fill in all required fields');
      return;
    }
    setSaving(true);
    try {
      const manufacturer = (form.manufacturer === '__other__'
        ? form.manufacturer_other
        : form.manufacturer).trim();
      const payload = {
        name: form.name.trim(),
        equipment_type: form.equipment_type,
        manufacturer,
        model: form.model.trim(),
        location: form.location,
        status: form.status,
      };
      if (form.serial_number.trim()) payload.serial_number = form.serial_number.trim();
      if (form.site_id) payload.site_id = form.site_id;
      if (form.notes.trim()) payload.notes = form.notes.trim();
      const qs = caseId ? `?case_id=${encodeURIComponent(caseId)}` : '';
      const r = await axios.post(
        `${API}/svc/engineer/equipment${qs}`,
        payload,
        auth(),
      );
      const attached = r.data?.attached_to_case;
      notify.success(
        attached
          ? `Added ${form.name} to this job`
          : `Saved ${form.name} to equipment`,
      );
      if (caseId) {
        navigate(`/svc/engineer/jobs/${caseId}`);
      } else {
        navigate('/svc/engineer/equipment');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map((d) => d.msg || d.loc?.join('.')).join(', ')
        : (detail || err?.message || 'Save failed');
      notify.error('Could not save', msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 pb-24" data-testid="engineer-equipment-form-page">
      <div className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="w-9 h-9 rounded-xl border border-slate-200 flex items-center justify-center text-slate-600 hover:bg-slate-50"
            data-testid="equipment-form-back-btn"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900 leading-tight">Add equipment</p>
            <p className="text-[11px] text-slate-500 leading-tight">
              {caseId ? 'Will be attached to the current job' : 'Flows into Operations'}
            </p>
          </div>
        </div>
      </div>

      {loadingMeta ? (
        <div className="flex items-center justify-center py-12 text-slate-400">
          <Loader2 size={16} className="animate-spin mr-2" /> Loading options…
        </div>
      ) : (
        <form
          onSubmit={submit}
          className="max-w-2xl mx-auto px-4 py-4 space-y-3"
          noValidate
        >
          <FormField label="Name" required error={errors.name}>
            <input
              type="text"
              value={form.name}
              onChange={set('name')}
              placeholder="e.g. Treadmill #14"
              maxLength={120}
              className={inputCls(errors.name)}
              data-testid="equipment-form-name"
            />
          </FormField>

          <FormField label="Type" required error={errors.equipment_type}>
            <select
              value={form.equipment_type}
              onChange={set('equipment_type')}
              className={inputCls(errors.equipment_type)}
              data-testid="equipment-form-type"
            >
              <option value="">Select type…</option>
              {(picklists?.equipment_type_options || []).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </FormField>

          <FormField label="Manufacturer" required error={errors.manufacturer}>
            <select
              value={form.manufacturer}
              onChange={set('manufacturer')}
              className={inputCls(errors.manufacturer)}
              data-testid="equipment-form-manufacturer"
            >
              <option value="">Select manufacturer…</option>
              {manufacturerList.map((m) => (
                <option key={m.domain || m.name} value={m.name}>{m.name}</option>
              ))}
              <option value="__other__">Other (enter manually)</option>
            </select>
            {form.manufacturer === '__other__' && (
              <input
                type="text"
                value={form.manufacturer_other}
                onChange={set('manufacturer_other')}
                placeholder="Manufacturer name"
                maxLength={80}
                className={`mt-2 ${inputCls(errors.manufacturer)}`}
                data-testid="equipment-form-manufacturer-other"
              />
            )}
          </FormField>

          <FormField label="Model" required error={errors.model}>
            <input
              type="text"
              value={form.model}
              onChange={set('model')}
              placeholder="e.g. Integrity DX"
              maxLength={80}
              className={inputCls(errors.model)}
              data-testid="equipment-form-model"
            />
          </FormField>

          <FormField label="Location" required error={errors.location}>
            <select
              value={form.location}
              onChange={set('location')}
              className={inputCls(errors.location)}
              data-testid="equipment-form-location"
            >
              <option value="">Select location…</option>
              {(picklists?.location_options || []).map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </FormField>

          {requireSite && (
            <FormField label="Site" required error={errors.site_id}>
              <select
                value={form.site_id}
                onChange={set('site_id')}
                className={inputCls(errors.site_id)}
                data-testid="equipment-form-site"
              >
                <option value="">Select site…</option>
                {sites.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </FormField>
          )}

          <FormField label="Serial number" hint="Recommended — scan or read from the sticker">
            <input
              type="text"
              value={form.serial_number}
              onChange={set('serial_number')}
              placeholder="e.g. LF-12345"
              maxLength={80}
              className={inputCls()}
              data-testid="equipment-form-serial"
            />
          </FormField>

          <FormField label="Status">
            <select
              value={form.status}
              onChange={set('status')}
              className={inputCls()}
              data-testid="equipment-form-status"
            >
              {(picklists?.status_options || []).map((s) => (
                <option key={s} value={s}>
                  {(STATUS_BADGE[s] || {}).label || s}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Notes" hint="Visible to the operations portal">
            <textarea
              value={form.notes}
              onChange={set('notes')}
              rows={3}
              maxLength={2000}
              placeholder="Anything Ops should know about this machine…"
              className={`${inputCls()} resize-none`}
              data-testid="equipment-form-notes"
            />
          </FormField>

          <button
            type="submit"
            disabled={saving}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-blue-600 text-white text-sm font-bold disabled:opacity-50 hover:bg-blue-700"
            data-testid="equipment-form-submit"
          >
            {saving ? (
              <><Loader2 size={14} className="animate-spin" /> Saving…</>
            ) : (
              <><CheckCircle2 size={14} /> {caseId ? 'Add to job' : 'Save equipment'}</>
            )}
          </button>
        </form>
      )}
    </div>
  );
}

function FormField({ label, required, hint, error, children }) {
  return (
    <div>
      <label className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-1 flex items-center gap-1">
        {label}
        {required && <span className="text-rose-600">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="mt-1 text-[11px] text-slate-400">{hint}</p>
      )}
      {error && (
        <p className="mt-1 text-[11px] text-rose-600 font-semibold">{error}</p>
      )}
    </div>
  );
}

function inputCls(hasError) {
  return (
    'w-full px-3 py-2.5 rounded-xl border text-sm bg-white focus:outline-none ' +
    'focus:ring-2 focus:ring-blue-500 ' +
    (hasError ? 'border-rose-400' : 'border-slate-200')
  );
}
