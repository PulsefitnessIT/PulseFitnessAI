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
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Search, AlertTriangle, Clock, CircleAlert, RefreshCw, Phone, Filter } from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceDeskIntakeForm from './ServiceDeskIntakeForm';
import ServiceCaseDrawer from './ServiceCaseDrawer';
import ServiceOpsShell, { SvcPrimaryButton, SvcSecondaryButton } from './ServiceOpsShell';

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

export default function ServiceDeskPage() {
  const [summary, setSummary] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ status: 'open', priority: '', search: '', sort: 'sla' });
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [lowStockCount, setLowStockCount] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, q, l] = await Promise.all([
        axios.get(`${API}/svc/desk/summary`, auth()),
        axios.get(`${API}/svc/cases`, {
          ...auth(),
          params: {
            status: filters.status || '',
            priority: filters.priority || '',
            search: filters.search || '',
            limit: 100,
          },
        }),
        axios.get(`${API}/svc/inventory/low-stock`, auth()).catch(() => ({ data: { count: 0 } })),
      ]);
      setSummary(s.data);
      setCases(q.data.cases || []);
      setLowStockCount(l.data?.count || 0);
    } catch (e) {
      notify.error('Failed to load service desk', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [filters.status, filters.priority, filters.search]);

  useEffect(() => { load(); }, [load]);
  // Auto-refresh every 60s — the SLA clock ticks against the user's screen.
  useEffect(() => {
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const k = summary?.kpis || {};

  const heroActions = (
    <>
      <SvcSecondaryButton icon={RefreshCw} onClick={load} data-testid="desk-refresh">
        Refresh
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
        <KPICard label="Closed (30d)" value={k.closed_last_30d ?? 0} tone="good" testId="kpi-closed" />
      </div>

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
                    <td className="text-xs svc-muted">{c.assigned_engineer_name || <span className="italic" style={{ opacity: 0.6 }}>unassigned</span>}</td>
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
