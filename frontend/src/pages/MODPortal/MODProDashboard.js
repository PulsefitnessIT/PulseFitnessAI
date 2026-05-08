/**
 * MOD PRO dashboard — branch (RAF / Army / Navy) or organisation-wide view.
 *
 * Surfaced when user.account_type === 'mod_branch' or 'mod_org'. Consumes
 * GET /api/mod/pro/dashboard. Shows availability KPIs, recent urgent faults
 * across scope, and top offender sites.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Activity, AlertTriangle, Building2, LogOut, Gauge, Wrench, Shield, ArrowUpRight, ClipboardList,
} from 'lucide-react';
import { useAuth } from '@/App';
import GymFloorManagerTab from '../LiteDashboard/GymFloorManagerTab';

export default function MODProDashboard() {
  const { user, logout, API } = useAuth();
  const navigate = useNavigate();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [data, setData] = useState(null);
  const [showGymFloor, setShowGymFloor] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/mod/pro/dashboard`, { headers });
      setData(res.data);
    } catch {
      setData({ totals: {}, top_offenders: [], recent_urgent: [], sites: [] });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

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
              <div key={s.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3.5" data-testid={`mod-pro-site-${s.id}`}>
                <div className="font-bold text-white text-sm">{s.name}</div>
                <div className="text-xs text-white/60">{s.mod_branch} · {s.site_code || '—'}</div>
              </div>
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
      </main>
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
