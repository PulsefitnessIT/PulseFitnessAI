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
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Clock, Wrench, Car, Loader2, RefreshCw,
  Play, Square, Plus, Trash2, Check, AlertTriangle, ReceiptPoundSterling as Receipt,
  ChevronRight, CheckCircle2, Search, Package, X, Image as ImageIcon,
  Video, MapPin, Send, Download, Phone, Navigation,
  Wifi, WifiOff, CloudUpload, Users, MessageSquare, Timer, ShieldCheck, QrCode,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { engineerSendOrQueue, useEngineerOfflineQueue } from '@/utils/engineerOfflineQueue';
import SignatureCanvas from './SignatureCanvas';
import EngineerDictationButton from './EngineerDictationButton';
// Iter 220ds — WorkReportCustomFields temporarily not rendered on
// Complete; the concept is retained (state, payload field) but the
// per-machine rendering needs a rework, planned for Equipment tab.
// Import intentionally left commented to make the future re-add
// trivial.
// import WorkReportCustomFields from './WorkReportCustomFields';
import WorkVisitMachinesCard from './WorkVisitMachinesCard';
import useJobDraft from './useJobDraft';
import { resolveChannel } from '@/utils/channelLabel';
import { compressImage } from '@/utils/compressImage';
import { chunkedUpload } from '@/utils/chunkedUpload';
import ComplianceCard from './ComplianceCard';
// Iter 220e6 — Offline write outbox for high-value mutating calls.
// Complete, signature, parts-use and time entries survive a flaky
// connection by being persisted in IndexedDB and replayed on
// reconnect.
import { outboxPost } from '@/utils/engineerOutbox';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const fmtGBP = (n) => `£${Number(n || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtMins = (m) => {
  const total = Math.max(0, Math.round(m || 0));
  const h = Math.floor(total / 60);
  const r = total % 60;
  return h > 0 ? `${h}h ${r}m` : `${r}m`;
};

// Iter 220dt — friendly labels for the case_type / job_type
// taxonomy. Customer portal + service desk + intake all use the
// short slug; this maps it to the customer-facing label shown on
// engineer Summary and the public live-tracking page.
export const CASE_TYPE_LABELS = {
  repair: 'Repair',
  ppm: 'PPM Service',
  install: 'Installation',
  inspection: 'Inspection',
  callout: 'Emergency callout',
  audit: 'Asset audit',
};

export function labelForCaseType(slug) {
  if (!slug) return '';
  return CASE_TYPE_LABELS[String(slug).toLowerCase()] || slug;
}

// Iter 220e1 — Cover state shared between Summary chip and Complete-
// tab outcome banner. Reads the case's coverage meta and returns a
// `{covered, kind, label, detail, tone}` shape so both surfaces tell
// the same story to engineer + ops without drifting.
//
// Engineer Summary uses this to know up-front whether to crack on
// (cover present → fit parts, no auth needed) or call ops first
// (chargeable → confirm spend with customer).
//
// Iter 220e2 — Three-tone signal:
//   • red   → chargeable (engineer must confirm spend before fitting)
//   • amber → cover ends within 90 days (still proceed, but flag the
//             renewal conversation to ops)
//   • green → comfortable runway on warranty/contract
function _daysUntil(dateStr) {
  if (!dateStr) return null;
  const d = new Date(String(dateStr).slice(0, 10) + 'T00:00:00Z');
  if (Number.isNaN(d.getTime())) return null;
  const today = new Date();
  const utcToday = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.round((d.getTime() - utcToday) / 86400000);
}

export function computeCoverState(job) {
  if (!job) {
    return { covered: false, kind: 'chargeable', tone: 'red', label: 'Chargeable visit' };
  }
  const meta = job.source_meta || {};
  const status = (meta.coverage_status || job.coverage_status || '').toLowerCase();
  const warrantyActive = !!meta.warranty_active;
  const cover = (job.cover_type || '').toLowerCase();
  const explicitCover = cover && cover !== 'chargeable' && cover !== 'none';
  const covered = status === 'covered' || warrantyActive || explicitCover;
  if (!covered) {
    return {
      covered: false,
      kind: 'chargeable',
      tone: 'red',
      expiringSoon: false,
      daysRemaining: null,
      label: 'Chargeable visit',
      detail: 'Confirm any spend with the customer before fitting parts.',
    };
  }
  if (warrantyActive) {
    const exp = (meta.warranty_expiry || '').slice(0, 10);
    const days = _daysUntil(exp);
    const expiringSoon = days !== null && days >= 0 && days <= 90;
    return {
      covered: true,
      kind: 'warranty',
      tone: expiringSoon ? 'amber' : 'green',
      expiringSoon,
      daysRemaining: days,
      label: 'Under manufacturer warranty' + (exp ? ` until ${exp}` : ''),
      short: expiringSoon ? `Warranty · ${days}d` : 'Warranty',
      detail: expiringSoon
        ? `Warranty ends in ${days} day${days === 1 ? '' : 's'} — flag renewal to ops after this visit.`
        : 'Parts + labour are warranty-funded. Proceed without spend approval.',
    };
  }
  const tier = (meta.contract_tier || '').toUpperCase();
  const end = (meta.contract_end_date || '').slice(0, 10);
  const days = _daysUntil(end);
  const expiringSoon = days !== null && days >= 0 && days <= 90;
  return {
    covered: true,
    kind: 'contract',
    tone: expiringSoon ? 'amber' : 'green',
    expiringSoon,
    daysRemaining: days,
    label: 'Under ' + (tier ? `${tier} ` : '') + 'service contract' + (end ? ` until ${end}` : ''),
    short: expiringSoon
      ? `${tier || 'Contract'} · ${days}d`
      : (tier ? `${tier} contract` : 'Contract'),
    detail: expiringSoon
      ? `Contract ends in ${days} day${days === 1 ? '' : 's'} — flag renewal to ops after this visit.`
      : 'Parts + labour covered by the contract. Proceed without spend approval.',
  };
}


const TABS = [
  // Iter 220dn — engineer flow restructure (Feb 2026).
  // The "Summary" tab now owns the customer/site/address/fault
  // overview + the big "I'm on site" CTA. Other tabs are clean —
  // no customer card redundancy, less scrolling to the actual work.
  // Photos drop out as a top-level tab and live alongside their
  // machine in Equipment (per-row) + a general site photos block
  // on Summary, matching how an engineer actually thinks: every
  // photo is *of* something specific (a machine, a part, a site).
  { id: 'summary',   label: 'Summary',   icon: Users },
  { id: 'travel',    label: 'Travel',    icon: Car },
  { id: 'time',      label: 'Time',      icon: Clock },
  { id: 'equipment', label: 'Equipment', icon: Package },
  { id: 'parts',     label: 'Parts',     icon: Wrench },
  { id: 'complete',  label: 'Complete',  icon: CheckCircle2 },
];

export default function EngineerJobDetailV2() {
  const navigate = useNavigate();
  const { caseId } = useParams();
  const [searchParams] = useSearchParams();
  // Iter 220dn — when the engineer claims a job from Up-for-grabs we
  // hand them straight into the detail; on back-press they expect
  // to land back in the queue, not on Home.
  const backHref = searchParams.get('from') === 'queue'
    ? '/svc/engineer/queue'
    : '/svc/engineer';
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  // Iter 220ea·5 — Honour `?tab=` so deep-links and the
  // equipment-new round-trip both land on the right tab instead of
  // bouncing the engineer to Summary every time.
  const validTabs = new Set(TABS.map(t => t.id));
  const initialTab = (searchParams.get('tab') || '').toLowerCase();
  const [activeTab, setActiveTab] = useState(
    validTabs.has(initialTab) ? initialTab : 'summary',
  );
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
    navigate(backHref);
  }, [draftDirty, navigate, backHref]);

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
        {/* Iter 220dn — JobAtAGlance lives in the Summary tab ONLY.
            Iter 220dr — Capture-media (PhotosTab) moved OUT of
            Summary into Equipment (per-machine evidence) and the
            "After-photos" gate in Complete. Summary is now strictly
            customer / site / fault context. */}
        {activeTab === 'summary' && (
          <JobAtAGlance
            job={job}
            mileage={mileage}
            setBusy={setBusy}
            busy={busy}
            onChange={load}
            onJumpToSafety={() => setActiveTab('complete')}
            onJumpToTab={setActiveTab}
          />
        )}
        {activeTab === 'time'   && <TimeTab job={job} busy={busy} setBusy={setBusy} onChange={load} />}
        {activeTab === 'travel' && <TravelTab job={job} mileage={mileage} onChange={load} />}
        {activeTab === 'equipment' && <EquipmentTab job={job} onChange={load} />}
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
//
// Iter 220ea·6 (Feb 2026) — Summary tab redesign. The card now
// opens with three explicit blocks: a Status Pill row (status +
// SLA countdown + priority), an Action Row (Call, Navigate,
// Email, Photo), and a 2x3 Stats Grid (on-site time, photos,
// parts, machines, safety, handoff). The old customer/site
// context block + chip row remain below so the surface stays
// information-dense without being noisy.
function JobAtAGlance({ job, mileage, busy: _busy, setBusy, onChange, onJumpToSafety, onJumpToTab }) {
  const phone = job.customer_phone;
  const email = job.customer_email;
  const address = [job.site_address, job.site_postcode].filter(Boolean).join(' ');
  const mapsHref = address
    ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`
    : null;
  const fault = job.description || job.fault_summary || job.summary || '';
  // Iter 220e1 — Cover state for the chip + the banner. Lets the
  // engineer know up-front whether to crack on or wait for spend
  // authorisation.
  const cover = computeCoverState(job);

  // Iter 220ea·5 — Pre-job H&S signoff state. Surfacing this on the
  // Summary tab (not just Time) means the engineer sees the form
  // they need to fill out the moment they open the job, rather
  // than discovering it when they try to start the timer.
  const safetyNeeded = !job.safety_signoff && !!job?.safety_template;
  const safetyItemCount = job?.safety_template?.items?.length || 0;

  // The arrival timer is driven by `setBusy` / `onChange` from the
  // parent's start-on-site button; we keep the active timer surface
  // logic here so the at-a-glance card can react to it.
  const entries = job.time_entries || [];
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
  // The `arrive` handler is currently wired through the parent
  // component's CTA elsewhere; reference it once here so a static
  // analyser doesn't flag it as dead while we keep the offline-
  // queued retry path warm.
  void arrive;

  return (
    <div
      className="rounded-2xl bg-white border border-slate-200 shadow-sm overflow-hidden"
      data-testid="job-at-a-glance"
    >
      {/* Iter 220ea·5 — Pre-job H&S checklist call-out. Surfacing
          it at the very top of Summary means the engineer can't
          miss it. The whole banner is a button that jumps to the
          Complete tab where the checklist UI lives. */}
      {safetyNeeded && (
        <button
          type="button"
          onClick={onJumpToSafety}
          className="w-full px-3 py-2.5 bg-amber-50 hover:bg-amber-100 border-b border-amber-200 flex items-center gap-2 text-left transition-colors"
          data-testid="summary-safety-checklist-banner"
        >
          <div className="w-9 h-9 rounded-full bg-amber-500 text-white flex items-center justify-center shrink-0 shadow-sm">
            <AlertTriangle size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-extrabold uppercase tracking-wider text-amber-900">
              Pre-job H&amp;S checklist
            </p>
            <p className="text-xs text-amber-900 leading-snug">
              {safetyItemCount > 0
                ? <>Tap to complete <b>{safetyItemCount} item{safetyItemCount === 1 ? '' : 's'}</b> before starting work.</>
                : <>Tap to complete the checklist before starting work.</>}
            </p>
          </div>
          <ChevronRight size={16} className="text-amber-700 shrink-0" />
        </button>
      )}

      <div className="p-3 space-y-3">
        {/* Iter 220ea·7 — Cover banner moved to the top of the
            Summary card (right under the tabs / safety banner).
            The engineer needs to read "Chargeable visit · confirm
            spend" before they look at anything else when the
            customer doesn't have cover. */}
        <div
          className={`rounded-2xl border p-3 ${
            cover.tone === 'green'
              ? 'bg-emerald-50 border-emerald-200'
              : cover.tone === 'amber'
                ? 'bg-amber-50 border-amber-300'
                : 'bg-rose-50 border-rose-300'
          }`}
          data-testid="jaag-cover-banner"
          data-tone={cover.tone}
        >
          <div className="flex items-start gap-2">
            <ShieldCheck
              size={16}
              className={`mt-0.5 shrink-0 ${
                cover.tone === 'green'
                  ? 'text-emerald-700'
                  : cover.tone === 'amber'
                    ? 'text-amber-700'
                    : 'text-rose-700'
              }`}
            />
            <div className="flex-1 min-w-0">
              <p
                className={`text-xs font-extrabold ${
                  cover.tone === 'green'
                    ? 'text-emerald-900'
                    : cover.tone === 'amber'
                      ? 'text-amber-900'
                      : 'text-rose-900'
                }`}
                data-testid="jaag-cover-banner-label"
              >
                {cover.label}
              </p>
              {cover.detail && (
                <p
                  className={`text-[11px] mt-0.5 ${
                    cover.tone === 'green'
                      ? 'text-emerald-800'
                      : cover.tone === 'amber'
                        ? 'text-amber-800'
                        : 'text-rose-800'
                  }`}
                  data-testid="jaag-cover-banner-detail"
                >
                  {cover.detail}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Iter 220ea·6 — Status pill row: job status badge,
            live SLA countdown, priority. The one-glance answer to
            "what state is this job in?". */}
        <SummaryStatusPill job={job} cover={cover} />

        {/* Iter 220ea·6 — Action row: 3 equal-width touch targets
            for the actions an engineer reaches for most (Call,
            Navigate, Email). Iter 220ea·7 — Photo dropped; the
            Equipment tab owns per-machine capture and a second
            entry-point on Summary was clutter on a 412px screen. */}
        <SummaryActionRow
          job={job}
          phone={phone}
          email={email}
          mapsHref={mapsHref}
          onJumpToTab={onJumpToTab}
        />

        {/* Iter 220ea·6 — Stats grid: 2x3 compact dashboard with
            the metrics the engineer wants at a glance (on-site
            time, photos, parts, machines, safety, handoff notes). */}
        <SummaryStatsGrid job={job} mileage={mileage} />

        <div className="pt-1 border-t border-slate-100">
          <div className="flex items-start justify-between gap-3 pt-2">
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

        {/* Iter 220ea·8 — Lower chip row removed. Priority + cover
            are already in the top status-pill row; case-type was
            promoted there too. Machine count lives in the stats
            grid above. Last-visit + customer-rating chips were
            infrequent and dropped to keep Summary uncluttered;
            if a returning engineer needs that context, the
            Asset History panel below has it. */}
      </div>

      {/* Iter 220ea·7 — Cover banner moved to the top of the
          card (above the status pill row); removed from this
          slot to avoid two copies on Summary.
          EngineerEntitlementPanel also removed — the engineer
          gets entitlement context from the CRM-driven cover
          banner + chargeable pill; the "No contract on file ·
          send feedback to coordinator" surface lived here but
          was confusing on Summary. CRM feedback flows live on
          the Complete tab. */}

      {/* Iter 220cz — Overrun warning, sibling-jobs warning.
          Iter 220ds — Handoff notes on Summary are read-only and
          only render when a PREVIOUS engineer left context (true
          second-visit case). The composer moves to the Complete
          tab where leaving handoff is the natural close-out
          action. */}
      <JobOverrunBanner overrun={job.overrun} />
      <SiblingJobsBanner cases={job.sibling_jobs} />
      <HandoffNotesPanel
        caseId={job.id}
        notes={job.handoff_notes || []}
        onChange={onChange}
        mode="read-only"
        currentUserId={job.viewer_user_id}
      />
      {/* Iter 220de — Compliance pack (PTW / COSHH / LOTO). */}
      <ComplianceCard caseId={job.id} onChange={onChange} />
      {/* Iter 220dg — Engineer → customer outbound ETA push. */}
      {job.status === 'en_route' && job.customer_email && (
        <EtaUpdateChip
          caseId={job.id}
          lastSentAt={job.eta_last_sent_at}
          lastMinutes={job.eta_last_minutes}
          onChange={onChange}
        />
      )}

      {/* Iter 220dt — the big "I'm on site" arrive button was
          removed from Summary; the Time tab now owns starting the
          on-site timer (one canonical entry point). We still
          surface a passive "On site — timer running" badge here
          while the timer is active so Summary stays informative
          without offering competing controls. */}
      {!['closed', 'invoiced', 'awaiting_sign_off', 'repaired'].includes(job.status) && activeOnSite && (
        <div className="border-t border-slate-100 p-2 bg-slate-50/40">
          <div
            className="flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-emerald-50 text-emerald-800 text-sm font-bold"
            data-testid="jaag-on-site-now"
          >
            <CheckCircle2 size={14} /> On site — timer running
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Iter 220ea·6 · Summary tab redesign ─────────────────────────
// Three small components that own the top of the JobAtAGlance
// card on the Summary tab: a status pill row, an action row, and
// a compact stats grid. Lifted out as their own components so
// the JobAtAGlance return stays readable and these can be unit-
// tested in isolation.

const STATUS_TONE = {
  new:              { label: 'New',              cls: 'bg-slate-100 text-slate-700 border-slate-300', dot: 'bg-slate-400' },
  scheduled:        { label: 'Scheduled',        cls: 'bg-indigo-100 text-indigo-800 border-indigo-300', dot: 'bg-indigo-500' },
  en_route:         { label: 'En route',         cls: 'bg-sky-100 text-sky-800 border-sky-300', dot: 'bg-sky-500' },
  in_progress:      { label: 'In progress',      cls: 'bg-blue-100 text-blue-800 border-blue-300', dot: 'bg-blue-500 animate-pulse' },
  on_hold:          { label: 'On hold',          cls: 'bg-amber-100 text-amber-900 border-amber-300', dot: 'bg-amber-500' },
  awaiting_parts:   { label: 'Awaiting parts',   cls: 'bg-amber-100 text-amber-900 border-amber-300', dot: 'bg-amber-500' },
  awaiting_sign_off:{ label: 'Awaiting sign-off',cls: 'bg-violet-100 text-violet-800 border-violet-300', dot: 'bg-violet-500' },
  repaired:         { label: 'Repaired',         cls: 'bg-emerald-100 text-emerald-800 border-emerald-300', dot: 'bg-emerald-500' },
  closed:           { label: 'Closed',           cls: 'bg-emerald-100 text-emerald-800 border-emerald-300', dot: 'bg-emerald-500' },
  invoiced:         { label: 'Invoiced',         cls: 'bg-emerald-100 text-emerald-800 border-emerald-300', dot: 'bg-emerald-500' },
};

function _formatSlaCountdown(targetIso) {
  if (!targetIso) return null;
  const target = new Date(targetIso).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - Date.now();
  const overdue = diffMs < 0;
  const absMs = Math.abs(diffMs);
  const mins = Math.floor(absMs / 60000);
  const hrs = Math.floor(mins / 60);
  const days = Math.floor(hrs / 24);
  let label;
  if (days >= 1) label = `${days}d ${hrs % 24}h`;
  else if (hrs >= 1) label = `${hrs}h ${mins % 60}m`;
  else label = `${mins}m`;
  return { label, overdue, urgent: !overdue && absMs < 60 * 60 * 1000 };
}

// Iter 220ea·8 — Human-friendly priority legend. Surfaced as a
// popover when the engineer taps the priority pill on Summary, so
// a new starter doesn't have to guess what "P2" means. Wording
// pulled from the ops handbook; intentionally short so it reads
// at a glance on a 412 px phone.
const PRIORITY_KEY = [
  { code: 'P1', label: 'Critical',  detail: 'Equipment down or safety risk — respond within 4 hours.', cls: 'bg-rose-50 text-rose-800 border-rose-200' },
  { code: 'P2', label: 'High',      detail: 'Major service impact — respond same day (within 24 hours).', cls: 'bg-amber-50 text-amber-800 border-amber-200' },
  { code: 'P3', label: 'Standard',  detail: 'Routine fault — respond within 3 working days.', cls: 'bg-slate-50 text-slate-700 border-slate-200' },
  { code: 'P4', label: 'Low',       detail: 'Cosmetic or scheduled work — respond within 7 working days.', cls: 'bg-slate-50 text-slate-600 border-slate-200' },
];

function SummaryStatusPill({ job, cover }) {
  const [showKey, setShowKey] = useState(false);
  // Iter 220ea·8 — Close the legend on outside-tap so it doesn't
  // get stuck open if the engineer scrolls away.
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!showKey) return undefined;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setShowKey(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('touchstart', onDoc);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('touchstart', onDoc);
    };
  }, [showKey]);

  const status = String(job?.status || 'new').toLowerCase();
  const tone = STATUS_TONE[status] || STATUS_TONE.new;
  const sla = _formatSlaCountdown(job?.sla_resolve_at);
  const priorityRaw = job?.priority ? String(job.priority).toUpperCase() : null;
  const priorityCode = (() => {
    if (!priorityRaw) return null;
    if (priorityRaw.startsWith('P1') || priorityRaw === 'CRITICAL') return 'P1';
    if (priorityRaw.startsWith('P2') || priorityRaw === 'HIGH')     return 'P2';
    if (priorityRaw.startsWith('P3') || priorityRaw === 'STANDARD' || priorityRaw === 'MEDIUM') return 'P3';
    if (priorityRaw.startsWith('P4') || priorityRaw === 'LOW')      return 'P4';
    return priorityRaw;
  })();
  const isHighPriority = priorityCode === 'P1' || priorityCode === 'P2';
  const caseTypeLabel = job?.case_type ? labelForCaseType(job.case_type) : null;
  return (
    <div
      ref={wrapRef}
      className="relative flex flex-wrap items-center gap-1.5"
      data-testid="summary-status-pill-row"
    >
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-extrabold ${tone.cls}`}
        data-testid="summary-status-pill"
        data-status={status}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
        {tone.label}
      </span>
      {sla && (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-bold ${
            sla.overdue
              ? 'bg-rose-100 text-rose-900 border-rose-300'
              : sla.urgent
                ? 'bg-amber-100 text-amber-900 border-amber-300'
                : 'bg-slate-50 text-slate-700 border-slate-200'
          }`}
          data-testid="summary-sla-pill"
          data-sla-state={sla.overdue ? 'overdue' : sla.urgent ? 'urgent' : 'ok'}
          title={`SLA target: ${new Date(job.sla_resolve_at).toLocaleString('en-GB')}`}
        >
          <Timer size={11} />
          {sla.overdue ? `${sla.label} over SLA` : `${sla.label} to SLA`}
        </span>
      )}
      {priorityCode && (
        <button
          type="button"
          onClick={() => setShowKey((v) => !v)}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border text-[10px] font-extrabold uppercase tracking-wider transition-colors ${
            isHighPriority
              ? 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100'
              : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
          }`}
          data-testid="summary-priority-pill"
          data-expanded={showKey ? 'true' : 'false'}
          aria-expanded={showKey}
          aria-haspopup="dialog"
          title="Tap for priority key"
        >
          {priorityCode}
          <ChevronRight
            size={10}
            className={`transition-transform ${showKey ? 'rotate-90' : ''}`}
          />
        </button>
      )}
      {/* Iter 220ea·8 — Case Type pill (Repair / PPM / Install /
          Inspection / Callout / Audit). Was previously in the
          lower chip row; promoted to the top so the engineer
          knows up-front what kind of visit this is. */}
      {caseTypeLabel && (
        <span
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full border text-[10px] font-extrabold uppercase tracking-wider bg-indigo-50 text-indigo-700 border-indigo-200"
          data-testid="summary-case-type-pill"
          title={`Job type · ${caseTypeLabel}`}
        >
          <Wrench size={10} /> {caseTypeLabel}
        </span>
      )}
      {cover?.tone === 'red' && (
        <span
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full border text-[10px] font-extrabold uppercase tracking-wider bg-rose-50 text-rose-700 border-rose-200"
          data-testid="summary-chargeable-pill"
          title={cover.detail}
        >
          <ShieldCheck size={10} /> Chargeable
        </span>
      )}
      {showKey && (
        <div
          className="absolute left-0 right-0 top-full mt-1.5 z-20 rounded-xl bg-white border border-slate-200 shadow-lg p-2.5 space-y-1.5"
          data-testid="summary-priority-key"
          role="dialog"
        >
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500">
              Priority key
            </p>
            <button
              type="button"
              onClick={() => setShowKey(false)}
              className="text-slate-400 hover:text-slate-700"
              aria-label="Close priority key"
              data-testid="summary-priority-key-close"
            >
              <X size={12} />
            </button>
          </div>
          <ul className="space-y-1">
            {PRIORITY_KEY.map((p) => (
              <li
                key={p.code}
                className={`flex items-start gap-2 rounded-lg px-2 py-1.5 border ${
                  p.code === priorityCode ? p.cls : 'bg-white border-slate-100'
                }`}
                data-testid={`summary-priority-key-row-${p.code}`}
              >
                <span className={`inline-flex items-center justify-center w-7 h-5 rounded-full text-[10px] font-extrabold border ${p.cls}`}>
                  {p.code}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-extrabold text-slate-900 leading-tight">
                    {p.label}
                  </p>
                  <p className="text-[10px] text-slate-600 leading-snug">
                    {p.detail}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SummaryActionRow({ job: _job, phone, email, mapsHref, onJumpToTab: _onJumpToTab }) {
  // Iter 220ea·7 — Photo action removed (Equipment tab owns
  // per-machine capture). The row is now a 3-column grid:
  // Call · Navigate · Email.
  const actions = [
    {
      key: 'call',
      label: 'Call',
      icon: Phone,
      href: phone ? `tel:${String(phone).replace(/\s+/g, '')}` : null,
      tone: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100',
      testid: 'jaag-call',
    },
    {
      key: 'navigate',
      label: 'Navigate',
      icon: Navigation,
      href: mapsHref,
      external: true,
      tone: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100',
      testid: 'jaag-maps',
    },
    {
      key: 'email',
      label: 'Email',
      icon: Send,
      href: email ? `mailto:${email}` : null,
      tone: 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100',
      testid: 'jaag-email',
    },
  ];
  return (
    <div className="grid grid-cols-3 gap-2" data-testid="summary-action-row">
      {actions.map((a) => {
        const Icon = a.icon;
        const disabled = !a.href && !a.onClick;
        const sharedCls = `flex flex-col items-center justify-center gap-1 py-2.5 rounded-xl border text-[11px] font-bold uppercase tracking-wider transition-colors ${a.tone} ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`;
        if (a.onClick) {
          return (
            <button
              key={a.key}
              type="button"
              onClick={a.onClick}
              disabled={disabled}
              className={sharedCls}
              data-testid={a.testid}
            >
              <Icon size={16} />
              <span>{a.label}</span>
            </button>
          );
        }
        if (disabled) {
          return (
            <span
              key={a.key}
              className={sharedCls}
              data-testid={`${a.testid}-disabled`}
              aria-disabled="true"
            >
              <Icon size={16} />
              <span>{a.label}</span>
            </span>
          );
        }
        return (
          <a
            key={a.key}
            href={a.href}
            target={a.external ? '_blank' : undefined}
            rel={a.external ? 'noopener noreferrer' : undefined}
            className={sharedCls}
            data-testid={a.testid}
          >
            <Icon size={16} />
            <span>{a.label}</span>
          </a>
        );
      })}
    </div>
  );
}

function SummaryStatsGrid({ job, mileage }) {
  // On-site minutes — accumulate completed + currently-running entry.
  const entries = Array.isArray(job?.time_entries) ? job.time_entries : [];
  let onSiteMins = 0;
  let activeOnSiteStart = null;
  for (const e of entries) {
    if (e.category !== 'on_site') continue;
    if (e.end_at) {
      onSiteMins += Number(e.duration_minutes || 0);
    } else if (e.start_at) {
      activeOnSiteStart = new Date(e.start_at).getTime();
    }
  }
  if (activeOnSiteStart) {
    onSiteMins += Math.max(0, Math.round((Date.now() - activeOnSiteStart) / 60000));
  }
  const photoCount = Array.isArray(job?.photos) ? job.photos.length : 0;
  const parts = Array.isArray(job?.allocated_parts) ? job.allocated_parts : [];
  const partsConsumed = parts.filter(p => p.fulfilled).length;
  const partsTotal = parts.length;
  const machineCount = job?.machines_count
    ?? (Array.isArray(job?.machines) ? job.machines.length : 0);
  // Safety: ticked items vs template items
  const ticked = Array.isArray(job?.safety_signoff?.ticked_item_ids)
    ? job.safety_signoff.ticked_item_ids.length : 0;
  const safetyTotal = job?.safety_template?.items?.length ?? ticked;
  const safetyLabel = job?.safety_signoff
    ? 'Signed off'
    : safetyTotal > 0 ? `${ticked}/${safetyTotal}` : '—';
  // Handoff notes count (from any engineer) — visible context the
  // engineer should be aware of before/after this visit.
  const handoffCount = Array.isArray(job?.handoff_notes) ? job.handoff_notes.length : 0;
  // Mileage — fall back to 0 if not loaded yet.
  const miles = Number(mileage?.total_miles || 0);
  const stats = [
    {
      key: 'time',
      label: 'On site',
      value: fmtMins(onSiteMins),
      sub: activeOnSiteStart ? 'Running' : (onSiteMins > 0 ? 'Logged' : 'Not started'),
      tone: activeOnSiteStart ? 'text-emerald-700' : 'text-slate-900',
      testid: 'summary-stat-time',
    },
    {
      key: 'photos',
      label: 'Photos',
      value: String(photoCount),
      sub: photoCount === 0 ? 'None yet' : (photoCount === 1 ? '1 captured' : `${photoCount} captured`),
      tone: 'text-slate-900',
      testid: 'summary-stat-photos',
    },
    {
      key: 'parts',
      label: 'Parts',
      value: partsTotal > 0 ? `${partsConsumed}/${partsTotal}` : '0',
      sub: partsTotal === 0 ? 'None allocated' : (partsConsumed === partsTotal ? 'All fitted' : 'In progress'),
      tone: partsTotal > 0 && partsConsumed === partsTotal ? 'text-emerald-700' : 'text-slate-900',
      testid: 'summary-stat-parts',
    },
    {
      key: 'machines',
      label: 'Machines',
      value: String(machineCount),
      sub: machineCount === 0 ? 'Not set' : (machineCount === 1 ? '1 asset' : `${machineCount} assets`),
      tone: 'text-slate-900',
      testid: 'summary-stat-machines',
    },
    {
      key: 'safety',
      label: 'H&S',
      value: safetyLabel,
      sub: job?.safety_signoff ? 'Cleared' : (safetyTotal > 0 ? 'Required' : 'No checklist'),
      tone: job?.safety_signoff ? 'text-emerald-700' : (safetyTotal > 0 ? 'text-amber-700' : 'text-slate-900'),
      testid: 'summary-stat-safety',
    },
    {
      key: 'mileage',
      label: 'Mileage',
      value: miles > 0 ? `${miles.toFixed(1)} mi` : (handoffCount > 0 ? String(handoffCount) : '0'),
      sub: miles > 0 ? 'Logged' : (handoffCount > 0 ? `${handoffCount} handoff${handoffCount === 1 ? '' : 's'}` : 'Not yet'),
      tone: 'text-slate-900',
      testid: 'summary-stat-mileage',
    },
  ];
  return (
    <div
      className="grid grid-cols-3 gap-1.5 rounded-xl bg-slate-50 border border-slate-200 p-1.5"
      data-testid="summary-stats-grid"
    >
      {stats.map((s) => (
        <div
          key={s.key}
          className="rounded-lg bg-white border border-slate-100 px-2 py-2 min-w-0"
          data-testid={s.testid}
        >
          <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400 truncate">
            {s.label}
          </p>
          <p className={`text-sm font-extrabold tabular-nums truncate ${s.tone}`}>
            {s.value}
          </p>
          <p className="text-[10px] text-slate-500 truncate">{s.sub}</p>
        </div>
      ))}
    </div>
  );
}


// ─── Iter 220cz · JobOverrunBanner ───────────────────────────────
// Pulls `overrun` from the engineer endpoint and shows an amber
// "approaching estimate" or rose "over estimate" banner. Hidden
// when no estimate is set so the engineer doesn't see noise on
// estimate-less jobs.
function JobOverrunBanner({ overrun }) {
  if (!overrun || !overrun.estimated_minutes) return null;
  const { estimated_minutes, on_site_minutes, is_overrun, is_approaching, percent_used } = overrun;
  if (!is_overrun && !is_approaching) return null;
  const cls = is_overrun
    ? 'bg-rose-50 text-rose-800 border-rose-200'
    : 'bg-amber-50 text-amber-800 border-amber-200';
  return (
    <div
      className={`mx-3 mb-2 p-2 rounded-lg border ${cls} flex items-start gap-2`}
      data-testid={is_overrun ? 'jaag-overrun' : 'jaag-overrun-approaching'}
    >
      <Timer size={14} className="mt-0.5 shrink-0" />
      <div className="text-xs leading-snug">
        <p className="font-bold uppercase tracking-wide text-[10px]">
          {is_overrun ? 'Over time estimate' : 'Approaching time estimate'}
        </p>
        <p>
          <span data-testid="jaag-overrun-used">{fmtMins(on_site_minutes)}</span>
          {' '}of{' '}
          <span data-testid="jaag-overrun-est">{fmtMins(estimated_minutes)}</span>
          {' '}on-site
          {percent_used ? ` · ${percent_used}%` : ''}
          {is_overrun ? ' — let dispatch know if the scope has grown.' : ''}
        </p>
      </div>
    </div>
  );
}

// ─── Iter 220cz · SiblingJobsBanner ──────────────────────────────
// Lists up to 5 OTHER open cases at the same customer + same site.
// Lets the engineer combine visits instead of bouncing between
// half-finished jobs on the same trip.
function SiblingJobsBanner({ cases }) {
  const navigate = useNavigate();
  if (!Array.isArray(cases) || cases.length === 0) return null;
  return (
    <div
      className="mx-3 mb-2 p-2 rounded-lg border bg-amber-50 text-amber-900 border-amber-200"
      data-testid="jaag-sibling-jobs"
    >
      <div className="flex items-center gap-2 mb-1">
        <Users size={14} />
        <p className="text-[10px] font-bold uppercase tracking-wide">
          {cases.length} other open {cases.length === 1 ? 'job' : 'jobs'} at this site
        </p>
      </div>
      <ul className="space-y-1" data-testid="jaag-sibling-jobs-list">
        {cases.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => navigate(`/svc/engineer/jobs/${c.id}`)}
              className="w-full text-left text-xs px-2 py-1 rounded bg-white border border-amber-200 hover:bg-amber-100"
              data-testid={`jaag-sibling-job-${c.id}`}
            >
              <span className="font-bold">{c.reference || c.id}</span>
              {c.title ? <span className="text-amber-900/80"> · {c.title}</span> : null}
              {c.status ? (
                <span className="ml-2 text-[10px] uppercase font-bold text-amber-700">
                  {String(c.status).replace(/_/g, ' ')}
                </span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ─── Iter 220cz · HandoffNotesPanel ──────────────────────────────
// Reads existing `case.handoff_notes` and lets the engineer add
// another. Posts to `POST /svc/engineer/jobs/{case_id}/handoff-note`.
//
// Iter 220ds (Feb 2026): split into two operating modes.
//   * ``mode="read-only"`` — surfaces previous engineers' notes
//     on the **Summary** tab so a returning engineer sees the
//     context. Hidden entirely when no prior notes exist (Summary
//     stays clean on first-visit jobs).
//   * ``mode="compose"`` — full composer + list. Lives on the
//     **Complete** tab so leaving handoff is part of wrapping up.
function HandoffNotesPanel({ caseId, notes, onChange, mode = 'compose', currentUserId }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const list = Array.isArray(notes) ? notes : [];
  const readOnly = mode === 'read-only';
  // Read-only Summary mode: only surface notes left by SOMEONE ELSE.
  // The current engineer's own notes don't count as "handover I
  // need to read", they're their own work.
  const visibleNotes = readOnly
    ? list.filter(n => (n.engineer_id || '') !== (currentUserId || ''))
    : list;
  const submit = async () => {
    const note = text.trim();
    if (!note) {
      notify.error('Empty note', 'Type a quick handoff message first.');
      return;
    }
    setBusy(true);
    try {
      await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/handoff-note`,
        { note },
        auth(),
      );
      setText('');
      setOpen(false);
      notify.success('Handoff note saved', 'The next engineer will see this on Job-at-a-Glance.');
      await onChange();
    } catch (e) {
      notify.error('Could not save note', e?.response?.data?.detail || e?.message || 'Try again.');
    } finally {
      setBusy(false);
    }
  };
  // Summary mode: render only when there's something to surface,
  // and never show the composer.
  if (readOnly) {
    if (visibleNotes.length === 0) return null;
    return (
      <div
        className="mx-3 mb-2 p-2 rounded-lg border bg-blue-50/60 text-slate-800 border-blue-200"
        data-testid="jaag-handoff-panel"
      >
        <div className="flex items-center gap-2 mb-1">
          <MessageSquare size={14} className="text-blue-700" />
          <p className="text-[10px] font-bold uppercase tracking-wide text-blue-800">
            From the previous engineer
          </p>
        </div>
        <ul className="space-y-1" data-testid="jaag-handoff-list">
          {visibleNotes.slice().reverse().map((n) => (
            <li
              key={n.id || `${n.at}-${n.engineer_id}`}
              className="text-xs bg-white border border-blue-100 rounded px-2 py-1"
              data-testid={`jaag-handoff-${n.id || 'item'}`}
            >
              <p className="text-slate-800 leading-snug whitespace-pre-wrap">{n.note}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {n.engineer_name || 'Engineer'}
                {n.at ? ' · ' + new Date(n.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
              </p>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  // Compose mode (Complete tab) — list + composer.
  if (list.length === 0 && !open) {
    return (
      <div className="mx-3 mb-2" data-testid="jaag-handoff-empty">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-[10px] font-bold uppercase tracking-wide text-slate-500 hover:text-slate-700 inline-flex items-center gap-1"
          data-testid="jaag-handoff-add"
        >
          <MessageSquare size={11} /> Leave a handoff note
        </button>
      </div>
    );
  }
  return (
    <div
      className="mx-3 mb-2 p-2 rounded-lg border bg-blue-50/60 text-slate-800 border-blue-200"
      data-testid="jaag-handoff-panel"
    >
      <div className="flex items-center gap-2 mb-1">
        <MessageSquare size={14} className="text-blue-700" />
        <p className="text-[10px] font-bold uppercase tracking-wide text-blue-800">
          Handoff notes
        </p>
      </div>
      {list.length > 0 && (
        <ul className="space-y-1 mb-2" data-testid="jaag-handoff-list">
          {list.slice().reverse().map((n) => (
            <li
              key={n.id || `${n.at}-${n.engineer_id}`}
              className="text-xs bg-white border border-blue-100 rounded px-2 py-1"
              data-testid={`jaag-handoff-${n.id || 'item'}`}
            >
              <p className="text-slate-800 leading-snug whitespace-pre-wrap">{n.note}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {n.engineer_name || 'Engineer'}
                {n.at ? ' · ' + new Date(n.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div className="space-y-1">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            placeholder="What does the next engineer need to know?"
            className="w-full text-xs px-2 py-1 rounded border border-blue-200 bg-white focus:outline-none focus:ring-1 focus:ring-blue-300"
            data-testid="jaag-handoff-input"
            maxLength={2000}
          />
          <div className="flex items-center justify-end gap-1">
            <button
              type="button"
              onClick={() => { setOpen(false); setText(''); }}
              className="text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded text-slate-600 hover:bg-slate-100"
              data-testid="jaag-handoff-cancel"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              data-testid="jaag-handoff-submit"
            >
              {busy ? 'Saving…' : 'Save note'}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="text-[10px] font-bold uppercase tracking-wide text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
          data-testid="jaag-handoff-add"
        >
          <Plus size={11} /> Add another handoff note
        </button>
      )}
    </div>
  );
}

// ─── Iter 220dg · EtaUpdateChip ──────────────────────────────────
// Engineer is en_route and the customer is on the live tracking
// page (or just received the auto-comm). This chip lets the
// engineer fire a manual ETA refresh in two taps. We default to the
// live haversine estimate; engineer can override with quick presets
// (+10, +20 min) or a free-text "what's happening" note.
function EtaUpdateChip({ caseId, lastSentAt, lastMinutes, onChange }) {
  const [open, setOpen] = useState(false);
  const [mins, setMins] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const body = {};
      const n = parseInt(mins, 10);
      if (Number.isFinite(n) && n >= 0) body.eta_minutes = n;
      if (message.trim()) body.message = message.trim();
      const r = await axios.post(
        `${API}/svc/engineer/jobs/${caseId}/eta-update`, body, auth(),
      );
      if (r.data?.ok) {
        notify.success('ETA sent', `Customer notified · ${r.data.eta_label}`);
        setOpen(false);
        setMins('');
        setMessage('');
        await onChange();
      } else {
        notify.error('Send failed', 'Email did not go out — try again.');
      }
    } catch (e) {
      notify.error('Send failed', e?.response?.data?.detail || e?.message);
    } finally { setBusy(false); }
  };
  const lastSentLabel = lastSentAt
    ? `Last sent ${new Date(lastSentAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}${lastMinutes ? ` · ${lastMinutes} min` : ''}`
    : 'Customer hasn\'t been updated yet';
  if (!open) {
    return (
      <div
        className="mx-3 mb-2 p-2 rounded-lg border bg-sky-50 border-sky-200 flex items-center gap-2"
        data-testid="jaag-eta-chip"
      >
        <Send size={14} className="text-sky-700 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wide text-sky-800">
            ETA update
          </p>
          <p className="text-[11px] text-sky-900/80 truncate" data-testid="jaag-eta-last">
            {lastSentLabel}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="px-3 py-1 rounded-full bg-sky-600 hover:bg-sky-700 text-white text-[10px] font-bold uppercase tracking-wide"
          data-testid="jaag-eta-open"
        >
          Send
        </button>
      </div>
    );
  }
  return (
    <div
      className="mx-3 mb-2 p-2 rounded-lg border bg-sky-50 border-sky-200 space-y-1.5"
      data-testid="jaag-eta-panel"
    >
      <div className="flex items-center gap-2">
        <Send size={14} className="text-sky-700" />
        <p className="text-[10px] font-bold uppercase tracking-wide text-sky-800 flex-1">
          ETA update
        </p>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sky-700/70 hover:text-sky-900"
          data-testid="jaag-eta-cancel"
          aria-label="Cancel"
        >
          <X size={13} />
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {[5, 10, 20, 30].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setMins(String(n))}
            className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide border ${
              mins === String(n)
                ? 'bg-sky-600 text-white border-sky-700'
                : 'bg-white text-sky-800 border-sky-200 hover:bg-sky-100'
            }`}
            data-testid={`jaag-eta-preset-${n}`}
          >
            +{n} min
          </button>
        ))}
        <input
          type="number"
          min={0}
          max={480}
          value={mins}
          onChange={(e) => setMins(e.target.value)}
          placeholder="or type"
          className="w-20 px-2 py-1 rounded border border-sky-200 text-xs"
          data-testid="jaag-eta-mins"
        />
      </div>
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Optional message (e.g. stuck in traffic)"
        maxLength={400}
        className="w-full px-2 py-1 rounded border border-sky-200 text-xs"
        data-testid="jaag-eta-message"
      />
      <button
        type="button"
        onClick={submit}
        disabled={busy}
        className="w-full px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-700 text-white text-[10px] font-bold uppercase tracking-wide disabled:opacity-50"
        data-testid="jaag-eta-submit"
      >
        {busy ? <Loader2 size={11} className="animate-spin inline" /> : 'Send to customer'}
      </button>
    </div>
  );
}

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
      {/* Iter 220ea·7 — H&S "checklist required" warning removed
          from the Time tab. The Summary tab's amber banner is now
          the single source of truth for the pre-job H&S signoff
          requirement — duplicating it here was redundant and
          competed for screen real estate with the Start a Timer
          card on a 412px phone. */}

      <div className="grid grid-cols-3 gap-2" data-testid="time-totals">
        <Totals label="On site"   value={fmtMins(totalsByCategory.on_site)} color="#1d4ed8" />
        <Totals label="Travel"    value={fmtMins(totalsByCategory.travel)}  color="#6366f1" />
        <Totals label="Admin"     value={fmtMins(totalsByCategory.admin)}   color="#64748b" />
      </div>

      {!active ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="time-start-card">
          <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">Start a timer</p>
          {/* Iter 220ds — Travel button removed from the Time tab.
              The Travel tab's "Start trip" is the better entry point
              (it captures distance + auto-mileage). Time stays scoped
              to on-site + admin so engineers can't pick between two
              competing travel timers. */}
          <div className="grid grid-cols-2 gap-2">
            <button disabled={busy} onClick={() => start('on_site')} className="flex flex-col items-center gap-1 py-3 rounded-xl border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 disabled:opacity-50" data-testid="time-start-on_site">
              <Play size={16} /><span className="text-xs font-bold">On site</span>
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

// Iter 220dr — Capture-media (PhotosTab) moved OUT of the main job
// detail flow. The implementation is preserved here so future flows
// (e.g. a "photos-only" capture path) can re-mount it without
// re-typing the upload pipeline.
// eslint-disable-next-line unused-imports/no-unused-vars
function PhotosTab({ job, onChange }) {
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
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
    setUploadPct(0);
    try {
      // Iter 220db — compress images client-side so an engineer on a
      // 4G connection isn't stuck waiting 30s for a 4 MB JPEG. Video
      // is passed through untouched (already validated above).
      const toSend = kind === 'video' ? file : await compressImage(file);
      // Iter 220e9 — chunked upload kicks in transparently for files
      // > 4 MB so a flaky 4G connection drops one chunk, not the
      // whole 25 MB video. `chunkedUpload` falls back to the legacy
      // single-shot path for anything below the threshold.
      const uploaded = await chunkedUpload({
        baseURL: API,
        file: toSend,
        category: 'service-media',
        authHeaders: auth().headers,
        onProgress: (pct) => setUploadPct(pct),
      });
      const fileUrl = uploaded?.download_url || uploaded?.storage_path;
      const prefix = stage === 'before' ? '[BEFORE] ' : stage === 'after' ? '[AFTER] ' : '';
      await axios.post(`${API}/svc/engineer/photos`, {
        case_id: job.id, file_url: fileUrl,
        mime_type: uploaded?.content_type || (kind === 'video' ? 'video/webm' : 'image/jpeg'),
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
    } finally { setUploading(false); setUploadPct(0); }
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
        {uploading && (
          <div className="mt-3" data-testid="photo-upload-progress">
            <div className="flex items-center justify-between text-[10px] uppercase font-bold tracking-wide text-slate-500 mb-1">
              <span>Uploading…</span>
              <span data-testid="photo-upload-pct">{uploadPct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full bg-blue-600 transition-[width] duration-150"
                style={{ width: `${uploadPct}%` }}
                data-testid="photo-upload-bar"
              />
            </div>
          </div>
        )}
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

// Iter 220dx — CaptureSerialCard pins the rubbed-off / unknown
// serial follow-up task at the top of the Equipment tab. The
// engineer reads the plate on site, types it, optionally attaches
// a photo, and the case + canonical equipment row both back-fill
// in one call. After successful capture the card disappears
// (`capture_serial_required` flips off).
function CaptureSerialCard({ job, onChange }) {
  const REASON_LABELS = {
    rubbed_off: 'Plate rubbed off / unreadable',
    not_visible: 'Plate not visible / behind cladding',
    never_had_one: 'Machine has no serial plate',
  };
  const [serial, setSerial] = useState('');
  const [photoFileId, setPhotoFileId] = useState(null);
  const [photoName, setPhotoName] = useState('');
  const [busy, setBusy] = useState(false);
  const reasonLabel =
    REASON_LABELS[(job.capture_serial_reason || '').toLowerCase()] ||
    'Customer couldn\'t read the serial at fault log';

  const uploadPhoto = async (file) => {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await axios.post(`${API}/files/upload`, fd, {
        ...auth(), headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
      });
      const fid = r.data?.file_id || r.data?.id;
      if (fid) {
        setPhotoFileId(fid);
        setPhotoName(file.name);
      } else {
        notify.error('Photo upload returned no id');
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Photo upload failed');
    }
  };

  const submit = async () => {
    const trimmed = serial.trim();
    if (!trimmed) { notify.error('Type the serial first'); return; }
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/jobs/${job.id}/capture-serial`,
        {
          serial: trimmed,
          photo_file_id: photoFileId,
          asset_id: job.asset_id || null,
        },
        auth(),
      );
      notify.success(
        'Serial captured',
        r?.data?.equipment_updated
          ? 'Saved to the case + back-filled on the equipment record.'
          : 'Saved to the case audit trail.',
      );
      await onChange?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not capture serial');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="rounded-2xl border border-amber-300 bg-amber-50 p-4"
      data-testid="capture-serial-card"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
          <QrCode size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-800">
            Action required · Capture serial on visit 1
          </p>
          <p className="text-sm font-extrabold text-amber-900 mt-0.5">
            Customer couldn't read the serial when logging this fault
          </p>
          <p className="text-xs text-amber-800 mt-0.5" data-testid="capture-serial-reason">
            {reasonLabel}
          </p>
        </div>
      </div>

      <div className="mt-3 space-y-2">
        <label className="block">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-amber-900 mb-1">
            Serial read off the plate
          </span>
          <input
            type="text"
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="e.g. LF-22-12345-A"
            className="w-full text-sm border border-amber-300 rounded-lg px-3 py-2 bg-white"
            data-testid="capture-serial-input"
            autoComplete="off"
          />
        </label>

        <label className="block">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-amber-900 mb-1">
            Plate photo (optional)
          </span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => uploadPhoto(e.target.files?.[0])}
            className="block w-full text-xs"
            data-testid="capture-serial-photo"
          />
          {photoName && (
            <p className="text-[11px] text-amber-700 mt-1" data-testid="capture-serial-photo-name">
              <Camera size={11} className="inline-block mr-1" /> {photoName}
            </p>
          )}
        </label>

        <button
          type="button"
          onClick={submit}
          disabled={busy || !serial.trim()}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-br from-amber-600 to-amber-700 text-white text-sm font-bold disabled:opacity-50"
          data-testid="capture-serial-submit"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
          Mark serial captured
        </button>
      </div>
    </div>
  );
}

function EquipmentTab({ job, onChange }) {
  // Iter 220dr — surface the customer-logged context at the top of
  // Equipment so the engineer knows *which* machine the fault was
  // reported against without scrolling back to Summary. Pulls from
  // the case fields the operator picks at intake (asset_name +
  // attachments) and from the engineer-facing case payload.
  const customerAttachments = useMemo(() => {
    const raw = job?.attachments;
    if (!Array.isArray(raw)) return [];
    return raw.filter(a => a && (a.url || a.file_id));
  }, [job?.attachments]);
  const customerPhotos = customerAttachments.filter(
    a => (a.mime_type || a.content_type || '').startsWith('image/'),
  );
  const customerFiles = customerAttachments.filter(
    a => !(a.mime_type || a.content_type || '').startsWith('image/'),
  );
  const customerSummary = (job?.description || '').trim();
  const reporterName = (job?.customer_name || '').trim();

  return (
    <div className="space-y-4" data-testid="equipment-tab">
      {/* Iter 220dx — Capture-serial task pinned at the very top of
          Equipment when the customer flagged a rubbed-off / missing
          serial on intake. Engineer reads the plate on site, types
          the serial, optionally snaps a photo, and the case + the
          canonical equipment row both back-fill in one call. */}
      {job?.capture_serial_required ? (
        <CaptureSerialCard job={job} onChange={onChange} />
      ) : null}

      {(customerSummary || customerPhotos.length || customerFiles.length || job?.asset_name) ? (
        <div
          className="rounded-2xl border border-blue-200 bg-blue-50/60 p-3"
          data-testid="equipment-customer-context"
        >
          <p className="text-[10px] font-bold uppercase tracking-wider text-blue-700">
            What the customer logged
          </p>
          {job?.asset_name ? (
            <p
              className="text-sm font-extrabold text-slate-900 mt-0.5"
              data-testid="equipment-customer-asset"
            >
              {job.asset_name}
            </p>
          ) : null}
          {customerSummary ? (
            <p
              className="text-xs text-slate-700 leading-snug mt-1"
              data-testid="equipment-customer-summary"
            >
              {customerSummary}
            </p>
          ) : null}
          {reporterName ? (
            <p className="text-[11px] text-slate-500 mt-1">
              Reported by {reporterName}
            </p>
          ) : null}
          {customerPhotos.length > 0 ? (
            <div
              className="grid grid-cols-3 gap-2 mt-3"
              data-testid="equipment-customer-photos"
            >
              {customerPhotos.slice(0, 9).map((p, idx) => (
                <a
                  key={p.id || p.file_id || idx}
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block aspect-square rounded-lg overflow-hidden border border-blue-200 bg-white"
                  data-testid={`equipment-customer-photo-${idx}`}
                >
                  <img
                    src={p.url}
                    alt={p.caption || `Customer photo ${idx + 1}`}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </a>
              ))}
            </div>
          ) : null}
          {customerFiles.length > 0 ? (
            <ul className="mt-3 space-y-1" data-testid="equipment-customer-files">
              {customerFiles.map((f, idx) => (
                <li key={f.id || f.file_id || idx}>
                  <a
                    href={f.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-semibold text-blue-700 hover:underline inline-flex items-center gap-1"
                  >
                    <Download size={12} /> {f.filename || f.name || 'Attachment'}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

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
  const [adhoc, setAdhoc] = useState({ part_sku: '', qty: 1, notes: '', machine_id: '' });
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

  const addPartUsage = async (sku, qty = 1, machineId = '', machineName = '') => {
    setBusy(true);
    try {
      // Iter 220do — pass the machine the part was used on so the
      // customer report links the spend to the specific asset.
      const mid = machineId || adhoc.machine_id || '';
      const m = machines.find(x => (x.id || x.machine_id) === mid);
      const mname = machineName || m?.name || m?.title || '';
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/parts/use`, {
        part_sku: sku, qty, notes: adhoc.notes || null,
        machine_id: mid || null,
        machine_name: mname || null,
      }, auth());
      notify.success(`${sku} × ${qty} added`);
      setAdhoc({ part_sku: '', qty: 1, notes: '', machine_id: '' });
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
  // Iter 220dd — Approved-but-not-yet-fulfilled with admin-supplied
  // ETA / backorder flag. The allocation is on the case already
  // (above) but the engineer wants to see the expected delivery
  // signal up-front so they can plan / push the visit.
  const incomingRequests = requests.filter(
    r => r.status === 'approved' && (r.eta_date || r.backordered),
  );

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

      {incomingRequests.length > 0 && (
        <div
          className="bg-white rounded-2xl border border-blue-200 bg-blue-50 p-4"
          data-testid="parts-incoming-requests"
        >
          <p className="text-[11px] uppercase font-bold tracking-wide text-blue-700 mb-2">
            On the way ({incomingRequests.length})
          </p>
          <ul className="divide-y divide-blue-100">
            {incomingRequests.map(r => (
              <li
                key={r.id}
                className="py-2 flex items-start gap-3"
                data-testid={`parts-incoming-${r.id}`}
              >
                <Package size={14} className="text-blue-600 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-blue-900">
                    {r.qty} × {r.part_sku}
                    {r.part_name ? <span className="text-blue-700 font-normal"> · {r.part_name}</span> : null}
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {r.backordered ? (
                      <span
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200 text-[10px] font-bold uppercase tracking-wide"
                        data-testid={`parts-backordered-${r.id}`}
                      >
                        <AlertTriangle size={9} /> Backordered
                      </span>
                    ) : null}
                    {r.eta_date ? (
                      <span
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200 text-[10px] font-bold uppercase tracking-wide"
                        data-testid={`parts-eta-${r.id}`}
                      >
                        <Clock size={9} /> ETA {r.eta_date}
                      </span>
                    ) : null}
                    {r.machine_name ? (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-white text-slate-700 border border-slate-200 text-[10px] font-bold uppercase tracking-wide">
                        {r.machine_name}
                      </span>
                    ) : null}
                  </div>
                  {r.eta_notes ? (
                    <p className="text-[11px] text-blue-700 mt-1">{r.eta_notes}</p>
                  ) : null}
                </div>
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
        {/* Iter 220do — tag the part to a specific machine so the
            customer report links spend to the asset that was fixed. */}
        {machines.length > 0 && (
          <label className="block mt-3" data-testid="parts-adhoc-machine-wrap">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              For machine (optional)
            </span>
            <select
              value={adhoc.machine_id}
              onChange={e => setAdhoc(f => ({ ...f, machine_id: e.target.value }))}
              className="w-full text-sm border border-slate-200 rounded-lg px-2 py-2 bg-white"
              data-testid="parts-adhoc-machine"
            >
              <option value="">— Not machine-specific —</option>
              {machines.map(m => (
                <option key={m.id || m.machine_id} value={m.id || m.machine_id}>
                  {m.name || m.title || m.equipment_name || m.id}
                </option>
              ))}
            </select>
          </label>
        )}
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
                  <p className="text-[11px] text-slate-500 truncate">
                    {a.part_name}
                    {a.machine_name ? <> · <span className="font-semibold text-slate-700">{a.machine_name}</span></> : null}
                  </p>
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

// Iter 220dp · ReturnToFixCard — top-of-Complete gate. "Yes" stays
// out of the way (collapsed default state), "No, need to return"
// expands into a date picker + reason + customer-notify toggle and
// posts to the new ``return-to-fix`` endpoint.
function ReturnToFixCard({ job, onRescheduled }) {
  const existing = job.return_to_fix || null;
  const [mode, setMode] = useState(existing ? 'no' : null);
  const [busy, setBusy] = useState(false);
  const defaultReturnAt = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 2);
    d.setHours(9, 0, 0, 0);
    // datetime-local needs YYYY-MM-DDTHH:mm
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }, []);
  const [returnAt, setReturnAt] = useState(
    existing?.return_at ? existing.return_at.slice(0, 16) : defaultReturnAt,
  );
  const [reason, setReason] = useState(existing?.reason || '');
  const [notifyCustomer, setNotifyCustomer] = useState(true);

  const submit = async () => {
    if (!returnAt) { notify.error('Pick a return date'); return; }
    setBusy(true);
    try {
      const iso = new Date(returnAt).toISOString();
      await axios.post(
        `${API}/svc/engineer/jobs/${job.id}/return-to-fix`,
        {
          return_at: iso,
          reason: reason.trim(),
          notify_customer: notifyCustomer,
        },
        auth(),
      );
      await onRescheduled?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not schedule return');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="bg-white rounded-2xl border border-slate-200 p-4"
      data-testid="complete-return-to-fix"
    >
      <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">
        Did you fix it on this visit?
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setMode('yes')}
          className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
            mode === 'yes'
              ? 'bg-emerald-600 text-white border-emerald-600'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
          }`}
          data-testid="rtf-yes"
        >
          Yes — closing today
        </button>
        <button
          type="button"
          onClick={() => setMode('no')}
          className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
            mode === 'no'
              ? 'bg-rose-600 text-white border-rose-600'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
          }`}
          data-testid="rtf-no"
        >
          No — need a return visit
        </button>
      </div>

      {mode === 'no' && (
        <div className="mt-3 space-y-2" data-testid="rtf-form">
          <label className="block">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Return date
            </span>
            <input
              type="datetime-local"
              value={returnAt}
              onChange={(e) => setReturnAt(e.target.value)}
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
              data-testid="rtf-return-at"
            />
          </label>
          <label className="block">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Why a return visit?
            </span>
            <textarea
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Parts on order · waiting on spec · need 2-person lift…"
              className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
              data-testid="rtf-reason"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-700 select-none">
            <input
              type="checkbox"
              checked={notifyCustomer}
              onChange={(e) => setNotifyCustomer(e.target.checked)}
              data-testid="rtf-notify-customer"
            />
            Notify the customer of the new return time
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-br from-rose-600 to-rose-700 text-white text-sm font-bold disabled:opacity-50"
            data-testid="rtf-submit"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Reschedule + notify customer
          </button>
          {existing && (
            <p className="text-[11px] text-slate-500" data-testid="rtf-existing">
              A return is already booked — submitting again will refresh
              the date and re-notify the customer.
            </p>
          )}
        </div>
      )}
    </div>
  );
}


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
  // Iter 220ea·3 — kept for symmetry with the other draft setters
  // (other tabs use it for editable custom-field rows). Unused at
  // close-out time, but harmless to keep.
  const _setCustomFields = (patchOrFn) => setDraft((prev) => ({
    ...prev,
    custom_fields: typeof patchOrFn === 'function'
      ? patchOrFn(prev?.custom_fields || {})
      : patchOrFn,
  }));
  const setAutoInvoice = (v) => setDraft({ auto_invoice: !!v });

  // Iter 220e0 — Cover-aware close-out. When the case sits under an
  // active contract or warranty we should not be defaulting to
  // "Close & invoice" — the gym already pays for cover. Engineers
  // can still tick "Misuse — bill anyway" for chargeable misuse, but
  // that's now an explicit override rather than the default.
  // Iter 220e1 — shared with the JobAtAGlance cover banner so both
  // surfaces tell the same story.
  const coverState = useMemo(() => computeCoverState(job), [job]);

  // When the case is covered we treat "misuse" as the chargeable
  // override. Stored on the draft so it autosaves like any other
  // close-out field.
  const misuseOverride = !!draft.misuse_override;
  const setMisuseOverride = (v) => setDraft({ misuse_override: !!v });

  // Effective "should we bill?" — covered cases default to no-bill;
  // misuse override flips it. Non-covered keep the existing
  // auto_invoice toggle.
  const willBill = coverState.covered ? misuseOverride : autoInvoice;
  const willGenerateInvoice = coverState.covered ? misuseOverride : autoInvoice;

  const complete = async () => {
    if (!summary.trim()) { notify.error('Add a work summary'); return; }
    setBusy(true);
    try {
      if (signatureData && signatureName.trim()) {
        await outboxPost(`${API}/svc/engineer/signature`, {
          case_id: job.id, signed_by_name: signatureName.trim(),
          image_data: signatureData, summary: summary.trim(),
        }, { headers: auth().headers, kind: 'signature',
            label: `Sign-off · ${job.reference || job.id}` });
      }
      const completeRes = await outboxPost(`${API}/svc/engineer/jobs/${job.id}/complete`, {
        summary: summary.trim(), target,
        // Iter 220e0 — chargeable now follows cover state, not always true.
        chargeable: willBill,
        custom_fields: customFields,
      }, { headers: auth().headers, kind: 'job_complete',
          label: `Complete · ${job.reference || job.id}` });
      if (completeRes?.queued) {
        notify.success('Saved offline — will sync when back online',
                       `Queued: Complete ${job.reference || job.id}`);
      } else {
        notify.success('Job completed');
      }
      if (willGenerateInvoice) {
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

  // Iter 220cv — "I'm done — send the invoice" one-tap close-out.
  // Runs the full close-of-day sequence in one button: stop the
  // on-site timer (if still running) → complete the job → generate
  // the invoice draft → email the branded service report to the
  // customer. Each step is wrapped in its own try so a single
  // failure (e.g. no parts allocated yet) doesn't break the chain.
  const completeAndSendInvoice = async () => {
    if (!summary.trim()) { notify.error('Add a work summary first'); return; }
    setBusy(true);
    try {
      // 1. Stop any active on-site timer.
      const active = (job.time_entries || []).find(
        e => !e.end_at && (e.category === 'on_site' || e.category === 'travel'),
      );
      if (active) {
        try {
          await engineerSendOrQueue({
            method: 'POST',
            path: '/svc/engineer/time/stop',
            body: { entry_id: active.id },
            label: 'Stop timer (close-out)',
          });
        } catch { /* non-blocking */ }
      }
      // 2. Capture signature if the engineer drew one.
      if (signatureData && signatureName.trim()) {
        try {
          await axios.post(`${API}/svc/engineer/signature`, {
            case_id: job.id, signed_by_name: signatureName.trim(),
            image_data: signatureData, summary: summary.trim(),
          }, auth());
        } catch { /* non-blocking */ }
      }
      // 3. Complete the job. Cover-aware: covered + no-misuse cases
      //    close out as "repaired" with chargeable=false; everything
      //    else stays on the original "closed + chargeable" path.
      const fastTarget = coverState.covered && !misuseOverride ? 'repaired' : 'closed';
      await axios.post(`${API}/svc/engineer/jobs/${job.id}/complete`, {
        summary: summary.trim(),
        target: fastTarget,
        chargeable: willBill,
        custom_fields: customFields,
      }, auth());
      // 4. Generate the invoice draft — ONLY when we're actually billing.
      let inv = null;
      if (willBill) {
        try {
          const r = await axios.post(
            `${API}/svc/engineer/jobs/${job.id}/generate-invoice-draft`, {}, auth(),
          );
          inv = r.data;
          setDraftResult(inv);
        } catch (e) {
          notify.error('Invoice draft skipped', e?.response?.data?.detail || e?.message);
        }
      }
      // 5. Email the branded service report (matches the "Email report"
      // button on the report card — same backend endpoint).
      try {
        await axios.post(`${API}/svc/cases/${job.id}/service-report/email`, {}, auth());
        notify.success(
          'Sent to customer',
          inv ? `Invoice ${inv.invoice_number} created · service report emailed.`
              : (coverState.covered && !misuseOverride
                  ? 'Service report emailed · no charge (under cover).'
                  : 'Service report emailed.'),
        );
      } catch (e) {
        notify.error('Report email failed', e?.response?.data?.detail || e?.message);
      }
      // 6. Iter 220cy — Fire the NPS feedback request. Lands the
      // customer on the public tracking page where the 5-star + NPS
      // form already lives. Soft-fail so a missing email never
      // blocks the close-out.
      try {
        await axios.post(`${API}/svc/cases/${job.id}/feedback-request/send`, {}, auth());
      } catch { /* non-blocking */ }
      await clearDraft?.();
      await onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not close the job');
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
      {/* Iter 220dp — explicit "did you fix it on this visit?" gate.
          Engineers regularly hit Complete on a job they actually need
          to come back to; the customer report then mis-states reality.
          Asking the question up-front lets us either run the normal
          close-out OR route into a clean reschedule + notify flow. */}
      <ReturnToFixCard
        job={job}
        onRescheduled={async () => {
          notify.success('Return visit booked', 'Customer notified — the job is back in the diary.');
          await clearDraft?.();
          await onChange();
        }}
      />

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

      {/* Iter 220ds — Handoff-note composer lives here, not on
          Summary. Leaving notes is part of wrapping up, so it
          belongs alongside the summary + signature + outcome. */}
      <div
        className="bg-white rounded-2xl border border-slate-200 p-4"
        data-testid="complete-handoff-card"
      >
        <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500 mb-2">
          Handoff for the next engineer
        </p>
        <HandoffNotesPanel
          caseId={job.id}
          notes={job.handoff_notes || []}
          onChange={onChange}
          mode="compose"
        />
      </div>

      {/* Iter 220ds — WorkReportCustomFields temporarily removed
          from Complete. The concept is still required (machine-
          specific fields for compliance / asset-specific
          reporting), but the placement needs a rework — likely
          per-machine on the Equipment tab. Component intentionally
          NOT deleted. */}

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
        {/* Iter 220e0 — Cover-aware banner. When the gym has an active
            contract or warranty we surface that fact + change the
            default close-out to "no invoice". */}
        {coverState.covered ? (
          <div
            className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3"
            data-testid="complete-cover-banner"
          >
            <div className="flex items-start gap-2">
              <ShieldCheck size={16} className="text-emerald-700 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-extrabold text-emerald-900" data-testid="complete-cover-label">
                  {coverState.label}
                </p>
                {coverState.detail && (
                  <p className="text-[11px] text-emerald-800 mt-0.5">{coverState.detail}</p>
                )}
              </div>
            </div>
            <label className="mt-2 flex items-center gap-2 text-xs text-emerald-900 select-none">
              <input
                type="checkbox"
                checked={misuseOverride}
                onChange={(e) => setMisuseOverride(e.target.checked)}
                data-testid="complete-misuse-override"
              />
              Mis-use / chargeable — bill anyway
            </label>
          </div>
        ) : null}
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'awaiting_sign_off', label: 'Awaiting sign-off' },
            { id: 'repaired',          label: 'Repaired' },
            {
              id: 'closed',
              label: coverState.covered && !misuseOverride ? 'Close (no invoice)' : 'Close & invoice',
            },
          ].map(o => (
            <button key={o.id} type="button" onClick={() => setTarget(o.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border ${target === o.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-200'}`}
              data-testid={`complete-target-${o.id}`}>
              {o.label}
            </button>
          ))}
        </div>
        {/* Auto-invoice toggle stays for non-covered cases. For covered
            cases the toggle is hidden (misuse override controls it
            from the cover banner). */}
        {!coverState.covered && (
          <label className="mt-3 flex items-center gap-2 text-xs text-slate-700 select-none">
            <input type="checkbox" checked={autoInvoice} onChange={e => setAutoInvoice(e.target.checked)} data-testid="complete-auto-invoice" />
            Generate invoice draft from time + mileage + parts
          </label>
        )}
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

      <div className="sticky bottom-4 space-y-2">
        {/* Iter 220cv — Fast-path close-out. Stops the timer, completes
            the job, generates the invoice draft and emails the branded
            service report in one tap.
            Iter 220e0 — label adapts to cover state: covered cases
            show "close & send report" instead of "close & send
            invoice". Misuse override re-enables the invoice path. */}
        <button
          onClick={completeAndSendInvoice}
          disabled={busy}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-gradient-to-br from-emerald-600 to-emerald-700 text-white text-sm font-bold shadow-md disabled:opacity-50"
          data-testid="complete-fast-path"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          {coverState.covered && !misuseOverride
            ? "I'm done — close & send the report"
            : "I'm done — close & send the invoice"}
        </button>
        <button
          onClick={complete}
          disabled={busy}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl bg-white border border-slate-200 text-slate-700 text-xs font-bold disabled:opacity-50"
          data-testid="complete-submit"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
          Or set status manually
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
