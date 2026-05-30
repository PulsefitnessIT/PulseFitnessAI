/**
 * EngineerJobDetailV2 — Phase 3 light-mode job workflow.
 *
 * Iter 216h133. Light-mode GymAxis aesthetic. Tabs: Time · Travel ·
 * Photos · Parts · Complete. Surfaces all existing engineer.py
 * primitives plus new Phase 3 endpoints (mileage, ad-hoc parts,
 * generate-invoice-draft).
 *
 * Endpoints used:
 *   GET    /api/svc/engineer/jobs/{caseId}
 *   POST   /api/svc/engineer/time/start | /time/stop
 *   POST   /api/svc/engineer/photos                       (existing)
 *   POST   /api/files/upload?category=photos              (existing)
 *   POST   /api/svc/engineer/jobs/{id}/mileage            (Phase 3 NEW)
 *   GET    /api/svc/engineer/jobs/{id}/mileage            (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/parts/use          (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/parts/{id}/consume (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/generate-invoice-draft (Phase 3 NEW)
 *   POST   /api/svc/engineer/jobs/{id}/complete           (existing)
 *   POST   /api/svc/engineer/signature                    (existing)
 *   GET    /api/svc/parts                                 (catalogue search)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Clock, Camera, Wrench, Car, Loader2, RefreshCw,
  Play, Square, Plus, Trash2, Check, AlertTriangle, ReceiptPoundSterling as Receipt,
  ChevronRight, CheckCircle2, Search, Package, X, Image as ImageIcon,
  Video, MapPin, Send, Download, Phone, Navigation, History, LogIn,
  Wifi, WifiOff, CloudUpload,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { engineerSendOrQueue, useEngineerOfflineQueue } from '@/utils/engineerOfflineQueue';
import SignatureCanvas from './SignatureCanvas';
import EngineerDictationButton from './EngineerDictationButton';
import WorkReportCustomFields from './WorkReportCustomFields';
import WorkVisitMachinesCard from './WorkVisitMachinesCard';
import useJobDraft from './useJobDraft';
import { resolveChannel } from '@/utils/channelLabel';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtMins = (m) => {
  const total = Math.max(0, Math.round(m || 0));
  const h = Math.floor(total / 60);
  const r = total % 60;
  return h > 0 ? `${h}h ${r}m` : `${r}m`;
};

const TABS = [
  // Iter 220cs — reorder to match the real-world arrival → diagnose
  // → fix → close flow. Time runs passively (sticky ActiveTimerBar
  // is always visible) so it no longer needs to be the first tab.
  { id: 'equipment', label: 'Equipment', icon: Package },
  { id: 'photos',    label: 'Photos',    icon: Camera },
  { id: 'parts',     label: 'Parts',     icon: Wrench },
  { id: 'time',      label: 'Time',      icon: Clock },
  { id: 'travel',    label: 'Travel',    icon: Car },
  { id: 'complete',  label: 'Complete',  icon: CheckCircle2 },
];

export default function EngineerJobDetailV2() {
  const navigate = useNavigate();
  const { caseId } = useParams();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('equipment');
  const [mileage, setMileage] = useState({ items: [], total_miles: 0, total_amount_gbp: 0 });
  const [busy, setBusy] = useState(false);
  // Iter 220c — Lift the draft state OUT of CompleteTab so it survives
  // tab switches (the component unmounts on every switch and was wiping
  // mid-typed work summaries). The hook also dual-writes to localStorage
  // + the backend so a page reload or device kill can't lose work.
  const { draft, setDraft, clearDraft, saving: savingDraft, lastSavedAt, dirty: draftDirty } = useJobDraft(caseId);

  const goBack = useCallback(() => {
    if (draftDirty) {
      const ok = window.confirm('You have unsaved work on this job. The draft is saved locally and will still be here when you return — leave anyway?');
      if (!ok) return;
    }
    navigate('/svc/engineer');
  }, [draftDirty, navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [j, m] = await Promise.all([
        axios.get(`${API}/svc/engineer/jobs/${caseId}`, auth()),
        axios.get(`${API}/svc/engineer/jobs/${caseId}/mileage`, auth()).catch(() => ({ data: { items: [], total_miles: 0, total_amount_gbp: 0 } })),
      ]);
      setJob(j.data);
      setMileage(m.data);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) notify.error('Job not found');
      else if (status === 403) notify.error('Not assigned to this job');
      else notify.error('Failed to load job');
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  const activeTimer = useMemo(() => (job?.time_entries || []).find(t => !t.end_at) || null, [job]);

  if (loading && !job) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        <Loader2 className="animate-spin mr-2" size={18} /> Loading job…
      </div>
    );
  }
  if (!job) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500">Job unavailable.</div>;
  }

  const lockedComplete = ['closed', 'invoiced', 'awaiting_sign_off', 'repaired'].includes(job.status);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-job-detail-v2">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={goBack} className="p-2 rounded-full hover:bg-slate-100" aria-label="Back" data-testid="job-back">
            <ArrowLeft size={18} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-blue-700">{job.reference}</p>
            <h1 className="text-base font-extrabold text-slate-900 truncate">{job.title}</h1>
            <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 mt-0.5">
              <p className="text-xs text-slate-500 truncate" data-testid="job-meta">
                {job.site_name || 'Unknown site'}{job.asset_name ? ` · ${job.asset_name}` : ''} · <span className="capitalize">{job.status}</span>
              </p>
              {(() => {
                const ch = resolveChannel(job);
                if (!ch) return null;
                return (
                  <span
                    className={`inline-flex items-center px-1.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide ${ch.cls}`}
                    title={`Logged via ${ch.label}`}
                    data-testid={`job-channel-pill-${ch.code}`}
                  >
                    {ch.label}
                  </span>
                );
              })()}
            </div>
          </div>
          {/* Iter 220c — autosave indicator. Lets engineers know the draft is safe. */}
          <DraftStatusPill saving={savingDraft} lastSavedAt={lastSavedAt} dirty={draftDirty} />
          {/* Iter 220ct — sync status chip. Turns the IndexedDB offline queue
              from an invisible safety net into a visible reassurance. */}
          <SyncStatusChip />
          <button onClick={load} aria-label="Refresh" className="p-2 rounded-full border border-slate-200 bg-white" data-testid="job-refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
        <ActiveTimerBar timer={activeTimer} onStop={async () => {
          setBusy(true);
          try {
            const r = await engineerSendOrQueue({
              method: 'POST',
              path: '/svc/engineer/time/stop',
              body: { entry_id: activeTimer.id },
              label: 'Stop timer',
            });
            if (r.ok) {
              notify.success('Timer stopped');
            } else if (r.offline) {
              notify.success('Saved offline — will sync when you reconnect');
            } else {
              notify.error('Could not stop timer');
            }
            await load();
          } catch (e) {
            notify.error('Could not stop timer');
          } finally { setBusy(false); }
        }} />
        <nav className="max-w-4xl mx-auto px-2 flex items-center gap-0.5 overflow-x-auto" data-testid="job-tabs">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = activeTab === t.id;
            return (
              <button key={t.id} type="button" onClick={() => setActiveTab(t.id)}
                className={`relative flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wide ${active ? 'text-blue-700' : 'text-slate-500 hover:text-slate-700'}`}
                data-testid={`job-tab-${t.id}`}>
                <Icon size={14} />
                {t.label}
                {active && <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-blue-700 rounded-t" />}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-5 pb-28 space-y-4">
        <JobAtAGlance job={job} setBusy={setBusy} busy={busy} onChange={load} />
        {activeTab === 'time'   && <TimeTab job={job} busy={busy} setBusy={setBusy} onChange={load} />}
        {activeTab === 'travel' && <TravelTab job={job} mileage={mileage} onChange={load} />}
        {activeTab === 'photos' && <PhotosTab job={job} onChange={load} />}
        {activeTab === 'equipment' && <EquipmentTab job={job} />}
        {activeTab === 'parts'  && <PartsTab job={job} onChange={load} />}
        {activeTab === 'complete' && (
          <CompleteTab
            job={job}
            locked={lockedComplete}
            onChange={load}
            navigate={navigate}
            draft={draft}
            setDraft={setDraft}
            clearDraft={clearDraft}
          />
        )}
      </main>
    </div>
  );
}

