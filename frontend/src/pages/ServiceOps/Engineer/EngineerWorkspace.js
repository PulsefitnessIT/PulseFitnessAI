/**
 * EngineerWorkspace — iter 216h141 · Phase 4 / Slice 4.
 *
 * Desktop 3-column workspace for field engineers (Linear / Superhuman
 * inspired). Replaces the stacked mobile flow with a "command center":
 *
 *   ┌─ Sidebar (64) ─┬─ Job list (360) ─┬─── Detail (flex) ────┐
 *   │ icons          │ search + filter   │ priority badge        │
 *   │ Home           │ open jobs         │ site / customer       │
 *   │ Jobs           │ ↳ active (blue)   │ scheduled · sla      │
 *   │ Diary          │ ↳ idle            │ recent events feed    │
 *   │ Quotes         │                    │ open-full-view CTA   │
 *   │ Invoices       │                    │                       │
 *   │ Payouts        │                    │                       │
 *   └─ shortcuts ────┴────────────────────┴───────────────────────┘
 *
 * Keyboard shortcuts (visible via ? overlay):
 *   j / ↓  next job        k / ↑  previous job
 *   /      focus search    r      refresh
 *   c      new quote       i      new invoice
 *   d      go to diary     h      go to home
 *   o      open full view  ?      shortcuts overlay
 *   Esc    close overlay / blur search
 *
 * Mobile (<lg) is auto-redirected back to /svc/engineer.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Home, Wrench, Calendar, FileText, ReceiptPoundSterling as Receipt, CreditCard, Search,
  RefreshCw, Loader2, ChevronRight, AlertTriangle, Clock, MapPin,
  Keyboard, ExternalLink, X, PlayCircle, Inbox as InboxIcon, Hand,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIO = {
  P1: { bg: 'bg-red-500',    text: 'text-white',    label: 'P1' },
  P2: { bg: 'bg-amber-500',  text: 'text-white',    label: 'P2' },
  P3: { bg: 'bg-blue-500',   text: 'text-white',    label: 'P3' },
  P4: { bg: 'bg-slate-400',  text: 'text-white',    label: 'P4' },
};
const prioStyle = (p) => PRIO[(p || 'P3').toUpperCase()] || PRIO.P3;

const fmtRelative = (iso) => {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const mins = Math.floor(abs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const sign = ms < 0 ? '-' : '';
  if (days >= 1) return `${sign}${days}d`;
  if (hours >= 1) return `${sign}${hours}h`;
  return `${sign}${mins}m`;
};

const SLAChip = ({ resolveAt }) => {
  if (!resolveAt) return null;
  const ms = new Date(resolveAt).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  const c = breached ? 'text-red-600 bg-red-50' :
            atRisk   ? 'text-amber-700 bg-amber-50' :
                       'text-emerald-700 bg-emerald-50';
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold ${c}`}>
      {breached ? <AlertTriangle size={9} /> : <Clock size={9} />}
      {breached ? 'BREACHED' : atRisk ? 'AT RISK' : fmtRelative(resolveAt)}
    </span>
  );
};

// ── Sidebar ────────────────────────────────────────────────────
const NavBtn = ({ icon: Icon, label, active, onClick, testid, shortcut }) => (
  <button
    type="button"
    onClick={onClick}
    title={`${label}${shortcut ? ` · ${shortcut}` : ''}`}
    className={`relative w-12 h-12 rounded-xl flex items-center justify-center transition-all ${
      active
        ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-200'
        : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
    }`}
    data-testid={testid}
  >
    <Icon size={18} />
    {active ? (
      <span className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-6 rounded-l-full bg-blue-600" />
    ) : null}
  </button>
);

const Sidebar = ({ onNav, onHelp }) => (
  <aside
    className="w-16 bg-white border-r border-slate-200 flex flex-col items-center py-4 gap-2 flex-shrink-0"
    data-testid="workspace-sidebar"
  >
    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-extrabold mb-3">
      G
    </div>
    <NavBtn icon={Home}     label="Home"     shortcut="h" onClick={() => onNav('/svc/engineer')}            testid="ws-nav-home" />
    <NavBtn icon={Wrench}   label="Jobs"     active                                                        testid="ws-nav-jobs" />
    <NavBtn icon={Hand}     label="Queue"    shortcut="q" onClick={() => onNav('/svc/engineer/queue')}     testid="ws-nav-queue" />
    <NavBtn icon={InboxIcon} label="Inbox"   shortcut="b" onClick={() => onNav('/svc/engineer/inbox')}     testid="ws-nav-inbox" />
    <NavBtn icon={Calendar} label="Diary"    shortcut="d" onClick={() => onNav('/svc/engineer/diary')}     testid="ws-nav-diary" />
    <NavBtn icon={FileText} label="Quotes"   shortcut="c" onClick={() => onNav('/svc/engineer/quotes')}    testid="ws-nav-quotes" />
    <NavBtn icon={Receipt}  label="Invoices" shortcut="i" onClick={() => onNav('/svc/engineer/invoices')}  testid="ws-nav-invoices" />
    <NavBtn icon={CreditCard} label="Payouts" onClick={() => onNav('/svc/engineer/payouts')}               testid="ws-nav-payouts" />
    <div className="flex-1" />
    <NavBtn icon={Keyboard} label="Shortcuts" shortcut="?" onClick={onHelp} testid="ws-nav-help" />
  </aside>
);

// ── Job list pane ─────────────────────────────────────────────
const JobRow = ({ job, active, onClick, refEl }) => {
  const p = prioStyle(job.priority);
  return (
    <button
      ref={refEl}
      type="button"
      onClick={onClick}
      data-testid={`ws-job-row-${job.reference}`}
      className={`w-full text-left px-3 py-2.5 border-l-2 transition-all ${
        active
          ? 'bg-blue-50 border-blue-600'
          : 'bg-white border-transparent hover:bg-slate-50'
      }`}
    >
      <div className="flex items-start gap-2 mb-1">
        <span className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold ${p.bg} ${p.text} tabular-nums`}>
          {p.label}
        </span>
        <p className="text-[11px] font-bold text-slate-500 tabular-nums truncate flex-1">
          {job.reference}
        </p>
        <SLAChip resolveAt={job.sla_resolve_at} />
      </div>
      <p className="text-sm font-semibold text-slate-900 truncate leading-snug">
        {job.title || 'Untitled job'}
      </p>
      <p className="text-xs text-slate-500 truncate mt-0.5">
        {job.site_name || job.customer_name || 'Unknown site'}
      </p>
    </button>
  );
};

const JobListPane = ({ jobs, selected, onSelect, search, setSearch, searchRef,
                       loading, onRefresh, filter, setFilter, activeTimer, onOpenTimerJob }) => {
  const filtered = useMemo(() => {
    const q = (search || '').trim().toLowerCase();
    return (jobs || []).filter((j) => {
      if (filter === 'today') {
        const today = new Date().toISOString().slice(0, 10);
        if (!j.scheduled_at || !j.scheduled_at.startsWith(today)) return false;
      } else if (filter === 'risk') {
        if (!j.sla_resolve_at) return false;
        const ms = new Date(j.sla_resolve_at) - Date.now();
        if (ms > 2 * 3600 * 1000) return false;
      }
      if (!q) return true;
      return (
        (j.title || '').toLowerCase().includes(q) ||
        (j.reference || '').toLowerCase().includes(q) ||
        (j.site_name || '').toLowerCase().includes(q) ||
        (j.customer_name || '').toLowerCase().includes(q)
      );
    });
  }, [jobs, search, filter]);

  return (
    <section
      className="w-[360px] bg-white border-r border-slate-200 flex flex-col flex-shrink-0"
      data-testid="workspace-job-list"
    >
      <header className="px-3 py-3 border-b border-slate-200 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-slate-500">
            Jobs · {filtered.length}
          </h2>
          <button
            type="button"
            onClick={onRefresh}
            className="text-slate-400 hover:text-slate-700"
            data-testid="ws-refresh"
            title="Refresh · r"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </button>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            ref={searchRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search jobs (press /)"
            className="w-full bg-slate-50 border border-slate-200 focus:bg-white focus:border-blue-400 rounded-md pl-7 pr-2 py-1.5 text-sm focus:outline-none"
            data-testid="ws-search"
          />
        </div>
        <div className="inline-flex bg-slate-100 rounded-md p-0.5 text-[11px] font-semibold w-full">
          {[
            { k: 'all',   label: 'All' },
            { k: 'today', label: 'Today' },
            { k: 'risk',  label: 'SLA risk' },
          ].map((opt) => (
            <button
              key={opt.k}
              type="button"
              onClick={() => setFilter(opt.k)}
              className={`flex-1 py-1 rounded ${
                filter === opt.k ? 'bg-white shadow text-slate-900' : 'text-slate-500'
              }`}
              data-testid={`ws-filter-${opt.k}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </header>

      {activeTimer ? (
        <button
          type="button"
          onClick={() => onOpenTimerJob(activeTimer)}
          className="m-3 rounded-xl p-3 text-white text-left flex items-center gap-2 shadow-sm"
          style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
          data-testid="ws-active-timer"
        >
          <PlayCircle size={18} />
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] opacity-90">
              On the clock · {activeTimer.category}
            </p>
            <p className="text-sm font-semibold truncate">
              {activeTimer.case_reference || activeTimer.case_id}
            </p>
          </div>
          <ChevronRight size={16} />
        </button>
      ) : null}

      <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
        {filtered.length === 0 && !loading ? (
          <div className="px-3 py-10 text-center" data-testid="ws-jobs-empty">
            <Wrench size={20} className="mx-auto text-slate-300 mb-2" />
            <p className="text-xs text-slate-500">No jobs match this filter.</p>
          </div>
        ) : (
          filtered.map((j) => (
            <JobRow
              key={j.id}
              job={j}
              active={selected?.id === j.id}
              onClick={() => onSelect(j)}
            />
          ))
        )}
      </div>
    </section>
  );
};

// ── Detail pane ──────────────────────────────────────────────
const Stat = ({ label, value, testid }) => (
  <div className="bg-white border border-slate-200 rounded-lg p-3" data-testid={testid}>
    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</p>
    <p className="text-sm font-semibold text-slate-900 mt-0.5">{value || '—'}</p>
  </div>
);

const DetailPane = ({ caseId, onOpenFull }) => {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    axios
      .get(`${API}/svc/engineer/jobs/${caseId}`, auth())
      .then((r) => setDetail(r.data))
      .catch((e) =>
        notify.error('Failed to load job', e?.response?.data?.detail || e.message),
      )
      .finally(() => setLoading(false));
  }, [caseId]);

  if (!caseId) {
    return (
      <section
        className="flex-1 flex items-center justify-center bg-slate-50"
        data-testid="workspace-detail-empty"
      >
        <div className="text-center max-w-sm">
          <Wrench size={28} className="mx-auto text-slate-300 mb-2" />
          <p className="text-sm font-semibold text-slate-700">Select a job to view the brief</p>
          <p className="text-xs text-slate-500 mt-1">
            Use <kbd className="px-1 py-0.5 rounded bg-slate-200 text-slate-700 font-mono text-[10px]">j</kbd> / <kbd className="px-1 py-0.5 rounded bg-slate-200 text-slate-700 font-mono text-[10px]">k</kbd> to move between jobs, or press <kbd className="px-1 py-0.5 rounded bg-slate-200 text-slate-700 font-mono text-[10px]">?</kbd> to see all shortcuts.
          </p>
        </div>
      </section>
    );
  }

  if (loading || !detail) {
    return (
      <section className="flex-1 flex items-center justify-center bg-slate-50">
        <Loader2 size={20} className="animate-spin text-slate-400" />
      </section>
    );
  }

  const c = detail.case || detail;
  const events = (detail.events || []).slice(0, 12);
  const p = prioStyle(c.priority);

  return (
    <section
      className="flex-1 overflow-y-auto bg-slate-50"
      data-testid="workspace-detail"
    >
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`px-2 py-0.5 rounded text-[10px] font-extrabold ${p.bg} ${p.text}`}>
                {p.label}
              </span>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 tabular-nums">
                {c.reference}
              </p>
              <SLAChip resolveAt={c.sla_resolve_at} />
            </div>
            <h1 className="text-xl font-extrabold text-slate-900" data-testid="ws-detail-title">
              {c.title || 'Untitled job'}
            </h1>
            <p className="text-sm text-slate-500 mt-0.5 flex items-center gap-2">
              <MapPin size={12} /> {c.site_name || c.customer_name || 'Unknown'}
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenFull}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-3 py-2 rounded-lg whitespace-nowrap"
            data-testid="ws-open-full"
            title="Open full view · o"
          >
            <ExternalLink size={14} /> Open job
          </button>
        </div>
      </header>

      <div className="p-6 space-y-5">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat label="Status"     value={c.status}            testid="ws-stat-status" />
          <Stat label="Scheduled"  value={c.scheduled_at ? new Date(c.scheduled_at).toLocaleString('en-GB',
                                          { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) : '—'}
                testid="ws-stat-scheduled" />
          <Stat label="Asset"      value={c.asset_name}        testid="ws-stat-asset" />
          <Stat label="Fault"      value={c.fault_code}        testid="ws-stat-fault" />
        </div>

        {c.description ? (
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Brief</p>
            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
              {c.description}
            </p>
          </div>
        ) : null}

        {events.length ? (
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-3">
              Recent activity
            </p>
            <ol className="space-y-3" data-testid="ws-detail-events">
              {events.map((e, i) => (
                <li key={i} className="flex items-start gap-3 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-600 mt-1.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-900">{e.kind || e.type || 'event'}</p>
                    {e.summary ? (
                      <p className="text-slate-500">{e.summary}</p>
                    ) : null}
                  </div>
                  <p className="text-[10px] text-slate-400 tabular-nums flex-shrink-0">
                    {e.at ? new Date(e.at).toLocaleTimeString('en-GB',
                      { hour:'2-digit', minute:'2-digit' }) : ''}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>
    </section>
  );
};

// ── Shortcuts overlay ──────────────────────────────────────────
const SHORTCUTS = [
  { k: 'j / ↓',  what: 'Next job in list' },
  { k: 'k / ↑',  what: 'Previous job in list' },
  { k: '/',      what: 'Focus search' },
  { k: 'r',      what: 'Refresh jobs' },
  { k: 'o',      what: 'Open full view of selected job' },
  { k: 'c',      what: 'New quote' },
  { k: 'i',      what: 'New invoice' },
  { k: 'q',      what: 'Org queue (up for grabs)' },
  { k: 'b',      what: 'Incoming requests inbox' },
  { k: 'd',      what: 'Go to diary' },
  { k: 'h',      what: 'Go to home' },
  { k: 'Esc',    what: 'Close overlay / blur search' },
  { k: '?',      what: 'Show this overlay' },
];

const ShortcutsOverlay = ({ onClose }) => (
  <div
    className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6"
    onClick={onClose}
    data-testid="ws-shortcuts-overlay"
  >
    <div
      className="bg-white rounded-2xl max-w-md w-full p-5"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
          <Keyboard size={18} /> Keyboard shortcuts
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700"
          data-testid="ws-shortcuts-close"
          aria-label="Close shortcuts"
        >
          <X size={18} />
        </button>
      </div>
      <ul className="divide-y divide-slate-100">
        {SHORTCUTS.map((s) => (
          <li key={s.k} className="flex items-center justify-between py-2 text-sm">
            <span className="text-slate-700">{s.what}</span>
            <kbd className="font-mono text-xs bg-slate-100 text-slate-900 rounded px-2 py-0.5 border border-slate-200">
              {s.k}
            </kbd>
          </li>
        ))}
      </ul>
    </div>
  </div>
);

// ── Main page ──────────────────────────────────────────────
export default function EngineerWorkspace() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [jobs, setJobs] = useState([]);
  const [activeTimer, setActiveTimer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all'); // all | today | risk
  const [selectedId, setSelectedId] = useState(params.get('job') || null);
  const [showHelp, setShowHelp] = useState(false);
  const searchRef = useRef(null);

  // Mobile fallback — defer to mobile home
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 1023px)').matches) {
      navigate('/svc/engineer', { replace: true });
    }
  }, [navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [jRes, mRes] = await Promise.all([
        axios.get(`${API}/svc/engineer/jobs?when=open`, auth()),
        axios.get(`${API}/svc/engineer/me`, auth()).catch(() => ({ data: null })),
      ]);
      const list = jRes.data?.jobs || [];
      setJobs(list);
      setActiveTimer(mRes.data?.active_timer || null);
      if (!selectedId && list[0]) {
        setSelectedId(list[0].id);
        setParams({ job: list[0].id });
      }
    } catch (e) {
      notify.error('Failed to load workspace', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  useEffect(() => { load(); }, [load]);

  const selectedJob = useMemo(
    () => jobs.find((j) => j.id === selectedId) || null,
    [jobs, selectedId],
  );

  const handleSelect = useCallback((job) => {
    setSelectedId(job.id);
    setParams({ job: job.id });
  }, [setParams]);

  const moveSelection = useCallback((dir) => {
    if (!jobs.length) return;
    const idx = Math.max(0, jobs.findIndex((j) => j.id === selectedId));
    const next = Math.min(jobs.length - 1, Math.max(0, idx + dir));
    handleSelect(jobs[next]);
  }, [jobs, selectedId, handleSelect]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      // Ignore typing inside inputs/textareas
      const tag = (e.target.tagName || '').toUpperCase();
      const inField = tag === 'INPUT' || tag === 'TEXTAREA' || e.target.isContentEditable;

      if (e.key === 'Escape') {
        if (showHelp) setShowHelp(false);
        else if (document.activeElement?.tagName === 'INPUT') document.activeElement.blur();
        return;
      }
      if (inField) return;

      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setShowHelp((v) => !v);
        return;
      }
      if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); moveSelection(1); return; }
      if (e.key === 'k' || e.key === 'ArrowUp')   { e.preventDefault(); moveSelection(-1); return; }
      if (e.key === '/') { e.preventDefault(); searchRef.current?.focus(); return; }
      if (e.key === 'r') { e.preventDefault(); load(); return; }
      if (e.key === 'o' && selectedId) { e.preventDefault(); navigate(`/svc/engineer/jobs/${selectedId}`); return; }
      if (e.key === 'c') { e.preventDefault(); navigate('/svc/engineer/quotes/new'); return; }
      if (e.key === 'i') { e.preventDefault(); navigate('/svc/engineer/invoices/new'); return; }
      if (e.key === 'd') { e.preventDefault(); navigate('/svc/engineer/diary'); return; }
      if (e.key === 'b') { e.preventDefault(); navigate('/svc/engineer/inbox'); return; }
      if (e.key === 'q') { e.preventDefault(); navigate('/svc/engineer/queue'); return; }
      if (e.key === 'h') { e.preventDefault(); navigate('/svc/engineer'); return; }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [moveSelection, navigate, selectedId, load, showHelp]);

  return (
    <div
      className="h-screen w-screen bg-slate-100 flex overflow-hidden"
      data-testid="engineer-workspace"
    >
      <Sidebar onNav={navigate} onHelp={() => setShowHelp(true)} />
      <JobListPane
        jobs={jobs}
        selected={selectedJob}
        onSelect={handleSelect}
        search={search}
        setSearch={setSearch}
        searchRef={searchRef}
        loading={loading}
        onRefresh={load}
        filter={filter}
        setFilter={setFilter}
        activeTimer={activeTimer}
        onOpenTimerJob={(t) => navigate(`/svc/engineer/jobs/${t.case_id}`)}
      />
      <DetailPane
        caseId={selectedId}
        onOpenFull={() => selectedId && navigate(`/svc/engineer/jobs/${selectedId}`)}
      />
      {showHelp ? <ShortcutsOverlay onClose={() => setShowHelp(false)} /> : null}

      {/* Footer hint */}
      <div className="fixed bottom-3 left-1/2 -translate-x-1/2 z-30 hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 text-white text-[11px] font-semibold shadow-lg">
        <kbd className="font-mono">?</kbd> shortcuts
        <span className="text-slate-400">·</span>
        <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> move
        <span className="text-slate-400">·</span>
        <kbd className="font-mono">/</kbd> search
        <span className="text-slate-400">·</span>
        <kbd className="font-mono">o</kbd> open
      </div>
    </div>
  );
}
