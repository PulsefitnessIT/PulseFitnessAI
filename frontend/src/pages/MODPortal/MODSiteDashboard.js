/**
 * MOD Portal — site-tier dashboard.
 *
 * Landed when a user's org.account_type === 'mod_site'. Shows site health,
 * open faults, opens the fault wizard, and drills into staff management.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  AlertTriangle, Wrench, Users, Shield, Gauge, ChevronRight,
  Activity, Clock, Zap, LogOut, CheckCircle2, Plus, QrCode, CloudOff, ShieldAlert, ShieldCheck,
} from 'lucide-react';
import { useAuth } from '@/App';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { installAutoFlush, countPending, flushQueue } from '@/utils/offlineFaultQueue';
import ClassificationBanner from '@/components/shared/ClassificationBanner';
import OfflineStatusPill from '@/components/shared/OfflineStatusPill';

function DrillBanner({ drill, onAcknowledge, acked }) {
  if (!drill) return null;
  return (
    <div
      className="rounded-xl border border-violet-500/50 bg-gradient-to-r from-violet-600/20 to-fuchsia-500/10 p-4 flex items-start gap-3"
      data-testid="mod-drill-banner"
    >
      <div className="w-10 h-10 rounded-lg bg-violet-500/30 grid place-items-center text-violet-200 shrink-0">
        <Shield size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-violet-300 mb-0.5">
          DRILL · Simulation in progress
        </div>
        <div className="text-white text-sm font-extrabold">{drill.drill_scenario || 'Red team drill'}</div>
        <div className="text-xs text-white/70 mt-1">
          Ticket {drill.mod_ticket_ref} · {drill.machine_type || 'Equipment'} · {drill.serial_number || '—'}
        </div>
        <div className="text-[11px] text-white/60 mt-1.5 italic">
          Respond as you would to a real URGENT. KPIs are unaffected.
        </div>
      </div>
      {acked ? (
        <div className="flex items-center gap-1 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-200 px-2.5 py-1.5 text-xs font-bold" data-testid="mod-drill-acked">
          <CheckCircle2 size={12} /> Acknowledged
        </div>
      ) : (
        <button
          onClick={onAcknowledge}
          className="rounded-lg px-3 py-2 text-xs font-extrabold shrink-0"
          style={{ background: '#c4b5fd', color: '#3b0764' }}
          data-testid="mod-drill-acknowledge"
        >
          Acknowledge drill
        </button>
      )}
    </div>
  );
}
import MODFaultWizard from './MODFaultWizard';
import MODIncidentWizard from './MODIncidentWizard';
import MODStaffModal from './MODStaffModal';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MODSiteDashboard() {
  const { user, logout, API: AUTH_API } = useAuth();
  const navigate = useNavigate();
  const [dash, setDash] = useState(null);
  const [nudges, setNudges] = useState([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [staffOpen, setStaffOpen] = useState(false);
  const [incidentOpen, setIncidentOpen] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);
  const [activeDrill, setActiveDrill] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    try {
      const tk = localStorage.getItem('token');
      const h = { Authorization: `Bearer ${tk}` };
      const base = AUTH_API || API;
      const [d, n, dr] = await Promise.all([
        axios.get(`${base}/mod/site/dashboard`, { headers: h }),
        axios.get(`${base}/mod/site/proactive-nudges`, { headers: h }),
        axios.get(`${base}/mod/site/drills/active`, { headers: h }).catch(() => ({ data: { drill: null } })),
      ]);
      setDash(d.data);
      setNudges(n.data.nudges || []);
      setActiveDrill(dr.data?.drill || null);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('MOD dashboard load failed', e?.response?.status, e?.response?.data || e.message);
      setDash({ stats: {}, open_faults: [], site: {} });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [AUTH_API]);

  const acknowledgeDrill = async () => {
    if (!activeDrill?.drill_id) return;
    const base = AUTH_API || API;
    try {
      await axios.post(`${base}/mod/site/drills/${activeDrill.drill_id}/acknowledge`, {}, { headers });
      notify.success('Drill acknowledged — timing captured');
      load();
    } catch {
      notify.error('Acknowledge failed');
    }
  };

  useEffect(() => { load(); }, [load]);

  // Wire up the offline-queue auto-flush + periodic count refresh. When
  // a queued submission successfully syncs, re-pull the dashboard so the
  // new ticket appears without a page reload.
  useEffect(() => {
    const base = AUTH_API || API;
    const cleanup = installAutoFlush(base, ({ remaining, synced }) => {
      setQueuedCount(remaining);
      if (synced > 0) {
        notify.success(`${synced} offline fault${synced > 1 ? 's' : ''} synced`);
        load();
      }
    });
    (async () => setQueuedCount(await countPending()))();
    return cleanup;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [AUTH_API]);

  const manualFlush = async () => {
    if (queuedCount === 0) return;
    const base = AUTH_API || API;
    notify.info(`Syncing ${queuedCount} offline fault${queuedCount > 1 ? 's' : ''}…`);
    const result = await flushQueue(base);
    setQueuedCount(await countPending());
    if (result.synced > 0) { notify.success(`${result.synced} synced`); load(); }
    if (result.failed > 0) notify.error(`${result.failed} still pending — check your connection`);
  };

  if (!dash) return <div className="min-h-screen bg-[var(--color-ink-deep)] text-white grid place-items-center">Loading…</div>;

  const stats = dash.stats || {};
  const site = dash.site || {};

  return (
    <div className="min-h-screen bg-[var(--color-ink-deep)] text-white pb-10" data-testid="mod-site-dashboard">
      <ClassificationBanner level={user?.classification || 'OFFICIAL'} rightSlot={<OfflineStatusPill />} />
      {/* Branded header */}
      <header className="border-b border-white/10 bg-[var(--color-surface-darker)] sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-5 py-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">
              Pulse Fitness · MOD Service Portal
            </div>
            <h1 className="text-white text-lg sm:text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em' }} data-testid="mod-site-name">
              {site.name || 'MOD Site'}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            {queuedCount > 0 && (
              <button
                onClick={manualFlush}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-extrabold rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-200 hover:bg-amber-500/30"
                data-testid="mod-queued-pill"
                title="Tap to retry sync"
              >
                <CloudOff size={13} /> {queuedCount} queued
              </button>
            )}
            <button
              onClick={async () => {
                try {
                  const tk = localStorage.getItem('token');
                  notify.info('Preparing QR sheet…');
                  const res = await fetch(`${AUTH_API || API}/mod/site/qr-sheet.pdf`, {
                    headers: { Authorization: `Bearer ${tk}` },
                  });
                  if (!res.ok) throw new Error(`HTTP ${res.status}`);
                  const blob = await res.blob();
                  const url = URL.createObjectURL(blob);
                  window.open(url, '_blank');
                  // Best-effort revoke after 60s; browser holds the tab open meanwhile.
                  setTimeout(() => URL.revokeObjectURL(url), 60000);
                } catch (e) {
                  notify.error('QR sheet download failed');
                }
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5"
              data-testid="mod-nav-qr-sheet"
              title="Download printable QR labels (12 per A4)"
            >
              <QrCode size={13} /> QR sheet
            </button>
            <button onClick={() => setStaffOpen(true)} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-nav-staff">
              <Users size={13} /> Staff
            </button>
            <button onClick={() => { logout(); navigate('/'); }} className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-white/10 hover:bg-white/5" data-testid="mod-nav-logout">
              <LogOut size={13} /> Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-5 pt-6 space-y-5">
        {/* Active drill banner — sits above everything so PTI sees it first */}
        <DrillBanner
          drill={activeDrill}
          acked={Boolean(activeDrill?.drill_acknowledged_at)}
          onAcknowledge={acknowledgeDrill}
        />

        {/* Primary CTA */}
        <button
          onClick={() => setWizardOpen(true)}
          className="w-full rounded-2xl p-6 text-left flex items-center gap-4 transition-all hover:scale-[1.01]"
          style={{
            background: 'linear-gradient(135deg, var(--color-brand-cyan) 0%, var(--color-brand-cyan-deep) 100%)',
            color: 'var(--color-surface-darker)',
            boxShadow: '0 0 50px rgba(25,205,255,0.25)',
          }}
          data-testid="mod-log-fault-btn"
        >
          <div className="w-14 h-14 rounded-xl bg-black/10 flex items-center justify-center">
            <AlertTriangle size={28} />
          </div>
          <div className="flex-1">
            <div className="text-lg sm:text-2xl font-extrabold tracking-tight">Log a Fault</div>
            <div className="text-sm font-semibold opacity-80">6-step guided wizard — AI-triaged in seconds</div>
          </div>
          <ChevronRight size={22} />
        </button>

        {/* Iter 216h117 — Personal-incident shortcut */}
        <button
          onClick={() => setIncidentOpen(true)}
          className="w-full rounded-2xl p-4 text-left flex items-center gap-4 border transition-all hover:scale-[1.01]"
          style={{
            background: 'rgba(220, 38, 38, 0.08)',
            borderColor: 'rgba(248, 113, 113, 0.4)',
            color: '#fff',
          }}
          data-testid="mod-incident-launch"
        >
          <div className="w-11 h-11 rounded-lg bg-rose-500/20 flex items-center justify-center">
            <ShieldAlert size={20} className="text-rose-300" />
          </div>
          <div className="flex-1">
            <div className="text-sm sm:text-base font-extrabold tracking-tight">Report a personal incident</div>
            <div className="text-xs font-semibold opacity-70">Injuries / RIDDOR — routes to base H&amp;S officer</div>
          </div>
          <ChevronRight size={18} className="text-rose-300" />
        </button>

        {/* Proactive nudges */}
        {nudges.length > 0 && (
          <div className="space-y-2" data-testid="mod-nudges">
            {nudges.map((n, i) => (
              <div key={i} className={`rounded-xl border p-3.5 flex items-start gap-3 ${
                n.level === 'warn'
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-100'
                  : 'bg-white/[0.04] border-white/10 text-white/80'
              }`}>
                <AlertTriangle size={15} className={`mt-0.5 shrink-0 ${n.level === 'warn' ? 'text-amber-300' : 'text-white/50'}`} />
                <div>
                  <div className="font-bold text-sm">{n.title}</div>
                  <div className="text-xs opacity-80">{n.body}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Stats row */}
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="mod-stats">
          <Stat icon={Activity} label="Availability" value={`${stats.availability_pct ?? 0}%`} tone="emerald" />
          <Stat icon={Gauge} label="Machines working" value={`${stats.equipment_working || 0} / ${stats.equipment_total || 0}`} />
          <Stat icon={Wrench} label="Open faults" value={stats.open_faults || 0} tone={stats.open_faults > 0 ? 'amber' : 'emerald'} />
          <Stat icon={Shield} label="Overdue checks" value={stats.overdue_checks || 0} tone={stats.overdue_checks > 0 ? 'amber' : 'emerald'} />
        </section>

        {/* Open faults */}
        <section>
          <h2 className="text-white/70 font-bold text-xs uppercase tracking-wider mb-3">
            Your open faults{dash.open_faults?.length ? ` · ${dash.open_faults.length}` : ''}
          </h2>
          {(dash.open_faults || []).length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/50">
              <CheckCircle2 size={20} className="mx-auto text-emerald-400 mb-2" />
              No open faults. Keep it that way.
            </div>
          ) : (
            <div className="space-y-2">
              {dash.open_faults.map((f) => <FaultCard key={f.id} fault={f} onChange={load} />)}
            </div>
          )}
        </section>
      </main>

      {wizardOpen && (
        <MODFaultWizard
          onClose={() => setWizardOpen(false)}
          onSubmitted={() => { setWizardOpen(false); load(); }}
        />
      )}
      {staffOpen && <MODStaffModal onClose={() => setStaffOpen(false)} />}
      {incidentOpen && (
        <MODIncidentWizard
          onClose={() => setIncidentOpen(false)}
          onSubmitted={() => { setIncidentOpen(false); load(); }}
        />
      )}
    </div>
  );
}


function Stat({ icon: Icon, label, value, tone = 'neutral' }) {
  const toneClasses = {
    emerald: 'border-emerald-500/30 bg-emerald-500/5',
    amber: 'border-amber-500/30 bg-amber-500/5',
    neutral: 'border-white/10 bg-white/[0.03]',
  }[tone];
  const iconColor = {
    emerald: 'text-emerald-400',
    amber: 'text-amber-400',
    neutral: 'text-[var(--color-brand-cyan)]',
  }[tone];
  return (
    <div className={`rounded-xl border p-4 ${toneClasses}`} data-testid={`mod-stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center gap-2 mb-1">
        <Icon size={13} className={iconColor} />
        <span className="text-[10px] uppercase tracking-wider font-bold text-white/60">{label}</span>
      </div>
      <div className="text-2xl font-extrabold text-white tracking-tight" style={{ letterSpacing: '-0.02em' }}>{value}</div>
    </div>
  );
}


function FaultCard({ fault, onChange }) {
  const { API } = useAuth();
  const severity = (fault.priority || fault.severity || '').toLowerCase();
  const toneMap = {
    urgent: 'border-red-500/40 bg-red-500/10',
    high: 'border-orange-500/40 bg-orange-500/10',
    medium: 'border-amber-500/40 bg-amber-500/10',
    low: 'border-emerald-500/40 bg-emerald-500/10',
  };
  const token = localStorage.getItem('token');
  // Reassemble a signed viewer URL per attachment path — tokens never
  // embed in the ticket record, only in the current viewer's session.
  const attachments = Array.isArray(fault.attachment_urls) ? fault.attachment_urls : [];
  const viewerUrl = (p) => `${API}/mod/site/attachments/serve?path=${encodeURIComponent(p)}&token=${encodeURIComponent(token)}`;
  const isVideo = (p = '') => /\.(mp4|mov|webm)$/i.test(p);

  // Iter 216h117 — DIO escalation. Site users can flag a fault to the
  // base's DIO (Defence Infrastructure Organisation) contact when HQ
  // has configured one. Button hides once a fault has already been
  // escalated.
  const [escalating, setEscalating] = useState(false);
  const alreadyEscalated = Boolean(fault.escalated_to_dio);
  const escalateToDIO = async () => {
    const note = window.prompt(
      `Escalate ${fault.mod_ticket_ref || 'this fault'} to DIO?\n\nOptional escalation note (max 2000 chars):`,
      '',
    );
    if (note === null) return; // cancelled
    setEscalating(true);
    try {
      const r = await axios.post(
        `${API}/mod/site/faults/${fault.id}/escalate-to-dio`,
        { note: (note || '').slice(0, 2000) },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      notify.success('Escalated to DIO', `Sent to ${r.data.escalated_to}.`);
      onChange?.();
    } catch (e) {
      const detail = e?.response?.data?.detail || 'Could not escalate fault';
      notify.error('Escalation failed', detail);
    } finally {
      setEscalating(false);
    }
  };

  return (
    <div className={`rounded-xl border p-4 ${toneMap[severity] || 'border-white/10 bg-white/[0.03]'}`} data-testid={`mod-fault-${fault.id}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-bold text-white text-sm">{fault.mod_ticket_ref || fault.id?.slice(0,8)}</span>
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider bg-white/10 text-white/90">
              {severity || 'pending'}
            </span>
            <span className="text-[10px] font-bold text-white/50">{fault.machine_type}</span>
            {alreadyEscalated && (
              <span
                className="text-[10px] font-extrabold px-1.5 py-0.5 rounded uppercase tracking-wider bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 inline-flex items-center gap-1"
                data-testid={`mod-fault-${fault.id}-dio-pill`}
                title={`Escalated ${fault.dio_escalated_at ? new Date(fault.dio_escalated_at).toLocaleString() : ''}`}
              >
                <ShieldCheck size={9} /> DIO
              </span>
            )}
          </div>
          <div className="text-sm text-white/80 truncate">{fault.issue_description}</div>
          {fault.reporter_name && (
            <div className="text-xs text-white/50 mt-1 flex items-center gap-1">
              <Clock size={10} /> Reported by {fault.reporter_name}
            </div>
          )}
        </div>
        {!alreadyEscalated && (
          <button
            type="button"
            onClick={escalateToDIO}
            disabled={escalating}
            className="shrink-0 inline-flex items-center gap-1 px-2 py-1 text-[11px] font-extrabold rounded-md border border-cyan-500/40 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-60"
            data-testid={`mod-fault-${fault.id}-escalate-dio`}
            title="Report to DIO (Defence Infrastructure Organisation)"
          >
            <ShieldCheck size={10} />
            {escalating ? 'Sending…' : 'Report to DIO'}
          </button>
        )}
      </div>
      {attachments.length > 0 && (
        <div className="mt-3 flex gap-1.5 flex-wrap" data-testid={`mod-fault-attachments-${fault.id}`}>
          {attachments.slice(0, 6).map((p, i) => (
            <a
              key={i}
              href={viewerUrl(p)}
              target="_blank"
              rel="noreferrer"
              className="relative w-14 h-14 rounded-lg overflow-hidden border border-white/15 bg-black/40 hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] transition shrink-0"
              data-testid={`mod-fault-${fault.id}-attach-${i}`}
              title="Open attachment"
            >
              {isVideo(p) ? (
                <>
                  <video src={viewerUrl(p)} className="w-full h-full object-cover" muted />
                  <div className="absolute inset-0 grid place-items-center bg-black/40">
                    <div className="text-white text-[9px] font-extrabold">VIDEO</div>
                  </div>
                </>
              ) : (
                <img src={viewerUrl(p)} alt="" className="w-full h-full object-cover" loading="lazy" />
              )}
            </a>
          ))}
          {attachments.length > 6 && (
            <div className="w-14 h-14 rounded-lg border border-white/10 bg-black/30 grid place-items-center text-white/60 text-xs font-bold">
              +{attachments.length - 6}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