// ─── JobAtAGlance ─────────────────────────────────────────────────
// Iter 220cs. The first thing an engineer sees when they open a
// job: customer / site / address / fault summary + tap-to-call,
// tap-to-navigate, and a big "I'm on site" button that starts the
// on-site timer (with the existing H&S gate respected).
function JobAtAGlance({ job, busy, setBusy, onChange }) {
  const phone = job.customer_phone;
  const email = job.customer_email;
  const address = [job.site_address, job.site_postcode].filter(Boolean).join(' ');
  const mapsHref = address
    ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`
    : null;
  const fault = job.description || job.fault_summary || job.summary || '';
  // Iter 220cs — surface the most recent prior visit to the same
  // asset (the engineer endpoint already returns `asset_history`).
  const lastVisitDoc = Array.isArray(job.asset_history) ? job.asset_history[0] : null;
  const lastVisit = lastVisitDoc
    ? `${lastVisitDoc.reference || 'previous'}${lastVisitDoc.closed_at ? ' · ' + new Date(lastVisitDoc.closed_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : ''}`
    : (job.last_visit_summary || null);
  const machineCount = (job.machines_count ?? (Array.isArray(job.machines) ? job.machines.length : null));

  // Has the engineer already arrived? We look for any on_site time
  // entry on the case (the existing TimeTab.start uses the same
  // /time/start endpoint).
  const entries = job.time_entries || [];
  const hasArrived = entries.some(e => e.category === 'on_site' || e.category === 'travel');
  const activeOnSite = entries.find(e => !e.end_at && e.category === 'on_site');

  const arrive = async () => {
    setBusy(true);
    try {
      const r = await engineerSendOrQueue({
        method: 'POST',
        path: '/svc/engineer/time/start',
        body: { case_id: job.id, category: 'on_site' },
        label: 'Start on-site timer',
      });
      if (r.ok) {
        notify.success('Arrived on site', 'On-site timer started.');
      } else if (r.offline) {
        notify.success('Arrival queued', 'Will sync when you reconnect.');
      }
      await onChange();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.code === 'safety_signoff_required') {
        notify.error('H&S checklist required', 'Open the Complete tab and tick off the H&S items before starting work.');
      } else {
        notify.error('Could not record arrival', e?.message || 'Try again.');
      }
    } finally { setBusy(false); }
  };

  return (
    <div
      className="rounded-2xl bg-white border border-slate-200 shadow-sm overflow-hidden"
      data-testid="job-at-a-glance"
    >
      <div className="p-3 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Customer
            </p>
            <p className="text-sm font-bold text-slate-900 truncate" data-testid="jaag-customer-name">
              {job.customer_name || 'Unknown customer'}
            </p>
            {job.site_name && (
              <p className="text-xs text-slate-500 truncate">
                {job.site_name}
              </p>
            )}
          </div>
          <div className="flex items-center gap-1">
            {phone && (
              <a
                href={`tel:${phone.replace(/\s+/g, '')}`}
                className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                title={`Call ${phone}`}
                data-testid="jaag-call"
              >
                <Phone size={14} />
              </a>
            )}
            {mapsHref && (
              <a
                href={mapsHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
                title="Open in Maps"
                data-testid="jaag-maps"
              >
                <Navigation size={14} />
              </a>
            )}
            {email && (
              <a
                href={`mailto:${email}`}
                className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200"
                title={`Email ${email}`}
                data-testid="jaag-email"
              >
                <Send size={14} />
              </a>
            )}
          </div>
        </div>

        {address && (
          <p className="text-xs text-slate-600 leading-snug" data-testid="jaag-address">
            <MapPin size={11} className="inline mr-1 -mt-0.5 text-slate-400" />
            {address}
          </p>
        )}

        {fault && (
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mt-2">
              What we're here for
            </p>
            <p className="text-xs text-slate-700 leading-snug" data-testid="jaag-fault">
              {fault}
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 pt-1">
          {job.priority && (
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide ${
                String(job.priority).toLowerCase().startsWith('p1') || String(job.priority).toLowerCase() === 'critical'
                  ? 'bg-rose-50 text-rose-700 border-rose-200'
                  : String(job.priority).toLowerCase().startsWith('p2') || String(job.priority).toLowerCase() === 'high'
                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                    : 'bg-slate-50 text-slate-600 border-slate-200'
              }`}
              data-testid="jaag-priority"
            >
              {String(job.priority).toUpperCase()}
            </span>
          )}
          {machineCount != null && machineCount > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide bg-slate-50 text-slate-600 border-slate-200" data-testid="jaag-machines">
              <Package size={9} /> {machineCount} {machineCount === 1 ? 'machine' : 'machines'}
            </span>
          )}
          {lastVisit && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide bg-blue-50 text-blue-700 border-blue-200" data-testid="jaag-last-visit">
              <History size={9} /> Last visit: {lastVisit}
            </span>
          )}
        </div>
      </div>

      {/* Big arrive button — only when not yet arrived and not closed. */}
      {!['closed', 'invoiced', 'awaiting_sign_off', 'repaired'].includes(job.status) && (
        <div className="border-t border-slate-100 p-2 bg-slate-50/40">
          {activeOnSite ? (
            <div className="flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-emerald-50 text-emerald-800 text-sm font-bold" data-testid="jaag-on-site-now">
              <CheckCircle2 size={14} /> On site — timer running
            </div>
          ) : hasArrived ? (
            <button
              type="button"
              onClick={arrive}
              disabled={busy}
              className="w-full inline-flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-white border border-slate-200 text-slate-700 text-xs font-bold uppercase tracking-wide disabled:opacity-50"
              data-testid="jaag-resume"
            >
              <Play size={12} /> Resume on-site timer
            </button>
          ) : (
            <button
              type="button"
              onClick={arrive}
              disabled={busy}
              className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-700 text-white text-sm font-bold uppercase tracking-wide shadow-sm disabled:opacity-50"
              data-testid="jaag-arrive"
            >
              <LogIn size={14} /> I'm on site
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// Iter 220c — header pill that mirrors the autosave state.
function DraftStatusPill({ saving, lastSavedAt, dirty }) {
  if (saving) {
    return (
      <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-blue-700" data-testid="draft-status-saving">
        <Loader2 size={10} className="animate-spin" /> Saving…
      </span>
    );
  }
  if (dirty) {
    return (
      <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-amber-600" data-testid="draft-status-dirty">
        ● Unsaved
      </span>
    );
  }
  if (lastSavedAt) {
    return (
      <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-emerald-600" data-testid="draft-status-saved">
        ✓ Saved
      </span>
    );
  }
  return null;
}

// Iter 220ct — visible sync-status chip. Reads the existing
// IndexedDB queue hook so we don't need any new plumbing.
//   • Online + 0 queued        →   green WiFi + "Synced"
//   • Online + N queued (replay) → blue cloud + "Syncing N"
//   • Offline                  →   amber WiFi-off + "Offline N queued"
function SyncStatusChip() {
  const { online, pending } = useEngineerOfflineQueue();
  let cls;
  let icon;
  let label;
  let testid;
  if (!online) {
    cls   = 'bg-amber-50 text-amber-800 border-amber-200';
    icon  = <WifiOff size={11} />;
    label = pending > 0 ? `Offline · ${pending} queued` : 'Offline';
    testid = 'sync-status-offline';
  } else if (pending > 0) {
    cls   = 'bg-blue-50 text-blue-800 border-blue-200';
    icon  = <CloudUpload size={11} className="animate-pulse" />;
    label = `Syncing · ${pending}`;
    testid = 'sync-status-syncing';
  } else {
    cls   = 'bg-emerald-50 text-emerald-700 border-emerald-200';
    icon  = <Wifi size={11} />;
    label = 'Synced';
    testid = 'sync-status-synced';
  }
  return (
    <span
      className={`hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wide ${cls}`}
      title={pending > 0 ? `${pending} pending write${pending === 1 ? '' : 's'} in the offline queue` : (online ? 'All changes synced' : 'No connection — your work is being saved locally')}
      data-testid={testid}
    >
      {icon} {label}
    </span>
  );
}


// ─────────────────────────── Active timer bar ───────────────────────────

function ActiveTimerBar({ timer, onStop }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!timer) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timer]);
  if (!timer) return null;
  const ms = Math.max(0, now - new Date(timer.start_at).getTime());
  const mins = Math.floor(ms / 60000);
  const secs = String(Math.floor((ms % 60000) / 1000)).padStart(2, '0');
  return (
    <div className="bg-emerald-50 border-y border-emerald-200" data-testid="job-active-timer-bar">
      <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-3">
        <Clock size={16} className="text-emerald-600" />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase font-bold tracking-wide text-emerald-700">
            On the clock · {timer.category}
          </p>
          <p className="text-base font-extrabold tabular-nums text-emerald-900">{mins}m {secs}s</p>
        </div>
        <button onClick={onStop} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700" data-testid="job-active-timer-stop">
          <Square size={12} /> Stop
        </button>
      </div>
    </div>
  );
}

// ────────────────────────────── Time tab ────────────────────────────────

function TimeTab({ job, busy, setBusy, onChange }) {
  const entries = job.time_entries || [];
  const active = entries.find(e => !e.end_at);
  const blockedBySafety = !job.safety_signoff && job?.safety_template;

  const start = async (category) => {
    setBusy(true);
    try {
      const r = await engineerSendOrQueue({
        method: 'POST',
        path: '/svc/engineer/time/start',
        body: { case_id: job.id, category },
        label: `Start ${category.replace('_', ' ')} timer`,
      });
      if (r.ok) {
        notify.success(`${category.replace('_', ' ')} timer started`);
      } else if (r.offline) {
        notify.success(`Timer start queued — will sync when you reconnect`);
      }
      await onChange();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.code === 'safety_signoff_required') {
        notify.error('Complete the H&S checklist first (on the existing job detail page).');
      } else {
        notify.error('Could not start timer');
      }
    } finally { setBusy(false); }
  };

  const totalsByCategory = entries.reduce((acc, e) => {
    const k = e.category || 'on_site';
    acc[k] = (acc[k] || 0) + (e.duration_minutes || 0);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {blockedBySafety && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 flex items-start gap-2" data-testid="time-safety-warning">
          <AlertTriangle size={14} className="mt-0.5" />
          <span>Pre-job H&amp;S checklist required before starting the <b>on-site</b> timer.</span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2" data-testid="time-totals">
        <Totals label="On site"   value={fmtMins(totalsByCategory.on_site)} color="#1d4ed8" />
        <Totals label="Travel"    value={fmtMins(totalsByCategory.travel)}  color="#6366f1" />
        <Totals label="Admin"     value={fmtMins(totalsByCategory.admin)}   color="#64748b" />
      </div>

      {!active ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="time-start-card">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Start a timer</p>
          <div className="grid grid-cols-3 gap-2">
            <button disabled={busy} onClick={() => start('on_site')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 disabled:opacity-50" data-testid="time-start-on_site">
              <Play size={16} /><span className="text-xs font-bold">On site</span>
            </button>
            <button disabled={busy} onClick={() => start('travel')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-800 hover:bg-indigo-100 disabled:opacity-50" data-testid="time-start-travel">
              <Car size={16} /><span className="text-xs font-bold">Travel</span>
            </button>
            <button disabled={busy} onClick={() => start('admin')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100 disabled:opacity-50" data-testid="time-start-admin">
              <Clock size={16} /><span className="text-xs font-bold">Admin</span>
            </button>
          </div>
        </div>
      ) : null}

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="time-history">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">History</p>
        {entries.length === 0 ? (
          <p className="text-center text-sm text-slate-400 py-6">No time logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {entries.map(e => (
              <li key={e.id} className="py-2 flex items-center gap-3" data-testid={`time-entry-${e.id}`}>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full"
                  style={{ background: e.category === 'on_site' ? '#dbeafe' : e.category === 'travel' ? '#e0e7ff' : '#f1f5f9',
                           color: e.category === 'on_site' ? '#1d4ed8' : e.category === 'travel' ? '#4338ca' : '#475569' }}>
                  {e.category}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{fmtMins(e.duration_minutes)} {!e.end_at && <span className="text-emerald-600">· running</span>}</p>
                  <p className="text-[11px] text-slate-500">{new Date(e.start_at).toLocaleString('en-GB')}</p>
                </div>
                {e.chargeable && <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">£</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const Totals = ({ label, value, color }) => (
  <div className="bg-white rounded-2xl border border-slate-200 p-3 text-center">
    <p className="text-[10px] uppercase font-bold tracking-wide text-slate-500">{label}</p>
    <p className="text-base font-extrabold tabular-nums mt-0.5" style={{ color }}>{value}</p>
  </div>
);

// ─────────────────────────── Travel / Mileage tab ───────────────────────

function TravelTab({ job, mileage, onChange }) {
  const [form, setForm] = useState({ miles: '', from_postcode: '', to_postcode: '', notes: '', chargeable: true });
  const [adding, setAdding] = useState(false);

  // Geolocation auto-trip tracker
  const [trip, setTrip] = useState(null); // { startedAt, miles, watchId, samples }
  const [geoError, setGeoError] = useState('');

  const haversineMiles = (a, b) => {
    const R = 3958.8; // Earth radius in miles
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const x = Math.sin(dLat / 2) ** 2
      + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
  };

  const startTrip = useCallback(() => {
    setGeoError('');
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGeoError('Geolocation not supported on this device.');
      return;
    }
    let last = null;
    let total = 0;
    let samples = 0;
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const here = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        samples += 1;
        if (last) {
          const seg = haversineMiles(last, here);
          // Ignore noisy GPS jitter (<5m ≈ 0.003 mi) and ignore impossible jumps (>2 mi between 10s pings = ~720 mph)
          if (seg > 0.003 && seg < 2) total += seg;
        }
        last = here;
        setTrip(t => t && ({ ...t, miles: total, samples, lastFix: here }));
      },
      (err) => {
        setGeoError(err?.message || 'Geolocation error');
        navigator.geolocation.clearWatch(id);
        setTrip(null);
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 },
    );
    setTrip({ startedAt: Date.now(), miles: 0, watchId: id, samples: 0, lastFix: null });
  }, []);

  const stopTrip = useCallback(() => {
    if (trip?.watchId != null) {
      try { navigator.geolocation.clearWatch(trip.watchId); } catch { /* noop */ }
    }
    if (trip) {
      const rounded = Math.round(trip.miles * 10) / 10; // 0.1 mi precision
      if (rounded > 0) {
        setForm(f => ({ ...f, miles: String(rounded) }));
        notify.success(`Trip captured: ${rounded.toFixed(1)} mi`);
      } else {
        notify.error('No mileage captured — check GPS signal.');
      }
    }
    setTrip(null);
  }, [trip]);

  useEffect(() => () => {
    // Cleanup the watcher on unmount or tab change
    if (trip?.watchId != null) {
      try { navigator.geolocation.clearWatch(trip.watchId); } catch { /* noop */ }
    }
  }, [trip?.watchId]);

  const submit = async () => {
    const miles = Number(form.miles);
    if (!(miles > 0)) { notify.error('Enter miles > 0'); return; }
    setAdding(true);
    try {
      const r = await engineerSendOrQueue({
        method: 'POST',
        path: `/svc/engineer/jobs/${job.id}/mileage`,
        body: {
          miles,
          from_postcode: form.from_postcode || null,
          to_postcode: form.to_postcode || null,
          notes: form.notes || null,
          chargeable: form.chargeable,
        },
        label: `Log mileage: ${miles} mi`,
      });
      if (r.ok) {
        notify.success('Mileage logged');
      } else if (r.offline) {
        notify.success('Mileage queued — will sync when you reconnect');
      }
      setForm({ miles: '', from_postcode: '', to_postcode: '', notes: '', chargeable: true });
      await onChange();
    } catch (e) {
      notify.error('Could not log mileage');
    } finally { setAdding(false); }
  };

  const remove = async (id) => {
    try {
      await axios.delete(`${API}/svc/engineer/jobs/${job.id}/mileage/${id}`, auth());
      notify.success('Removed');
      await onChange();
    } catch { notify.error('Could not delete'); }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2">
        <Totals label="Miles"   value={mileage.total_miles?.toFixed(1) || '0.0'} color="#6366f1" />
        <Totals label="Billable" value={fmtGBP(mileage.total_amount_gbp)} color="#059669" />
      </div>

      {/* Geo-auto trip tracker */}
      <div
        className={`rounded-2xl border p-4 ${trip ? 'border-rose-200 bg-rose-50' : 'border-slate-200 bg-white'}`}
        data-testid="mileage-trip-tracker"
      >
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
          <MapPin size={11} /> Auto-track this trip
        </p>
        {trip ? (
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full bg-rose-500 animate-pulse shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-base font-extrabold tabular-nums text-rose-700">
                {trip.miles.toFixed(2)} mi
              </p>
              <p className="text-[11px] text-rose-700">
                {Math.floor((Date.now() - trip.startedAt) / 1000)}s elapsed · {trip.samples} GPS samples
              </p>
            </div>
            <button
              type="button"
              onClick={stopTrip}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-full bg-rose-600 text-white text-xs font-bold"
              data-testid="mileage-trip-stop"
            >
              <Square size={12} /> Stop trip
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <p className="text-xs text-slate-500 flex-1">
              Tap to start GPS tracking — the captured distance auto-fills the form below.
              You can edit before saving.
            </p>
            <button
              type="button"
              onClick={startTrip}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-full bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-xs font-bold"
              data-testid="mileage-trip-start"
            >
              <Play size={12} /> Start trip
            </button>
          </div>
        )}
        {geoError && <p className="text-[11px] text-rose-600 mt-2" data-testid="mileage-trip-error">{geoError}</p>}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="mileage-form">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Log mileage</p>
        <div className="grid grid-cols-2 gap-2">
          <Input label="Miles *" type="number" v={form.miles} on={v => setForm(f => ({ ...f, miles: v }))} testid="mileage-miles" />
          <div className="flex items-end gap-2">
            <label className="text-xs text-slate-600 flex items-center gap-2 select-none">
              <input type="checkbox" checked={form.chargeable} onChange={e => setForm(f => ({ ...f, chargeable: e.target.checked }))} data-testid="mileage-chargeable" />
              Chargeable
            </label>
          </div>
          <Input label="From postcode" v={form.from_postcode} on={v => setForm(f => ({ ...f, from_postcode: v }))} testid="mileage-from" />
          <Input label="To postcode"   v={form.to_postcode}   on={v => setForm(f => ({ ...f, to_postcode: v }))}   testid="mileage-to" />
        </div>
        <Input label="Notes" v={form.notes} on={v => setForm(f => ({ ...f, notes: v }))} testid="mileage-notes" fullWidth />
        <button onClick={submit} disabled={adding} className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="mileage-add-btn">
          {adding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Add mileage
        </button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="mileage-history">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">History</p>
        {mileage.items.length === 0 ? (
          <p className="text-center text-sm text-slate-400 py-6">No mileage logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {mileage.items.map(m => (
              <li key={m.id} className="py-2 flex items-center gap-3" data-testid={`mileage-row-${m.id}`}>
                <Car size={16} className="text-indigo-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{m.miles} mi · {fmtGBP(m.amount_gbp)}</p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {(m.from_postcode || '—')} → {(m.to_postcode || '—')}
                    {m.notes ? ` · ${m.notes}` : ''}
                  </p>
                </div>
                <button onClick={() => remove(m.id)} className="p-1 text-slate-400 hover:text-rose-600" aria-label="Remove" data-testid={`mileage-remove-${m.id}`}>
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

const Input = ({ label, v, on, testid, type = 'text', fullWidth }) => (
  <div className={fullWidth ? 'col-span-2 mt-2' : ''}>
    <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">{label}</label>
    <input type={type} value={v ?? ''} onChange={e => on(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" data-testid={testid} />
  </div>
);

// ───────────────────────── Photos / Media tab ──────────────────────────

const MAX_VIDEO_MB = 30;
const MAX_VIDEO_SECONDS = 30;

async function probeVideoDuration(file) {
  return await new Promise((resolve) => {
    const v = document.createElement('video');
    v.preload = 'metadata';
    v.onloadedmetadata = () => resolve(Math.round(v.duration || 0));
    v.onerror = () => resolve(0);
    v.src = URL.createObjectURL(file);
  });
}

function PhotosTab({ job, onChange }) {
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState('');
  const [stage, setStage] = useState('progress'); // before / progress / after
  const photoInput = useRef(null);
  const videoInput = useRef(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  const photos = job.photos || [];

  const grouped = useMemo(() => ({
    before:   photos.filter(p => (p.caption || '').toLowerCase().startsWith('[before]')),
    progress: photos.filter(p => !/^\[(before|after)]/i.test(p.caption || '')),
    after:    photos.filter(p => (p.caption || '').toLowerCase().startsWith('[after]')),
  }), [photos]);

  const uploadFile = useCallback(async (file, kind) => {
    if (!file) return;
    // Video-specific validation: ≤30 MB, ≤30 s
    if (kind === 'video') {
      const sizeMb = file.size / (1024 * 1024);
      if (sizeMb > MAX_VIDEO_MB) {
        notify.error(`Video too large (${sizeMb.toFixed(1)} MB > ${MAX_VIDEO_MB} MB)`);
        return;
      }
      const dur = await probeVideoDuration(file);
      if (dur > MAX_VIDEO_SECONDS) {
        notify.error(`Video too long (${dur}s > ${MAX_VIDEO_SECONDS}s)`);
        return;
      }
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      // Iter 216h257 — use `service-media` so the backend allow-list
      // covers BOTH images and videos. Old `photos|videos` categories
      // used the global MIME_ALL_ATTACHMENTS allow-list which silently
      // 415'd every video.
      const u = await axios.post(`${API}/files/upload?category=service-media`, fd, {
        ...auth(),
        headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const fileUrl = u.data?.download_url || u.data?.storage_path;
      const prefix = stage === 'before' ? '[BEFORE] ' : stage === 'after' ? '[AFTER] ' : '';
      await axios.post(`${API}/svc/engineer/photos`, {
        case_id: job.id, file_url: fileUrl,
        mime_type: u.data?.content_type || (kind === 'video' ? 'video/webm' : 'image/jpeg'),
        caption: (prefix + (caption || '')).trim(),
        duration_seconds: kind === 'video' ? await probeVideoDuration(file) : null,
      }, auth());
      notify.success(kind === 'video' ? 'Video attached' : 'Photo attached');
      setCaption('');
      await onChange();
    } catch (err) {
      // Iter 216h257 — surface the real reason. "Upload failed" with no
      // detail trained engineers to ignore the toast and re-try the
      // same file (still failing). Now show the server-supplied detail
      // when available so MIME / size / auth errors are obvious.
      const detail = err?.response?.data?.detail
        || err?.response?.data?.message
        || err?.message
        || 'Unknown error';
      notify.error('Upload failed', String(detail).slice(0, 200));
    } finally { setUploading(false); }
  }, [stage, caption, job.id, onChange]);

  const onPhoto = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    await uploadFile(f, 'photo');
  };
  const onVideo = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    await uploadFile(f, 'video');
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="photos-uploader">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Capture media</p>
        <div className="flex gap-1 mb-3" data-testid="photo-stage-toggle">
          {['before', 'progress', 'after'].map(s => (
            <button key={s} type="button" onClick={() => setStage(s)}
              className={`flex-1 py-1.5 rounded-lg text-xs font-bold capitalize border ${stage === s ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200'}`}
              data-testid={`photo-stage-${s}`}>
              {s}
            </button>
          ))}
        </div>
        <input type="text" placeholder="Optional caption" value={caption} onChange={e => setCaption(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white mb-2" data-testid="photo-caption" />
        <input ref={photoInput} type="file" accept="image/*" capture="environment" onChange={onPhoto} className="hidden" data-testid="photo-file-input" />
        <input ref={videoInput} type="file" accept="video/*" capture="environment" onChange={onVideo} className="hidden" data-testid="video-file-input" />
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => photoInput.current?.click()} disabled={uploading} className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="photo-upload-btn">
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
            Photo
          </button>
          <button type="button" onClick={() => videoInput.current?.click()} disabled={uploading} className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white border border-slate-200 text-slate-700 text-sm font-bold hover:bg-slate-50 disabled:opacity-50" data-testid="video-upload-btn">
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Video size={14} />}
            Video (≤{MAX_VIDEO_SECONDS}s)
          </button>
        </div>
      </div>

      {(['before', 'progress', 'after']).map(stage => (
        <div key={stage} className="bg-white rounded-2xl border border-slate-200 p-4" data-testid={`photos-group-${stage}`}>
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2 capitalize">{stage} ({grouped[stage].length})</p>
          {grouped[stage].length === 0 ? (
            <p className="text-center text-xs text-slate-400 py-4">No {stage} media.</p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              {grouped[stage].map(p => <MediaTile key={p.id} item={p} />)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function MediaTile({ item }) {
  const isVideo = item.kind === 'video' || (item.mime_type || '').startsWith('video/');
  if (isVideo) {
    return (
      <a href={item.file_url} target="_blank" rel="noopener" className="relative aspect-square rounded-lg overflow-hidden bg-slate-900 border border-slate-200 group" data-testid={`video-${item.id}`}>
        
        <video src={item.file_url} className="w-full h-full object-cover" preload="metadata" muted />
        <span className="absolute inset-0 flex items-center justify-center">
          <span className="w-9 h-9 rounded-full bg-white/90 flex items-center justify-center shadow-md group-hover:scale-110 transition-transform">
            <Play size={14} className="text-slate-900" style={{ marginLeft: 2 }} />
          </span>
        </span>
        {item.duration_seconds ? (
          <span className="absolute bottom-1 right-1 bg-black/70 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">{item.duration_seconds}s</span>
        ) : null}
      </a>
    );
  }
  return (
    <a href={item.file_url} target="_blank" rel="noopener" className="aspect-square rounded-lg overflow-hidden bg-slate-100 border border-slate-200 hover:border-slate-300" data-testid={`photo-${item.id}`}>
      
      <img src={item.file_url} alt={item.caption || 'job photo'} className="w-full h-full object-cover" />
    </a>
  );
}

// ─────────────────────────── Equipment tab (iter 220cn) ─────────────
//
// Auto-loads every equipment record for the case's site and lets the
// engineer tick which ones they're working on. The picked rows fan
// out as `svc_work_visit_machines` rows on the case — used by the
// per-machine work report (serviced/cleaned/notes), the Parts tab
// (parts can be assigned per row), and the Complete tab's
// `WorkVisitMachinesCard` is now hosted here too.

function EquipmentTab({ job }) {
  return (
    <div className="space-y-4" data-testid="equipment-tab">
      <div className="bg-white rounded-2xl border border-slate-200 p-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Package size={18} className="text-blue-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold text-slate-900">Site equipment</p>
            <p className="text-[11px] text-slate-500 leading-snug mt-0.5">
              Tap <strong>From site</strong> to pre-load every machine at this
              gym, then tick the ones you'll service. Write your report and
              tag parts against each row.
            </p>
          </div>
        </div>
      </div>

      {/* Iter 220cn — All machine actions for this job live in this
          card: "From site" picker (multi-select), "New asset" link,
          and per-row serviced/cleaned/notes. Moved out of Complete. */}
      <WorkVisitMachinesCard caseId={job.id} />
    </div>
  );
}


// ─────────────────────────── Parts tab ───────────────────────────────

function PartsTab({ job, onChange }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [adhoc, setAdhoc] = useState({ part_sku: '', qty: 1, notes: '' });
  const [busy, setBusy] = useState(false);
  const [showRequest, setShowRequest] = useState(null); // {sku, name} or null
  const [requests, setRequests] = useState([]);
  // Iter 220cn — load this case's machine rows so the request modal
  // can show a machine picker (parts can be tagged per machine).
  const [machines, setMachines] = useState([]);

  const loadRequests = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/parts-requests`, {
        ...auth(), params: { case_id: job.id },
      });
      setRequests(r.data?.items || []);
    } catch { /* noop */ }
  }, [job.id]);
  useEffect(() => { loadRequests(); }, [loadRequests]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/svc/engineer/jobs/${job.id}/machines`, auth(),
        );
        if (!cancelled) setMachines(r.data?.machines || r.data || []);
      } catch { /* noop — machine list is optional context */ }
    })();
    return () => { cancelled = true; };
  }, [job.id]);

  const runSearch = useCallback(async (q) => {
    if (!q || q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const r = await axios.get(`${API}/svc/parts`, { ...auth(), params: { q, limit: 12 } });
      setResults(r.data?.items || []);
    } catch { setResults([]); }
    finally { setSearching(false); }
  }, []);
  useEffect(() => {
    const id = setTimeout(() => runSearch(search), 300);
    return () => clearTimeout(id);
  }, [search, runSearch]);

  const consume = async (allocationId) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/parts/${allocationId}/consume`, {}, auth());
      notify.success('Marked as used');
      await onChange();
    } catch { notify.error('Could not update'); }
    finally { setBusy(false); }
  };

  const addPartUsage = async (sku, qty = 1) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/parts/use`, {
        part_sku: sku, qty, notes: adhoc.notes || null,
      }, auth());
      notify.success(`${sku} × ${qty} added`);
      setAdhoc({ part_sku: '', qty: 1, notes: '' });
      setSearch('');
      setResults([]);
      await onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not add part');
    } finally { setBusy(false); }
  };

  const submitRequest = async (sku, name, qty, urgency, notes, machineId, machineName) => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/parts-requests`, {
        case_id: job.id, part_sku: sku, part_name: name,
        qty, urgency, notes,
        machine_id: machineId || null,
        machine_name: machineName || null,
      }, auth());
      notify.success('Parts request sent to admin');
      setShowRequest(null);
      await loadRequests();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not send request');
    } finally { setBusy(false); }
  };

  const cancelRequest = async (id) => {
    try {
      await axios.delete(`${API}/svc/engineer/parts-requests/${id}`, auth());
      notify.success('Request cancelled');
      await loadRequests();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not cancel');
    }
  };

  const allocated = job.allocated_parts || [];
  const open = allocated.filter(a => !a.fulfilled);
  const used = allocated.filter(a => a.fulfilled);
  const pendingRequests = requests.filter(r => r.status === 'pending');

  return (
    <div className="space-y-4">
      {open.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-allocated">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Allocated for this job</p>
          <ul className="divide-y divide-slate-100">
            {open.map(a => (
              <li key={a.id} className="py-2 flex items-center gap-3" data-testid={`parts-allocated-${a.id}`}>
                <Package size={16} className="text-slate-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{a.qty} × {a.part_sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{a.part_name} · from {a.source}</p>
                </div>
                <button onClick={() => consume(a.id)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold disabled:opacity-50" data-testid={`parts-consume-${a.id}`}>
                  <Check size={12} /> Mark used
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pendingRequests.length > 0 && (
        <div className="bg-white rounded-2xl border border-amber-200 bg-amber-50 p-4" data-testid="parts-pending-requests">
          <p className="text-[11px] uppercase font-bold tracking-wide text-amber-700 mb-2">
            Awaiting admin approval ({pendingRequests.length})
          </p>
          <ul className="divide-y divide-amber-100">
            {pendingRequests.map(r => (
              <li key={r.id} className="py-2 flex items-center gap-3" data-testid={`parts-request-${r.id}`}>
                <Send size={14} className="text-amber-600" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-amber-900">{r.qty} × {r.part_sku}</p>
                  <p className="text-[11px] text-amber-700 truncate">
                    {r.part_name} · <span className="capitalize">{r.urgency}</span>
                    {r.machine_name ? <> · <span className="font-semibold">{r.machine_name}</span></> : null}
                  </p>
                </div>
                <button onClick={() => cancelRequest(r.id)} className="p-1 text-amber-700 hover:text-rose-600" aria-label="Cancel" data-testid={`parts-request-cancel-${r.id}`}>
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-adhoc-form">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Add a part you used</p>
        <div className="relative mb-2">
          <Search size={14} className="absolute left-3 top-3 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search catalogue by SKU or name…" className="w-full text-sm border border-slate-200 rounded-lg pl-9 pr-3 py-2 bg-white" data-testid="parts-search" />
        </div>
        {results.length > 0 && (
          <ul className="border border-slate-200 rounded-lg divide-y divide-slate-100 max-h-56 overflow-y-auto mb-2" data-testid="parts-search-results">
            {results.map(p => (
              <li key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50" data-testid={`parts-result-${p.sku}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{p.sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{p.name} · {fmtGBP(p.list_price)}</p>
                </div>
                <button onClick={() => addPartUsage(p.sku, 1)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-blue-600 text-white text-xs font-bold disabled:opacity-50" data-testid={`parts-use-${p.sku}`}>
                  <Plus size={12} /> Use
                </button>
                <button onClick={() => setShowRequest({ sku: p.sku, name: p.name })} className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-white border border-slate-200 text-slate-700 text-xs font-bold hover:bg-slate-50" data-testid={`parts-request-${p.sku}`}>
                  <Send size={12} /> Request
                </button>
              </li>
            ))}
          </ul>
        )}
        {search.length >= 2 && !searching && results.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-200 p-3 mb-2 flex items-center gap-2" data-testid="parts-empty-catalogue">
            <AlertTriangle size={14} className="text-slate-400" />
            <p className="text-xs text-slate-600 flex-1">"{search}" isn't in the catalogue.</p>
            <button
              type="button"
              onClick={() => setShowRequest({ sku: search.toUpperCase(), name: '' })}
              className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-amber-600 text-white text-xs font-bold"
              data-testid="parts-request-new-sku"
            >
              <Send size={12} /> Request it
            </button>
          </div>
        )}
        <div className="grid grid-cols-3 gap-2 mt-2">
          <Input label="SKU"   v={adhoc.part_sku} on={v => setAdhoc(f => ({ ...f, part_sku: v }))} testid="parts-adhoc-sku" />
          <Input label="Qty"   type="number" v={adhoc.qty} on={v => setAdhoc(f => ({ ...f, qty: Math.max(1, Number(v)) }))} testid="parts-adhoc-qty" />
          <div className="flex items-end">
            <button onClick={() => adhoc.part_sku && addPartUsage(adhoc.part_sku.toUpperCase(), Number(adhoc.qty) || 1)} disabled={busy || !adhoc.part_sku} className="w-full inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="parts-adhoc-add">
              <Plus size={14} /> Add
            </button>
          </div>
        </div>
      </div>

      {used.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="parts-used-list">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Used on this job</p>
          <ul className="divide-y divide-slate-100">
            {used.map(a => (
              <li key={a.id} className="py-2 flex items-center gap-3" data-testid={`parts-used-${a.id}`}>
                <CheckCircle2 size={16} className="text-emerald-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">{a.qty} × {a.part_sku}</p>
                  <p className="text-[11px] text-slate-500 truncate">{a.part_name}</p>
                </div>
                {a.list_price_gbp ? <span className="text-xs font-bold text-slate-700 tabular-nums">{fmtGBP(a.list_price_gbp * (a.qty || 0))}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showRequest && (
        <PartsRequestModal
          sku={showRequest.sku}
          name={showRequest.name}
          machines={machines}
          onCancel={() => setShowRequest(null)}
          onSubmit={(q, u, n, mid, mname) =>
            submitRequest(showRequest.sku, showRequest.name, q, u, n, mid, mname)
          }
          busy={busy}
        />
      )}
    </div>
  );
}

function PartsRequestModal({ sku, name, machines = [], onCancel, onSubmit, busy }) {
  const [qty, setQty] = useState(1);
  const [urgency, setUrgency] = useState('normal');
  const [notes, setNotes] = useState('');
  // Iter 220cn — machine picker. Engineers can tag a parts request
  // to a specific machine on this case so admin/CRM knows exactly
  // which asset the spare is destined for. Optional — falls back to
  // the case-level request when no machine is picked.
  const [machineId, setMachineId] = useState('');
  const selectedMachine = machines.find(m => (m.id || m._id) === machineId);
  const machineName = selectedMachine
    ? (selectedMachine.asset_name
        || selectedMachine.name
        || selectedMachine.machine_name
        || selectedMachine.asset_serial
        || '')
    : '';
  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-end md:items-center justify-center p-4" data-testid="parts-request-modal">
      <div className="bg-white rounded-2xl w-full max-w-md p-5 shadow-xl border border-slate-200">
        <div className="flex items-center gap-2 mb-3">
          <Send size={16} className="text-blue-600" />
          <h3 className="text-base font-bold text-slate-900">Request a part</h3>
        </div>
        <p className="text-xs text-slate-500 mb-3">
          Admin will be notified instantly. On approval the part is allocated to your van and this job.
        </p>
        <div className="space-y-2">
          <Input label="SKU" v={sku} on={() => {}} testid="parts-request-sku" fullWidth />
          {name ? (
            <Input label="Name" v={name} on={() => {}} testid="parts-request-name" fullWidth />
          ) : null}
          <Input label="Quantity" type="number" v={qty} on={v => setQty(Math.max(1, Number(v) || 1))} testid="parts-request-qty" fullWidth />
          {machines.length > 0 && (
            <div>
              <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">
                Machine (optional)
              </label>
              <select
                value={machineId}
                onChange={(e) => setMachineId(e.target.value)}
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                data-testid="parts-request-machine"
              >
                <option value="">— Case-level (no specific machine) —</option>
                {machines.map(m => {
                  const id = m.id || m._id;
                  const label = m.asset_name || m.name || m.machine_name || m.model || m.asset_serial || id;
                  const sub = [m.asset_serial, m.asset_type].filter(Boolean).join(' · ');
                  return (
                    <option key={id} value={id} data-testid={`parts-request-machine-opt-${id}`}>
                      {label}{sub ? ` — ${sub}` : ''}
                    </option>
                  );
                })}
              </select>
              <p className="text-[11px] text-slate-400 mt-1">
                Tag this spare to the exact machine being worked on.
              </p>
            </div>
          )}
          <div>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Urgency</label>
            <div className="flex gap-1">
              {['normal', 'urgent', 'critical'].map(u => (
                <button key={u} type="button" onClick={() => setUrgency(u)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-bold capitalize border ${urgency === u ? (
                    u === 'critical' ? 'bg-rose-600 text-white border-rose-600'
                    : u === 'urgent' ? 'bg-amber-500 text-white border-amber-500'
                    : 'bg-blue-600 text-white border-blue-600'
                  ) : 'bg-white text-slate-600 border-slate-200'}`}
                  data-testid={`parts-request-urgency-${u}`}>
                  {u}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-[11px] uppercase font-bold tracking-wide text-slate-500 block mb-1">Notes</label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)} className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" data-testid="parts-request-notes" placeholder="e.g. specific brand, customer in a hurry…" />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-2 rounded-full bg-white border border-slate-200 text-slate-700 text-sm font-bold" data-testid="parts-request-cancel">Cancel</button>
          <button onClick={() => onSubmit(qty, urgency, notes, machineId || null, machineName || null)} disabled={busy} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold disabled:opacity-50" data-testid="parts-request-submit">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send to admin
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────── Complete tab ───────────────────────────

function CompleteTab({ job, locked, onChange, navigate, draft, setDraft, clearDraft }) {
  // Iter 220c — Use the parent's lifted draft so tab switches NEVER
  // lose typed text. Falls back to the case's stored values on first
  // open so engineers see what was previously persisted.
  const summary = draft.summary !== undefined ? draft.summary : (job.resolution_notes || '');
  const signatureName = draft.signature_name || '';
  const target = draft.target || 'awaiting_sign_off';
  const customFields = draft.custom_fields || {};
  const autoInvoice = draft.auto_invoice === undefined ? true : !!draft.auto_invoice;

  const [signatureData, setSignatureData] = useState('');
  const [showSignature, setShowSignature] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draftResult, setDraftResult] = useState(null);

  const setSummary = (v) => setDraft({ summary: v });
  const setSignatureName = (v) => setDraft({ signature_name: v });
  const setTarget = (v) => setDraft({ target: v });
  const setCustomFields = (patchOrFn) => setDraft((prev) => ({
    ...prev,
    custom_fields: typeof patchOrFn === 'function'
      ? patchOrFn(prev?.custom_fields || {})
      : patchOrFn,
  }));
  const setAutoInvoice = (v) => setDraft({ auto_invoice: !!v });

  const complete = async () => {
    if (!summary.trim()) { notify.error('Add a work summary'); return; }
    setBusy(true);
    try {
      if (signatureData && signatureName.trim()) {
        await axios.post(`${API}/svc/engineer/signature`, {
          case_id: job.id, signed_by_name: signatureName.trim(),
          image_data: signatureData, summary: summary.trim(),
        }, auth());
      }
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/complete`, {
        summary: summary.trim(), target, chargeable: true,
        custom_fields: customFields,
      }, auth());
      notify.success('Job completed');
      if (autoInvoice) {
        try {
          const r = await axios.post(
            `${API}/svc/engineer/jobs/${job.id}/generate-invoice-draft`, {}, auth(),
          );
          setDraftResult(r.data);
          notify.success(`Draft ${r.data.invoice_number} created`);
        } catch (e) {
          const m = e?.response?.data?.detail || 'No chargeable lines yet';
          notify.error(`Invoice draft skipped: ${m}`);
        }
      }
      // Iter 220c — flush the autosave draft now that the job is wrapped.
      await clearDraft?.();
      await onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not complete job');
    } finally { setBusy(false); }
  };

  if (locked) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-5 text-center" data-testid="complete-locked">
        <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
        <p className="text-sm font-bold text-slate-900 capitalize">{job.status.replace('_', ' ')}</p>
        <p className="text-xs text-slate-500 mt-1">This job is already wrapped up.</p>
        {job.invoice_draft_id ? (
          <button onClick={() => navigate(`/svc/engineer/invoices/${job.invoice_draft_id}`)} className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-bold" data-testid="complete-open-invoice">
            <Receipt size={14} /> Open invoice {job.invoice_draft_number}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-summary-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Work summary *</p>
        <textarea rows={4} value={summary} onChange={e => setSummary(e.target.value)} placeholder="What was repaired / replaced / advised…" className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white" data-testid="complete-summary" />
      </div>

      <EngineerDictationButton
        caseId={job.id}
        hint={`${job.title || ''} · ${job.asset_name || ''}`.trim()}
        onResult={(data) => {
          // Prefer the polished summary; fall back to raw transcript.
          if (data?.summary) setSummary(data.summary);
          else if (data?.transcript) setSummary(data.transcript);
        }}
      />

      {/* Iter 220 — Machine-specific custom fields (engineer-managed) */}
      <WorkReportCustomFields
        caseId={job.id}
        values={customFields}
        onChange={setCustomFields}
      />

      {/* Iter 220cn — `WorkVisitMachinesCard` moved to the dedicated
          Equipment tab. Keeping it out of Complete prevents engineers
          from filling out the work-report twice and matches the
          user-requested tab structure (Time / Travel / Photos /
          Equipment / Parts / Complete). */}

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-signature-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Customer signature (optional)</p>
        <Input label="Signed by" v={signatureName} on={setSignatureName} testid="complete-signed-by" fullWidth />
        <button type="button" onClick={() => setShowSignature(true)} className="mt-2 w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold" data-testid="complete-open-signature">
          {signatureData ? <><Check size={14} className="text-emerald-600" /> Signature captured · re-sign</> : <><ImageIcon size={14} /> Capture signature</>}
        </button>
        {showSignature && (
          <SignatureCanvas
            onSubmit={(dataUrl) => { setSignatureData(dataUrl); setShowSignature(false); }}
            onCancel={() => setShowSignature(false)}
          />
        )}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="complete-options-card">
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Outcome</p>
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'awaiting_sign_off', label: 'Awaiting sign-off' },
            { id: 'repaired',          label: 'Repaired' },
            { id: 'closed',            label: 'Close & invoice' },
          ].map(o => (
            <button key={o.id} type="button" onClick={() => setTarget(o.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border ${target === o.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200'}`}
              data-testid={`complete-target-${o.id}`}>
              {o.label}
            </button>
          ))}
        </div>
        <label className="mt-3 flex items-center gap-2 text-xs text-slate-700 select-none">
          <input type="checkbox" checked={autoInvoice} onChange={e => setAutoInvoice(e.target.checked)} data-testid="complete-auto-invoice" />
          Generate invoice draft from time + mileage + parts
        </label>
      </div>

      {draftResult && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3" data-testid="complete-draft-banner">
          <CheckCircle2 size={20} className="text-emerald-600" />
          <div className="flex-1">
            <p className="text-sm font-bold text-emerald-900">Invoice draft {draftResult.invoice_number} created</p>
            <p className="text-[11px] text-emerald-800">{(draftResult.lines || []).length} line(s) · total {fmtGBP(draftResult.total)}</p>
          </div>
          <button onClick={() => navigate(`/svc/engineer/invoices/${draftResult.id}`)} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-emerald-600 text-white text-xs font-bold" data-testid="complete-open-draft">
            <ChevronRight size={12} /> Open
          </button>
        </div>
      )}

      {/* Iter 216h257 — Report actions surface so the engineer can
          download the branded PDF or email it straight to the customer
          without leaving the Complete screen. */}
      <ReportActionsCard job={job} />

      <div className="sticky bottom-4">
        <button onClick={complete} disabled={busy} className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow-md disabled:opacity-50" data-testid="complete-submit">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
          Complete job
        </button>
      </div>
    </div>
  );
}

// Iter 216h257 — Compact card that wires the existing
// /api/svc/cases/{id}/service-report.pdf + /service-report/email
// endpoints into the Complete screen so the engineer can hand the
// customer a PDF the moment the job is done.
function ReportActionsCard({ job }) {
  const [emailing, setEmailing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [overrideEmail, setOverrideEmail] = useState('');
  const [note, setNote] = useState('');

  const download = async () => {
    setDownloading(true);
    try {
      const r = await axios.get(
        `${API}/svc/cases/${job.id}/service-report.pdf`,
        { ...auth(), responseType: 'blob' },
      );
      const blob = new Blob([r.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `service-report-${job.reference || job.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify.success('Report downloaded');
    } catch (err) {
      notify.error('Download failed', err?.response?.data?.detail || err?.message || '');
    } finally { setDownloading(false); }
  };

  const email = async () => {
    setEmailing(true);
    try {
      const body = {};
      if (overrideEmail.trim()) body.to = overrideEmail.trim();
      if (note.trim()) body.note = note.trim();
      await axios.post(`${API}/svc/cases/${job.id}/service-report/email`, body, auth());
      notify.success('Report emailed to customer');
      setNote('');
    } catch (err) {
      notify.error('Email failed', err?.response?.data?.detail || err?.message || '');
    } finally { setEmailing(false); }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3" data-testid="complete-report-card">
      <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">Service report</p>
      <p className="text-xs text-slate-600">
        Send the branded PDF straight to {job.customer_email || 'the customer'} — or download it for your records.
      </p>
      <input
        type="email"
        value={overrideEmail}
        onChange={(e) => setOverrideEmail(e.target.value)}
        placeholder={`Customer email (default: ${job.customer_email || '—'})`}
        className="w-full text-sm px-3 py-2 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-400"
        data-testid="complete-report-email-to"
      />
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Optional cover note for the customer…"
        rows={2}
        className="w-full text-sm px-3 py-2 rounded-lg border border-slate-200 focus:outline-none focus:border-blue-400"
        data-testid="complete-report-note"
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={download}
          disabled={downloading}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-bold border border-slate-200 bg-white text-slate-700 disabled:opacity-50"
          data-testid="complete-report-download"
        >
          {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
          Download PDF
        </button>
        <button
          type="button"
          onClick={email}
          disabled={emailing}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-xs font-bold bg-blue-600 text-white disabled:opacity-50"
          data-testid="complete-report-email"
        >
          {emailing ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          Email report
        </button>
      </div>
    </div>
  );
}
