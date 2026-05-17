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
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Wrench, FileText, AlertTriangle, Clock, Package, MessageCircle,
  CheckCircle2, Bell, TrendingUp, Calendar, RefreshCw, Loader2,
  PoundSterling, PlayCircle, ChevronRight, Plus, Receipt, FileSignature,
  CreditCard, Inbox,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const fmtGBP = (n) => n == null ? '—' : `£${Number(n).toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
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

const QuoteRow = ({ quote, onClick }) => (
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
      <p className="text-sm font-bold text-slate-900 tabular-nums">{fmtGBP(quote.total)}</p>
      <p className="text-[10px] text-slate-400 capitalize">{quote.status}</p>
    </div>
  </button>
);

export default function EngineerHomeV2() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [payouts, setPayouts] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, mRes, pRes] = await Promise.all([
        axios.get(`${API}/svc/engineer/dashboard`, auth()),
        axios.get(`${API}/svc/engineer/me`, auth()),
        axios.get(`${API}/svc/engineer/stripe/connect/status`, auth())
          .catch(() => ({ data: null })),
      ]);
      setData(dRes.data);
      setMe(mRes.data);
      setPayouts(pRes.data);
    } catch (e) {
      notify.error('Failed to load home', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const kpis = data?.kpis || {};

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-home-v2">
      {/* Header — light mode GymAxis brand */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
              GymAxis · Engineer
            </p>
            <h1 className="text-xl font-extrabold text-slate-900 truncate" data-testid="engineer-home-greeting">
              {me?.engineer?.full_name ? `Hi, ${me.engineer.full_name.split(' ')[0]}` : 'Field engineer'}
            </h1>
            <p className="text-xs text-slate-500">
              {kpis.today_jobs || 0} today · {kpis.upcoming_jobs || 0} upcoming · {kpis.notifications_unread || 0} new
            </p>
          </div>
          <div className="flex items-center gap-2">
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

            {/* Stripe Connect onboarding nudge — only shows until ready */}
            {payouts && !payouts.ready ? (
              <button
                type="button"
                onClick={() => navigate('/svc/engineer/payouts')}
                className="w-full text-left rounded-2xl border border-amber-200 bg-amber-50 p-4 flex items-center gap-3 hover:border-amber-300 transition-colors"
                data-testid="engineer-home-connect-stripe-banner"
              >
                <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                  <CreditCard size={18} className="text-amber-700" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-amber-900">
                    {payouts.connected
                      ? 'Finish Stripe onboarding to take card payments'
                      : 'Accept card payments on your invoices'}
                  </p>
                  <p className="text-xs text-amber-800">
                    {payouts.connected
                      ? "Stripe still needs a few details — usually ID or bank account."
                      : 'Connect your Stripe (3 min) so customers can pay invoices by card.'}
                  </p>
                </div>
                <ChevronRight size={18} className="text-amber-700" />
              </button>
            ) : null}

            {/* Earnings hero card */}
            <div
              className="rounded-2xl p-5 text-white shadow-md"
              style={{ background: 'linear-gradient(135deg, #1d4ed8 0%, #6366f1 60%, #8b5cf6 100%)' }}
              data-testid="engineer-home-earnings-card"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">Earnings this month</p>
                  <p className="text-3xl font-extrabold tabular-nums mt-1">
                    {fmtGBP(kpis.earnings_this_month)}
                  </p>
                  <p className="text-xs opacity-90 mt-1">
                    {kpis.quote_accepted || 0} accepted · {kpis.quote_invoiced || 0} invoiced
                  </p>
                </div>
                <TrendingUp size={42} className="opacity-50" />
              </div>
            </div>

            {/* KPI Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="engineer-home-kpi-grid">
              <KPITile icon={Calendar} label="Today" value={kpis.today_jobs} accent="#1d4ed8"
                       testid="kpi-today" onClick={() => navigate('/svc/engineer?tab=today')} />
              <KPITile icon={Clock} label="Upcoming" value={kpis.upcoming_jobs} accent="#6366f1"
                       testid="kpi-upcoming" onClick={() => navigate('/svc/engineer?tab=upcoming')} />
              <KPITile icon={AlertTriangle} label="Overdue" value={kpis.overdue_jobs} accent="#dc2626"
                       testid="kpi-overdue" onClick={() => navigate('/svc/engineer?tab=open')} />
              <KPITile icon={Package} label="Awaiting parts" value={kpis.awaiting_parts} accent="#f59e0b"
                       testid="kpi-parts" onClick={() => navigate('/svc/engineer?tab=open')} />
              <KPITile icon={FileText} label="Pending quotes" value={kpis.quote_pending} accent="#0891b2"
                       testid="kpi-pending-quotes" onClick={() => navigate('/svc/engineer/quotes')} />
              <KPITile icon={CheckCircle2} label="Accepted" value={kpis.quote_accepted} accent="#059669"
                       testid="kpi-accepted-quotes" onClick={() => navigate('/svc/engineer/quotes?status=accepted')} />
              <KPITile icon={MessageCircle} label="Awaiting customer" value={kpis.awaiting_customer} accent="#7c3aed"
                       testid="kpi-awaiting-customer" />
              <KPITile icon={Receipt} label="Invoiced" value={kpis.quote_invoiced} accent="#16a34a"
                       testid="kpi-invoiced" />
            </div>

            {/* Quick actions */}
            <div className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="engineer-home-quick-actions">
              <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-3">Quick actions</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <QuickAction icon={Wrench} primary label="New job"
                             testid="qa-new-job"
                             onClick={() => navigate('/svc/engineer/jobs/new')} />
                <QuickAction icon={Inbox} label="Inbox"
                             testid="qa-inbox"
                             onClick={() => navigate('/svc/engineer/inbox')} />
                <QuickAction icon={Plus} label="New quote"
                             testid="qa-new-quote"
                             onClick={() => navigate('/svc/engineer/quotes/new')} />
                <QuickAction icon={Receipt} label="New invoice"
                             testid="qa-new-invoice"
                             onClick={() => navigate('/svc/engineer/invoices/new')} />
                <QuickAction icon={Calendar} label="View diary"
                             testid="qa-diary"
                             onClick={() => navigate('/svc/engineer/diary')} />
                <QuickAction icon={FileText} label="My quotes"
                             testid="qa-quotes"
                             onClick={() => navigate('/svc/engineer/quotes')} />
                <QuickAction icon={Receipt} label="My invoices"
                             testid="qa-invoices"
                             onClick={() => navigate('/svc/engineer/invoices')} />
                <QuickAction icon={Package} label="Parts"
                             testid="qa-parts"
                             onClick={() => navigate('/svc/engineer/parts')} />
                <QuickAction icon={FileSignature} label="Send report"
                             testid="qa-report"
                             onClick={() => navigate('/svc/engineer/jobs')} />
                <QuickAction icon={MessageCircle} label="Support"
                             testid="qa-support"
                             onClick={() => navigate('/support')} />
                <QuickAction icon={CreditCard} label={payouts?.ready ? 'Payouts' : 'Connect Stripe'}
                             testid="qa-payouts"
                             onClick={() => navigate('/svc/engineer/payouts')} />
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
    </div>
  );
}
