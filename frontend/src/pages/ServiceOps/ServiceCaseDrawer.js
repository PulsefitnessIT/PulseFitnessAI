/**
 * ServiceCaseDrawer — iter 215dx (Phase 1 + Polish).
 *
 * Right-slide drawer showing the full case record, refreshed to use
 * the shared `_serviceops.css` design layer (gradient header, glassy
 * backdrop, premium tabs/inputs/timeline, full light/dark support).
 *
 * Body tabs: Timeline · Details · Customer
 * Footer: state-machine transitions (legal next states only),
 * inline save for edits.
 *
 * Backed by:
 *   GET    /api/svc/cases/{id}
 *   PUT    /api/svc/cases/{id}
 *   POST   /api/svc/cases/{id}/notes
 *   POST   /api/svc/cases/{id}/transition
 *   POST   /api/svc/ai/summarise/{id}
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  X, Loader2, Clock, AlertTriangle, MapPin, Phone, Mail, User as UserIcon,
  Wrench, Activity, Save, Send, ChevronRight, Sparkles, CheckCircle2, History, Bell,
  FileText, Link as LinkIcon, RefreshCw, Briefcase, Award, TrendingUp, Route,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import CoverageBanner from '@/components/shared/CoverageBanner';
import ServiceCaseLifecycleTab from './ServiceCaseLifecycleTab';
import './_serviceops.css';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

// Mirrors backend utils/svc_state.py — keep in sync.
const TRANSITIONS = {
  new: ['triaged', 'assigned', 'rejected'],
  triaged: ['assigned', 'rejected'],
  assigned: ['en_route', 'on_site', 'rejected'],
  en_route: ['on_site', 'assigned'],
  on_site: ['paused_parts', 'paused_customer', 'repaired', 'awaiting_sign_off', 'closed'],
  paused_parts: ['on_site', 'assigned', 'repaired'],
  paused_customer: ['on_site', 'assigned', 'repaired'],
  repaired: ['awaiting_sign_off', 'closed'],
  awaiting_sign_off: ['closed', 'on_site'],
  closed: ['invoiced'],
  invoiced: [],
  rejected: [],
};

const STATUS_LABEL = {
  new: 'New', triaged: 'Triaged', assigned: 'Assigned', en_route: 'En route',
  on_site: 'On site', paused_parts: 'Waiting parts', paused_customer: 'Waiting customer',
  repaired: 'Repaired', awaiting_sign_off: 'Awaiting sign-off', closed: 'Closed',
  invoiced: 'Invoiced', rejected: 'Rejected',
};
// i18n: translated status label (falls back to English map)
const statusLabel = (t, s) => t(`service.cd_status_${s}`, STATUS_LABEL[s] || s);

const PRIORITY_META = {
  p1: { label: 'P1 · Critical', tone: 'p1' },
  p2: { label: 'P2 · High', tone: 'p2' },
  p3: { label: 'P3 · Standard', tone: 'p3' },
  p4: { label: 'P4 · Low', tone: 'p4' },
};
const priorityLabel = (t, p) => t(`service.cd_prio_${p}`, PRIORITY_META[p]?.label || p);

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function relativeFromNow(iso, t) {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const mins = Math.floor(abs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const sign = ms < 0 ? (t ? `${t('service.cd_overdue', 'overdue')} ` : 'overdue ') : '';
  if (days >= 1) return `${sign}${days}d ${hours % 24}h`;
  if (hours >= 1) return `${sign}${hours}h ${mins % 60}m`;
  return `${sign}${mins}m`;
}

function SLABadge({ resolveAt }) {
  const { t } = useTranslation();
  if (!resolveAt) return null;
  const ms = new Date(resolveAt).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  const tone = breached ? 'danger' : atRisk ? 'warn' : 'good';
  const label = breached ? t('service.cd_sla_breached', 'SLA breached') : atRisk ? t('service.cd_sla_at_risk', 'SLA at risk') : t('service.cd_sla_on_track', 'SLA on track');
  const Icon = breached ? AlertTriangle : tone === 'warn' ? AlertTriangle : Clock;
  return (
    <span className={`svc-pill svc-pill--${tone}`} data-testid="drawer-sla-badge">
      <Icon size={11} /> {label} · {relativeFromNow(resolveAt, t)}
    </span>
  );
}

function TabButton({ id, label, icon: Icon, active, onClick, count }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`svc-tab ${active ? 'svc-tab--active' : ''}`}
      style={{ flex: 1, justifyContent: 'center' }}
      data-testid={`drawer-tab-${id}`}
    >
      <Icon size={13} /> {label}
      {typeof count === 'number' ? <span className="svc-muted">({count})</span> : null}
    </button>
  );
}

function CrmContextCard({ caseId }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    axios.get(`${API}/svc/cases/${caseId}/crm-context`, auth())
      .then((r) => { if (alive) setData(r.data); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [caseId]);

  if (loading) {
    return <div className="svc-card" style={{ padding: 14 }} data-testid="drawer-crm-context-loading"><Loader2 size={15} className="animate-spin" /></div>;
  }
  if (!data || !data.linked) {
    return (
      <div className="svc-card" style={{ padding: 12 }} data-testid="drawer-crm-context-unlinked">
        <div className="inline-flex items-center gap-1.5 svc-muted text-xs"><Briefcase size={12} /> {t('service.cd_crm_unlinked', 'Not linked to a CRM account yet.')}</div>
      </div>
    );
  }
  const gbp = (n) => `£${Number(n || 0).toLocaleString('en-GB')}`;
  return (
    <div className="svc-card" style={{ padding: 14 }} data-testid="drawer-crm-context">
      <div className="flex items-center justify-between mb-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold"><Briefcase size={13} /> {t('service.cd_sales_context', 'Sales context (CRM)')}</span>
        <a href={`/crm`} className="svc-link text-[11px]" data-testid="drawer-crm-open">{t('service.cd_open_crm', 'Open in CRM')}</a>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div><span className="svc-muted">{t('service.cd_account_owner', 'Account owner')}</span><div className="font-medium" data-testid="drawer-crm-owner">{data.account_owner || '—'}</div></div>
        <div><span className="svc-muted">{t('service.cd_contract_tier', 'Contract tier')}</span><div className="font-medium inline-flex items-center gap-1" data-testid="drawer-crm-tier"><Award size={11} />{data.contract_tier || '—'}</div></div>
        <div><span className="svc-muted">{t('service.cd_open_deals', 'Open deals')}</span><div className="font-medium" data-testid="drawer-crm-open-deals">{data.open_deal_count} · {gbp(data.open_pipeline_value)}</div></div>
        <div><span className="svc-muted">{t('service.cd_won_revenue', 'Won revenue')}</span><div className="font-medium inline-flex items-center gap-1"><TrendingUp size={11} />{gbp(data.won_revenue)}</div></div>
      </div>
      {data.active_contract?.contract_number ? (
        <div className="text-[11px] svc-muted mt-2">{t('service.cd_active_contract', 'Active contract {{num}}', { num: data.active_contract.contract_number })}{data.active_contract.end_date ? ` · ${t('service.cd_ends', 'ends')} ${new Date(data.active_contract.end_date).toLocaleDateString('en-GB')}` : ''}</div>
      ) : null}
      {(data.open_deals || []).length > 0 ? (
        <div className="mt-2 space-y-1" data-testid="drawer-crm-deal-list">
          {data.open_deals.map((d) => (
            <div key={d.id} className="flex items-center justify-between text-[11px] border-t pt-1" style={{ borderColor: 'var(--svc-border, #e5e7eb)' }}>
              <span className="truncate">{d.name || 'Deal'}</span>
              <span className="svc-muted whitespace-nowrap">{(d.stage || '').replace(/_/g, ' ')} · {gbp(d.value)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const TIMELINE_KIND = (type) => {
  if (type === 'state_change') return 'state';
  if (type === 'note') return 'note';
  if (type === 'comm') return 'comm';
  if (type === 'intake') return 'intake';
  return '';
};

export default function ServiceCaseDrawer({ caseId, onClose, onChanged }) {
  const { t } = useTranslation();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('timeline');
  const [note, setNote] = useState('');
  const [edits, setEdits] = useState({});
  const [transitionReason, setTransitionReason] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiSummary, setAiSummary] = useState(null);
  const [commsLog, setCommsLog] = useState([]);
  const [commsLoading, setCommsLoading] = useState(false);
  const [commsTemplates, setCommsTemplates] = useState([]);
  const [commsTemplateKey, setCommsTemplateKey] = useState('case_logged');
  const [commsSending, setCommsSending] = useState(false);

  const runSummary = async () => {
    if (!caseId) return;
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/svc/ai/summarise/${caseId}`, {}, auth());
      if (r.data?.ok) setAiSummary(r.data);
      else notify.error(t('service.cd_ai_unavailable', 'AI summary unavailable'), r.data?.error || t('service.cd_try_again', 'Try again'));
    } catch (e) {
      notify.error(t('service.cd_ai_failed', 'AI summary failed'), e?.response?.data?.detail || e.message);
    } finally { setAiBusy(false); }
  };

  const load = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/cases/${caseId}`, auth());
      setDoc(r.data);
      setEdits({});
    } catch (e) {
      notify.error(t('service.cd_load_case_failed', 'Failed to load case'), e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  // Esc closes the drawer.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const events = doc?.events || [];
  const merged = useMemo(() => ({ ...(doc || {}), ...edits }), [doc, edits]);
  const dirty = Object.keys(edits).length > 0;
  const legalNext = TRANSITIONS[merged?.status] || [];
  const pri = PRIORITY_META[merged?.priority] || PRIORITY_META.p3;

  const setEdit = (k, v) => setEdits((e) => ({ ...e, [k]: v }));

  const saveEdits = async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      const r = await axios.put(`${API}/svc/cases/${caseId}`, edits, auth());
      setDoc((d) => ({ ...d, ...r.data, events: d?.events || [] }));
      setEdits({});
      notify.success(t('service.cd_case_updated', 'Case updated'));
      await load();
      onChanged?.();
    } catch (e) {
      notify.error(t('service.cd_save_failed', 'Failed to save'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const submitNote = async () => {
    const body = note.trim();
    if (!body) return;
    setSaving(true);
    try {
      await axios.post(`${API}/svc/cases/${caseId}/notes`, { body, visibility: 'internal' }, auth());
      setNote('');
      await load();
      notify.success(t('service.cd_note_added', 'Note added'));
    } catch (e) {
      notify.error(t('service.cd_note_failed', 'Failed to add note'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const loadComms = useCallback(async () => {
    if (!caseId) return;
    setCommsLoading(true);
    try {
      const [logResp, tplResp] = await Promise.all([
        axios.get(`${API}/svc/comms/log`, { ...auth(), params: { case_id: caseId, limit: 50 } }),
        commsTemplates.length === 0
          ? axios.get(`${API}/svc/comms/templates`, auth()).catch(() => ({ data: { templates: [] } }))
          : Promise.resolve({ data: { templates: commsTemplates } }),
      ]);
      setCommsLog(logResp.data?.events || []);
      const tpl = tplResp.data?.templates || [];
      if (tpl.length && commsTemplates.length === 0) {
        setCommsTemplates(tpl.filter((t) => t.audience === 'customer'));
      }
    } catch (e) {
      notify.error(t('service.cd_comms_failed', 'Failed to load comms'), e?.response?.data?.detail || e.message);
    } finally { setCommsLoading(false); }
  }, [caseId, commsTemplates]);

  useEffect(() => {
    if (tab === 'comms') loadComms();
  }, [tab, loadComms]);

  const sendCustomerEmail = async () => {
    if (!caseId || !commsTemplateKey) return;
    if (!doc?.customer_email) {
      notify.error(t('service.cd_no_email', 'No customer email'), t('service.cd_no_email_hint', 'Set a customer email on the Customer tab first.'));
      return;
    }
    setCommsSending(true);
    try {
      const r = await axios.post(
        `${API}/svc/comms/case/${caseId}/notify`,
        { template_key: commsTemplateKey },
        auth(),
      );
      if (r.data?.ok) {
        notify.success(t('service.cd_email_sent', 'Email sent'), `${doc.customer_email}`);
      } else {
        notify.error(t('service.cd_email_failed', 'Email send failed'), r.data?.log?.error || t('service.cd_provider_rejected', 'Provider rejected the request'));
      }
      await loadComms();
      await load();
    } catch (e) {
      notify.error(t('service.cd_send_failed', 'Send failed'), e?.response?.data?.detail || e.message);
    } finally { setCommsSending(false); }
  };

  const toggleAutoNotify = async () => {
    const next = !(doc?.comms_auto_notify !== false);
    try {
      await axios.put(`${API}/svc/cases/${caseId}`, { comms_auto_notify: next }, auth());
      await load();
    } catch (e) {
      notify.error(t('service.cd_update_failed', 'Failed to update'), e?.response?.data?.detail || e.message);
    }
  };

  // Iter 216h82 — Service Report PDF + email (operator-side fast-path)
  const [reportBusy, setReportBusy] = useState('');
  const openServiceReport = () => {
    if (!caseId) return;
    fetch(`${API}/svc/cases/${caseId}/service-report.pdf`, auth())
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank', 'noopener');
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      })
      .catch((e) => notify.error(t('service.cd_open_report_failed', 'Could not open report'), e.message || String(e)));
  };
  const emailServiceReport = async () => {
    if (!caseId || reportBusy) return;
    const defaultTo = doc?.customer_email || '';
    const to = window.prompt(t('service.cd_report_to', 'Send the service report to which email?'), defaultTo);
    if (!to) return;
    const note = window.prompt(t('service.cd_short_note', 'Add a short note (optional)'), '') || '';
    setReportBusy('email');
    try {
      const r = await axios.post(
        `${API}/svc/cases/${caseId}/service-report/email`,
        { to, note },
        auth(),
      );
      notify.success(t('service.cd_report_emailed', 'Report emailed'), t('service.cd_sent_to', 'Sent to {{to}}', { to: r.data?.to || to }));
      await load();
    } catch (e) {
      notify.error(t('service.cd_report_send_failed', 'Could not send report'), e?.response?.data?.detail || e.message);
    } finally { setReportBusy(''); }
  };

  // Iter 216h83 — Customer Live Tracking link (Uber-style share)
  const [trackingUrl, setTrackingUrl] = useState('');
  const copyTrackingLink = async () => {
    if (!caseId) return;
    try {
      const r = await axios.get(`${API}/svc/cases/${caseId}/tracking-link`, auth());
      const url = r.data?.url || '';
      setTrackingUrl(url);
      try {
        await navigator.clipboard.writeText(url);
        notify.success(t('service.cd_track_copied', 'Tracking link copied'), t('service.cd_track_copied_hint', 'Paste into SMS / WhatsApp / email for the customer.'));
      } catch {
        window.prompt(t('service.cd_copy_link', 'Copy the link below and share with the customer:'), url);
      }
    } catch (e) {
      notify.error(t('service.cd_track_gen_failed', 'Could not generate tracking link'), e?.response?.data?.detail || e.message);
    }
  };
  const regenerateTrackingLink = async () => {
    if (!caseId) return;
    if (!window.confirm(t('service.cd_regen_confirm', 'Regenerate the tracking link? The previous link will stop working.'))) return;
    try {
      const r = await axios.post(`${API}/svc/cases/${caseId}/tracking-link/regenerate`, {}, auth());
      const url = r.data?.url || '';
      setTrackingUrl(url);
      try {
        await navigator.clipboard.writeText(url);
        notify.success(t('service.cd_new_track_copied', 'New tracking link copied'), t('service.cd_old_link_invalid', 'Old link is now invalid.'));
      } catch {
        window.prompt(t('service.cd_copy_new_link', 'Copy the new link:'), url);
      }
    } catch (e) {
      notify.error(t('service.cd_regen_failed', 'Could not regenerate'), e?.response?.data?.detail || e.message);
    }
  };

  // Iter 216h81 — Customer rating prompt at case sign-off. When the
  // customer closes a case, surface a star rating prompt BEFORE the
  // transition fires so they can't miss it.
  const [ratingTarget, setRatingTarget] = useState(null); // pending status target
  const [rating, setRating] = useState(0);
  const [ratingComment, setRatingComment] = useState('');
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  // If a rating already exists on the case, don't re-prompt.
  const existingRating = merged?.customer_rating;

  const doTransition = async (target) => {
    // Closing/sign-off path → prompt for rating if engineer is assigned
    // and no rating recorded yet.
    if (
      (target === 'closed' || target === 'invoiced')
      && merged?.assigned_engineer_id
      && !existingRating
      && ratingTarget !== target  // already shown
    ) {
      setRatingTarget(target);
      return;
    }
    setSaving(true);
    try {
      await axios.post(
        `${API}/svc/cases/${caseId}/transition`,
        { to: target, reason: transitionReason || '' },
        auth(),
      );
      setTransitionReason('');
      notify.success(t('service.cd_moved_to', 'Moved to {{status}}', { status: statusLabel(t, target) }));
      await load();
      onChanged?.();
    } catch (e) {
      notify.error(t('service.cd_transition_rejected', 'Transition rejected'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const submitRatingAndTransition = async () => {
    if (!ratingTarget) return;
    setRatingSubmitting(true);
    try {
      // 1) Write the rating (and optional comment) onto the case
      if (rating > 0) {
        await axios.put(`${API}/svc/cases/${caseId}`, {
          customer_rating: rating,
          customer_rating_comment: ratingComment.trim() || undefined,
        }, auth());
      }
      // 2) Then perform the transition
      await axios.post(
        `${API}/svc/cases/${caseId}/transition`,
        { to: ratingTarget, reason: transitionReason || '' },
        auth(),
      );
      setTransitionReason('');
      const tgt = ratingTarget;
      setRatingTarget(null); setRating(0); setRatingComment('');
      notify.success(rating > 0 ? t('service.cd_closed_rating', 'Closed · thanks for rating {{n}} stars', { n: rating }) : t('service.cd_moved_to', 'Moved to {{status}}', { status: statusLabel(t, tgt) }));
      await load();
      onChanged?.();
    } catch (e) {
      notify.error(t('service.cd_close_failed', 'Could not close'), e?.response?.data?.detail || e.message);
    } finally { setRatingSubmitting(false); }
  };

  const skipRatingAndTransition = async () => {
    if (!ratingTarget) return;
    setRating(0); setRatingComment('');
    const tgt = ratingTarget;
    setRatingTarget(null);
    // Re-enter doTransition with no rating; the guard checks `ratingTarget !== target`
    // so we briefly hold this in a local then call the API directly.
    setSaving(true);
    try {
      await axios.post(
        `${API}/svc/cases/${caseId}/transition`,
        { to: tgt, reason: transitionReason || '' },
        auth(),
      );
      setTransitionReason('');
      notify.success(t('service.cd_moved_to', 'Moved to {{status}}', { status: statusLabel(t, tgt) }));
      await load();
      onChanged?.();
    } catch (e) {
      notify.error(t('service.cd_transition_rejected', 'Transition rejected'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const drawer = (
    <div
      className="svc-drawer-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      data-testid="case-drawer"
    >
      <aside
        className="svc-drawer"
        role="dialog"
        aria-label={t('service.cd_case_detail', 'Service case detail')}
        style={{ maxWidth: 720 }}
      >
        {/* Header */}
        <header className="svc-drawer-head">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="svc-eyebrow">{merged?.reference || t('service.cd_loading', 'Loading…')}</p>
              <h2 className="svc-h1" style={{ fontSize: 19, marginTop: 2 }} data-testid="drawer-title">
                {merged?.title || (loading ? '…' : t('service.cd_untitled', 'Untitled case'))}
              </h2>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <span className={`svc-pill svc-pill--${pri.tone === 'p1' ? 'danger' : pri.tone === 'p2' ? 'warn' : pri.tone === 'p3' ? 'info' : ''}`} data-testid="drawer-priority">
                  {priorityLabel(t, merged?.priority)}
                </span>
                <span className="svc-pill" data-testid="drawer-status">
                  {statusLabel(t, merged?.status) || merged?.status || '—'}
                </span>
                <SLABadge resolveAt={merged?.sla_resolve_at} />
                {merged?.customer_po_number ? (
                  <span
                    className="svc-pill inline-flex items-center gap-1"
                    style={{ background: '#ecfeff', color: '#0e7490', fontWeight: 700 }}
                    title={t('service.cd_po_title', "Customer PO / reference — links this chargeable job to the customer's purchase order")}
                    data-testid="drawer-customer-po">
                    PO / Ref: {merged.customer_po_number}
                  </span>
                ) : null}
                {existingRating ? (
                  <span
                    className="svc-pill inline-flex items-center gap-0.5"
                    style={{ background: '#fef3c7', color: '#92400e', fontWeight: 700 }}
                    title={merged?.customer_rating_comment || t('service.cd_rated_title', 'Customer rated this case {{n}}/5', { n: existingRating })}
                    data-testid="drawer-customer-rating">
                    <span style={{ color: '#f59e0b' }}>★</span> {existingRating}/5
                  </span>
                ) : null}
              </div>
            </div>
            <button type="button" onClick={onClose} aria-label={t('service.cd_close', 'Close')} data-testid="drawer-close" className="svc-icon-btn">
              <X size={16} />
            </button>
          </div>
        </header>

        {/* Tabs */}
        <div className="svc-tabs" style={{ margin: 0, padding: '0 18px' }}>
          <TabButton id="timeline" label={t('service.cd_tab_timeline', 'Timeline')} icon={Activity} active={tab === 'timeline'} onClick={() => setTab('timeline')} count={events.length} />
          <TabButton id="details" label={t('service.cd_tab_details', 'Details')} icon={Wrench} active={tab === 'details'} onClick={() => setTab('details')} />
          <TabButton id="customer" label={t('service.cd_tab_customer', 'Customer')} icon={UserIcon} active={tab === 'customer'} onClick={() => setTab('customer')} />
          <TabButton id="comms" label={t('service.cd_tab_comms', 'Comms')} icon={Bell} active={tab === 'comms'} onClick={() => setTab('comms')} />
          <TabButton id="lifecycle" label={t('service.cd_tab_lifecycle', 'Lifecycle')} icon={Route} active={tab === 'lifecycle'} onClick={() => setTab('lifecycle')} />
        </div>

        {/* Body */}
        <div className="svc-drawer-body space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm svc-muted"><Loader2 size={14} className="animate-spin" /> {t('service.cd_loading_case', 'Loading case…')}</div>
          ) : tab === 'timeline' ? (
            <>
              {/* AI summary */}
              <div className="svc-ai-block" data-testid="drawer-ai-summary-block">
                <div className="flex items-center justify-between gap-2">
                  <p className="svc-ai-eyebrow"><Sparkles size={11} /> AI summary</p>
                  <button
                    type="button"
                    onClick={runSummary}
                    disabled={aiBusy}
                    className="svc-btn svc-btn-primary svc-btn-sm"
                    data-testid="drawer-ai-summary-run"
                  >
                    {aiBusy ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                    {aiBusy ? '…' : aiSummary ? t('service.cd_refresh', 'Refresh') : t('service.cd_generate', 'Generate')}
                  </button>
                </div>
                {aiSummary ? (
                  <div className="space-y-2 text-xs mt-2">
                    <div>
                      <p className="svc-label" style={{ marginBottom: 2 }}>{t('service.cd_for_customer', 'For the customer')}</p>
                      <p data-testid="drawer-ai-customer-summary" style={{ lineHeight: 1.55 }}>{aiSummary.customer_summary}</p>
                    </div>
                    {aiSummary.engineer_summary ? (
                      <div>
                        <p className="svc-label" style={{ marginBottom: 2 }}>{t('service.cd_for_engineer', 'For the engineer')}</p>
                        <p data-testid="drawer-ai-engineer-summary" style={{ lineHeight: 1.55 }}>{aiSummary.engineer_summary}</p>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-[11.5px] svc-muted mt-2">{t('service.cd_ai_summary_hint', 'One-click summary of every event so far — one for the customer, one for the engineer.')}</p>
                )}
              </div>

              {/* Add note */}
              <div className="svc-card-base p-3">
                <p className="svc-label">{t('service.cd_add_note', 'Add internal note')}</p>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  placeholder={t('service.cd_note_ph', 'Customer called back to confirm engineer access…')}
                  className="svc-textarea"
                  style={{ fontFamily: 'inherit', fontSize: 13 }}
                  data-testid="drawer-note-input"
                />
                <div className="flex justify-end mt-2">
                  <button
                    type="button"
                    disabled={!note.trim() || saving}
                    onClick={submitNote}
                    className="svc-btn svc-btn-primary svc-btn-sm"
                    data-testid="drawer-note-submit"
                  >
                    <Send size={11} /> {t('service.cd_add_note_btn', 'Add note')}
                  </button>
                </div>
              </div>

              {/* Timeline */}
              <ol className="svc-timeline" data-testid="drawer-timeline">
                {events.length === 0 ? (
                  <li className="text-sm svc-muted">{t('service.cd_no_events', 'No timeline events yet.')}</li>
                ) : events.map((ev) => {
                  const kind = TIMELINE_KIND(ev.type);
                  return (
                    <li key={ev.id} className={kind ? `svc-tl--${kind}` : ''}>
                      <p className="svc-tl-meta">
                        {ev.type === 'state_change'
                          ? `${statusLabel(t, ev.from_state)} → ${statusLabel(t, ev.to_state)}`
                          : ev.type}
                        <span className="svc-tl-meta-time"> · {fmtDate(ev.at)}{ev.actor_name ? ` · ${ev.actor_name}` : ''}</span>
                      </p>
                      {ev.body ? <p className="svc-tl-body">{ev.body}</p> : null}
                      {ev.reason ? <p className="svc-tl-reason">{t('service.cd_reason', 'Reason:')} {ev.reason}</p> : null}
                    </li>
                  );
                })}
              </ol>
            </>
          ) : tab === 'details' ? (
            <>
              {/* Iter 216h205 — coverage banner derived from
                 source_meta.coverage_* stamped by the issue intake
                 (iter h199). Tells the operator at a glance whether
                 this case is under contract, in warranty or
                 chargeable, BEFORE they edit cover_type below. */}
              {(merged.source_meta?.coverage_status || merged.cover_type) && (
                <div className="mb-3" data-testid="case-coverage-section">
                  <CoverageBanner
                    coverage={merged.source_meta || {
                      coverage_status:
                        merged.cover_type === 'contract' ? 'covered_contract'
                        : merged.cover_type === 'warranty' ? 'covered_warranty'
                        : 'uncovered',
                    }}
                    testid="case-coverage"
                  />
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label={t('service.cd_f_title', 'Title')}>
                  <input value={merged.title || ''} onChange={(e) => setEdit('title', e.target.value)} className="svc-input" data-testid="drawer-edit-title" />
                </Field>
                <Field label={t('service.cd_f_priority', 'Priority')}>
                  <select value={merged.priority || 'p3'} onChange={(e) => setEdit('priority', e.target.value)} className="svc-select" data-testid="drawer-edit-priority">
                    <option value="p1">{t('service.cd_prio_p1', 'P1 · Critical')}</option>
                    <option value="p2">{t('service.cd_prio_p2', 'P2 · High')}</option>
                    <option value="p3">{t('service.cd_prio_p3', 'P3 · Standard')}</option>
                    <option value="p4">{t('service.cd_prio_p4', 'P4 · Low')}</option>
                  </select>
                </Field>
                <Field label={t('service.cd_f_site', 'Site')}>
                  <input value={merged.site_name || ''} onChange={(e) => setEdit('site_name', e.target.value)} className="svc-input" data-testid="drawer-edit-site" />
              </Field>
              <Field label={t('service.cd_f_asset', 'Asset')}>
                <input value={merged.asset_name || ''} onChange={(e) => setEdit('asset_name', e.target.value)} className="svc-input" data-testid="drawer-edit-asset" />
              </Field>
              <Field label={t('service.cd_f_fault', 'Fault code')}>
                <input value={merged.fault_code || ''} onChange={(e) => setEdit('fault_code', e.target.value)} className="svc-input" data-testid="drawer-edit-fault" />
              </Field>
              <Field label={t('service.cd_f_case_type', 'Case type')}>
                <select value={merged.case_type || ''} onChange={(e) => setEdit('case_type', e.target.value)} className="svc-select" data-testid="drawer-edit-case-type">
                  <option value="">—</option>
                  <option value="repair">{t('service.cd_type_repair', 'Repair')}</option>
                  <option value="ppm">{t('service.cd_type_ppm', 'PPM')}</option>
                  <option value="install">{t('service.cd_type_install', 'Install')}</option>
                </select>
              </Field>
              <Field label={t('service.cd_f_cover', 'Cover type')}>
                <select value={merged.cover_type || ''} onChange={(e) => setEdit('cover_type', e.target.value)} className="svc-select" data-testid="drawer-edit-cover">
                  <option value="">—</option>
                  <option value="contract">{t('service.cd_cover_contract', 'Contract')}</option>
                  <option value="warranty">{t('service.cd_cover_warranty', 'Warranty')}</option>
                  <option value="chargeable">{t('service.cd_cover_chargeable', 'Chargeable')}</option>
                </select>
              </Field>
              <Field label={t('service.cd_f_engineer', 'Engineer')}>
                <input
                  value={merged.assigned_engineer_name || ''}
                  onChange={(e) => setEdit('assigned_engineer_name', e.target.value)}
                  placeholder={t('service.cd_unassigned', 'Unassigned')}
                  className="svc-input"
                  data-testid="drawer-edit-engineer"
                />
              </Field>
              <Field label={t('service.cd_f_est_minutes', 'Estimated minutes')}>
                <input
                  type="number"
                  value={merged.estimated_minutes || 0}
                  onChange={(e) => setEdit('estimated_minutes', Number(e.target.value))}
                  className="svc-input"
                  data-testid="drawer-edit-est"
                />
              </Field>
              <div className="sm:col-span-2">
                <Field label={t('service.cd_f_description', 'Description')}>
                  <textarea
                    value={merged.description || ''}
                    onChange={(e) => setEdit('description', e.target.value)}
                    rows={4}
                    className="svc-textarea"
                    style={{ fontFamily: 'inherit', fontSize: 13 }}
                    data-testid="drawer-edit-description"
                  />
                </Field>
              </div>
              <div className="sm:col-span-2 grid grid-cols-2 gap-3 text-xs svc-muted">
                <p>{t('service.cd_logged', 'Logged:')} {fmtDate(doc?.created_at)}{doc?.logged_by_name ? ` · ${doc.logged_by_name}` : ''}</p>
                <p>{t('service.cd_sla_respond_by', 'SLA respond by:')} {fmtDate(doc?.sla_response_at)}</p>
                <p>{t('service.cd_source', 'Source:')} {doc?.source || '—'}</p>
                <p>{t('service.cd_sla_resolve_by', 'SLA resolve by:')} {fmtDate(doc?.sla_resolve_at)}</p>
              </div>
            </div>
            </>
          ) : tab === 'customer' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label={t('service.cd_f_customer_name', 'Customer name')}>
                <input value={merged.customer_name || ''} onChange={(e) => setEdit('customer_name', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-name" />
              </Field>
              <Field label={t('service.cd_f_phone', 'Phone')}>
                <input value={merged.customer_phone || ''} onChange={(e) => setEdit('customer_phone', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-phone" />
              </Field>
              <Field label={t('service.cd_f_email', 'Email')}>
                <input value={merged.customer_email || ''} onChange={(e) => setEdit('customer_email', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-email" />
              </Field>
              <Field label={t('service.cd_f_site', 'Site')}>
                <input value={merged.site_name || ''} onChange={(e) => setEdit('site_name', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-site" />
              </Field>
              <div className="sm:col-span-2 flex flex-wrap gap-3 text-xs pt-1">
                {merged.customer_phone ? <a href={`tel:${merged.customer_phone}`} className="svc-link inline-flex items-center gap-1"><Phone size={11} /> {t('service.cd_call', 'Call')}</a> : null}
                {merged.customer_email ? <a href={`mailto:${merged.customer_email}`} className="svc-link inline-flex items-center gap-1"><Mail size={11} /> {t('service.cd_email', 'Email')}</a> : null}
                {merged.site_name ? <span className="inline-flex items-center gap-1 svc-muted"><MapPin size={11} /> {merged.site_name}</span> : null}
              </div>
              <div className="sm:col-span-2"><CrmContextCard caseId={caseId} /></div>
            </div>
          ) : tab === 'lifecycle' ? (
            <ServiceCaseLifecycleTab caseId={caseId} onNavigate={setTab} />
          ) : (
            <CommsTab
              doc={doc}
              commsLog={commsLog}
              commsLoading={commsLoading}
              templates={commsTemplates}
              templateKey={commsTemplateKey}
              setTemplateKey={setCommsTemplateKey}
              onSend={sendCustomerEmail}
              sending={commsSending}
              autoNotify={doc?.comms_auto_notify !== false}
              onToggleAutoNotify={toggleAutoNotify}
              onRefresh={loadComms}
            />
          )}
        </div>

        {/* Footer — transitions + save */}
        <footer className="svc-drawer-foot space-y-2">
          {tab !== 'timeline' && dirty ? (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={saveEdits}
                disabled={saving}
                className="svc-btn svc-btn-primary svc-btn-sm"
                data-testid="drawer-save"
              >
                <Save size={11} /> {t('service.cd_save_changes', 'Save changes')}
              </button>
            </div>
          ) : null}
          {/* Iter 216h83 — Customer Live Tracking link share */}
          <div
            className="rounded-lg border p-2 flex items-center gap-2 flex-wrap"
            style={{ borderColor: 'var(--theme-border, #e5e7eb)' }}
            data-testid="drawer-tracking-link-row"
          >
            <LinkIcon size={13} className="opacity-70" />
            <span className="text-[11.5px] font-semibold">{t('service.cd_customer_tracking', 'Customer tracking')}</span>
            {trackingUrl ? (
              <span
                className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                style={{ background: '#dbeafe', color: '#0891b2' }}
                data-testid="drawer-tracking-link-active"
              >
                Link active
              </span>
            ) : null}
            <div className="ml-auto flex gap-1.5">
              <button
                type="button"
                onClick={copyTrackingLink}
                className="svc-btn svc-btn-primary svc-btn-sm"
                data-testid="drawer-tracking-link-copy"
              >
                <LinkIcon size={11} /> {trackingUrl ? t('service.cd_copy_again', 'Copy again') : t('service.cd_get_link', 'Get link')}
              </button>
              {trackingUrl ? (
                <button
                  type="button"
                  onClick={regenerateTrackingLink}
                  className="svc-btn svc-btn-secondary svc-btn-sm"
                  title={t('service.cd_regen_title', 'Invalidate the old link and mint a fresh one')}
                  data-testid="drawer-tracking-link-regenerate"
                >
                  <RefreshCw size={11} /> {t('service.cd_regenerate', 'Regenerate')}
                </button>
              ) : null}
            </div>
          </div>
          {/* Iter 216h82 — Customer-facing Service Report shortcut */}
          {(['repaired', 'awaiting_sign_off', 'closed', 'invoiced'].includes(doc?.status)) ? (
            <div
              className="rounded-lg border p-2 flex items-center gap-2 flex-wrap"
              style={{ borderColor: 'var(--theme-border, #e5e7eb)' }}
              data-testid="drawer-service-report"
            >
              <FileText size={13} className="opacity-70" />
              <span className="text-[11.5px] font-semibold">{t('service.cd_service_report', 'Service report')}</span>
              {doc?.service_report_sent_at ? (
                <span
                  className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                  style={{ background: '#dcfce7', color: '#166534' }}
                  data-testid="drawer-service-report-sent"
                >
                  {t('service.cd_report_sent_to', 'Sent to {{who}}', { who: doc.service_report_sent_to || t('service.cd_the_customer', 'customer') })}
                </span>
              ) : null}
              <div className="ml-auto flex gap-1.5">
                <button
                  type="button"
                  onClick={openServiceReport}
                  className="svc-btn svc-btn-secondary svc-btn-sm"
                  data-testid="drawer-service-report-view"
                >
                  {t('service.cd_view', 'View')}
                </button>
                <button
                  type="button"
                  onClick={emailServiceReport}
                  disabled={reportBusy === 'email'}
                  className="svc-btn svc-btn-primary svc-btn-sm"
                  data-testid="drawer-service-report-email"
                >
                  <Send size={11} /> {reportBusy === 'email' ? t('service.cd_sending', 'Sending…') : (doc?.service_report_sent_at ? t('service.cd_resend', 'Resend') : t('service.cd_email_customer', 'Email customer'))}
                </button>
              </div>
            </div>
          ) : null}
          {legalNext.length > 0 ? (
            <div className="space-y-2">
              <input
                value={transitionReason}
                onChange={(e) => setTransitionReason(e.target.value)}
                placeholder={t('service.cd_reason_ph', 'Reason / note (optional)')}
                className="svc-input svc-input-sm"
                data-testid="drawer-transition-reason"
              />
              <div className="flex flex-wrap gap-1.5">
                {legalNext.map((s) => {
                  const isDanger = s === 'rejected';
                  const isPositive = s === 'closed' || s === 'invoiced' || s === 'repaired';
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => doTransition(s)}
                      disabled={saving}
                      className={`svc-btn svc-btn-sm ${isPositive ? 'svc-btn-primary' : isDanger ? 'svc-btn-danger' : 'svc-btn-secondary'}`}
                      data-testid={`drawer-transition-${s}`}
                    >
                      {isPositive ? <CheckCircle2 size={11} /> : null}
                      {STATUS_LABEL[s] ? statusLabel(t, s) : s}
                      {!isPositive && !isDanger ? <ChevronRight size={11} /> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="text-[11.5px] svc-muted">{t('service.cd_no_transitions', 'No further transitions available from this state.')}</p>
          )}
        </footer>
      </aside>

      {/* Iter 216h81 — Customer rating prompt at sign-off */}
      {ratingTarget && (
        <RatingPromptModal
          rating={rating}
          setRating={setRating}
          comment={ratingComment}
          setComment={setRatingComment}
          busy={ratingSubmitting}
          targetLabel={statusLabel(t, ratingTarget)}
          onSubmit={submitRatingAndTransition}
          onSkip={skipRatingAndTransition}
          onCancel={() => { setRatingTarget(null); setRating(0); setRatingComment(''); }}
        />
      )}
    </div>
  );

  return createPortal(drawer, document.body);
}


function RatingPromptModal({ rating, setRating, comment, setComment, busy, targetLabel, onSubmit, onSkip, onCancel }) {
  const { t } = useTranslation();
  return (
    <div
      className="svc-drawer-overlay"
      style={{ zIndex: 1100 }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel?.(); }}
      data-testid="rating-prompt-modal"
    >
      <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-xl max-w-md w-full p-6"
        style={{ margin: 'auto' }}>
        <h2 className="text-lg font-black mb-1">{t('service.cd_rate_title', "Rate this engineer's work")}</h2>
        <p className="text-xs svc-muted mb-4">
          {t('service.cd_rate_blurb', 'Your rating feeds the partner performance score and helps Pulse Fitness recognise the best engineers. Optional — you can skip.')}
        </p>
        <div className="flex gap-1.5 justify-center my-4" data-testid="rating-stars">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" onClick={() => setRating(n)}
              data-testid={`rating-star-${n}`}
              className="text-3xl leading-none transition-transform hover:scale-110"
              style={{ color: rating >= n ? '#f59e0b' : '#d4d4d8' }}>
              ★
            </button>
          ))}
        </div>
        {rating > 0 && (
          <div className="text-center text-xs font-bold svc-muted mb-3" data-testid="rating-summary">
            {['', t('service.cd_rate_1', 'Poor'), t('service.cd_rate_2', 'Could be better'), t('service.cd_rate_3', 'Solid'), t('service.cd_rate_4', 'Great'), t('service.cd_rate_5', 'Excellent')][rating]}
          </div>
        )}
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">{t('service.cd_comment_optional', 'Comment (optional)')}</span>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value.slice(0, 500))}
            placeholder={t('service.cd_comment_ph', "Anything you'd like to flag to Pulse Fitness or the engineer?")}
            rows={3}
            className="svc-input w-full mt-1"
            data-testid="rating-comment"
          />
        </label>
        <div className="flex items-center justify-between gap-2 mt-5 pt-3 border-t border-zinc-100 dark:border-zinc-800">
          <button onClick={onSkip} disabled={busy}
            className="svc-btn-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 disabled:opacity-50"
            data-testid="rating-skip">
            {t('service.cd_skip_and', 'Skip & {{action}}', { action: targetLabel.toLowerCase() })}
          </button>
          <div className="flex gap-2">
            <button onClick={onCancel} disabled={busy}
              className="svc-btn-sm"
              data-testid="rating-cancel">
              Cancel
            </button>
            <button onClick={onSubmit} disabled={busy || rating === 0}
              className="svc-btn-sm svc-btn-primary disabled:opacity-50"
              data-testid="rating-submit">
              {busy ? t('service.cd_saving', 'Saving…') : t('service.cd_submit_and', 'Submit & {{action}}', { action: targetLabel.toLowerCase() })}

            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="svc-label">{label}</span>
      {children}
    </label>
  );
}

function CommsTab({
  doc, commsLog, commsLoading, templates, templateKey, setTemplateKey,
  onSend, sending, autoNotify, onToggleAutoNotify, onRefresh,
}) {
  const { t } = useTranslation();
  const customerEmail = doc?.customer_email || '';
  const customerName = doc?.customer_name || '';
  return (
    <div className="space-y-3" data-testid="drawer-comms-tab">
      {/* Auto-notify toggle */}
      <div className="svc-card-base p-3" data-testid="drawer-comms-auto-card">
        <div className="flex items-start gap-3">
          <Bell size={14} className="mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="font-bold text-sm">{t('service.cd_auto_notify_title', 'Auto-notify customer on key events')}</p>
            <p className="text-[11.5px] svc-muted mt-0.5">
              {t('service.cd_auto_notify_desc', 'When enabled, Pulse Fitness automatically emails {{email}} as the engineer moves to en route, arrives on site, and the case is completed. Each event sends at most once per case.', { email: customerEmail || t('service.cd_the_customer_lc', 'the customer') })}
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer text-xs">
            <input
              type="checkbox"
              checked={autoNotify}
              onChange={onToggleAutoNotify}
              data-testid="drawer-comms-auto-toggle"
            />
            <span className="font-bold">{autoNotify ? t('service.cd_on', 'On') : t('service.cd_off', 'Off')}</span>
          </label>
        </div>
      </div>

      {/* Manual send */}
      <div className="svc-card-base p-3" data-testid="drawer-comms-send-card">
        <p className="svc-label">{t('service.cd_send_email_now', 'Send customer email now')}</p>
        {!customerEmail ? (
          <p className="text-[11.5px] svc-muted mt-1">
            {t('service.cd_no_email_send', 'No customer email on this case. Add one on the Customer tab to enable sends.')}
          </p>
        ) : (
          <p className="text-[11.5px] svc-muted mt-1">
            {t('service.cd_to_label', 'To:')} <strong>{customerName ? `${customerName} <${customerEmail}>` : customerEmail}</strong>
          </p>
        )}
        <div className="flex flex-wrap gap-2 mt-2 items-center">
          <select
            value={templateKey}
            onChange={(e) => setTemplateKey(e.target.value)}
            className="svc-select svc-select-sm"
            style={{ maxWidth: 240 }}
            disabled={!customerEmail || sending}
            data-testid="drawer-comms-template-select"
          >
            {templates.length === 0 ? (
              <>
                <option value="case_logged">case_logged</option>
                <option value="engineer_en_route">engineer_en_route</option>
                <option value="engineer_arrived">engineer_arrived</option>
                <option value="case_completed">case_completed</option>
              </>
            ) : templates.map((tpl) => (
              <option key={tpl.key} value={tpl.key}>{tpl.key}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={onSend}
            disabled={!customerEmail || sending || !templateKey}
            className="svc-btn svc-btn-primary svc-btn-sm"
            data-testid="drawer-comms-send-btn"
          >
            {sending ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
            {sending ? t('service.cd_sending', 'Sending…') : t('service.cd_send_now', 'Send now')}
          </button>
          <button
            type="button"
            onClick={onRefresh}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="drawer-comms-refresh"
          >
            <History size={11} /> {t('service.cd_refresh_log', 'Refresh log')}
          </button>
        </div>
      </div>

      {/* Log */}
      <div className="svc-section" data-testid="drawer-comms-log-section">
        <div className="svc-section-head">
          <div className="svc-section-title inline-flex items-center gap-1.5">
            <History size={13} /> {t('service.cd_email_history', 'Email history')}
            <span className="svc-muted text-xs">({commsLog.length})</span>
          </div>
        </div>
        <div className="svc-section-body">
          {commsLoading ? (
            <div className="svc-empty"><Loader2 size={14} className="animate-spin" /> {t('service.cd_loading', 'Loading…')}</div>
          ) : commsLog.length === 0 ? (
            <p className="text-[11.5px] svc-muted italic">{t('service.cd_no_emails', 'No emails have been sent for this case yet.')}</p>
          ) : (
            <ul className="space-y-2" data-testid="drawer-comms-log-list">
              {commsLog.map((row) => (
                <li
                  key={row.id}
                  className="flex items-start gap-2 p-2 rounded border"
                  style={{ borderColor: 'var(--theme-border)' }}
                  data-testid={`drawer-comms-log-${row.id}`}
                >
                  {row.ok ? (
                    <CheckCircle2 size={14} style={{ color: '#10b981', flexShrink: 0, marginTop: 2 }} />
                  ) : (
                    <AlertTriangle size={14} style={{ color: '#ef4444', flexShrink: 0, marginTop: 2 }} />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-bold text-sm truncate">{row.subject || t('service.cd_no_subject', '(no subject)')}</span>
                      <span className="text-[10px] svc-muted tabular-nums">
                        {new Date(row.at).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                      <span className="svc-pill" data-testid={`drawer-comms-log-kind-${row.id}`}>
                        {row.kind === 'case_notify_auto' ? t('service.cd_auto', 'auto') : t('service.cd_manual', 'manual')}
                      </span>
                      <span className="text-[11px] svc-muted">{row.template_key} · {row.to}</span>
                      {!row.ok && row.error ? (
                        <span className="text-[11px]" style={{ color: '#b91c1c' }}>· {row.error}</span>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
