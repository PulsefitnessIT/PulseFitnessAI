/**
 * Engineer Home v2 — iter 216h129.
 *
 * Light-mode GymAxis-branded control centre for field engineers.
 * Replaces the basic `EngineerHome` for the home tab. Existing job
 * card + active timer behaviour preserved.
 *
 * Surfaces:
 *  • Today / Upcoming / Overdue / Awaiting parts / Awaiting customer
 *  • Pending quotes (draft + sent) with last-touched + total
 *  • Quick actions: New quote, New invoice (Phase 2), New job (later),
 *    View diary, Send report (already-built /pwa/report-pdf), Support
 *  • Earnings this month (from accepted+invoiced quote totals)
 *  • Notifications unread badge
 *
 * Pulls from:
 *   GET /api/svc/engineer/dashboard   (this iter)
 *   GET /api/svc/engineer/me           (existing — for active_timer)
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Wrench, FileText, AlertTriangle, Clock, Package, MessageCircle, Boxes,
  CheckCircle2, Bell, TrendingUp, Calendar, RefreshCw, Loader2, PlayCircle, ChevronRight, Plus,
  ReceiptPoundSterling as Receipt, FileSignature,
  CreditCard, Inbox, Hand, Users, Menu, Sun, Navigation, ListChecks, Wand2, X, Wallet,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import EngineerAccountSettings from './EngineerAccountSettings';
// Iter 220e6 — Release readiness: outbox pill + global error reporter.
import { OutboxStatusPill, installEngineerErrorReporters } from '@/utils/engineerStatusBoot';
import PausedUploadsPill from './PausedUploadsPill';
import useEngineerAttention from './hooks/useEngineerAttention';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';
import EngineerAppShellNudge from './EngineerAppShellNudge';
import EngineerAccessGate from './EngineerAccessGate';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

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

const KPITile = ({ icon: Icon, label, value, accent, testid, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="text-left rounded-2xl bg-white border border-slate-200 p-4 hover:border-slate-300 hover:shadow-md transition-all active:scale-[0.99]"
    style={{ minWidth: 0 }}
    data-testid={testid}
  >
    <div className="flex items-center justify-between mb-2">
      <Icon size={16} style={{ color: accent || '#1d4ed8' }} />
      {value !== 0 && value != null ? null : <span className="text-xs text-slate-400">·</span>}
    </div>
    <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
    <p className="text-2xl font-bold mt-1 text-slate-900 tabular-nums">{value ?? '—'}</p>
  </button>
);

const QuickAction = ({ icon: Icon, label, onClick, primary, testid }) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold border transition-all active:scale-[0.99] ${
      primary
        ? 'bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white border-transparent shadow-md hover:shadow-lg'
        : 'bg-white text-slate-900 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
    }`}
    data-testid={testid}
  >
    <Icon size={18} />
    <span>{label}</span>
  </button>
);

const ActiveTimerCard = ({ timer, onView }) => {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!timer) return null;
  const elapsed = Math.max(0, Math.floor((now - new Date(timer.start_at).getTime()) / 1000));
  const m = Math.floor(elapsed / 60);
  const s = String(elapsed % 60).padStart(2, '0');
  return (
    <button
      type="button"
      onClick={onView}
      className="w-full text-left rounded-2xl p-4 flex items-center justify-between text-white shadow-md"
      style={{ background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)' }}
      data-testid="engineer-home-active-timer"
    >
      <div className="flex items-center gap-3">
        <PlayCircle size={28} />
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">
            On the clock · {timer.category}
          </p>
          <p className="text-2xl font-extrabold tabular-nums">{m}m {s}s</p>
          <p className="text-xs opacity-90">Case {timer.case_reference || timer.case_id}</p>
        </div>
      </div>
      <ChevronRight size={22} />
    </button>
  );
};

const JobRow = ({ job, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="w-full text-left flex items-center gap-3 py-3 px-1 hover:bg-slate-50 rounded-lg transition-colors"
    data-testid={`home-today-job-${job.reference}`}
  >
    <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
      <Wrench size={16} className="text-slate-500" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm font-semibold text-slate-900 truncate">{job.title}</p>
      <p className="text-xs text-slate-500 truncate">
        {job.site_name || 'Unknown site'}
        {job.asset_name ? ` · ${job.asset_name}` : ''}
      </p>
    </div>
    <div className="text-right flex-shrink-0">
      <p className="text-xs font-semibold text-slate-700 tabular-nums">{job.reference}</p>
      {job.sla_resolve_at ? (
        <p className="text-[10px] text-slate-400">SLA {fmtRelative(job.sla_resolve_at)}</p>
      ) : null}
    </div>
  </button>
);

const QuoteRow = ({ quote, onClick }) => {
  const loc = useLocalization();
  return (
  <button
    type="button"
    onClick={onClick}
    className="w-full text-left flex items-center gap-3 py-3 px-1 hover:bg-slate-50 rounded-lg transition-colors"
    data-testid={`home-pending-quote-${quote.quote_number}`}
  >
    <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
      <FileText size={16} className="text-blue-600" />
    </div>
    <div className="flex-1 min-w-0">
      <p className="text-sm font-semibold text-slate-900 truncate">{quote.quote_number}</p>
      <p className="text-xs text-slate-500 truncate">{quote.customer_name || 'Unknown customer'}</p>
    </div>
    <div className="text-right flex-shrink-0">
      <p className="text-sm font-bold text-slate-900 tabular-nums">{formatMoney(quote.total, loc, { nullDisplay: '—', minimumFractionDigits: 0, maximumFractionDigits: 0 })}</p>
      <p className="text-[10px] text-slate-400 capitalize">{quote.status}</p>
    </div>
  </button>
  );
};

export default function EngineerHomeV2() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [payouts, setPayouts] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Iter 220ea·33 — dismissible Legacy Import tile. Once an engineer has
  // migrated all their historic reports they may never need it again, so
  // they can hide it from Home (still reachable via Settings → Tools).
  const [legacyTileHidden, setLegacyTileHidden] = useState(() => {
    try { return localStorage.getItem('gx_engineer_legacy_tile_hidden') === '1'; } catch { return false; }
  });
  const hideLegacyTile = () => {
    try { localStorage.setItem('gx_engineer_legacy_tile_hidden', '1'); } catch { /* ignore */ }
    setLegacyTileHidden(true);
    notify.success('Hidden from Home', 'Find it again in Settings → Tools.');
  };
  // Iter 220cu — one-glance "My day" briefing (next stop, miles,
  // pending parts, pending quotes, unread inbox).
  const [briefing, setBriefing] = useState(null);
  // Iter 273 — render the subscribe/access paywall instead of an opaque
  // "Failed to load home" toast when the backend 402s (engineer_app_blocked).
  const [accessBlock, setAccessBlock] = useState(null);
  // Iter 220j — pulsing-dot attention digest (compliance, sub, app status).
  const attention = useEngineerAttention({ poll: true });
  // Iter 261 — org name in the header + internal/partner split.
  const orgBrand = useEngineerOrgBrand();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, mRes, pRes, bRes] = await Promise.all([
        axios.get(`${API}/svc/engineer/dashboard`, auth()),
        axios.get(`${API}/svc/engineer/me`, auth()),
        axios.get(`${API}/svc/engineer/stripe/connect/status`, auth())
          .catch(() => ({ data: null })),
        axios.get(`${API}/svc/engineer/me/briefing`, auth())
          .catch(() => ({ data: null })),
      ]);
      setAccessBlock(null);
      setData(dRes.data);
      setMe(mRes.data);
      setPayouts(pRes.data);
      setBriefing(bRes.data);
    } catch (e) {
      // 402 means the engineer is approved but not yet subscribed / on a
      // trial — route them to the access gate (clear next-step CTA), not
      // an opaque error toast.
      if (e?.response?.status === 402 && e?.response?.data?.detail?.code === 'engineer_app_blocked') {
        setAccessBlock(e.response.data.detail);
      } else {
        notify.error('Failed to load home', e?.response?.data?.detail || e.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  // Iter 220e6 — Install global JS error reporter once the Engineer
  // App home is reached. Idempotent.
  useEffect(() => { installEngineerErrorReporters(); }, []);

  const kpis = data?.kpis || {};

  if (accessBlock) {
    return <EngineerAccessGate detail={accessBlock} />;
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-home-v2">
      {/* Header — light mode GymAxis brand */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700" data-testid="engineer-home-brand">
              {orgBrand.label}
            </p>
            <h1 className="text-xl font-extrabold text-slate-900 truncate" data-testid="engineer-home-greeting">
              {me?.engineer?.full_name ? `Hi, ${me.engineer.full_name.split(' ')[0]}` : 'Field engineer'}
            </h1>
            <p className="text-xs text-slate-500">
              {kpis.today_jobs || 0} today · {kpis.upcoming_jobs || 0} upcoming · {kpis.notifications_unread || 0} new
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Iter 220e6 — Offline outbox status pill. Only renders
                when offline or there are queued mutations. */}
            <OutboxStatusPill />
            {/* Iter 220ea·4 — Paused-uploads pill. Only renders when
                there are media uploads sitting in the stash. Lets
                the engineer resume from where they left off. */}
            <PausedUploadsPill />
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/workspace')}
              className="hidden lg:inline-flex items-center gap-1.5 px-3 py-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700"
              data-testid="engineer-home-open-workspace"
              title="Open desktop workspace"
            >
              <PlayCircle size={14} className="text-blue-600" /> Workspace
            </button>
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/notifications')}
              className="relative p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              data-testid="engineer-home-notifications-btn"
            >
              <Bell size={16} />
              {kpis.notifications_unread > 0 && (
                <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                  {kpis.notifications_unread}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={load}
              aria-label="Refresh"
              className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              data-testid="engineer-home-refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="relative p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              data-testid="engineer-home-menu-btn"
              aria-label="Open account settings"
              title="Account settings"
            >
              <Menu size={16} />
              {(() => {
                // Iter 220j — unified attention dot. RED beats AMBER beats
                // legacy "payouts not ready" amber. Pulses on red so the
                // engineer notices a blocked subscription / expired doc
                // before opening the drawer.
                const dotSev = attention.severity === 'red'
                  ? 'red'
                  : (attention.severity === 'amber' || (payouts && !payouts.ready))
                    ? 'amber'
                    : null;
                if (!dotSev) return null;
                const cls = dotSev === 'red' ? 'bg-rose-500' : 'bg-amber-500';
                const pulse = dotSev === 'red' ? 'animate-ping' : '';
                return (
                  <span
                    className={`absolute -top-0.5 -right-0.5 rounded-full w-2.5 h-2.5 ring-2 ring-white ${cls}`}
                    aria-hidden="true"
                    data-testid={`engineer-menu-attention-${dotSev}`}
                  >
                    {pulse && (
                      <span className={`absolute inset-0 rounded-full ${cls} opacity-75 ${pulse}`} />
                    )}
                  </span>
                );
              })()}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-28 space-y-5">
        {loading && !data ? (
          <div className="text-center py-16 text-slate-400">
            <Loader2 className="animate-spin mx-auto mb-2" size={20} />
            Loading your control centre…
          </div>
        ) : (
          <>
            {/* Active timer banner */}
            {me?.active_timer ? (
              <ActiveTimerCard
                timer={me.active_timer}
                onView={() => navigate(`/svc/engineer/jobs/${me.active_timer.case_id}`)}
              />
            ) : null}

            {/* Stripe Connect onboarding moved to the Account Settings drawer
                (hamburger menu, top-right). The hamburger shows an amber dot
                while payouts aren't ready so the nudge stays visible. */}

            {/* Iter 216h257 — Earnings hero card removed per user feedback.
                Earnings live in the KPI grid + the new Analytics page. */}

    {/* Iter 220cu — "My day" briefing strip. Composes the next
        stop + miles + pending parts/quotes/inbox into one
        glanceable line so the engineer knows the shape of their
        day without tapping anything. */}
    {briefing && (briefing.next_stop || briefing.jobs_today_total > 0
                  || briefing.pending_parts_count > 0
                  || briefing.pending_quotes_count > 0
                  || briefing.not_invoiced_count > 0) && (
      <MyDayBriefing briefing={briefing} navigate={navigate} />
    )}
    {/* Iter 220dc — Nearest-job chip. Engineer taps once, browser
        prompts for geolocation, backend returns the nearest open
        job. One-tap "navigate me to the closest stop" use-case. */}
    {briefing && briefing.jobs_today_total > 0 && (
      <NearestJobChip navigate={navigate} />
    )}
    {/* Iter 220df — PWA install + push subscribe nudge.
        Quietly hides itself when both already done OR cooldown active. */}
    <EngineerAppShellNudge />
    {/* Iter 220cx — Closed-but-not-invoiced recovery card. Catches
        the silent-failure case where the "I'm done" fast-path
        closed the job but the invoice step errored. */}
    {briefing?.not_invoiced_count > 0 && (
      <NotInvoicedAlert
        cases={briefing.not_invoiced || []}
        navigate={navigate}
      />
    )}

            {/* KPI Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="engineer-home-kpi-grid">
              <KPITile icon={Calendar} label="Today" value={kpis.today_jobs} accent="#1d4ed8"
                       testid="kpi-today" onClick={() => navigate('/svc/engineer/jobs?when=today')} />
              <KPITile icon={Clock} label="Upcoming" value={kpis.upcoming_jobs} accent="#6366f1"
                       testid="kpi-upcoming" onClick={() => navigate('/svc/engineer/upcoming')} />
              <KPITile icon={AlertTriangle} label="Overdue" value={kpis.overdue_jobs} accent="#dc2626"
                       testid="kpi-overdue" onClick={() => navigate('/svc/engineer/jobs?when=open')} />
              <KPITile icon={Package} label="Awaiting parts" value={kpis.awaiting_parts} accent="#f59e0b"
                       testid="kpi-parts" onClick={() => navigate('/svc/engineer/jobs?when=open')} />
              <KPITile icon={FileText} label="Pending quotes" value={kpis.quote_pending} accent="#0891b2"
                       testid="kpi-pending-quotes" onClick={() => navigate('/svc/engineer/quotes')} />
              <KPITile icon={CheckCircle2} label="Accepted" value={kpis.quote_accepted} accent="#059669"
                       testid="kpi-accepted-quotes" onClick={() => navigate('/svc/engineer/quotes?status=accepted')} />
              <KPITile icon={MessageCircle} label="Awaiting customer" value={kpis.awaiting_customer} accent="#7c3aed"
                       testid="kpi-awaiting-customer"
                       onClick={() => navigate('/svc/engineer/quotes?status=sent')} />
              <KPITile icon={Receipt} label="Invoiced" value={kpis.quote_invoiced} accent="#16a34a"
                       testid="kpi-invoiced"
                       onClick={() => navigate('/svc/engineer/invoices')} />
            </div>

            {/* Iter 220ea·33 — Legacy import promo tile (dismissible).
                Iter 261 — hidden for internal engineers: their Service Desk
                imports historical reports via Settings instead. */}
            {!legacyTileHidden && !orgBrand.internal && (
              <div
                className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 via-white to-blue-50/40 p-4 flex items-center gap-3"
                data-testid="engineer-home-legacy-tile"
              >
                <button
                  type="button"
                  onClick={() => navigate('/svc/engineer/legacy-import')}
                  className="flex items-center gap-3 flex-1 min-w-0 text-left"
                  data-testid="engineer-home-legacy-open"
                >
                  <div className="w-10 h-10 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center flex-shrink-0">
                    <Wand2 size={18} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-purple-700">New</p>
                    <p className="text-sm font-bold text-slate-900 truncate">Import legacy reports</p>
                    <p className="text-xs text-slate-500 truncate">Old PDFs &amp; spreadsheets → branded GymAxis PDFs.</p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={hideLegacyTile}
                  className="p-1.5 rounded-full border border-slate-200 bg-white hover:bg-slate-50 flex-shrink-0"
                  data-testid="engineer-home-legacy-hide"
                  aria-label="Hide legacy import tile"
                  title="Hide from Home"
                >
                  <X size={14} className="text-slate-400" />
                </button>
              </div>
            )}

            {/* Quick actions — Iter 220cr: grouped by workflow
                (jobs → quotes → invoices → records → other) so the
                most-used actions cluster naturally. */}
            <div className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="engineer-home-quick-actions">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-3">Quick actions</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {/* — Jobs — */}
                <QuickAction icon={Wrench} primary label="New job"
                             testid="qa-new-job"
                             onClick={() => navigate('/svc/engineer/jobs/new')} />
                <QuickAction icon={Hand} label="Up for grabs"
                             testid="qa-queue"
                             onClick={() => navigate('/svc/engineer/queue')} />
                <QuickAction icon={Inbox} label="Inbox"
                             testid="qa-inbox"
                             onClick={() => navigate('/svc/engineer/inbox')} />
                <QuickAction icon={Calendar} label="View diary"
                             testid="qa-diary"
                             onClick={() => navigate('/svc/engineer/diary')} />
                {/* — Quotes — */}
                <QuickAction icon={Plus} label="New quote"
                             testid="qa-new-quote"
                             onClick={() => navigate('/svc/engineer/quotes/new')} />
                <QuickAction icon={FileText} label="My quotes"
                             testid="qa-quotes"
                             onClick={() => navigate('/svc/engineer/quotes')} />
                {/* — Invoices — */}
                <QuickAction icon={Receipt} label="New invoice"
                             testid="qa-new-invoice"
                             onClick={() => navigate('/svc/engineer/invoices/new')} />
                <QuickAction icon={Receipt} label="My invoices"
                             testid="qa-invoices"
                             onClick={() => navigate('/svc/engineer/invoices')} />
                {/* — Records — */}
                <QuickAction icon={Users} label="My customers"
                             testid="qa-customers"
                             onClick={() => navigate('/svc/engineer/customers')} />
                <QuickAction icon={Package} label="Equipment"
                             testid="qa-equipment"
                             onClick={() => navigate('/svc/engineer/equipment')} />
                <QuickAction icon={Boxes} label="Stock"
                             testid="qa-parts"
                             onClick={() => navigate('/svc/engineer/stock')} />
                <QuickAction icon={Wallet} label="Expenses"
                             testid="qa-expenses"
                             onClick={() => navigate('/svc/engineer/expenses')} />
                {/* — Other — */}
                <QuickAction icon={FileSignature} label="Send report"
                             testid="qa-report"
                             onClick={() => navigate('/svc/engineer/jobs')} />
                <QuickAction icon={Sun} label="End of day"
                             testid="qa-end-of-day"
                             onClick={() => navigate('/svc/engineer/end-of-day')} />
                {payouts?.ready ? (
                  <QuickAction icon={CreditCard} label="Payouts"
                               testid="qa-payouts"
                               onClick={() => navigate('/svc/engineer/payouts')} />
                ) : null}
                {/* Iter 216h257 — Analytics surface with filtered KPI breakdowns. */}
                <QuickAction icon={TrendingUp} label="Analytics"
                             testid="qa-analytics"
                             onClick={() => navigate('/svc/engineer/analytics')} />
              </div>
            </div>

            {/* Today's jobs + Pending quotes (side-by-side on md+) */}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="engineer-home-today-list">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-bold text-slate-900">Today's jobs</p>
                  <button onClick={() => navigate('/svc/engineer')} className="text-xs font-semibold text-blue-600 hover:text-blue-700" data-testid="today-jobs-view-all">
                    View all →
                  </button>
                </div>
                {data?.today_jobs?.length ? (
                  <div className="divide-y divide-slate-100">
                    {data.today_jobs.map(j => (
                      <JobRow key={j.id} job={j}
                              onClick={() => navigate(`/svc/engineer/jobs/${j.id}`)} />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-sm text-slate-400">
                    <CheckCircle2 size={20} className="mx-auto mb-2 opacity-50" />
                    Nothing on the diary today.
                  </div>
                )}
              </div>

              <div className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="engineer-home-pending-quotes-list">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-bold text-slate-900">Pending quotes</p>
                  <button onClick={() => navigate('/svc/engineer/quotes')} className="text-xs font-semibold text-blue-600 hover:text-blue-700" data-testid="pending-quotes-view-all">
                    View all →
                  </button>
                </div>
                {data?.pending_quotes?.length ? (
                  <div className="divide-y divide-slate-100">
                    {data.pending_quotes.map(q => (
                      <QuoteRow key={q.id} quote={q}
                                onClick={() => navigate(`/svc/engineer/quotes/${q.id}`)} />
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-sm text-slate-400">
                    <FileText size={20} className="mx-auto mb-2 opacity-50" />
                    No quotes awaiting customer response.
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </main>

      <EngineerAccountSettings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        payouts={payouts}
        attention={attention}
        onChanged={() => { load(); attention.refresh(); }}
      />
    </div>
  );
}


// ─── NearestJobChip ───────────────────────────────────────────────
// Iter 220dc. Engineers leaving a job want to know which of their
// remaining stops is geographically closest, not the chronologically
// next one. Tap → browser asks for location → backend returns the
// nearest open assignment with distance + ETA → tap the chip to
// open the job.
function NearestJobChip({ navigate }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const find = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setError('Location not available in this browser.');
      return;
    }
    setBusy(true);
    setError('');
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const r = await axios.get(
            `${API}/svc/engineer/queue/my-nearest`,
            {
              ...auth(),
              params: { lat: pos.coords.latitude, lon: pos.coords.longitude, limit: 1 },
            },
          );
          if (r.data?.nearest) {
            setResult(r.data.nearest);
          } else {
            setError('No open jobs to route to.');
          }
        } catch (e) {
          setError(e?.response?.data?.detail || e?.message || 'Lookup failed.');
        } finally { setBusy(false); }
      },
      (geoErr) => {
        setBusy(false);
        setError(geoErr.message || 'Location permission denied.');
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    );
  };

  if (result) {
    const addr = [result.site_address, result.site_postcode].filter(Boolean).join(' ');
    const mapsHref = addr
      ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(addr)}`
      : null;
    return (
      <div
        className="rounded-2xl bg-white border border-emerald-200 p-3 flex items-center gap-3"
        data-testid="nearest-job-card"
      >
        <div className="w-9 h-9 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center flex-shrink-0">
          <Navigation size={14} />
        </div>
        <button
          type="button"
          onClick={() => navigate(`/svc/engineer/jobs/${result.id}`)}
          className="flex-1 text-left min-w-0"
          data-testid="nearest-job-open"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-700">
            Nearest stop
          </p>
          <p className="text-sm font-bold text-slate-900 truncate">
            {result.reference || 'Job'}
            {result.site_name ? ` · ${result.site_name}` : ''}
          </p>
          <p className="text-xs text-slate-500">
            {result.distance_km != null ? `${result.distance_km} km` : 'distance unknown'}
            {result.eta_minutes != null ? ` · ~${result.eta_minutes} min` : ''}
          </p>
        </button>
        {mapsHref && (
          <a
            href={mapsHref}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold whitespace-nowrap"
            data-testid="nearest-job-navigate"
          >
            <Navigation size={12} /> Go
          </a>
        )}
      </div>
    );
  }

  return (
    <div
      className="rounded-2xl bg-white border border-slate-200 p-3 flex items-center gap-2"
      data-testid="nearest-job-chip"
    >
      <button
        type="button"
        onClick={find}
        disabled={busy}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 hover:bg-blue-100 text-blue-800 text-xs font-bold border border-blue-200 disabled:opacity-50"
        data-testid="nearest-job-find"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Navigation size={12} />}
        Find nearest stop
      </button>
      {error && (
        <p className="text-[11px] text-amber-700" data-testid="nearest-job-error">{error}</p>
      )}
    </div>
  );
}


// ─── MyDayBriefing ────────────────────────────────────────────────
// Iter 220cu. Single-line summary of the engineer's day. Falls
// quietly silent when there's nothing to highlight.
function MyDayBriefing({ briefing, navigate }) {
  const ns = briefing.next_stop;
  const address = ns ? [ns.site_address, ns.site_postcode].filter(Boolean).join(' ') : '';
  const mapsHref = address
    ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`
    : null;
  const remaining = briefing.jobs_today_remaining || 0;
  const total = briefing.jobs_today_total || 0;
  return (
    <div
      className="rounded-2xl bg-gradient-to-br from-blue-50 via-white to-emerald-50/40 border border-blue-200 p-4 flex items-start gap-3"
      data-testid="engineer-home-my-day"
    >
      <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center flex-shrink-0">
        <Sun size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
          Your day
        </p>
        {total > 0 ? (
          <p className="text-sm font-bold text-slate-900" data-testid="my-day-headline">
            {remaining > 0
              ? `${remaining} of ${total} job${total === 1 ? '' : 's'} left today`
              : `All ${total} job${total === 1 ? '' : 's'} done — nice one`}
          </p>
        ) : (
          <p className="text-sm font-bold text-slate-900">No jobs scheduled today</p>
        )}
        {ns && (
          <button
            type="button"
            onClick={() => navigate(`/svc/engineer/jobs/${ns.id}`)}
            className="mt-1 inline-flex items-start gap-1.5 text-left hover:bg-white/50 rounded-lg px-1.5 py-1 -mx-1.5"
            data-testid="my-day-next-stop"
          >
            <ListChecks size={11} className="text-emerald-700 mt-0.5" />
            <span className="text-xs text-slate-700 leading-snug">
              <span className="font-bold">Next: {ns.reference || 'Job'}</span>
              {ns.site_name ? ` · ${ns.site_name}` : ''}
              {ns.title ? ` — ${ns.title}` : ''}
            </span>
          </button>
        )}
        <div className="mt-1.5 flex items-center flex-wrap gap-1.5">
          {briefing.pending_parts_count > 0 && (
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/jobs')}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-bold uppercase tracking-wide"
              data-testid="my-day-pending-parts"
            >
              <Package size={9} /> {briefing.pending_parts_count} part{briefing.pending_parts_count === 1 ? '' : 's'} pending
            </button>
          )}
          {briefing.pending_quotes_count > 0 && (
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/quotes')}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-800 border border-indigo-200 text-[10px] font-bold uppercase tracking-wide"
              data-testid="my-day-pending-quotes"
            >
              <FileText size={9} /> {briefing.pending_quotes_count} quote{briefing.pending_quotes_count === 1 ? '' : 's'} pending
            </button>
          )}
          {briefing.unread_inbox_count > 0 && (
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/inbox')}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-rose-50 text-rose-800 border border-rose-200 text-[10px] font-bold uppercase tracking-wide"
              data-testid="my-day-unread-inbox"
            >
              <Inbox size={9} /> {briefing.unread_inbox_count} unread
            </button>
          )}
        </div>
      </div>
      {mapsHref && (
        <a
          href={mapsHref}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold whitespace-nowrap"
          data-testid="my-day-navigate"
        >
          <Navigation size={12} /> Navigate
        </a>
      )}
    </div>
  );
}


// ─── NotInvoicedAlert ─────────────────────────────────────────────
// Iter 220cx. Surfaces jobs the engineer closed in the last 7 days
// that DON'T have an invoice attached — recovers from the silent
// failure mode where the fast-path close-out closes the job but
// the invoice-draft step errors (e.g. no chargeable lines yet).
function NotInvoicedAlert({ cases, navigate }) {
  if (!cases || cases.length === 0) return null;
  const fmtDate = (iso) => {
    try {
      return new Date(iso).toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short',
      });
    } catch { return ''; }
  };
  return (
    <div
      className="rounded-2xl bg-amber-50/80 border border-amber-200 p-4"
      data-testid="engineer-home-not-invoiced"
    >
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center flex-shrink-0">
          <AlertTriangle size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-800">
            Closed but not invoiced
          </p>
          <p className="text-sm font-bold text-slate-900 mt-1">
            {cases.length} job{cases.length === 1 ? '' : 's'} from the last 7 days have no invoice yet.
          </p>
          <p className="text-[11px] text-amber-900 mt-0.5">
            Tap one to generate an invoice draft — your fast-path close-out probably failed silently.
          </p>
          <ul className="mt-2 space-y-1" data-testid="not-invoiced-list">
            {cases.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/svc/engineer/invoices/new?case_id=${c.id}`)}
                  className="w-full inline-flex items-center gap-2 text-left px-2 py-1 rounded-lg bg-white border border-amber-200 hover:border-amber-300 text-xs"
                  data-testid={`not-invoiced-case-${c.id}`}
                >
                  <span className="font-bold text-blue-700 tabular-nums">
                    {c.reference || c.id?.slice(0, 8)}
                  </span>
                  <span className="flex-1 truncate text-slate-700">
                    {c.title || '(untitled)'}
                  </span>
                  {c.customer_name && (
                    <span className="text-[10px] text-slate-500 truncate hidden sm:inline">
                      {c.customer_name}
                    </span>
                  )}
                  <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700">
                    {fmtDate(c.closed_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
