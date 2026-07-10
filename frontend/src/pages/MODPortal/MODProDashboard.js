/**
 * MOD PRO dashboard — branch (RAF / Army / Navy) or organisation-wide view.
 *
 * Surfaced when user.account_type === 'mod_branch' or 'mod_org'. Consumes
 * GET /api/mod/pro/dashboard. Shows availability KPIs, recent urgent faults
 * across scope, and top offender sites.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Activity, AlertTriangle, Building2, LogOut, Gauge, Wrench, Shield, ArrowUpRight,
  ClipboardList, FileText, PoundSterling, KeyRound, Copy, Check, Loader2, Mail, X, ShieldAlert,
} from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import GymFloorManagerTab from '../LiteDashboard/GymFloorManagerTab';
import MODASERPortal from './MODASERPortal';
import CapexIntelligenceTab from '../CapexIntelligenceTab';

export default function MODProDashboard() {
  const { _user, logout, API } = useAuth();
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [data, setData] = useState(null);
  const [showGymFloor, setShowGymFloor] = useState(false);
  // Iter 216h110 — Operations / CAPEX / Reports pillars
  const [activePillar, setActivePillar] = useState('operations');
  const [capex, setCapex] = useState(null);
  const [reports, setReports] = useState(null);
  const [aserOpen, setAserOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/mod/pro/dashboard`, { headers });
      setData(res.data);
    } catch {
      setData({ totals: {}, top_offenders: [], recent_urgent: [], sites: [] });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  // Lazy-load CAPEX + Reports when each pillar is first opened.
  useEffect(() => {
    if (activePillar === 'capex' && !capex) {
      axios.get(`${API}/mod/capex/overview`, { headers }).then((r) => setCapex(r.data)).catch(() => setCapex({ recommendations: [], age_buckets: {} }));
    }
    if (activePillar === 'reports' && !reports) {
      axios.get(`${API}/mod/reports/summary`, { headers }).then((r) => setReports(r.data)).catch(() => setReports({ kpis: {}, fault_by_type_90d: [] }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [activePillar]);

  if (!data) return <div className="min-h-screen bg-[var(--color-ink-deep)] text-white grid place-items-center">Loading…</div>;

  const t = data.totals || {};
  const scopeLabel = data.scope === 'mod_branch' ? `${data.branch || ''} Branch` : 'MOD Estates';

  return (
    <div className="min-h-screen bg-[var(--color-ink-deep)] text-white pb-10" data-testid="mod-pro-dashboard">
      <header className="border-b border-white/10 bg-[var(--color-surface-darker)] sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">
              Pulse Fitness · MOD PRO {data.scope === 'mod_branch' ? 'Branch' : 'Organisation'}
            </div>
            <h1 className="text-white text-lg sm:text-xl font-extrabold tracking-tight" data-testid="mod-pro-scope">
              {scopeLabel}
            </h1>
          </div>
          <button onClick={() => { logout(); navigate('/'); }} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-pro-logout">
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-5 pt-6 space-y-5">
        {/* Iter 216h110 — Operations · CAPEX · Reports pillar nav */}
        <nav className="flex items-center gap-2 border-b border-white/10 -mb-3" data-testid="mod-pro-pillars">
          {[
            { id: 'operations', label: 'Operations',  icon: Activity },
            { id: 'capex',      label: 'CAPEX',       icon: PoundSterling },
            { id: 'reports',    label: 'Reports',     icon: FileText },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActivePillar(id)}
              className={`inline-flex items-center gap-2 px-4 py-2.5 text-xs font-extrabold uppercase tracking-wider transition-colors ${
                activePillar === id
                  ? 'text-white border-b-2 border-amber-400 -mb-px'
                  : 'text-white/40 hover:text-white/70 border-b-2 border-transparent'
              }`}
              data-testid={`mod-pillar-${id}`}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </nav>

        {activePillar === 'operations' && (<>
        {/* Hero totals */}
        <section className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="mod-pro-totals">
          <StatTile icon={Building2} label="Sites"          value={t.sites ?? 0} />
          <StatTile icon={Gauge}     label="Machines"       value={t.equipment ?? 0} />
          <StatTile icon={Activity}  label="Availability"   value={`${t.availability_pct ?? 100}%`} tone="emerald" />
          <StatTile icon={Wrench}    label="Out of service" value={t.out_of_service ?? 0} tone={t.out_of_service > 0 ? 'amber' : 'emerald'} />
          <StatTile icon={AlertTriangle} label="Open URGENT" value={t.open_urgent ?? 0} tone={t.open_urgent > 0 ? 'red' : 'emerald'} />
        </section>

        {/* Top offenders */}
        <section>
          <h2 className="text-white/70 font-bold text-xs uppercase tracking-wider mb-3">
            Top offenders · last 30 days
          </h2>
          {(data.top_offenders || []).length === 0 ? (
            <EmptyRow text="No faults in the last 30 days across your scope." />
          ) : (
            <div className="space-y-2">
              {data.top_offenders.map((o) => (
                <div key={o.id || o._id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4 flex items-center gap-3" data-testid={`mod-pro-offender-${o.id || o._id}`}>
                  <div className="w-10 h-10 rounded-lg bg-amber-500/15 grid place-items-center text-amber-300"><Shield size={16} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-white text-sm truncate">{o.name || '(unnamed site)'} <span className="text-white/50 font-normal">· {o.mod_branch || '—'}</span></div>
                    <div className="text-xs text-white/60">{o.fault_count} faults · {o.urgent} urgent</div>
                  </div>
                  <DowntimeBar count={o.fault_count} max={Math.max(...data.top_offenders.map((x) => x.fault_count || 0))} />
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Recent urgent */}
        <section>
          <h2 className="text-white/70 font-bold text-xs uppercase tracking-wider mb-3">
            Recent urgent faults
          </h2>
          {(data.recent_urgent || []).length === 0 ? (
            <EmptyRow text="No urgent faults. Keep it that way." tone="emerald" />
          ) : (
            <div className="space-y-2">
              {data.recent_urgent.map((i) => (
                <div key={i.id} className="rounded-xl border border-red-500/30 bg-red-500/10 p-3.5" data-testid={`mod-pro-urgent-${i.id}`}>
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-bold text-white text-sm">{i.mod_ticket_ref || i.id?.slice(0,8)}</span>
                        <span className="text-[10px] font-extrabold uppercase tracking-wider bg-red-500/30 text-red-100 px-1.5 py-0.5 rounded">URGENT</span>
                        <span className="text-[10px] text-white/60">{i.site_name || ''}</span>
                      </div>
                      <div className="text-sm text-white/80 truncate">{i.issue_description}</div>
                      <div className="text-xs text-white/50 mt-1">
                        {i.reporter_name ? `${i.reporter_name} · ${i.reporter_phone || i.reporter_email}` : '—'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Sites list */}
        <section>
          <h2 className="text-white/70 font-bold text-xs uppercase tracking-wider mb-3">
            Sites in scope · {data.sites?.length || 0}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(data.sites || []).map((s) => (
              <SiteRow key={s.id} site={s} API={API} headers={headers} />
            ))}
          </div>
        </section>

        {/* Gym Floor — handover diary & shared credential manager */}
        <section data-testid="mod-pro-gym-floor-section">
          <button
            onClick={() => setShowGymFloor((v) => !v)}
            className="w-full rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-[rgb(var(--rgb-brand-cyan)/0.05)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.1)] transition-colors p-4 flex items-center justify-between gap-3"
            data-testid="mod-pro-gym-floor-toggle"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.15)] grid place-items-center text-[var(--color-brand-cyan)]">
                <ClipboardList size={18} />
              </div>
              <div className="text-left">
                <div className="font-bold text-white text-sm">Gym Floor · Handover Diary</div>
                <div className="text-xs text-white/60">Shared staff credential + AI-moderated shift notes</div>
              </div>
            </div>
            <ArrowUpRight size={16} className={`text-white/60 transition-transform ${showGymFloor ? 'rotate-45' : ''}`} />
          </button>
          {showGymFloor && (
            <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <GymFloorManagerTab />
            </div>
          )}
        </section>
        </>)}

        {/* Iter 216h110 — CAPEX pillar */}
        {activePillar === 'capex' && (
          <div className="space-y-5">
            <CapexPanel capex={capex} />
            {/* Asset Financial Intelligence: residual value, TCO, Cap-Spend
                budget & the replacement sweet-spot planner — scoped to this
                MOD estate via resolve_mod_query_filter. */}
            <CapexIntelligenceTab />
          </div>
        )}

        {/* Iter 216h110 — Reports pillar */}
        {activePillar === 'reports' && (
          <>
            <div className="mb-4">
              <button onClick={() => setAserOpen(true)} className="w-full rounded-xl border border-red-500/30 bg-red-500/5 hover:bg-red-500/10 transition-colors p-4 flex items-center justify-between gap-3" data-testid="mod-pro-aser-open">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-red-500/15 grid place-items-center text-red-300"><ShieldAlert size={18} /></div>
                  <div className="text-left">
                    <div className="font-bold text-white text-sm">ASER — Activity Safety Events Register</div>
                    <div className="text-xs text-white/60">Equipment safety events impacting rehab / activity delivery across your sites</div>
                  </div>
                </div>
                <ArrowUpRight size={16} className="text-white/60" />
              </button>
            </div>
            <ReportsPanel reports={reports} />
          </>
        )}
      </main>
      {aserOpen && <MODASERPortal onClose={() => setAserOpen(false)} />}
    </div>
  );
}


function StatTile({ icon: Icon, label, value, tone = 'neutral' }) {
  const toneClasses = {
    emerald: 'border-emerald-500/30 bg-emerald-500/5',
    amber:   'border-amber-500/30 bg-amber-500/5',
    red:     'border-red-500/40 bg-red-500/10',
    neutral: 'border-white/10 bg-white/[0.03]',
  }[tone];
  const iconColor = {
    emerald: 'text-emerald-400',
    amber:   'text-amber-400',
    red:     'text-red-400',
    neutral: 'text-[var(--color-brand-cyan)]',
  }[tone];
  return (
    <div className={`rounded-xl border p-4 ${toneClasses}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon size={13} className={iconColor} />
        <span className="text-[10px] uppercase tracking-wider font-bold text-white/60">{label}</span>
      </div>
      <div className="text-2xl font-extrabold text-white tracking-tight" style={{ letterSpacing: '-0.02em' }}>{value}</div>
    </div>
  );
}


function DowntimeBar({ count, max }) {
  const pct = max > 0 ? Math.min(100, Math.round((count / max) * 100)) : 0;
  return (
    <div className="w-28 shrink-0">
      <div className="h-2 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full bg-amber-400" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}


function EmptyRow({ text, tone = 'neutral' }) {
  const cls = tone === 'emerald' ? 'border-emerald-500/20 text-emerald-300' : 'border-white/10 text-white/50';
  return (
    <div className={`rounded-xl border ${cls} bg-white/[0.02] p-6 text-center text-sm`}>{text}</div>
  );
}



/* ─────────────── Iter 216h110 — CAPEX & Reports panels ─────────────── */
function CapexPanel({ capex }) {
  if (!capex) return <Skeleton text="Loading CAPEX projection…" />;
  const fmt = (n) => `£${Math.round(n || 0).toLocaleString('en-GB')}`;
  const ageEntries = Object.entries(capex.age_buckets || {});
  const maxAge = Math.max(1, ...ageEntries.map(([, v]) => v));

  return (
    <section className="space-y-5" data-testid="mod-capex-panel">
      {/* Headline KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Fleet replacement cost" value={fmt(capex.fleet_replacement_cost_total)} accent="text-emerald-300" />
        <Kpi label="Flagged for replacement" value={fmt(capex.fleet_replacement_cost_flagged)} accent="text-amber-300" />
        <Kpi label="Equipment in scope" value={capex.total_equipment ?? 0} accent="text-sky-300" />
        <Kpi label="Recommendations" value={capex.recommendation_total ?? 0} accent="text-rose-300" />
      </div>

      {/* Age histogram */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
        <h3 className="text-sm font-bold uppercase tracking-wider text-white/80 mb-3">Equipment age profile · {capex.scope}</h3>
        <div className="space-y-2.5">
          {ageEntries.map(([bucket, count]) => (
            <div key={bucket} className="flex items-center gap-3" data-testid={`mod-capex-age-${bucket}`}>
              <span className="w-20 text-xs text-white/70">{bucket}</span>
              <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                <div className="h-full bg-amber-400" style={{ width: `${(count / maxAge) * 100}%` }} />
              </div>
              <span className="w-12 text-right text-xs font-mono text-white">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Top recommendations table */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] overflow-hidden">
        <div className="px-5 py-3 border-b border-white/10 flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white/80">Top replacement candidates</h3>
          <span className="text-[10px] uppercase tracking-wider text-white/40">High priority first · max 50 shown</span>
        </div>
        <div className="max-h-[480px] overflow-auto">
          {(capex.recommendations || []).length === 0 ? (
            <p className="text-center text-xs text-white/50 py-10">No replacement candidates — fleet is healthy.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-white/[0.04] text-white/50 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="text-left px-4 py-2 font-bold">Asset</th>
                  <th className="text-left px-4 py-2 font-bold">Manufacturer</th>
                  <th className="text-left px-4 py-2 font-bold">Reasons</th>
                  <th className="text-right px-4 py-2 font-bold">Replacement £</th>
                  <th className="text-center px-4 py-2 font-bold">Priority</th>
                </tr>
              </thead>
              <tbody>
                {capex.recommendations.map((r) => (
                  <tr key={r.equipment_id} className="border-t border-white/5 hover:bg-white/[0.02]" data-testid={`mod-capex-row-${r.equipment_id}`}>
                    <td className="px-4 py-2 text-white">{r.name}</td>
                    <td className="px-4 py-2 text-white/60">{r.manufacturer || '—'}</td>
                    <td className="px-4 py-2 text-white/60">{(r.reasons || []).join(' · ')}</td>
                    <td className="px-4 py-2 text-right font-mono text-emerald-300">{fmt(r.replacement_cost)}</td>
                    <td className="px-4 py-2 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                        r.priority === 'high' ? 'bg-rose-500/15 text-rose-300' : 'bg-amber-500/15 text-amber-300'
                      }`}>{r.priority}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}


function ReportsPanel({ reports }) {
  if (!reports) return <Skeleton text="Building service KPIs…" />;
  const k = reports.kpis || {};
  const max = Math.max(1, ...((reports.fault_by_type_90d || []).map((f) => f.count)));
  return (
    <section className="space-y-5" data-testid="mod-reports-panel">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Availability (live)" value={`${k.availability_pct ?? 100}%`} accent="text-emerald-300" />
        <Kpi label="Out of service" value={k.out_of_service ?? 0} accent="text-rose-300" />
        <Kpi label="Faults · 30 days" value={k.faults_30d ?? 0} accent="text-amber-300" />
        <Kpi label="Open now" value={k.open_now ?? 0} accent="text-sky-300" />
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white/80 mb-3">Fault types · last 90 days</h3>
          {(reports.fault_by_type_90d || []).length === 0 ? (
            <p className="text-xs text-white/50 py-6 text-center">No faults logged in the last 90 days.</p>
          ) : (
            <div className="space-y-2.5">
              {reports.fault_by_type_90d.map((f) => (
                <div key={f.type} className="flex items-center gap-3" data-testid={`mod-report-type-${f.type}`}>
                  <span className="w-32 text-xs text-white/70 capitalize">{f.type}</span>
                  <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-sky-400" style={{ width: `${(f.count / max) * 100}%` }} />
                  </div>
                  <span className="w-10 text-right text-xs font-mono text-white">{f.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 space-y-3">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white/80">Service snapshot</h3>
          <Stat label="Faults · 90 days" value={k.faults_90d ?? 0} />
          <Stat label="Urgent · 30 days" value={k.urgent_30d ?? 0} />
          <Stat label="Equipment total" value={k.equipment_total ?? 0} />
          <Stat label="Scope" value={reports.scope} />
          <p className="text-[10px] text-white/40 leading-relaxed pt-1">
            Reports auto-refresh each time you open this panel.
            Detailed PDF exports per Command Centre are available
            on request — request via your account director.
          </p>
        </div>
      </div>
    </section>
  );
}


function Kpi({ label, value, accent = 'text-white' }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <p className="text-[10px] uppercase tracking-wider font-bold text-white/50">{label}</p>
      <p className={`text-2xl font-extrabold tracking-tight ${accent}`} style={{ letterSpacing: '-0.02em' }}>{value}</p>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs text-white/60">{label}</span>
      <span className="text-sm font-bold text-white">{value}</span>
    </div>
  );
}

function Skeleton({ text }) {
  return <p className="text-center text-xs text-white/50 py-10">{text}</p>;
}


/* ─────────── Iter 216h114 — Site Login provisioning ─────────── */
function SiteRow({ site, API, headers }) {
  const [showModal, setShowModal] = useState(false);
  return (
    <>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3.5 flex items-center gap-3" data-testid={`mod-pro-site-${site.id}`}>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-white text-sm truncate">{site.name}</div>
          <div className="text-xs text-white/60">{site.mod_branch} · {site.site_code || '—'}</div>
        </div>
        <button
          type="button"
          onClick={() => setShowModal(true)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] font-bold uppercase tracking-wider bg-[var(--color-brand-cyan)]/10 hover:bg-[var(--color-brand-cyan)]/20 text-[var(--color-brand-cyan)] border border-[var(--color-brand-cyan)]/30"
          data-testid={`mod-pro-site-login-btn-${site.id}`}
          title="Generate / rotate this site's login"
        >
          <KeyRound size={12} /> Site login
        </button>
      </div>
      {showModal && (
        <GenerateLoginModal
          site={site}
          API={API}
          headers={headers}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  );
}

function GenerateLoginModal({ site, API, headers, onClose }) {
  const [step, setStep] = useState('confirm'); // confirm · result
  const [notifyEmail, setNotifyEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  const generate = async () => {
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/mod/pro/sites/${site.id}/provision-credentials`,
        { notify_email: notifyEmail.trim() || null, rotate_if_exists: true },
        { headers },
      );
      setResult(r.data);
      setStep('result');
      if (r.data?.notified_email) notify.success(`Credentials emailed to ${r.data.notified_email}`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not generate site login');
    } finally {
      setSubmitting(false);
    }
  };

  const copyCreds = async () => {
    if (!result) return;
    const text = `Site: ${result.site_name}\nUsername: ${result.username}\nSite code: ${result.password}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch { /* ignore */ }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" data-testid="mod-site-login-modal">
      <div className="w-full max-w-md rounded-2xl bg-[var(--color-surface-darker)] border border-white/10 overflow-hidden">
        <header className="px-5 py-4 border-b border-white/10 flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">
              Pulse Fitness · MOD Site Login
            </div>
            <h3 className="text-white text-base font-extrabold tracking-tight mt-1" data-testid="mod-site-login-title">
              {site.name}
            </h3>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-full text-white/60 hover:text-white hover:bg-white/10" data-testid="mod-site-login-close">
            <X size={16} />
          </button>
        </header>

        <div className="p-5 space-y-4">
          {step === 'confirm' && (
            <>
              <p className="text-sm text-white/80">
                Generate (or rotate) the shared site login for this MOD site.
                The new password is shown once — copy it now and share securely
                with the on-site PTI.
              </p>
              <div className="space-y-1.5">
                <label className="block text-[11px] font-bold uppercase tracking-wider text-white/60">
                  Email credentials to (optional)
                </label>
                <div className="flex items-center gap-2">
                  <Mail size={14} className="text-white/40 shrink-0" />
                  <input
                    type="email"
                    placeholder="ops.lead@army.mod.local"
                    value={notifyEmail}
                    onChange={(e) => setNotifyEmail(e.target.value)}
                    className="flex-1 bg-white/5 border border-white/10 rounded-md px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[var(--color-brand-cyan)]"
                    data-testid="mod-site-login-notify-email"
                  />
                </div>
                <p className="text-[11px] text-white/40">
                  Leave blank to view + copy from this dialog only.
                </p>
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button type="button" onClick={onClose} className="px-3 py-2 text-xs font-bold rounded-md text-white/70 hover:text-white" data-testid="mod-site-login-cancel">
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={generate}
                  className="inline-flex items-center gap-2 px-3 py-2 text-xs font-extrabold uppercase tracking-wider rounded-md bg-[var(--color-brand-cyan)] hover:opacity-90 text-black disabled:opacity-50"
                  data-testid="mod-site-login-generate"
                >
                  {submitting ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />}
                  Generate
                </button>
              </div>
            </>
          )}

          {step === 'result' && result && (
            <>
              <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200" data-testid="mod-site-login-once-warning">
                {result.note || 'This password is shown once — copy it now.'}
              </div>
              <div className="space-y-2">
                <div className="rounded-md bg-white/5 border border-white/10 p-3">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-white/50">Username</div>
                  <code className="block mt-1 text-sm font-mono text-white" data-testid="mod-site-login-username">{result.username}</code>
                </div>
                <div className="rounded-md bg-black border border-[var(--color-brand-cyan)]/40 p-3">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-cyan)]">Site code</div>
                  <code className="block mt-1 text-sm font-mono text-white break-all" data-testid="mod-site-login-password">{result.password}</code>
                </div>
              </div>
              <div className="flex items-center justify-between gap-2 pt-1">
                <button
                  type="button"
                  onClick={copyCreds}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md border border-white/10 text-white/80 hover:bg-white/5"
                  data-testid="mod-site-login-copy"
                >
                  {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                  {copied ? 'Copied' : 'Copy both'}
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-2 text-xs font-extrabold uppercase tracking-wider rounded-md bg-[var(--color-brand-cyan)] text-black hover:opacity-90"
                  data-testid="mod-site-login-done"
                >
                  Done
                </button>
              </div>
              {result.rotated ? (
                <p className="text-[11px] text-white/40 pt-1">Previous code has been invalidated immediately.</p>
              ) : (
                <p className="text-[11px] text-white/40 pt-1">New site account created — ready to use straight away.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
