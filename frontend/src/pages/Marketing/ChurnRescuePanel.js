/**
 * Churn Rescue — True 1:1 personalised win-back campaigns.
 *
 * Two-step workflow:
 *   1. Scan         → multi-signal detector returns at-risk members with
 *                     their EXACT exit signal (lapsed, class affinity drop,
 *                     payment failure, frequency drop, frozen, late-cancel
 *                     streak). One row per member.
 *   2. Generate     → multi-select rows → Claude writes per-member rescue
 *                     copy across email/sms/push/in_app referencing the
 *                     specific signal evidence.
 *   3. Review       → staff sees generated copy, refines or approves/rejects.
 *   4. Approve      → schedules the send via Autopilot at the member's
 *                     personal best window with multi-channel smart
 *                     fallback.
 *
 * Per user choices: multi-signal detector + queue for staff approval +
 * multi-channel with smart fallback.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  HeartCrack, Loader2, Sparkles, Search, RefreshCw, Check, X, Send,
  AlertTriangle, Mail, MessageSquare, Bell, Inbox, Lock, Wand2, Clock,
  TrendingDown, Snowflake, CreditCard, CalendarX, Users, ChevronRight,
  ChevronDown,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const SIGNAL_META = {
  payment_failure:     { icon: CreditCard,  color: 'text-rose-500',    bg: 'bg-rose-500/10',    label: 'Payment failure' },
  frozen_membership:   { icon: Snowflake,   color: 'text-sky-500',     bg: 'bg-sky-500/10',     label: 'Plan frozen' },
  late_cancel_streak:  { icon: CalendarX,   color: 'text-orange-500',  bg: 'bg-orange-500/10',  label: 'Cancel streak' },
  class_affinity_drop: { icon: HeartCrack,  color: 'text-fuchsia-500', bg: 'bg-fuchsia-500/10', label: 'Stopped favourite class' },
  frequency_drop:      { icon: TrendingDown,color: 'text-amber-500',   bg: 'bg-amber-500/10',   label: 'Visits dropped' },
  lapsed_visit:        { icon: Clock,       color: 'text-zinc-500',    bg: 'bg-zinc-500/10',    label: 'Lapsed' },
};

const CHANNEL_ICON = {
  email:  Mail, sms: MessageSquare, push: Bell, in_app: Inbox,
};

const ChurnRescuePanel = ({ API, headers, entitlement }) => {
  const [scanning, setScanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [targets, setTargets] = useState([]);
  const [scannedAt, setScannedAt] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [queue, setQueue] = useState([]);
  const [expanded, setExpanded] = useState(null); // rescue_id currently expanded for review
  const [refineBusyId, setRefineBusyId] = useState(null);
  const [refineText, setRefineText] = useState('');

  const locked = entitlement && !entitlement.features?.ai_creative_studio;

  const loadAll = async () => {
    setScanning(true);
    try {
      const [scanR, queueR] = await Promise.all([
        axios.get(`${API}/api/marketing/creative/director/churn-risk/scan?limit=100`, { headers }),
        axios.get(`${API}/api/marketing/creative/director/churn-risk/queue?limit=200`, { headers }),
      ]);
      setTargets(scanR.data?.targets || []);
      setScannedAt(scanR.data?.scanned_at || null);
      setQueue(queueR.data?.rescues || []);
    } catch (e) {
      notifyApiError(notify, e, 'Scan failed');
    }
    setScanning(false);
  };

  // Iter 216h226-polish-5 — depend on `locked` so the gated load fires
  // ONLY after the entitlement check resolves. Without this, mount
  // runs before `entitlement` lands → `locked` is undefined → we load
  // even on locked tiers. `loadAll` deliberately excluded — re-creating
  // it each render is fine; we want the effect to re-fire only when
  // the entitlement gate flips.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!locked) loadAll(); }, [locked]);

  const toggleSelect = (memberId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(memberId)) next.delete(memberId); else next.add(memberId);
      return next;
    });
  };

  const selectableCount = useMemo(
    () => targets.filter((t) => !t.existing_rescue_id).length, [targets],
  );

  const selectAll = () => {
    const ids = targets.filter((t) => !t.existing_rescue_id).map((t) => t.member_id);
    setSelected(new Set(ids));
  };
  const clearSelection = () => setSelected(new Set());

  const generate = async () => {
    if (selected.size === 0) {
      notify.error('Select at least one member to rescue');
      return;
    }
    setGenerating(true);
    try {
      const r = await axios.post(
        `${API}/api/marketing/creative/director/churn-risk/generate`,
        { member_ids: Array.from(selected) },
        { headers, timeout: 180000 },
      );
      const created = r.data?.count || 0;
      const failed = (r.data?.failed || []).length;
      if (created) notify.success(`${created} bespoke rescue${created === 1 ? '' : 's'} drafted — review the queue below`);
      if (failed) notify.error(`${failed} failed — see queue for details`);
      setSelected(new Set());
      await loadAll();
    } catch (e) {
      notifyApiError(notify, e, 'Generation failed');
    }
    setGenerating(false);
  };

  const approve = async (rescueId, sendNow = false) => {
    try {
      await axios.post(
        `${API}/api/marketing/creative/director/churn-risk/${rescueId}/approve`,
        { send_now: sendNow }, { headers },
      );
      notify.success(sendNow ? 'Approved — sending shortly' : 'Approved — scheduled at member\'s best window');
      await loadAll();
    } catch (e) {
      notifyApiError(notify, e, 'Approve failed');
    }
  };

  const approveBulk = async () => {
    const pending = queue.filter((q) => q.status === 'pending_approval').map((q) => q.id);
    if (!pending.length) {
      notify.error('No pending rescues to approve');
      return;
    }
    try {
      const r = await axios.post(
        `${API}/api/marketing/creative/director/churn-risk/approve-bulk`,
        { rescue_ids: pending }, { headers },
      );
      notify.success(`Approved ${r.data?.approved_count || 0} rescues`);
      await loadAll();
    } catch (e) {
      notifyApiError(notify, e, 'Bulk approve failed');
    }
  };

  const reject = async (rescueId) => {
    try {
      await axios.post(
        `${API}/api/marketing/creative/director/churn-risk/${rescueId}/reject`,
        { reason: 'Staff rejected' }, { headers },
      );
      notify.success('Rejected');
      await loadAll();
    } catch (e) {
      notifyApiError(notify, e, 'Reject failed');
    }
  };

  const refine = async (rescueId) => {
    if (!refineText.trim()) return;
    setRefineBusyId(rescueId);
    try {
      await axios.post(
        `${API}/api/marketing/creative/director/churn-risk/${rescueId}/refine`,
        { instruction: refineText.trim() }, { headers, timeout: 120000 },
      );
      notify.success('Refined');
      setRefineText('');
      await loadAll();
    } catch (e) {
      notifyApiError(notify, e, 'Refine failed');
    }
    setRefineBusyId(null);
  };

  if (locked) {
    return (
      <div className="rounded-xl border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 p-6 text-center" data-testid="churn-rescue-locked">
        <Lock className="mx-auto text-amber-500 mb-2" size={28} />
        <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">Churn Rescue is a Pro feature</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">Upgrade to Pro to unlock AI 1:1 win-back personalization.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="churn-rescue-panel">
      {/* Header / hero */}
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-white via-white to-rose-50/30 dark:from-zinc-900 dark:via-zinc-900 dark:to-rose-950/10 p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <HeartCrack className="text-rose-500" size={18} />
          <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100">
            Churn Rescue — True 1:1 Personalisation
          </h2>
          <span className="ml-2 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-600 dark:text-rose-300">
            New
          </span>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Multi-signal detector spots members showing exit signals (dropped attendance, missed classes, frequency drops, frozen plans, payment issues) and Claude writes a bespoke message that names their exact behaviour — never a generic blast.
        </p>
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <button onClick={loadAll} disabled={scanning}
            className="px-3 py-1.5 rounded-md bg-rose-500 hover:bg-rose-600 disabled:bg-zinc-300 disabled:dark:bg-zinc-700 text-white text-xs font-semibold flex items-center gap-1.5"
            data-testid="churn-rescan-btn">
            {scanning ? <Loader2 size={12} className="animate-spin"/> : <Search size={12}/>}
            {scanning ? 'Scanning…' : 'Re-scan members'}
          </button>
          {scannedAt && (
            <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
              Last scanned {new Date(scannedAt).toLocaleString()}
            </span>
          )}
          {selected.size > 0 && (
            <span className="ml-auto text-xs text-zinc-600 dark:text-zinc-300">
              {selected.size} of {selectableCount} selected
            </span>
          )}
          <button onClick={selectAll} disabled={!selectableCount || generating}
            className="px-2.5 py-1.5 rounded-md text-[11px] font-medium border border-zinc-200 dark:border-zinc-700 hover:border-rose-500 hover:text-rose-500 disabled:opacity-40"
            data-testid="churn-select-all">
            Select all
          </button>
          <button onClick={clearSelection} disabled={!selected.size || generating}
            className="px-2.5 py-1.5 rounded-md text-[11px] font-medium border border-zinc-200 dark:border-zinc-700 hover:border-zinc-500 disabled:opacity-40"
            data-testid="churn-clear-selection">
            Clear
          </button>
          <button onClick={generate} disabled={!selected.size || generating}
            className="px-3 py-1.5 rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] disabled:bg-zinc-300 disabled:dark:bg-zinc-700 text-white text-xs font-semibold flex items-center gap-1.5"
            data-testid="churn-generate-btn">
            {generating ? <Loader2 size={12} className="animate-spin"/> : <Sparkles size={12}/>}
            {generating ? 'Drafting…' : `Generate 1:1 rescue${selected.size > 1 ? 's' : ''}`}
          </button>
        </div>
      </div>

      {/* At-risk targets table */}
      {targets.length === 0 && !scanning && (
        <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20 p-6 text-center" data-testid="churn-no-targets">
          <Check className="mx-auto text-emerald-500 mb-2" size={28} />
          <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">No exit signals detected right now</p>
          <p className="text-xs text-emerald-600/80 dark:text-emerald-400/80 mt-1">Members are engaging healthily. We&apos;ll keep watching.</p>
        </div>
      )}

      {targets.length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
          <div className="px-4 py-2 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-2 bg-zinc-50/50 dark:bg-zinc-900/40">
            <Users size={13} className="text-zinc-500"/>
            <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
              {targets.length} at-risk member{targets.length === 1 ? '' : 's'} detected
            </p>
            <span className="text-[10px] text-zinc-400 ml-auto">Sorted by signal severity, then lifetime value</span>
          </div>
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800 max-h-[440px] overflow-y-auto">
            {targets.map((t) => {
              const meta = SIGNAL_META[t.signal] || SIGNAL_META.lapsed_visit;
              const Icon = meta.icon;
              const checked = selected.has(t.member_id);
              const hasExisting = !!t.existing_rescue_id;
              return (
                <div key={t.member_id}
                  className={`px-4 py-2.5 flex items-start gap-3 ${checked ? 'bg-rose-50/50 dark:bg-rose-950/10' : ''}`}
                  data-testid={`churn-target-${t.member_id}`}>
                  <input type="checkbox" checked={checked} disabled={hasExisting}
                    onChange={() => toggleSelect(t.member_id)}
                    className="mt-1 accent-rose-500 cursor-pointer disabled:cursor-not-allowed disabled:opacity-30"
                    data-testid={`churn-target-check-${t.member_id}`}/>
                  <div className={`flex-shrink-0 w-7 h-7 rounded-md ${meta.bg} flex items-center justify-center`}>
                    <Icon size={13} className={meta.color}/>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{t.full_name}</p>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${meta.bg} ${meta.color} font-semibold`}>
                        {t.signal_label}
                      </span>
                      {hasExisting && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 font-semibold">
                          {t.existing_rescue_status === 'pending_approval' ? 'In queue' :
                           t.existing_rescue_status === 'approved' ? 'Approved' :
                           t.existing_rescue_status === 'scheduled' ? 'Scheduled' : t.existing_rescue_status}
                        </span>
                      )}
                      {t.lifetime_value_gbp > 0 && (
                        <span className="text-[10px] text-zinc-500 dark:text-zinc-400">£{t.lifetime_value_gbp.toFixed(0)} LTV</span>
                      )}
                    </div>
                    <p className="text-xs text-zinc-600 dark:text-zinc-300 mt-0.5">{t.signal_evidence}</p>
                    <p className="text-[10px] text-zinc-400 dark:text-zinc-500 mt-0.5 truncate">
                      {t.email} · {t.tenure_days}d tenure
                      {t.last_class_name ? ` · loved ${t.last_class_name}` : ''}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Queue / review */}
      {queue.length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 overflow-hidden">
          <div className="px-4 py-2 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-2 bg-zinc-50/50 dark:bg-zinc-900/40 flex-wrap">
            <Inbox size={13} className="text-zinc-500"/>
            <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200">
              Approval queue ({queue.length})
            </p>
            <button onClick={approveBulk}
              disabled={!queue.some((q) => q.status === 'pending_approval')}
              className="ml-auto px-2.5 py-1 rounded-md text-[11px] font-medium bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-300 disabled:dark:bg-zinc-700 text-white flex items-center gap-1"
              data-testid="churn-approve-bulk">
              <Check size={11}/> Approve all pending
            </button>
          </div>
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800 max-h-[560px] overflow-y-auto">
            {queue.map((r) => (
              <RescueRow key={r.id} rescue={r}
                expanded={expanded === r.id}
                onToggleExpand={() => setExpanded(expanded === r.id ? null : r.id)}
                onApprove={() => approve(r.id, false)}
                onApproveNow={() => approve(r.id, true)}
                onReject={() => reject(r.id)}
                onRefine={() => refine(r.id)}
                refineText={refineText} setRefineText={setRefineText}
                refineBusy={refineBusyId === r.id}/>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};


const RescueRow = ({
  rescue, expanded, onToggleExpand, onApprove, onApproveNow, onReject,
  onRefine, refineText, setRefineText, refineBusy,
}) => {
  const meta = SIGNAL_META[rescue.signal] || SIGNAL_META.lapsed_visit;
  const Icon = meta.icon;
  const PrimaryIcon = CHANNEL_ICON[rescue.primary_channel] || Mail;
  const FallbackIcon = CHANNEL_ICON[rescue.fallback_channel] || Inbox;
  const statusMeta = {
    pending_approval: { color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-500/15', label: 'Pending approval' },
    approved:         { color: 'text-blue-600 dark:text-blue-400',   bg: 'bg-blue-500/15',  label: 'Approved' },
    scheduled:        { color: 'text-violet-600 dark:text-violet-400', bg: 'bg-violet-500/15', label: 'Scheduled' },
    sent:             { color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-500/15', label: 'Sent' },
    rejected:         { color: 'text-zinc-500',                       bg: 'bg-zinc-500/15',  label: 'Rejected' },
    send_failed:      { color: 'text-rose-600',                       bg: 'bg-rose-500/15',  label: 'Send failed' },
  }[rescue.status] || { color: 'text-zinc-500', bg: 'bg-zinc-500/15', label: rescue.status };

  return (
    <div className="px-4 py-3" data-testid={`churn-rescue-${rescue.id}`}>
      <div className="flex items-start gap-3">
        <button onClick={onToggleExpand}
          className="mt-0.5 text-zinc-400 hover:text-[var(--color-brand-blue)]"
          data-testid={`churn-rescue-toggle-${rescue.id}`}>
          {expanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
        </button>
        <div className={`flex-shrink-0 w-7 h-7 rounded-md ${meta.bg} flex items-center justify-center`}>
          <Icon size={13} className={meta.color}/>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{rescue.member_name}</p>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${statusMeta.bg} ${statusMeta.color} font-semibold`}>
              {statusMeta.label}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${meta.bg} ${meta.color}`}>
              {rescue.signal_label}
            </span>
            <span className="text-[10px] text-zinc-400 dark:text-zinc-500 inline-flex items-center gap-1">
              <PrimaryIcon size={9}/> {rescue.primary_channel}
              <span>→</span>
              <FallbackIcon size={9}/> {rescue.fallback_channel}
            </span>
            {rescue.scheduled_for && (
              <span className="text-[10px] text-violet-600 dark:text-violet-400 inline-flex items-center gap-1">
                <Clock size={9}/> {new Date(rescue.scheduled_for).toLocaleString()}
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-600 dark:text-zinc-300 mt-0.5 truncate">
            <strong>Subject:</strong> {rescue.copy?.email_subject || '—'}
          </p>
        </div>
        {rescue.status === 'pending_approval' && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <button onClick={onApprove}
              className="px-2 py-1 rounded-md text-[11px] font-medium bg-emerald-500 hover:bg-emerald-600 text-white flex items-center gap-1"
              title="Approve and schedule at the member's optimal window"
              data-testid={`churn-approve-${rescue.id}`}>
              <Check size={11}/> Approve
            </button>
            <button onClick={onApproveNow}
              className="px-2 py-1 rounded-md text-[11px] font-medium bg-blue-500 hover:bg-blue-600 text-white flex items-center gap-1"
              title="Approve and send within the next minute"
              data-testid={`churn-approve-now-${rescue.id}`}>
              <Send size={11}/> Send now
            </button>
            <button onClick={onReject}
              className="px-2 py-1 rounded-md text-[11px] font-medium border border-zinc-200 dark:border-zinc-700 hover:border-rose-500 hover:text-rose-500"
              data-testid={`churn-reject-${rescue.id}`}>
              <X size={11}/>
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="mt-3 ml-12 pl-4 border-l-2 border-zinc-100 dark:border-zinc-800 space-y-2">
          <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-3 bg-zinc-50/50 dark:bg-zinc-950/40">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400 mb-1">
              Detected evidence
            </p>
            <p className="text-xs text-zinc-700 dark:text-zinc-200 italic">{rescue.signal_evidence}</p>
            {rescue.primary_recommendation && (
              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 mt-1.5">
                <AlertTriangle size={9} className="inline mr-1 text-amber-500"/>
                Lever: {rescue.primary_recommendation}
              </p>
            )}
          </div>

          <RescueChannel kind="email" copy={rescue.copy}/>
          <RescueChannel kind="sms" copy={rescue.copy}/>
          <RescueChannel kind="push" copy={rescue.copy}/>
          <RescueChannel kind="in_app" copy={rescue.copy}/>

          {rescue.copy?.expected_lever && (
            <p className="text-[10px] text-zinc-500 dark:text-zinc-400 italic">
              <Sparkles size={9} className="inline mr-1 text-rose-500"/>
              Why this should work: {rescue.copy.expected_lever}
            </p>
          )}

          {rescue.status === 'pending_approval' && (
            <div className="flex gap-1.5 items-center pt-1">
              <Wand2 size={11} className="text-zinc-500 flex-shrink-0"/>
              <input value={refineText} onChange={(e) => setRefineText(e.target.value)}
                placeholder="Refine — e.g. 'shorter', 'warmer', 'remove the discount'"
                className="flex-1 px-2 py-1 border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 rounded-md text-xs"
                onKeyDown={(e) => e.key === 'Enter' && onRefine()}
                disabled={refineBusy}
                data-testid={`churn-refine-input-${rescue.id}`}/>
              <button onClick={onRefine} disabled={refineBusy || !refineText.trim()}
                className="px-2 py-1 rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-alt2)] disabled:bg-zinc-300 disabled:dark:bg-zinc-700 text-white text-[11px] font-medium flex items-center gap-1"
                data-testid={`churn-refine-btn-${rescue.id}`}>
                {refineBusy ? <Loader2 size={10} className="animate-spin"/> : <RefreshCw size={10}/>}
                Refine
              </button>
            </div>
          )}

          {rescue.delivered_via && rescue.delivered_via.length > 0 && (
            <p className="text-[10px] text-emerald-600 dark:text-emerald-400">
              <Check size={9} className="inline mr-1"/> Delivered via: {rescue.delivered_via.join(', ')}
            </p>
          )}
          {rescue.send_failed_reason && (
            <p className="text-[10px] text-rose-500">
              <AlertTriangle size={9} className="inline mr-1"/> {rescue.send_failed_reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
};


const RescueChannel = ({ kind, copy }) => {
  if (!copy) return null;
  const Icon = CHANNEL_ICON[kind] || Mail;
  if (kind === 'email') {
    return (
      <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2.5 bg-white dark:bg-zinc-900">
        <div className="flex items-center gap-1.5 mb-1">
          <Icon size={11} className="text-blue-500"/>
          <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400">Email</p>
        </div>
        <p className="text-xs"><strong>Subject:</strong> {copy.email_subject || '—'}</p>
        {copy.email_preheader && <p className="text-[11px] text-zinc-500 italic">Preview: {copy.email_preheader}</p>}
        {copy.email_body_html && (
          <div className="mt-1 rounded-md border border-zinc-100 dark:border-zinc-800 p-2 bg-zinc-50/50 dark:bg-zinc-950 prose prose-sm dark:prose-invert max-w-none text-xs"
            dangerouslySetInnerHTML={{ __html: copy.email_body_html }}/>
        )}
      </div>
    );
  }
  if (kind === 'sms' && copy.sms_body) {
    return (
      <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2.5 bg-white dark:bg-zinc-900">
        <div className="flex items-center gap-1.5 mb-1">
          <Icon size={11} className="text-emerald-500"/>
          <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400">SMS</p>
          <span className="text-[10px] text-zinc-400">{(copy.sms_body || '').length}/160</span>
        </div>
        <p className="text-xs font-mono text-zinc-700 dark:text-zinc-200">{copy.sms_body}</p>
      </div>
    );
  }
  if (kind === 'push' && (copy.push_title || copy.push_body)) {
    return (
      <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2.5 bg-white dark:bg-zinc-900">
        <div className="flex items-center gap-1.5 mb-1">
          <Icon size={11} className="text-amber-500"/>
          <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400">Push</p>
        </div>
        <p className="text-xs font-semibold text-zinc-900 dark:text-zinc-100">{copy.push_title}</p>
        <p className="text-xs text-zinc-600 dark:text-zinc-300">{copy.push_body}</p>
      </div>
    );
  }
  if (kind === 'in_app' && copy.in_app_message) {
    return (
      <div className="rounded-md border border-zinc-200 dark:border-zinc-700 p-2.5 bg-white dark:bg-zinc-900">
        <div className="flex items-center gap-1.5 mb-1">
          <Icon size={11} className="text-violet-500"/>
          <p className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500 dark:text-zinc-400">In-app</p>
        </div>
        <p className="text-xs text-zinc-700 dark:text-zinc-200">{copy.in_app_message}</p>
      </div>
    );
  }
  return null;
};


export default ChurnRescuePanel;
