/**
 * IntegrationsConsole — /admin/integrations (iter 215dy).
 *
 * Master-admin dashboard for Sicon Service Manager and Sage 200 UK.
 * Shows live config status, outbox health (pending / in-flight / dead-letter
 * counts, 24h success/failure rates, last-success-per-kind), and recent
 * outbox rows. Designed so the moment credentials land the UI lights up
 * with no further changes needed.
 *
 * Backed by:
 *   GET /api/integrations/admin/health
 *   GET /api/integrations/admin/sicon/outbox
 *   GET /api/integrations/admin/sage/outbox
 *   GET /api/integrations/admin/mapping/sections
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Cable, RefreshCw, AlertTriangle, Inbox,
  Database, Workflow, FileText, Zap, ZapOff, Cog, Play, FlaskConical, RotateCcw,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import '../ServiceOps/_serviceops.css';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const TABS = [
  { id: 'overview', label: 'Overview', icon: Workflow },
  { id: 'sicon',    label: 'Sicon Outbox', icon: Cable },
  { id: 'sage',     label: 'Sage Outbox',  icon: Database },
  { id: 'mapping',  label: 'Field Mapping',  icon: FileText },
];

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function StatusPip({ live, configured }) {
  if (live && configured) {
    return <span className="svc-pill svc-pill--good"><Zap size={10} /> Live</span>;
  }
  if (configured) {
    return <span className="svc-pill svc-pill--info"><Cog size={10} /> Configured</span>;
  }
  return <span className="svc-pill svc-pill--warn"><ZapOff size={10} /> Dry-run · awaiting credentials</span>;
}

function KPI({ label, value, tone, hint, testid }) {
  return (
    <div className={`svc-kpi svc-kpi--${tone || 'info'}`} data-testid={testid}>
      <p className="svc-kpi-label">{label}</p>
      <p className="svc-kpi-value">{value === null || value === undefined ? '—' : value}</p>
      {hint ? <p className="svc-kpi-hint">{hint}</p> : null}
    </div>
  );
}

function SystemCard({ name, system, testidPrefix, eyebrow, controls }) {
  const cfg = system.config || {};
  const ob  = system.outbox || {};
  return (
    <section className="svc-section" data-testid={`${testidPrefix}-card`}>
      <div className="svc-section-head">
        <div className="svc-section-title flex items-center gap-2">
          {name === 'Sicon' ? <Cable size={14} /> : <Database size={14} />}
          {name}
          <span className="svc-muted text-[11px] font-normal normal-case tracking-normal">
            {eyebrow}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <StatusPip live={system.live} configured={cfg.configured} />
          {controls}
        </div>
      </div>
      <div className="svc-section-body space-y-4">
        {/* Config readout */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[12px]">
          <div>
            <p className="svc-label">Configured tenants</p>
            <p className="font-bold tabular-nums">{cfg.tenant_count ?? 0}</p>
          </div>
          <div>
            <p className="svc-label">Env fallback</p>
            <p className="font-bold">{cfg.env_fallback_present ? 'present' : 'absent'}</p>
          </div>
          <div>
            <p className="svc-label">Last test</p>
            <p className="font-bold tabular-nums">{cfg.last_test_at ? fmtDate(cfg.last_test_at) : '—'}</p>
          </div>
          <div>
            <p className="svc-label">{name === 'Sicon' ? 'Base URL' : 'Tier'}</p>
            <p className="font-bold truncate" title={cfg.base_url || cfg.tier || '—'}>
              {cfg.base_url || cfg.tier || '—'}
            </p>
          </div>
        </div>

        {/* Outbox KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3" data-testid={`${testidPrefix}-outbox-kpis`}>
          <KPI label="Pending"      value={ob.pending}       tone={ob.pending > 0 ? 'warn' : 'good'}    testid={`${testidPrefix}-kpi-pending`} />
          <KPI label="In-flight"    value={ob.in_flight}     tone="info"                                 testid={`${testidPrefix}-kpi-inflight`} />
          <KPI label="Succeeded 24h" value={ob.succeeded_24h} tone="good"                                testid={`${testidPrefix}-kpi-success`} />
          <KPI label="Failed 24h"    value={ob.failed_24h}    tone={ob.failed_24h > 0 ? 'danger' : 'good'} testid={`${testidPrefix}-kpi-failed`} />
          <KPI label="Dead-letter"  value={ob.dead_letter}  tone={ob.dead_letter > 0 ? 'danger' : 'neutral'} testid={`${testidPrefix}-kpi-dlq`} />
        </div>

        {/* Last success per kind */}
        {Object.keys(ob.last_success_per_kind || {}).length > 0 ? (
          <div>
            <p className="svc-label" style={{ marginBottom: 6 }}>Last successful sync · per kind</p>
            <ul className="text-xs space-y-1 svc-card-base p-3">
              {Object.entries(ob.last_success_per_kind).map(([kind, at]) => (
                <li key={kind} className="flex justify-between gap-2">
                  <span className="svc-muted">{kind}</span>
                  <span className="tabular-nums">{fmtDate(at)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-[11.5px] svc-muted italic">No successful syncs yet — the worker will start draining the moment {name} credentials are configured.</p>
        )}
      </div>
    </section>
  );
}

function OutboxTable({ system, kindFilter, statusFilter, onChangeKind, onChangeStatus }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (kindFilter) params.set('kind', kindFilter);
      if (statusFilter) params.set('status', statusFilter);
      const r = await axios.get(`${API}/integrations/admin/${system}/outbox?${params}`, auth());
      setRows(r.data?.rows || []);
    } catch (e) {
      notify.error('Failed to load outbox', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [system, kindFilter, statusFilter]);
  useEffect(() => { load(); }, [load]);

  const kinds = useMemo(() => Array.from(new Set(rows.map((r) => r.kind))).filter(Boolean).sort(), [rows]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-end">
        <div>
          <p className="svc-label">Kind</p>
          <select value={kindFilter} onChange={(e) => onChangeKind(e.target.value)} className="svc-select svc-select-sm" data-testid={`${system}-filter-kind`}>
            <option value="">All</option>
            {kinds.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <p className="svc-label">Status</p>
          <select value={statusFilter} onChange={(e) => onChangeStatus(e.target.value)} className="svc-select svc-select-sm" data-testid={`${system}-filter-status`}>
            <option value="">All</option>
            <option value="pending">pending</option>
            <option value="in_flight">in_flight</option>
            <option value="simulated">simulated</option>
            <option value="simulated_succeeded">simulated_succeeded</option>
            <option value="succeeded">succeeded</option>
            <option value="posted">posted</option>
            <option value="submitted">submitted</option>
            <option value="failed">failed</option>
            <option value="dead_letter">dead_letter</option>
          </select>
        </div>
        <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm ml-auto" data-testid={`${system}-refresh`}>
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>
      <div className="svc-table-wrap">
        <table className="svc-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Kind</th>
              <th>Reference</th>
              <th>Status</th>
              <th>Attempts</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6"><div className="svc-empty"><span className="svc-spinner" /> Loading…</div></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan="6"><div className="svc-empty"><Inbox size={20} /><div>Outbox is empty.</div></div></td></tr>
            ) : rows.map((r, i) => {
              const tone = r.status === 'pending' ? 'warn'
                : r.status === 'in_flight' || r.status === 'simulated' ? 'info'
                : (r.status === 'succeeded' || r.status === 'posted' || r.status === 'submitted') ? 'good'
                : r.status === 'simulated_succeeded' ? 'violet'
                : (r.status === 'failed' || r.status === 'dead_letter') ? 'danger' : '';
              return (
                <tr key={`${r.kind}-${r.our_reference || r.id || i}`} data-testid={`${system}-outbox-row-${i}`}>
                  <td className="text-[11px] tabular-nums svc-muted">{fmtDate(r.updated_at || r.created_at)}</td>
                  <td className="text-[11px]"><span className="svc-pill">{r.kind}</span></td>
                  <td className="text-[11px] tabular-nums">{r.our_reference || r.kind_id || '—'}</td>
                  <td><span className={`svc-pill svc-pill--${tone}`}>{r.status}</span></td>
                  <td className="num">{r.attempts ?? 0}</td>
                  <td className="text-[11px] svc-muted truncate" style={{ maxWidth: '20rem' }} title={r.error || ''}>{r.error || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MappingTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/integrations/admin/mapping/sections`, auth());
        setData(r.data);
      } catch (e) {
        notify.error('Failed to load mapping doc', e?.response?.data?.detail || e.message);
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <div className="svc-empty"><span className="svc-spinner" /> Loading mapping doc…</div>;
  if (!data) return <div className="svc-empty">Mapping doc not available.</div>;

  return (
    <div className="space-y-4" data-testid="mapping-tab">
      <section className="svc-section">
        <div className="svc-section-head">
          <div className="svc-section-title">Module integration matrix</div>
        </div>
        <div className="svc-section-body">
          <p className="text-[11.5px] svc-muted mb-3">Which Pulse Fitness modules are wired to which external system. Source: <code>/app/memory/INTEGRATION_FIELD_MAPPING.md</code> § 0.</p>
          <div className="svc-table-wrap">
            <table className="svc-table">
              <thead>
                <tr>
                  <th>Module</th>
                  <th>Sicon</th>
                  <th>Sage 200</th>
                  <th>Direction</th>
                  <th>Section</th>
                </tr>
              </thead>
              <tbody>
                {(data.modules || []).map((m, i) => (
                  <tr key={i} data-testid={`mapping-module-row-${i}`}>
                    <td className="font-bold">{stripFormatting(m.module)}</td>
                    <td className="text-[11.5px]">{stripFormatting(m.sicon_summary)}</td>
                    <td className="text-[11.5px]">{stripFormatting(m.sage_summary)}</td>
                    <td className="text-[11.5px] svc-muted">{stripFormatting(m.direction)}</td>
                    <td className="text-[11.5px] tabular-nums">{stripFormatting(m.section_ref)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="svc-section">
          <div className="svc-section-head"><div className="svc-section-title">Master doc · sections</div></div>
          <div className="svc-section-body">
            <ul className="text-sm space-y-1">
              {(data.master || []).map((s, i) => (
                <li key={i} className="flex gap-2"><span className="svc-muted tabular-nums w-12">§ {s.section}</span><span>{s.title}</span></li>
              ))}
            </ul>
          </div>
        </section>
        <section className="svc-section">
          <div className="svc-section-head"><div className="svc-section-title">Legacy doc · Service Ops detail</div></div>
          <div className="svc-section-body">
            <ul className="text-sm space-y-1">
              {(data.legacy || []).map((s, i) => (
                <li key={i} className="flex gap-2"><span className="svc-muted tabular-nums w-12">§ {s.section}</span><span>{s.title}</span></li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}

function stripFormatting(s) {
  if (!s) return '';
  return String(s).replace(/\*\*/g, '').replace(/`/g, '');
}

export default function IntegrationsConsole() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [siconKind, setSiconKind] = useState('');
  const [siconStatus, setSiconStatus] = useState('');
  const [sageKind, setSageKind] = useState('');
  const [sageStatus, setSageStatus] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/integrations/admin/health`, auth());
      setHealth(r.data);
    } catch (e) {
      notify.error('Failed to load integrations health', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const drain = useCallback(async (system, mode) => {
    setBusy(`${system}-${mode}`);
    try {
      const url = mode === 'simulate'
        ? `${API}/integrations/admin/${system}/simulate-drain?max_rows=100`
        : `${API}/integrations/admin/${system}/drain-now?max_rows=100`;
      const r = await axios.post(url, null, auth());
      const d = r.data || {};
      const tone = d.failed > 0 || d.dead_letter > 0 ? 'warning' : 'success';
      notify[tone](
        `${system === 'sicon' ? 'Sicon' : 'Sage'} ${mode === 'simulate' ? 'simulated drain complete' : 'drain pass complete'}`,
        `${d.attempted ?? 0} attempted · ${d.succeeded ?? 0} succeeded · ${d.failed ?? 0} failed · ${d.skipped_no_config ?? 0} skipped (no creds)`,
      );
      await load();
    } catch (e) {
      notify.error('Drain failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  }, [load]);

  const requeue = useCallback(async (system) => {
    setBusy(`${system}-requeue`);
    try {
      const r = await axios.post(`${API}/integrations/admin/${system}/requeue-failed`, null, auth());
      notify.success(
        `${system === 'sicon' ? 'Sicon' : 'Sage'} requeue done`,
        `${r.data?.requeued ?? 0} failed rows moved back to ${system === 'sage' ? 'their eligible state' : 'pending'}`,
      );
      await load();
    } catch (e) {
      notify.error('Requeue failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  }, [load]);

  // Iter 248 — inbound half of the Sicon loop: pull cases the service
  // team scheduled in Sicon into svc_cases (and onto engineers' job lists).
  const pollInbound = useCallback(async () => {
    setBusy('sicon-poll');
    try {
      const r = await axios.post(`${API}/integrations/admin/sicon/poll-now`, null, auth());
      const d = r.data || {};
      notify.success(
        'Sicon inbound poll complete',
        `${d.fetched ?? 0} fetched · ${d.created ?? 0} created · ${d.updated ?? 0} updated · ${d.skipped_no_config ?? 0} org(s) skipped (no creds)`,
      );
      await load();
    } catch (e) {
      notify.error('Inbound poll failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  }, [load]);

  const renderControls = (system) => (
    <div className="flex flex-wrap gap-1.5" data-testid={`${system}-controls`}>
      {system === 'sicon' && (
        <button
          type="button"
          onClick={() => navigate('/admin/integrations/sicon')}
          className="svc-btn svc-btn-primary svc-btn-sm"
          data-testid="sicon-connect-cta"
          title="Open the Sicon credentials & connection-test panel"
        >
          <Cog size={11} /> Connect
        </button>
      )}      <button
        type="button"
        onClick={() => drain(system, 'simulate')}
        disabled={!!busy}
        className="svc-btn svc-btn-secondary svc-btn-sm"
        data-testid={`${system}-simulate-drain`}
        title={`Demo mode: transitions eligible ${system === 'sicon' ? 'pending' : 'ready/pending'} rows to simulated_succeeded without touching ${system === 'sicon' ? 'Sicon' : 'Sage 200'}`}
      >
        <FlaskConical size={11} /> {busy === `${system}-simulate` ? '…' : 'Simulate drain'}
      </button>
      <button
        type="button"
        onClick={() => drain(system, 'live')}
        disabled={!!busy}
        className="svc-btn svc-btn-primary svc-btn-sm"
        data-testid={`${system}-drain-now`}
        title={`Live drain — only effective once ${system === 'sicon' ? 'Sicon' : 'Sage 200'} credentials are configured`}
      >
        <Play size={11} /> {busy === `${system}-live` ? '…' : 'Drain now'}
      </button>
      {system === 'sicon' && (
        <button
          type="button"
          onClick={pollInbound}
          disabled={!!busy}
          className="svc-btn svc-btn-secondary svc-btn-sm"
          data-testid="sicon-poll-inbound"
          title="Pull cases scheduled/amended in Sicon into Pulse Fitness — assigned engineers receive them in the Engineer App"
        >
          <Play size={11} /> {busy === 'sicon-poll' ? '…' : 'Poll inbound'}
        </button>
      )}
      <button
        type="button"
        onClick={() => requeue(system)}
        disabled={!!busy}
        className="svc-btn svc-btn-ghost svc-btn-sm"
        data-testid={`${system}-requeue`}
        title="Move failed rows back to their eligible state"
      >
        <RotateCcw size={11} /> {busy === `${system}-requeue` ? '…' : 'Requeue failed'}
      </button>
    </div>
  );

  const siconControls = renderControls('sicon');
  const sageControls = renderControls('sage');

  return (
    <div className="svc-shell" data-testid="integrations-console">
      <div className="svc-page">
        <header className="svc-hero" data-testid="integrations-hero">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="svc-eyebrow"><Cable size={11} /> Master admin · Integrations</p>
              <h1 className="svc-h1">Integrations console</h1>
              <p className="svc-subtitle">
                Live status of every external sync. Sicon and Sage 200 are currently in
                <strong> dry-run mode</strong> — every write accumulates in the outbox and will start
                draining the moment credentials are configured. No code changes required at that point.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="integrations-refresh">
                <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
              </button>
            </div>
          </div>
        </header>

        <nav className="svc-tabs mt-4" data-testid="integrations-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`svc-tab ${active ? 'svc-tab--active' : ''}`}
                data-testid={`integrations-tab-${t.id}`}
              >
                <Icon size={13} /> {t.label}
              </button>
            );
          })}
        </nav>

        <div className="space-y-4 mt-4" data-testid="integrations-body">
          {tab === 'overview' ? (
            loading ? (
              <div className="svc-empty"><span className="svc-spinner" /> Loading…</div>
            ) : !health ? (
              <div className="svc-empty"><AlertTriangle size={20} /><div>Couldn't load health.</div></div>
            ) : (
              <>
                <SystemCard
                  name="Sicon"
                  system={health.sicon}
                  testidPrefix="sicon"
                  eyebrow="Service Manager · cases, tracking notes, parts, signatures"
                  controls={siconControls}
                />
                <SystemCard
                  name="Sage 200"
                  system={health.sage}
                  testidPrefix="sage"
                  eyebrow="UK · invoice posting, customer accounts, nominal codes"
                  controls={sageControls}
                />
                <div className="text-[11px] svc-muted text-right tabular-nums">
                  Snapshot generated {fmtDate(health.generated_at)}
                </div>
              </>
            )
          ) : tab === 'sicon' ? (
            <OutboxTable system="sicon" kindFilter={siconKind} statusFilter={siconStatus}
              onChangeKind={setSiconKind} onChangeStatus={setSiconStatus} />
          ) : tab === 'sage' ? (
            <OutboxTable system="sage" kindFilter={sageKind} statusFilter={sageStatus}
              onChangeKind={setSageKind} onChangeStatus={setSageStatus} />
          ) : (
            <MappingTab />
          )}
        </div>
      </div>
    </div>
  );
}
