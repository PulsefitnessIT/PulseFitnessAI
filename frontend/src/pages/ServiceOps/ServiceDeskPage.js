/**
 * ServiceDeskPage — iter 215dn (Phase 1).
 *
 * Service Operations control centre:
 *  • KPI strip (open / unassigned / SLA at risk / breached / closed 30d)
 *  • Filterable queue with sort modes
 *  • One-click "Log new case" launches the intake form modal
 *  • Click a row → opens the Case Detail drawer with full timeline
 *
 * NOTE: this is the native replacement for the Sicon Service desk view.
 * The legacy Sicon panel still works in parallel until cutover (Phase 8).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Plus, Search, AlertTriangle, Clock, CircleAlert, RefreshCw, Phone, Filter,
  Sparkles, Users, MapPin, CheckCircle2, Truck, Coffee, Target, Wrench, Calendar,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceDeskIntakeForm from './ServiceDeskIntakeForm';
import ServiceCaseDrawer from './ServiceCaseDrawer';
import ServiceOpsShell, { SvcPrimaryButton, SvcSecondaryButton } from './ServiceOpsShell';
// Iter 216h78 — Engineer Roster (customer-grants UI for ad-hoc contractors)
import EngineerRosterPanel from './EngineerRosterPanel';
// Iter 216h80 — Find an engineer (verified partners, GymAxis-only)
import FindEngineerPanel from './FindEngineerPanel';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const PRIORITY_META = {
  p1: { label: 'P1', tone: 'p1' },
  p2: { label: 'P2', tone: 'p2' },
  p3: { label: 'P3', tone: 'p3' },
  p4: { label: 'P4', tone: 'p4' },
};

const STATUS_LABEL = {
  new: 'New', triaged: 'Triaged', assigned: 'Assigned', en_route: 'En route',
  on_site: 'On site', paused_parts: 'Waiting parts', paused_customer: 'Waiting customer',
  repaired: 'Repaired', awaiting_sign_off: 'Sign-off', closed: 'Closed', invoiced: 'Invoiced',
};

function fmtRelative(iso) {
  if (!iso) return '—';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const mins = Math.floor(abs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const sign = ms < 0 ? '-' : '';
  if (days >= 1) return `${sign}${days}d ${hours % 24}h`;
  if (hours >= 1) return `${sign}${hours}h ${mins % 60}m`;
  return `${sign}${mins}m`;
}

function SLAPill({ resolveAt }) {
  if (!resolveAt) return <span className="svc-muted text-xs">—</span>;
  const ms = new Date(resolveAt).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  const tone = breached ? 'danger' : atRisk ? 'warn' : 'good';
  const Icon = breached ? AlertTriangle : atRisk ? CircleAlert : Clock;
  return (
    <span className={`svc-pill svc-pill--${tone}`} data-testid="case-sla-pill">
      <Icon size={10} /> {breached ? 'Breached' : atRisk ? 'At risk' : fmtRelative(resolveAt)}
    </span>
  );
}

function KPICard({ label, value, tone = 'neutral', testId, hint }) {
  return (
    <div className={`svc-kpi svc-kpi--${tone}`} data-testid={testId}>
      <p className="svc-kpi-label">{label}</p>
      <p className="svc-kpi-value">{value === null || value === undefined ? '—' : value}</p>
      {hint ? <p className="svc-kpi-hint">{hint}</p> : null}
    </div>
  );
}

const LIVE_STATUS_META = {
  en_route:  { label: 'En route', tone: 'warn',    Icon: Truck },
  on_site:   { label: 'On site',  tone: 'info',    Icon: Wrench },
  assigned:  { label: 'Assigned', tone: 'violet',  Icon: Target },
  available: { label: 'Available', tone: 'good',   Icon: CheckCircle2 },
  off_duty:  { label: 'Off duty', tone: 'neutral', Icon: Coffee },
};

function LiveEngineerRow({ eng, onCaseClick }) {
  const meta = LIVE_STATUS_META[eng.live_status] || LIVE_STATUS_META.off_duty;
  const Icon = meta.Icon;
  return (
    <li
      className="flex items-center gap-3 p-2 rounded border"
      style={{ borderColor: 'var(--theme-border)' }}
      data-testid={`live-engineer-${eng.id}`}
    >
      <span
        className="inline-flex items-center justify-center rounded-full"
        style={{
          width: 28, height: 28,
          background: 'var(--theme-surface, #f8fafc)',
          border: '1px solid var(--theme-border)',
        }}
        aria-hidden
      >
        <Icon size={14} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-bold text-sm truncate">{eng.full_name || 'Engineer'}</span>
          <span className={`svc-pill svc-pill--${meta.tone}`} data-testid={`live-status-${eng.id}`}>
            {meta.label}
          </span>
          <span className="text-[11px] svc-muted ml-auto tabular-nums">
            {eng.open_cases ?? 0} open
          </span>
        </div>
        {eng.live_case ? (
          <button
            type="button"
            onClick={() => onCaseClick && onCaseClick(eng.live_case.id)}
            className="text-[11px] mt-0.5 inline-flex items-center gap-1 hover:underline text-left"
            style={{ color: 'var(--color-brand-blue, #1d4ed8)' }}
            data-testid={`live-case-link-${eng.id}`}
          >
            <MapPin size={10} />
            <span className="truncate">{eng.live_case.reference} · {eng.live_case.site_name || 'site'}</span>
          </button>
        ) : (
          <p className="text-[11px] svc-muted mt-0.5">
            {eng.skills?.length ? `${eng.skills.slice(0, 3).join(' · ')}` : 'No active job'}
          </p>
        )}
      </div>
    </li>
  );
}

function LiveEngineersPanel({ engineers, liveStats, loading, onCaseClick }) {
  // Sort: active field jobs first (en_route, on_site, assigned), then available, then off-duty
  const order = { en_route: 0, on_site: 1, assigned: 2, available: 3, off_duty: 4 };
  const sorted = [...(engineers || [])].sort(
    (a, b) => (order[a.live_status] ?? 9) - (order[b.live_status] ?? 9),
  );
  return (
    <div className="svc-section" data-testid="live-engineers-panel">
      <div className="svc-section-head">
        <div className="svc-section-title inline-flex items-center gap-1.5">
          <Users size={14} /> Live engineers
        </div>
        <div className="ml-auto flex items-center gap-1.5 flex-wrap">
          <span className="svc-pill svc-pill--warn" data-testid="live-count-en-route">
            <Truck size={10} /> {liveStats.en_route} en route
          </span>
          <span className="svc-pill svc-pill--info" data-testid="live-count-on-site">
            <Wrench size={10} /> {liveStats.on_site} on site
          </span>
          <span className="svc-pill svc-pill--violet" data-testid="live-count-assigned">
            <Target size={10} /> {liveStats.assigned} assigned
          </span>
          <span className="svc-pill svc-pill--good" data-testid="live-count-available">
            <CheckCircle2 size={10} /> {liveStats.available} available
          </span>
          <span className="svc-pill" data-testid="live-count-off-duty">
            <Coffee size={10} /> {liveStats.off_duty} off-duty
          </span>
        </div>
      </div>
      <div className="svc-section-body">
        {loading && sorted.length === 0 ? (
          <div className="svc-empty"><span className="svc-spinner" /> Loading engineer roster…</div>
        ) : sorted.length === 0 ? (
          <div className="svc-empty">
            <Users size={22} />
            <div>No engineers yet.</div>
            <div className="text-xs mt-1">Add engineers from the <strong>Engineers</strong> tab to see them here.</div>
          </div>
        ) : (
          <ul
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2"
            data-testid="live-engineers-list"
          >
            {sorted.map((eng) => (
              <LiveEngineerRow key={eng.id} eng={eng} onCaseClick={onCaseClick} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function ServiceDeskPage() {
  const [summary, setSummary] = useState(null);
  const [cases, setCases] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: 'open', priority: '', case_type: '', search: '', sort: 'sla' });
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [lowStockCount, setLowStockCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, q, l, eng] = await Promise.all([
        axios.get(`${API}/svc/desk/summary`, auth()),
        axios.get(`${API}/svc/cases`, {
          ...auth(),
          params: {
            status: filters.status || '',
            priority: filters.priority || '',
            case_type: filters.case_type || '',
            search: filters.search || '',
            limit: 100,
          },
        }),
        axios.get(`${API}/svc/inventory/low-stock`, auth()).catch(() => ({ data: { count: 0 } })),
        axios.get(`${API}/svc/desk/engineers`, auth()).catch(() => ({ data: { engineers: [] } })),
      ]);
      setSummary(s.data);
      setCases(q.data.cases || []);
      setLowStockCount(l.data?.count || 0);
      setEngineers(eng.data?.engineers || []);
    } catch (e) {
      notify.error('Failed to load service desk', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [filters.status, filters.priority, filters.case_type, filters.search]);

  useEffect(() => { load(); }, [load]);
  // Auto-refresh every 60s — the SLA clock ticks against the user's screen.
  useEffect(() => {
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const k = summary?.kpis || {};

  const liveStats = useMemo(() => {
    const s = { en_route: 0, on_site: 0, assigned: 0, available: 0, off_duty: 0 };
    for (const e of engineers) {
      const ls = e.live_status || 'off_duty';
      if (s[ls] !== undefined) s[ls] += 1;
    }
      return s;
  }, [engineers]);
  const totalEngineers = engineers.length;
  const activeFieldEngineers = liveStats.en_route + liveStats.on_site + liveStats.assigned;

  const heroActions = (
    <>
      <SvcSecondaryButton icon={RefreshCw} onClick={load} data-testid="desk-refresh">
        Refresh
      </SvcSecondaryButton>
      <SvcSecondaryButton
        icon={Calendar}
        onClick={() => (window.location.href = '/service-desk/dispatch')}
        data-testid="desk-dispatch-board"
      >
        Dispatch
      </SvcSecondaryButton>
      <SvcPrimaryButton icon={Plus} onClick={() => setIntakeOpen(true)} data-testid="desk-log-case">
        Log new case
      </SvcPrimaryButton>
    </>
  );

  return (
    <ServiceOpsShell
      icon={Phone}
      title="Service desk"
      subtitle="Live queue of every open case across your sites. SLA at risk first — click any row for the full timeline."
      actions={heroActions}
      active="desk"
      lowStockCount={lowStockCount}
      pageTestId="service-desk-page"
    >
      <div className="svc-kpi-grid" data-testid="desk-kpis">
        <KPICard label="Open" value={k.open} tone="info" testId="kpi-open" />
        <KPICard label="Unassigned" value={k.unassigned} tone={k.unassigned > 0 ? 'warn' : 'neutral'} testId="kpi-unassigned" />
        <KPICard label="SLA at risk" value={k.sla_at_risk} tone={k.sla_at_risk > 0 ? 'warn' : 'good'} testId="kpi-at-risk" />
        <KPICard label="Breached" value={k.sla_breached} tone={k.sla_breached > 0 ? 'danger' : 'good'} testId="kpi-breached" />
        <KPICard
          label="First-time fix"
          value={k.first_time_fix_pct === null || k.first_time_fix_pct === undefined ? '—' : `${k.first_time_fix_pct}%`}
          tone={(k.first_time_fix_pct ?? 0) >= 80 ? 'good' : (k.first_time_fix_pct ?? 0) >= 60 ? 'warn' : 'danger'}
          hint={`${k.closed_last_30d ?? 0} closed (30d)`}
          testId="kpi-ftf"
        />
        <KPICard
          label="Avg resolve"
          value={k.avg_resolve_hours === null || k.avg_resolve_hours === undefined ? '—' : `${k.avg_resolve_hours}h`}
          tone="info"
          hint="Mean over 30 days"
          testId="kpi-avg-resolve"
        />
        <KPICard
          label="Skill gap"
          value={k.skill_gap ?? 0}
          tone={(k.skill_gap ?? 0) > 0 ? 'warn' : 'neutral'}
          hint="No matched engineer"
          testId="kpi-skill-gap"
        />
        <KPICard
          label="Field engineers"
          value={`${activeFieldEngineers}/${totalEngineers}`}
          tone="info"
          hint={`${liveStats.en_route} en route · ${liveStats.on_site} on-site`}
          testId="kpi-field-engineers"
        />
      </div>

      <LiveEngineersPanel
        engineers={engineers}
        liveStats={liveStats}
        loading={loading}
        onCaseClick={setActiveCaseId}
      />

      <EngineerRosterPanel />

      <FindEngineerPanel />

      <div className="svc-section">
        <div className="svc-section-head">
          <div className="flex items-center gap-1.5 text-xs font-bold svc-muted">
            <Filter size={12} /> Filters
          </div>
          <select
            value={filters.status}
            onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
            className="svc-select svc-select-sm"
            style={{ width: 'auto' }}
            data-testid="filter-status"
          >
            <option value="open">All open</option>
            <option value="new">New</option>
            <option value="assigned">Assigned</option>
            <option value="en_route">En route</option>
            <option value="on_site">On site</option>
            <option value="paused_parts">Waiting parts</option>
            <option value="awaiting_sign_off">Sign-off</option>
            <option value="closed">Closed</option>
          </select>
          <select
            value={filters.priority}
            onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value }))}
            className="svc-select svc-select-sm"
            style={{ width: 'auto' }}
            data-testid="filter-priority"
          >
            <option value="">All priorities</option>
            <option value="p1">P1 — Critical</option>
            <option value="p2">P2 — High</option>
            <option value="p3">P3 — Standard</option>
            <option value="p4">P4 — Low</option>
          </select>
          <select
            value={filters.case_type}
            onChange={(e) => setFilters((f) => ({ ...f, case_type: e.target.value }))}
            className="svc-select svc-select-sm"
            style={{ width: 'auto' }}
            data-testid="filter-case-type"
          >
            <option value="">All types</option>
            <option value="repair">Repair</option>
            <option value="ppm">PPM</option>
            <option value="install">Install</option>
          </select>
          <div className="svc-search ml-auto" style={{ width: 280 }}>
            <Search size={13} />
            <input
              type="text"
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              placeholder="Search reference, title, customer…"
              className="svc-input svc-input-sm"
              data-testid="filter-search"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="svc-table" style={{ minWidth: '60rem' }}>
            <thead>
              <tr>
                <th>Ref</th>
                <th>Pri</th>
                <th>Title</th>
                <th>Site</th>
                <th>Status</th>
                <th>Engineer</th>
                <th className="num">SLA</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="7"><div className="svc-empty"><span className="svc-spinner" /> Loading cases…</div></td></tr>
              ) : cases.length === 0 ? (
                <tr><td colSpan="7"><div className="svc-empty">
                  <Phone size={22} />
                  <div>No cases match the current filters.</div>
                  <div className="text-xs mt-1">Click <strong>Log new case</strong> to create one.</div>
                </div></td></tr>
              ) : cases.map((c) => {
                const pri = PRIORITY_META[c.priority] || PRIORITY_META.p3;
                return (
                  <tr
                    key={c.id}
                    onClick={() => setActiveCaseId(c.id)}
                    className="svc-row--clickable"
                    data-testid={`case-row-${c.reference}`}
                  >
                    <td className="font-bold tabular-nums">{c.reference}</td>
                    <td><span className={`svc-prio svc-prio--${pri.tone}`}>{pri.label}</span></td>
                    <td style={{ maxWidth: '20rem' }}>
                      <div className="font-semibold truncate">{c.title}</div>
                      <div className="text-[11px] svc-muted truncate">{c.fault_code || c.fault_category || '—'}</div>
                    </td>
                    <td className="text-xs svc-muted">{c.site_name || '—'}</td>
                    <td className="text-xs"><span className="svc-pill">{STATUS_LABEL[c.status] || c.status}</span></td>
                    <td className="text-xs svc-muted">
                      {c.assigned_engineer_name ? (
                        c.assigned_engineer_name
                      ) : c.recommended_engineer_name ? (
                        <span
                          className="inline-flex items-center gap-1"
                          title={c.recommended_engineer_reason || 'AI suggestion'}
                          data-testid={`case-recommended-${c.reference}`}
                        >
                          <Sparkles size={11} style={{ color: '#1d4ed8' }} />
                          <span style={{ color: '#1d4ed8' }}>Suggest: {c.recommended_engineer_name}</span>
                        </span>
                      ) : (
                        <span className="italic" style={{ opacity: 0.6 }}>unassigned</span>
                      )}
                    </td>
                    <td className="num"><SLAPill resolveAt={c.sla_resolve_at} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {intakeOpen ? (
        <ServiceDeskIntakeForm
          onClose={() => setIntakeOpen(false)}
          onCreated={(c) => {
            setIntakeOpen(false);
            notify.success('Case logged', `${c.reference} — ${c.title}`);
            load();
            setActiveCaseId(c.id);
          }}
        />
      ) : null}

      {activeCaseId ? (
        <ServiceCaseDrawer
          caseId={activeCaseId}
          onClose={() => setActiveCaseId(null)}
          onChanged={load}
        />
      ) : null}
    </ServiceOpsShell>
  );
}
