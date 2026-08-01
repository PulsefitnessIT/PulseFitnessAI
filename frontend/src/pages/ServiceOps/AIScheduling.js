/**
 * AI Scheduling — Service Desk (Phase 1 MVP).
 *
 * "The AI recommends. The planner decides."
 *
 * Left: today's engineer schedules (current state) with lock controls.
 * Top:  re-plan modes (Re-plan Remaining Day · Add Priority Job).
 * Right: generated proposal — side-by-side current vs proposed, with
 *        approve all / approve selected / reject + override reason.
 *
 * All job mutations apply via the existing diary writer on the backend.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Sparkles, RefreshCw, Lock, Unlock, AlertTriangle, Clock, ArrowRight,
  CheckCircle2, XCircle, ShieldCheck, Wand2, Loader2, Calendar, Plus,
  TrendingUp, MapPin, Gauge, ShieldAlert, BarChart3, Settings, Inbox, Zap, X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—');
const fmtDateTime = (iso) => (iso ? new Date(iso).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : '—');
const todayStr = () => new Date().toISOString().slice(0, 10);

// SLA / change styling — cls stays static; labels are resolved via i18n
// helpers below so the badges translate without losing their colours.
const SLA_STYLE = {
  on_track: { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  at_risk: { cls: 'bg-amber-100 text-amber-700 border-amber-200' },
  breached: { cls: 'bg-rose-100 text-rose-700 border-rose-200' },
  saved: { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  worsened: { cls: 'bg-rose-100 text-rose-700 border-rose-200' },
  none: { cls: 'bg-slate-100 text-slate-600 border-slate-200' },
};
const SLA_FALLBACK = {
  on_track: 'On Track', at_risk: 'At Risk', breached: 'Breached',
  saved: 'Saved by Re-plan', worsened: 'Worsened', none: 'No SLA',
};
const slaLabel = (t, key) => t(`service.aisch_sla_${key || 'none'}`, SLA_FALLBACK[key] || SLA_FALLBACK.none);

const CHANGE_STYLE = {
  move: { cls: 'bg-cyan-100 text-cyan-700' },
  insert: { cls: 'bg-teal-100 text-teal-700' },
  reassign: { cls: 'bg-teal-100 text-teal-700' },
  defer: { cls: 'bg-amber-100 text-amber-700' },
  unchanged: { cls: 'bg-slate-100 text-slate-600' },
  protected: { cls: 'bg-slate-200 text-slate-700' },
};
const CHANGE_FALLBACK = {
  move: 'Moved', insert: 'Inserted', reassign: 'Reassigned',
  defer: 'Deferred', unchanged: 'Unchanged', protected: 'Protected',
};
const changeLabel = (t, key) => t(`service.aisch_change_${key || 'unchanged'}`, CHANGE_FALLBACK[key] || CHANGE_FALLBACK.unchanged);

const RISK_DOT = { high: 'bg-rose-500', medium: 'bg-amber-500', low: 'bg-emerald-500' };

function StatCard({ icon: Icon, label, value, tone = 'slate', testid }) {
  const tones = {
    slate: 'text-slate-700', rose: 'text-rose-600', amber: 'text-amber-600',
    emerald: 'text-emerald-600', blue: 'text-cyan-600',
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-3" data-testid={testid}>
      <div className={`shrink-0 ${tones[tone]}`}><Icon size={20} /></div>
      <div>
        <div className={`text-2xl font-semibold ${tones[tone]}`}>{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  );
}

export default function AIScheduling() {
  const { t } = useTranslation();
  const [date, setDate] = useState(todayStr());
  const [board, setBoard] = useState(null);
  const [loadingBoard, setLoadingBoard] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [items, setItems] = useState([]);
  const [planning, setPlanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [override, setOverride] = useState('');
  const [showPriorityPicker, setShowPriorityPicker] = useState(false);
  const [unassigned, setUnassigned] = useState([]);
  const [disruptEng, setDisruptEng] = useState('');
  const [delayMins, setDelayMins] = useState(60);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState(null);
  const [showInsights, setShowInsights] = useState(false);
  const [insights, setInsights] = useState(null);
  const [pending, setPending] = useState([]);

  const loadPending = useCallback(async () => {
    try {
      const r = await api.get('/svc/scheduling/proposals', { params: { status: 'awaiting_approval', limit: 10 } });
      setPending(r.data.proposals || []);
    } catch { /* silent */ }
  }, []);

  const openProposal = async (id) => {
    setPlanning(true);
    try {
      const r = await api.get(`/svc/scheduling/proposals/${id}`);
      setProposal(r.data.proposal);
      setItems(r.data.items || []);
      const actionable = (r.data.items || []).filter((i) => ['move', 'insert', 'reassign', 'defer'].includes(i.change_type) && i.decision === 'pending');
      setSelected(new Set(actionable.map((i) => i.id)));
    } catch (e) {
      notify.error(t('service.aisch_could_not_open', 'Could not open suggestion'), e?.response?.data?.detail || '');
    } finally {
      setPlanning(false);
    }
  };

  const dismissPending = async (id) => {
    setPending((prev) => prev.filter((p) => p.id !== id));  // optimistic
    try {
      await api.post(`/svc/scheduling/proposals/${id}/reject`, { reject_all: true });
      notify.info(t('service.aisch_suggestion_dismissed', 'Suggestion dismissed'), t('service.aisch_no_changes', 'No changes were made.'));
      if (proposal?.id === id) { setProposal(null); setItems([]); }
    } catch (e) {
      notify.error(t('service.aisch_could_not_dismiss', 'Could not dismiss'), e?.response?.data?.detail || '');
      loadPending();
    }
  };

  const loadSettings = useCallback(async () => {
    try {
      const r = await api.get('/svc/scheduling/settings');
      setSettings(r.data.settings);
    } catch (e) { notify.error(t('service.aisch_could_not_load_settings', 'Could not load settings'), e?.response?.data?.detail || ''); }
  }, [t]);

  const saveSettings = async (patch) => {
    try {
      const r = await api.put('/svc/scheduling/settings', patch);
      setSettings(r.data.settings);
      notify.success(t('service.aisch_settings_saved', 'Settings saved'), '');
    } catch (e) { notify.error(t('service.aisch_could_not_save_settings', 'Could not save settings'), e?.response?.data?.detail || ''); }
  };

  const loadInsights = useCallback(async () => {
    try {
      const [rep, dur] = await Promise.all([
        api.get('/svc/scheduling/reports', { params: { days: 30 } }),
        api.get('/svc/scheduling/duration-insights'),
      ]);
      setInsights({ report: rep.data, durations: dur.data.insights || [] });
    } catch (e) { notify.error(t('service.aisch_could_not_load_insights', 'Could not load insights'), e?.response?.data?.detail || ''); }
  }, [t]);

  const loadBoard = useCallback(async () => {
    setLoadingBoard(true);
    try {
      const r = await api.get('/svc/scheduling/board', { params: { date } });
      setBoard(r.data);
    } catch (e) {
      notify.error(t('service.aisch_could_not_load_schedule', 'Could not load schedule'), e?.response?.data?.detail || t('service.aisch_try_again', 'Try again.'));
    } finally {
      setLoadingBoard(false);
    }
  }, [date, t]);

  useEffect(() => { loadBoard(); loadPending(); }, [loadBoard, loadPending]);

  const generate = async (mode, opts = {}) => {
    setPlanning(true);
    setProposal(null); setItems([]); setSelected(new Set()); setOverride('');
    try {
      const r = await api.post('/svc/scheduling/replan', { mode, date, trigger: 'manual', ...opts });
      setProposal(r.data.proposal);
      setItems(r.data.items || []);
      const actionable = (r.data.items || []).filter((i) => ['move', 'insert', 'reassign', 'defer'].includes(i.change_type));
      setSelected(new Set(actionable.map((i) => i.id)));
      if (!actionable.length) notify.info(t('service.aisch_no_safe_changes', 'No safe changes'), t('service.aisch_already_optimal', 'The schedule is already optimal or fully protected.'));
    } catch (e) {
      notify.error(t('service.aisch_replan_failed', 'Re-plan failed'), e?.response?.data?.detail || t('service.aisch_try_again', 'Try again.'));
    } finally {
      setPlanning(false);
      setShowPriorityPicker(false);
    }
  };

  const simulate = async (scenario, opts = {}) => {
    setPlanning(true);
    setProposal(null); setItems([]); setSelected(new Set()); setOverride('');
    try {
      const r = await api.post('/svc/scheduling/simulate', { scenario, date, ...opts });
      setProposal(r.data.proposal);
      setItems(r.data.items || []);
      notify.info(t('service.aisch_sim_ready', 'Simulation ready'), t('service.aisch_sim_preview_only', 'Preview only — nothing has been changed.'));
    } catch (e) {
      notify.error(t('service.aisch_sim_failed', 'Simulation failed'), e?.response?.data?.detail || t('service.aisch_try_again', 'Try again.'));
    } finally {
      setPlanning(false);
    }
  };

  const openPriorityPicker = async () => {
    try {
      const r = await api.get('/svc/admin/diary/unassigned', { params: { limit: 50 } });
      setUnassigned(r.data.jobs || []);
      setShowPriorityPicker(true);
    } catch (e) {
      notify.error(t('service.aisch_could_not_load_unassigned', 'Could not load unassigned jobs'), e?.response?.data?.detail || '');
    }
  };

  const toggleLock = async (job) => {
    try {
      if (job.protected_reason === 'Locked by planner' || job._locked) {
        await api.delete(`/svc/scheduling/locks/${job.id}`);
        notify.success(t('service.aisch_job_unlocked', 'Job unlocked'), job.reference || '');
      } else {
        await api.post('/svc/scheduling/locks', { case_id: job.id, reason: 'Planner-locked' });
        notify.success(t('service.aisch_job_locked', 'Job locked'), t('service.aisch_will_not_move', '{{ref}} will not be moved by the AI.', { ref: job.reference || '' }));
      }
      loadBoard();
    } catch (e) {
      notify.error(t('service.aisch_lock_failed', 'Lock action failed'), e?.response?.data?.detail || '');
    }
  };

  const actionableItems = useMemo(
    () => items.filter((i) => ['move', 'insert', 'reassign', 'defer'].includes(i.change_type)),
    [items],
  );

  // Simulation state is derived from the proposal itself (trigger starts with
  // "simulation:") so it can never go stale across mode switches.
  const proposalIsSim = Boolean(proposal?.trigger && String(proposal.trigger).startsWith('simulation'));

  const toggleSel = (id) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const approve = async (all) => {
    if (!proposal) return;
    setApplying(true);
    try {
      const payload = all
        ? { approve_all: true, override_reason: override || null }
        : { item_ids: [...selected], override_reason: override || null };
      const r = await api.post(`/svc/scheduling/proposals/${proposal.id}/approve`, payload);
      notify.success(t('service.aisch_schedule_updated', 'Schedule updated'), t('service.aisch_changes_applied_notified', '{{n}} change(s) applied. Engineers notified.', { n: r.data.applied }));
      if (r.data.errors?.length) notify.error(t('service.aisch_some_failed', 'Some changes failed'), t('service.aisch_could_not_apply', '{{n}} could not apply.', { n: r.data.errors.length }));
      setProposal(r.data.proposal);
      await loadBoard();
      await loadPending();
      // refresh item decisions
      const fresh = await api.get(`/svc/scheduling/proposals/${proposal.id}`);
      setItems(fresh.data.items || []);
    } catch (e) {
      notify.error(t('service.aisch_approval_failed', 'Approval failed'), e?.response?.data?.detail || '');
    } finally {
      setApplying(false);
    }
  };

  const reject = async () => {
    if (!proposal) return;
    try {
      await api.post(`/svc/scheduling/proposals/${proposal.id}/reject`, { reject_all: true });
      notify.info(t('service.aisch_proposal_rejected', 'Proposal rejected'), t('service.aisch_no_changes', 'No changes were made.'));
      setProposal(null); setItems([]); setSelected(new Set());
      loadPending();
    } catch (e) {
      notify.error(t('service.aisch_reject_failed', 'Reject failed'), e?.response?.data?.detail || '');
    }
  };

  const stats = board?.stats || {};
  const summary = proposal?.summary || {};

  return (
    <div className="space-y-6" data-testid="ai-scheduling-page">
      {/* Hero */}
      <div className="rounded-2xl bg-slate-900 bg-gradient-to-br from-slate-900 to-teal-900 text-white p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-white/10 p-2"><Sparkles size={22} /></div>
            <div>
              <div className="text-2xl font-semibold text-white">{t('service.aisch_title', 'AI Scheduling')}</div>
              <p className="text-sm text-teal-200">{t('service.aisch_tagline', 'The AI recommends. Your planner decides.')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date" value={date} onChange={(e) => setDate(e.target.value)}
              className="rounded-lg bg-white border border-white/20 text-slate-900 text-sm px-3 py-2"
              data-testid="ai-scheduling-date"
            />
            <Button variant="secondary" size="sm" onClick={loadBoard} data-testid="ai-scheduling-refresh">
              <RefreshCw size={14} className="mr-1" /> {t('service.aisch_refresh', 'Refresh')}
            </Button>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button className="text-white" onClick={() => generate('remaining_day')} disabled={planning} data-testid="replan-remaining-day-btn">
            {planning ? <Loader2 size={15} className="mr-1 animate-spin" /> : <Wand2 size={15} className="mr-1" />}
            {t('service.aisch_replan_remaining', 'Re-plan Remaining Day')}
          </Button>
          <Button variant="secondary" onClick={() => generate('reduce_travel')} disabled={planning} data-testid="reduce-travel-btn">
            <MapPin size={15} className="mr-1" /> {t('service.aisch_reduce_travel', 'Reduce Travel')}
          </Button>
          <Button variant="secondary" onClick={() => generate('sla_rescue')} disabled={planning} data-testid="sla-rescue-btn">
            <ShieldAlert size={15} className="mr-1" /> {t('service.aisch_sla_rescue', 'SLA Rescue')}
          </Button>
          <Button variant="secondary" onClick={openPriorityPicker} disabled={planning} data-testid="add-priority-job-btn">
            <Plus size={15} className="mr-1" /> {t('service.aisch_add_priority', 'Add Priority Job')}
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" className="text-white/90 hover:text-white" onClick={() => generate('full_day')} disabled={planning} data-testid="full-day-btn">{t('service.aisch_full_day', 'Full Day')}</Button>
          <Button variant="ghost" size="sm" className="text-white/90 hover:text-white" onClick={() => generate('tomorrow')} disabled={planning} data-testid="tomorrow-btn">{t('service.aisch_tomorrow', 'Tomorrow')}</Button>
          <Button variant="ghost" size="sm" className="text-white/90 hover:text-white" onClick={() => generate('weekly')} disabled={planning} data-testid="weekly-btn">{t('service.aisch_weekly', 'Weekly')}</Button>
          <span className="flex-1" />
          <Button variant="ghost" size="sm" className="text-white/90 hover:text-white" onClick={() => { setShowInsights((v) => !v); if (!insights) loadInsights(); }} data-testid="insights-toggle-btn"><BarChart3 size={14} className="mr-1" /> {t('service.aisch_insights', 'Insights')}</Button>
          <Button variant="ghost" size="sm" className="text-white/90 hover:text-white" onClick={() => { setShowSettings((v) => !v); if (!settings) loadSettings(); }} data-testid="settings-toggle-btn"><Settings size={14} className="mr-1" /> {t('service.aisch_settings', 'Settings')}</Button>
        </div>
      </div>

      {/* Dashboard cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="ai-scheduling-stats">
        <StatCard icon={Gauge} label={t('service.aisch_engineers_working', 'Engineers working')} value={stats.engineers_working ?? '—'} tone="blue" testid="stat-engineers-working" />
        <StatCard icon={ShieldAlert} label={t('service.aisch_jobs_at_risk', 'Jobs at SLA risk')} value={stats.jobs_at_risk ?? '—'} tone="rose" testid="stat-jobs-at-risk" />
        <StatCard icon={ArrowRight} label={t('service.aisch_safe_to_move', 'Safe to move')} value={stats.jobs_movable ?? '—'} tone="emerald" testid="stat-jobs-movable" />
        <StatCard icon={Lock} label={t('service.aisch_locked_protected', 'Locked & protected')} value={stats.jobs_locked ?? '—'} tone="slate" testid="stat-jobs-locked" />
        <StatCard icon={AlertTriangle} label={t('service.aisch_unassigned', 'Unassigned')} value={stats.jobs_unassigned ?? '—'} tone="amber" testid="stat-jobs-unassigned" />
      </div>

      {/* Pending AI suggestions inbox */}
      {pending.length > 0 && (
        <div className="rounded-xl border border-teal-200 bg-teal-50 p-4" data-testid="pending-suggestions">
          <div className="flex items-center gap-2 mb-2 text-teal-800 font-semibold text-sm">
            <Inbox size={16} /> {t('service.aisch_pending_title', 'Pending AI suggestions ({{n}})', { n: pending.length })}
          </div>
          <div className="space-y-2">
            {pending.map((p) => {
              const proactive = String(p.trigger || '').startsWith('priority_job') || String(p.trigger || '').includes('priority');
              return (
                <div key={p.id}
                  className="w-full rounded-lg bg-white border border-teal-100 hover:border-teal-400 p-3 transition-colors flex items-center justify-between gap-2"
                  data-testid={`pending-${p.id}`}>
                  <button onClick={() => openProposal(p.id)} className="text-left min-w-0 flex-1" data-testid={`pending-open-${p.id}`}>
                    <div className="text-sm font-medium text-slate-800 flex items-center gap-2">
                      {proactive && <span className="text-amber-600 flex items-center gap-0.5 text-[11px] font-semibold"><Zap size={12} /> {t('service.aisch_auto', 'AUTO')}</span>}
                      {p.mode.replace(/_/g, ' ')} · {t('service.aisch_changes_count', '{{n}} change(s)', { n: p.summary?.actionable ?? 0 })}
                    </div>
                    <div className="text-[11px] text-slate-500">{p.date} · {p.trigger?.replace(/_/g, ' ')} · {new Date(p.created_at).toLocaleString([], { hour: '2-digit', minute: '2-digit' })}</div>
                  </button>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={() => openProposal(p.id)} className="text-xs text-teal-600 font-medium px-2 py-1 hover:bg-teal-50 rounded" data-testid={`pending-review-${p.id}`}>{t('service.aisch_review', 'Review →')}</button>
                    <button onClick={() => dismissPending(p.id)} title={t('service.aisch_dismiss', 'Dismiss')} className="text-slate-400 hover:text-rose-600 p-1 rounded" data-testid={`pending-dismiss-${p.id}`}>
                      <X size={15} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Settings panel */}
      {showSettings && settings && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="settings-panel">
          <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2"><Settings size={15} /> {t('service.aisch_settings_title', 'Scheduling Settings')}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
            <div>
              <label className="block text-[11px] text-slate-500 mb-1">{t('service.aisch_work_start', 'Work start (hr)')}</label>
              <input type="number" min="0" max="23" defaultValue={settings.work_start_hour}
                onBlur={(e) => saveSettings({ work_start_hour: Number(e.target.value) })}
                className="rounded-lg border border-slate-200 text-sm px-3 py-2 w-full" data-testid="setting-work-start" />
            </div>
            <div>
              <label className="block text-[11px] text-slate-500 mb-1">{t('service.aisch_work_end', 'Work end (hr)')}</label>
              <input type="number" min="1" max="24" defaultValue={settings.work_end_hour}
                onBlur={(e) => saveSettings({ work_end_hour: Number(e.target.value) })}
                className="rounded-lg border border-slate-200 text-sm px-3 py-2 w-full" data-testid="setting-work-end" />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={!!settings.proactive_p1}
                onChange={(e) => saveSettings({ proactive_p1: e.target.checked })} data-testid="setting-proactive" />
              {t('service.aisch_proactive_p1', 'Proactive P1 suggestions')}
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={!!(settings.customer_notifications || {}).enabled}
                onChange={(e) => saveSettings({ customer_notifications: { ...(settings.customer_notifications || {}), enabled: e.target.checked } })} data-testid="setting-customer-notify" />
              {t('service.aisch_notify_customers', 'Notify customers on reschedule')}
            </label>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{t('service.aisch_approval_note', 'Approval is always required before any change is applied. Times are in {{tz}}.', { tz: settings.timezone || 'UTC' })}</p>
        </div>
      )}

      {/* Insights / reports panel */}
      {showInsights && insights && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="insights-panel">
          <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2"><BarChart3 size={15} /> {t('service.aisch_insights_title', 'Scheduling insights (30 days)')}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <StatCard icon={Wand2} label={t('service.aisch_proposals', 'Proposals')} value={insights.report.proposals_generated} tone="blue" testid="report-proposals" />
            <StatCard icon={CheckCircle2} label={t('service.aisch_changes_applied', 'Changes applied')} value={insights.report.changes_applied} tone="emerald" testid="report-applied" />
            <StatCard icon={Gauge} label={t('service.aisch_ai_acceptance', 'AI acceptance')} value={insights.report.ai_acceptance_rate_pct != null ? `${insights.report.ai_acceptance_rate_pct}%` : '—'} tone="blue" testid="report-acceptance" />
            <StatCard icon={TrendingUp} label={t('service.aisch_travel_saved_min', 'Travel saved (min)')} value={insights.report.travel_saved_minutes} tone="emerald" testid="report-travel-saved" />
          </div>
          {insights.durations.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-600 mb-1">{t('service.aisch_job_duration', 'Job duration — estimated vs actual')}</div>
              <div className="space-y-1">
                {insights.durations.slice(0, 6).map((d) => (
                  <div key={d.fault_code} className="flex items-center justify-between text-xs bg-slate-50 rounded-lg px-3 py-1.5" data-testid={`duration-${d.fault_code}`}>
                    <span className="font-mono text-slate-600">{d.fault_code}</span>
                    <span className="text-slate-500">{t('service.aisch_actual', 'actual')} <b>{d.avg_actual_minutes}m</b> · {t('service.aisch_est', 'est')} {d.avg_estimated_minutes ?? '—'}m
                      {d.variance_pct != null && <span className={d.variance_pct > 0 ? 'text-rose-600 ml-1' : 'text-emerald-600 ml-1'}>({d.variance_pct > 0 ? '+' : ''}{d.variance_pct}%)</span>}
                      <span className="text-slate-400 ml-1">n={d.sample_count}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Disruptions & What-if */}
      <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="disruption-panel">
        <h3 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
          <ShieldAlert size={15} /> {t('service.aisch_disruptions_title', 'Disruptions & What-if')}
        </h3>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">{t('service.aisch_engineer', 'Engineer')}</label>
            <select
              value={disruptEng} onChange={(e) => setDisruptEng(e.target.value)}
              className="rounded-lg border border-slate-200 text-sm px-3 py-2 min-w-[180px]"
              data-testid="disrupt-engineer-select"
            >
              <option value="">{t('service.aisch_select_engineer', 'Select engineer…')}</option>
              {(board?.engineers || []).map((e) => (
                <option key={e.engineer_id} value={e.engineer_id}>{`${e.engineer_name} (${e.job_count})`}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">{t('service.aisch_delay_min', 'Delay (min)')}</label>
            <input
              type="number" min="0" step="15" value={delayMins}
              onChange={(e) => setDelayMins(Number(e.target.value))}
              className="rounded-lg border border-slate-200 text-sm px-3 py-2 w-24"
              data-testid="disrupt-delay-input"
            />
          </div>
          <Button variant="secondary" size="sm" disabled={!disruptEng || planning}
            onClick={() => generate('engineer_delayed', { engineer_id: disruptEng, delay_minutes: delayMins })}
            data-testid="engineer-delayed-btn">
            <Clock size={14} className="mr-1" /> {t('service.aisch_engineer_delayed', 'Engineer Delayed')}
          </Button>
          <Button variant="secondary" size="sm" disabled={!disruptEng || planning}
            onClick={() => generate('engineer_unavailable', { engineer_id: disruptEng })}
            data-testid="engineer-unavailable-btn">
            <XCircle size={14} className="mr-1" /> {t('service.aisch_engineer_unavailable', 'Engineer Unavailable')}
          </Button>
          <Button variant="ghost" size="sm" disabled={!disruptEng || planning}
            onClick={() => simulate('engineer_sick', { engineer_id: disruptEng })}
            data-testid="whatif-sick-btn">
            <Wand2 size={14} className="mr-1" /> {t('service.aisch_whatif_sick', 'What-if: off sick (simulate)')}
          </Button>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">{t('service.aisch_sim_note', 'Simulations preview the impact only — nothing is applied or saved as a change.')}</p>
      </div>

      {/* Priority job picker */}
      {showPriorityPicker && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="priority-picker">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-slate-800">{t('service.aisch_pick_urgent', 'Pick the urgent job to insert')}</h3>
            <Button variant="ghost" size="sm" onClick={() => setShowPriorityPicker(false)}>{t('service.aisch_close', 'Close')}</Button>
          </div>
          {unassigned.length === 0 ? (
            <p className="text-sm text-slate-500">{t('service.aisch_no_unassigned', 'No unassigned jobs waiting.')}</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-auto">
              {unassigned.map((j) => (
                <button
                  key={j.id} onClick={() => generate('add_priority_job', { priority_case_id: j.id })}
                  className="w-full text-left rounded-lg border border-slate-200 hover:border-teal-400 hover:bg-teal-50 p-3 transition-colors"
                  data-testid={`priority-job-${j.id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-800 text-sm">{j.reference} · {j.title}</span>
                    <Badge variant="outline" className="uppercase text-[10px]">{j.priority || 'p3'}</Badge>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">{j.site_name || j.customer_name || ''}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* LEFT — current schedule */}
        <div className="space-y-3" data-testid="current-schedule">
          <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <Calendar size={15} /> {t('service.aisch_todays_schedule', "Today's schedule")}
          </h2>
          {loadingBoard ? (
            <div className="py-10 text-center text-slate-400 text-sm"><Loader2 size={16} className="inline animate-spin mr-1" /> {t('service.aisch_loading', 'Loading…')}</div>
          ) : (board?.engineers || []).filter((e) => e.job_count > 0).length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              {t('service.aisch_no_jobs_day', 'No scheduled jobs for this day.')}
            </div>
          ) : (
            (board?.engineers || []).filter((e) => e.job_count > 0).map((eng) => (
              <div key={eng.engineer_id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="font-medium text-slate-800 text-sm mb-2">{eng.engineer_name}</div>
                <div className="space-y-2">
                  {eng.jobs.map((j) => {
                    const sla = SLA_STYLE[j.sla_state] || SLA_STYLE.none;
                    const locked = j.protected_reason === 'Locked by planner';
                    return (
                      <div key={j.id} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2" data-testid={`board-job-${j.id}`}>
                        <span className="text-xs font-mono text-slate-500 w-12 shrink-0">{fmtTime(j.scheduled_at)}</span>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-slate-800 truncate">{j.reference} · {j.title}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sla.cls}`}>{slaLabel(t, j.sla_state)}</span>
                            {j.protected && (
                              <span className="text-[10px] text-slate-500 flex items-center gap-0.5">
                                <ShieldCheck size={11} /> {j.protected_reason}
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => toggleLock(j)}
                          className={`shrink-0 p-1.5 rounded-md ${locked ? 'text-teal-600 bg-teal-50' : 'text-slate-400 hover:text-slate-700'}`}
                          title={locked ? t('service.aisch_unlock', 'Unlock') : t('service.aisch_lock', 'Lock (protect from AI)')}
                          data-testid={`lock-toggle-${j.id}`}
                        >
                          {locked ? <Lock size={14} /> : <Unlock size={14} />}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        {/* RIGHT — proposal */}
        <div className="space-y-3" data-testid="proposal-panel">
          <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <Sparkles size={15} /> {t('service.aisch_ai_proposal', 'AI proposal')}
          </h2>
          {!proposal ? (
            <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
              {t('service.aisch_proposal_empty', 'Run a re-plan to see recommended changes. Nothing moves until you approve.')}
            </div>
          ) : (
            <>
              {/* proposal summary */}
              <div className="rounded-xl border border-teal-200 bg-teal-50 p-4" data-testid="proposal-summary">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-teal-700 uppercase tracking-wide">{proposal.mode.replace(/_/g, ' ')}</span>
                  {proposalIsSim
                    ? <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-200" data-testid="simulation-badge">{t('service.aisch_sim_not_applied', 'Simulation — not applied')}</Badge>
                    : <Badge variant="outline" data-testid="proposal-status">{proposal.status.replace(/_/g, ' ')}</Badge>}
                </div>
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                  <div><div className="text-lg font-semibold text-cyan-700">{(summary.jobs_moved || 0) + (summary.jobs_inserted || 0)}</div><div className="text-[10px] text-slate-500">{t('service.aisch_stat_changes', 'changes')}</div></div>
                  <div><div className="text-lg font-semibold text-slate-700">{summary.jobs_protected || 0}</div><div className="text-[10px] text-slate-500">{t('service.aisch_stat_protected', 'protected')}</div></div>
                  <div><div className="text-lg font-semibold text-emerald-700">{summary.sla_saved || 0}</div><div className="text-[10px] text-slate-500">{t('service.aisch_stat_sla_saved', 'SLA saved')}</div></div>
                  <div><div className="text-lg font-semibold text-amber-700">{summary.jobs_deferred || 0}</div><div className="text-[10px] text-slate-500">{t('service.aisch_stat_deferred', 'deferred')}</div></div>
                </div>
                <div className="mt-2 flex items-center justify-between flex-wrap gap-1">
                  <div className="text-[11px] text-teal-700 flex items-center gap-1">
                    <Gauge size={12} /> {t('service.aisch_confidence', 'Confidence {{n}}%', { n: Math.round((proposal.confidence || 0) * 100) })}
                  </div>
                  {(summary.travel_saved_minutes ?? 0) !== 0 && (
                    <div className={`text-[11px] flex items-center gap-1 font-medium ${summary.travel_saved_minutes > 0 ? 'text-emerald-700' : 'text-rose-600'}`} data-testid="travel-saved">
                      <TrendingUp size={12} /> {summary.travel_saved_minutes > 0 ? t('service.aisch_travel_saved', '{{n}} min travel saved', { n: summary.travel_saved_minutes }) : t('service.aisch_travel_more', '{{n}} min more travel', { n: Math.abs(summary.travel_saved_minutes) })}
                    </div>
                  )}
                </div>
                {proposal.narrative && (
                  <p className="mt-2 text-[12px] text-slate-700 bg-white/70 rounded-lg p-2 border border-teal-100" data-testid="proposal-narrative">
                    {proposal.narrative}
                  </p>
                )}
              </div>

              {/* items */}
              <div className="space-y-2 max-h-[460px] overflow-auto pr-1" data-testid="proposal-items">
                {items.map((i) => {
                  const ch = CHANGE_STYLE[i.change_type] || CHANGE_STYLE.unchanged;
                  const sla = SLA_STYLE[i.sla_label] || SLA_STYLE.none;
                  const isAction = ['move', 'insert', 'reassign', 'defer'].includes(i.change_type);
                  const isApplied = i.decision === 'applied';
                  return (
                    <div key={i.id} className={`rounded-lg border p-3 ${isApplied ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white'}`} data-testid={`proposal-item-${i.case_id}`}>
                      <div className="flex items-start gap-2">
                        {isAction && !isApplied && (
                          <input type="checkbox" className="mt-1" checked={selected.has(i.id)} onChange={() => toggleSel(i.id)} data-testid={`item-select-${i.case_id}`} />
                        )}
                        <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${RISK_DOT[i.risk_level] || RISK_DOT.low}`} title={t('service.aisch_risk_title', '{{level}} risk', { level: i.risk_level })} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-slate-800">{i.reference} · {i.title}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${ch.cls}`}>{changeLabel(t, i.change_type)}</span>
                            {isApplied && <span className="text-[10px] text-emerald-700 flex items-center gap-0.5"><CheckCircle2 size={11} /> {t('service.aisch_applied', 'applied')}</span>}
                          </div>
                          <div className="text-xs text-slate-500">{i.engineer_name}{i.site_name ? ` · ${i.site_name}` : ''}</div>
                          {isAction ? (
                            <div className="mt-1 flex items-center gap-2 text-xs">
                              <span className="text-slate-400 line-through">{fmtDateTime(i.old_scheduled_at)}</span>
                              <ArrowRight size={12} className="text-slate-400" />
                              <span className="font-medium text-slate-800">{fmtDateTime(i.new_scheduled_at)}</span>
                              {i.travel_impact_minutes > 0 && (
                                <span className="text-slate-400 flex items-center gap-0.5"><MapPin size={11} /> ~{i.travel_impact_minutes}m</span>
                              )}
                            </div>
                          ) : (
                            <div className="mt-1 text-xs text-slate-500 flex items-center gap-1"><ShieldCheck size={12} /> {i.protected_reason}</div>
                          )}
                          <div className="mt-1 flex items-center gap-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sla.cls}`}>{slaLabel(t, i.sla_label)}</span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500 italic">{i.reason}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* approval bar */}
              {actionableItems.length > 0 && !proposalIsSim && proposal.status !== 'applied' && proposal.status !== 'rejected' && (
                <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2" data-testid="approval-bar">
                  <input
                    value={override} onChange={(e) => setOverride(e.target.value)}
                    placeholder={t('service.aisch_override_ph', 'Optional override / decision note…')}
                    className="w-full text-sm rounded-lg border border-slate-200 px-3 py-2"
                    data-testid="override-reason"
                  />
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => approve(true)} disabled={applying} data-testid="approve-all-btn">
                      {applying ? <Loader2 size={14} className="mr-1 animate-spin" /> : <CheckCircle2 size={14} className="mr-1" />}
                      {t('service.aisch_approve_all', 'Approve all')}
                    </Button>
                    <Button variant="secondary" onClick={() => approve(false)} disabled={applying || selected.size === 0} data-testid="approve-selected-btn">
                      {t('service.aisch_approve_selected', 'Approve selected ({{n}})', { n: selected.size })}
                    </Button>
                    <Button variant="ghost" className="text-rose-600" onClick={reject} disabled={applying} data-testid="reject-btn">
                      <XCircle size={14} className="mr-1" /> {t('service.aisch_reject_all', 'Reject all')}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
