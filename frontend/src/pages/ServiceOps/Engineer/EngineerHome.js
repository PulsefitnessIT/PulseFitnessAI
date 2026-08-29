/**
 * EngineerHome — iter 215dp (Phase 2).
 *
 * Mobile-first home screen for field engineers (`/svc/engineer`).
 * Lists today's assigned jobs in priority + SLA order, surfaces the
 * active timer, and offers a one-tap path into the job detail flow.
 *
 * Designed for one-handed use on a phone: chunky tap targets,
 * high-contrast SLA chips, no horizontal scroll.
 *
 * Backed by:
 *   GET /api/svc/engineer/me
 *   GET /api/svc/engineer/jobs?when=today|upcoming|open
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Wrench, MapPin, Clock, AlertTriangle, ChevronRight, Loader2, RefreshCw,
  PlayCircle, WifiOff, ArrowLeft, X, RotateCcw,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { notify } from '@/components/notifications';
import EngineerAccessGate from './EngineerAccessGate';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const PRIORITY_COLOUR = { p1: '#ef4444', p2: '#f59e0b', p3: '#0891b2', p4: '#6b7280' };

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

function SLAChip({ resolveAt }) {
  const { t } = useTranslation();
  if (!resolveAt) return null;
  const ms = new Date(resolveAt).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  const c = breached ? '#ef4444' : atRisk ? '#f59e0b' : '#10b981';
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold"
      style={{ background: `${c}22`, color: c }}
      data-testid="job-sla-chip"
    >
      {breached ? <AlertTriangle size={10} /> : <Clock size={10} />}
      {breached ? t('service.eng_home_sla_breached', 'BREACHED') : atRisk ? t('service.eng_home_sla_at_risk', 'AT RISK') : fmtRelative(resolveAt)}
    </span>
  );
}

function ActiveTimerBanner({ timer, onView }) {
  const { t } = useTranslation();
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
      className="w-full text-left rounded-2xl px-4 py-3 flex items-center justify-between text-white shadow-lg"
      style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}
      data-testid="active-timer-banner"
    >
      <div className="flex items-center gap-3">
        <PlayCircle size={28} />
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">{t('service.eng_home_on_the_clock', 'On the clock')} · {timer.category}</p>
          <p className="text-xl font-extrabold tabular-nums">{m}m {s}s</p>
          <p className="text-xs opacity-90">{t('service.eng_home_case', 'Case')} {timer.case_reference || timer.case_id}</p>
        </div>
      </div>
      <ChevronRight size={20} />
    </button>
  );
}

export default function EngineerHome() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // Iter 220ec — honour the ?when= filter passed by the home KPI tiles
  // (Overdue/Today/Awaiting parts) so they actually open a filtered list.
  const VALID_TABS = ['today', 'upcoming', 'open', 'overdue', 'return_to_fix', 'awaiting_parts', 'closed'];
  const initialTab = VALID_TABS.includes(searchParams.get('when')) ? searchParams.get('when') : 'today';
  const [me, setMe] = useState(null);
  const [tab, setTabState] = useState(initialTab);
  const setTab = (t) => {
    setTabState(t);
    setSearchParams(t === 'today' ? {} : { when: t }, { replace: true });
  };
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [accessBlock, setAccessBlock] = useState(null);

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, j] = await Promise.all([
        axios.get(`${API}/svc/engineer/me`, auth()),
        axios.get(`${API}/svc/engineer/jobs`, { ...auth(), params: { when: tab } }),
      ]);
      setMe(m.data);
      setJobs(j.data.jobs || []);
      setAccessBlock(null);
    } catch (e) {
      // Iter 216h77 — Engineer App access guard. 402 means the engineer
      // doesn't have an active subscription / grant; render the access
      // gate landing in-place rather than a toast spam.
      if (e?.response?.status === 402 && e?.response?.data?.detail?.code === 'engineer_app_blocked') {
        setAccessBlock(e.response.data.detail);
        return;
      }
      if (online) notify.error('Failed to load jobs', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [tab, online]);

  useEffect(() => { load(); }, [load]);

  if (accessBlock) {
    return <EngineerAccessGate detail={accessBlock} />;
  }

  return (
    <div className="min-h-screen pb-24" style={{ background: 'var(--theme-bg, #f8fafc)' }} data-testid="engineer-home">
      <header className="px-4 pt-5 pb-3 sticky top-0 z-10" style={{ background: 'var(--theme-surface, #fff)', borderBottom: '1px solid var(--theme-border, #e5e7eb)' }}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              aria-label={t('service.eng_home_back', 'Back to home')}
              className="p-2 rounded-full border shrink-0"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="engineer-jobs-back"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: '#0891b2' }}>{t('service.eng_home_eyebrow', 'Service Ops · Engineer')}</p>
            <h1 className="text-xl font-extrabold truncate" style={{ color: 'var(--theme-text)' }} data-testid="engineer-greeting">
              {me?.engineer?.full_name ? t('service.eng_home_hi', 'Hi, {{name}}', { name: me.engineer.full_name.split(' ')[0] }) : t('service.eng_home_field_engineer', 'Field engineer')}
            </h1>
            <p className="text-xs opacity-70">
              {me ? t('service.eng_home_stats', '{{today}} today · {{open}} open', { today: me.stats?.today_jobs || 0, open: me.stats?.open_jobs || 0 }) : ' '}
            </p>
          </div>
          </div>
          <div className="flex items-center gap-2">
            {!online ? (
              <span
                className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold"
                style={{ background: '#fef3c7', color: '#92400e' }}
                data-testid="offline-pill"
              >
                <WifiOff size={11} /> {t('service.eng_home_offline', 'OFFLINE')}
              </span>
            ) : null}
            <button
              type="button"
              onClick={load}
              aria-label={t('service.eng_home_refresh', 'Refresh')}
              className="p-2 rounded-full border"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="engineer-refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        <div className="mt-3 flex gap-2" data-testid="engineer-tab-bar">
          {[
            { id: 'today', label: t('service.eng_home_tab_today', 'Today') },
            { id: 'upcoming', label: t('service.eng_home_tab_upcoming', 'Upcoming') },
            { id: 'open', label: t('service.eng_home_tab_open', 'All open') },
            { id: 'closed', label: t('service.eng_home_tab_closed', 'Closed') },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className="px-3 py-1.5 rounded-full text-xs font-bold"
              style={{
                background: tab === t.id ? '#0891b2' : 'transparent',
                color: tab === t.id ? '#fff' : 'var(--theme-text)',
                border: `1px solid ${tab === t.id ? '#0891b2' : 'var(--theme-border)'}`,
              }}
              data-testid={`engineer-tab-${t.id}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Iter 278c — when arriving from the Overdue / Awaiting-parts KPI
            tiles there is no matching pill in the tab bar, so show a clear,
            removable indicator of the active special filter. */}
        {(tab === 'overdue' || tab === 'return_to_fix' || tab === 'awaiting_parts') && (
          <div className="mt-2 flex items-center gap-2" data-testid="engineer-jobs-special-filter">
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold"
              style={{ background: tab === 'overdue' ? '#fee2e2' : '#fef3c7', color: tab === 'overdue' ? '#b91c1c' : '#92400e' }}
            >
              {tab === 'overdue' ? <AlertTriangle size={11} /> : <RotateCcw size={11} />}
              {tab === 'overdue' ? 'Overdue' : 'Return to Fix'}
            </span>
            <button
              type="button"
              onClick={() => setTab('open')}
              className="inline-flex items-center gap-1 text-[11px] font-semibold opacity-70"
              data-testid="engineer-jobs-clear-filter"
            >
              <X size={11} /> {t('service.eng_home_show_all_open', 'Show all open')}
            </button>
          </div>
        )}
      </header>

      <main className="px-4 mt-4 space-y-3" data-testid="engineer-job-list">
        {me?.active_timer ? (
          <ActiveTimerBanner
            timer={me.active_timer}
            onView={() => navigate(`/svc/engineer/jobs/${me.active_timer.case_id}`)}
          />
        ) : null}

        {loading ? (
          <div className="flex items-center gap-2 text-sm opacity-70 py-8 justify-center">
            <Loader2 size={16} className="animate-spin" /> {t('service.eng_home_loading', 'Loading…')}
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12 px-6 rounded-2xl border" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="engineer-empty">
            <Wrench size={28} className="mx-auto opacity-40 mb-2" />
            <p className="font-bold" style={{ color: 'var(--theme-text)' }}>{tab === 'today' ? t('service.eng_home_empty_today', 'No jobs scheduled today') : tab === 'upcoming' ? t('service.eng_home_empty_upcoming', 'No upcoming jobs') : tab === 'closed' ? t('service.eng_home_empty_closed', 'No closed jobs yet') : t('service.eng_home_empty_open', 'No open jobs')}</p>
            <p className="text-xs opacity-70 mt-1">{t('service.eng_home_empty_hint', 'Pull down to refresh, or check back later.')}</p>
          </div>
        ) : jobs.map((j) => {
          const colour = PRIORITY_COLOUR[j.priority] || '#6b7280';
          return (
            <button
              key={j.id}
              type="button"
              onClick={() => navigate(`/svc/engineer/jobs/${j.id}`)}
              className="w-full text-left rounded-2xl border p-4 active:scale-[0.99] transition-transform"
              style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
              data-testid={`engineer-job-card-${j.reference}`}
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-extrabold tracking-wider"
                    style={{ background: `${colour}22`, color: colour }}
                  >
                    {(j.priority || 'p3').toUpperCase()}
                  </span>
                  <span className="text-xs font-bold opacity-70 tabular-nums">{j.reference}</span>
                  {/* Iter 220cx — in-progress red dot. Engineers
                      sometimes leave a job started but not closed
                      over the weekend; this surfaces it visually. */}
                  {(j.status === 'in_progress' || j.status === 'on_site') && (
                    <span
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[9px] font-bold uppercase tracking-wide"
                      data-testid={`job-${j.id}-in-progress`}
                    >
                      <span className="relative inline-block w-1.5 h-1.5">
                        <span className="absolute inset-0 rounded-full bg-emerald-500" />
                        <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-75" />
                      </span>
                      {t('service.eng_home_in_progress', 'In progress')}
                    </span>
                  )}
                </div>
                <SLAChip resolveAt={j.sla_resolve_at} />
              </div>
              <p className="font-bold text-base leading-tight" style={{ color: 'var(--theme-text)' }}>{j.title}</p>
              <div className="mt-2 space-y-0.5 text-xs opacity-80">
                {j.site_name ? (
                  <p className="inline-flex items-center gap-1.5"><MapPin size={11} /> {j.site_name}</p>
                ) : null}
                {j.asset_name ? (
                  <p className="inline-flex items-center gap-1.5"><Wrench size={11} /> {j.asset_name}</p>
                ) : null}
              </div>
              <div className="mt-3 flex items-center justify-between text-[11px] opacity-60">
                <span>{j.estimated_minutes ? t('service.eng_home_mins', '~{{min}} min', { min: j.estimated_minutes }) : t('service.eng_home_unsized', 'unsized')}</span>
                <span className="inline-flex items-center gap-1 font-bold" style={{ color: '#0891b2' }}>
                  {t('service.eng_home_open_cta', 'Open')} <ChevronRight size={12} />
                </span>
              </div>
            </button>
          );
        })}
      </main>
    </div>
  );
}
