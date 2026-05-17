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
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, RefreshCw, Loader2, AlertTriangle, Clock, MapPin,
  Hand, CheckCircle2, X, ShieldCheck, Inbox,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIO = {
  P1: 'bg-red-500',
  P2: 'bg-amber-500',
  P3: 'bg-blue-500',
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
  const [mins, setMins] = useState(job?.estimated_minutes || 60);
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
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Estimated minutes
            </span>
            <input
              type="number"
              min={15}
              max={600}
              step={15}
              value={mins}
              onChange={(e) => setMins(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="claim-minutes-input"
            />
          </label>
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
            disabled={busy}
            onClick={() =>
              onConfirm({
                scheduled_at: when ? new Date(when).toISOString() : null,
                estimated_minutes: Number(mins) || 60,
              })
            }
            className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white rounded-lg py-2 text-sm font-bold flex items-center justify-center gap-2"
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

// ── Row ──────────────────────────────────────────────────────
const Row = ({ job, onClaim }) => (
  <li className="p-3 sm:p-4 flex items-start gap-3" data-testid={`queue-row-${job.reference}`}>
    <span
      className={`w-1.5 self-stretch rounded-full ${PRIO[job.priority] || PRIO.P3} flex-shrink-0`}
      aria-hidden
    />
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1">
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-extrabold text-white ${PRIO[job.priority] || PRIO.P3}`}>
          {job.priority || 'P3'}
        </span>
        <p className="text-[11px] font-bold text-slate-500 tabular-nums truncate">
          {job.reference}
        </p>
        {fmtSLA(job.sla_resolve_at)}
        <span className="text-[10px] text-slate-400 ml-auto tabular-nums">
          {fmtRelative(job.created_at)} ago
        </span>
      </div>
      <p className="text-sm font-semibold text-slate-900 truncate">{job.title}</p>
      <p className="text-xs text-slate-500 mt-0.5 truncate flex items-center gap-1.5">
        <MapPin size={10} /> {job.site_name || job.customer_name || 'Site TBC'}
        {job.site_postcode ? ` · ${job.site_postcode}` : ''}
        {job.intake_channel ? <span className="text-slate-400">· {job.intake_channel}</span> : null}
      </p>
      {job.description ? (
        <p className="text-xs text-slate-500 mt-1 line-clamp-2 leading-snug">{job.description}</p>
      ) : null}
    </div>
    <button
      type="button"
      onClick={() => onClaim(job)}
      className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-1.5 flex-shrink-0"
      data-testid={`queue-claim-${job.reference}`}
    >
      <Hand size={12} /> Allocate to me
    </button>
  </li>
);

// ── Main page ──────────────────────────────────────────────
export default function EngineerQueue() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState({ total: 0, p1: 0, sla_breached_or_due: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [claimFor, setClaimFor] = useState(null);
  const [claimBusy, setClaimBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, s] = await Promise.all([
        axios.get(`${API}/svc/engineer/queue/unassigned`, auth()),
        axios.get(`${API}/svc/engineer/queue/stats`, auth()),
      ]);
      setJobs(j.data?.jobs || []);
      setStats(s.data || stats);
    } catch (e) {
      notify.error('Failed to load queue', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 30s so race-with-other-engineers doesn't show stale jobs.
  useEffect(() => {
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const filtered = useMemo(() => {
    if (filter === 'all') return jobs;
    if (filter === 'p1') return jobs.filter((j) => (j.priority || '').toUpperCase() === 'P1');
    if (filter === 'risk') return jobs.filter((j) => {
      if (!j.sla_resolve_at) return false;
      const ms = new Date(j.sla_resolve_at) - Date.now();
      return ms < 2 * 3600 * 1000;
    });
    return jobs;
  }, [jobs, filter]);

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
      navigate(`/svc/engineer/jobs/${r.data.case_id}`);
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
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
                GymAxis · Engineer
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <Hand size={20} /> Up for grabs
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

        {/* Filters */}
        <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 flex items-center gap-1">
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
                filter === opt.k ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
              data-testid={`queue-filter-${opt.k}`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* List */}
        {!loading && filtered.length === 0 ? (
          <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center" data-testid="queue-empty">
            <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-semibold text-slate-700">All caught up</p>
            <p className="text-xs text-slate-500 mt-1">
              No unassigned jobs in your org right now. We refresh this every 30 seconds.
            </p>
          </div>
        ) : (
          <ul className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
            {filtered.map((j) => (
              <Row key={j.id} job={j} onClaim={setClaimFor} />
            ))}
          </ul>
        )}

        {/* Footer hint */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-900 flex items-start gap-2">
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
    </div>
  );
}
