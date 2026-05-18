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
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  X, Loader2, Clock, AlertTriangle, MapPin, Phone, Mail, User as UserIcon,
  Wrench, Activity, Save, Send, ChevronRight, Sparkles, CheckCircle2, History, Bell,
  FileText, Link as LinkIcon, RefreshCw,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import CoverageBanner from '@/components/shared/CoverageBanner';
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

const PRIORITY_META = {
  p1: { label: 'P1 · Critical', tone: 'p1' },
  p2: { label: 'P2 · High', tone: 'p2' },
  p3: { label: 'P3 · Standard', tone: 'p3' },
  p4: { label: 'P4 · Low', tone: 'p4' },
};

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function relativeFromNow(iso) {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(ms);
  const mins = Math.floor(abs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  const sign = ms < 0 ? 'overdue ' : '';
  if (days >= 1) return `${sign}${days}d ${hours % 24}h`;
  if (hours >= 1) return `${sign}${hours}h ${mins % 60}m`;
  return `${sign}${mins}m`;
}

function SLABadge({ resolveAt }) {
  if (!resolveAt) return null;
  const ms = new Date(resolveAt).getTime() - Date.now();
  const breached = ms < 0;
  const atRisk = !breached && ms < 2 * 3600 * 1000;
  const tone = breached ? 'danger' : atRisk ? 'warn' : 'good';
  const label = breached ? 'SLA breached' : atRisk ? 'SLA at risk' : 'SLA on track';
  const Icon = breached ? AlertTriangle : tone === 'warn' ? AlertTriangle : Clock;
  return (
    <span className={`svc-pill svc-pill--${tone}`} data-testid="drawer-sla-badge">
      <Icon size={11} /> {label} · {relativeFromNow(resolveAt)}
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

const TIMELINE_KIND = (type) => {
  if (type === 'state_change') return 'state';
  if (type === 'note') return 'note';
  if (type === 'comm') return 'comm';
  if (type === 'intake') return 'intake';
  return '';
};

export default function ServiceCaseDrawer({ caseId, onClose, onChanged }) {
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
      else notify.error('AI summary unavailable', r.data?.error || 'Try again');
    } catch (e) {
      notify.error('AI summary failed', e?.response?.data?.detail || e.message);
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
      notify.error('Failed to load case', e?.response?.data?.detail || e.message);
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
      notify.success('Case updated');
      await load();
      onChanged?.();
    } catch (e) {
      notify.error('Failed to save', e?.response?.data?.detail || e.message);
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
      notify.success('Note added');
    } catch (e) {
      notify.error('Failed to add note', e?.response?.data?.detail || e.message);
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
      notify.error('Failed to load comms', e?.response?.data?.detail || e.message);
    } finally { setCommsLoading(false); }
  }, [caseId, commsTemplates]);

  useEffect(() => {
    if (tab === 'comms') loadComms();
  }, [tab, loadComms]);

  const sendCustomerEmail = async () => {
    if (!caseId || !commsTemplateKey) return;
    if (!doc?.customer_email) {
      notify.error('No customer email', 'Set a customer email on the Customer tab first.');
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
        notify.success('Email sent', `${doc.customer_email}`);
      } else {
        notify.error('Email send failed', r.data?.log?.error || 'Provider rejected the request');
      }
      await loadComms();
      await load();
    } catch (e) {
      notify.error('Send failed', e?.response?.data?.detail || e.message);
    } finally { setCommsSending(false); }
  };

  const toggleAutoNotify = async () => {
    const next = !(doc?.comms_auto_notify !== false);
    try {
      await axios.put(`${API}/svc/cases/${caseId}`, { comms_auto_notify: next }, auth());
      await load();
    } catch (e) {
      notify.error('Failed to update', e?.response?.data?.detail || e.message);
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
      .catch((e) => notify.error('Could not open report', e.message || String(e)));
  };
  const emailServiceReport = async () => {
    if (!caseId || reportBusy) return;
    const defaultTo = doc?.customer_email || '';
    const to = window.prompt('Send the service report to which email?', defaultTo);
    if (!to) return;
    const note = window.prompt('Add a short note (optional)', '') || '';
    setReportBusy('email');
    try {
      const r = await axios.post(
        `${API}/svc/cases/${caseId}/service-report/email`,
        { to, note },
        auth(),
      );
      notify.success('Report emailed', `Sent to ${r.data?.to || to}`);
      await load();
    } catch (e) {
      notify.error('Could not send report', e?.response?.data?.detail || e.message);
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
        notify.success('Tracking link copied', 'Paste into SMS / WhatsApp / email for the customer.');
      } catch {
        window.prompt('Copy the link below and share with the customer:', url);
      }
    } catch (e) {
      notify.error('Could not generate tracking link', e?.response?.data?.detail || e.message);
    }
  };
  const regenerateTrackingLink = async () => {
    if (!caseId) return;
    if (!window.confirm('Regenerate the tracking link? The previous link will stop working.')) return;
    try {
      const r = await axios.post(`${API}/svc/cases/${caseId}/tracking-link/regenerate`, {}, auth());
      const url = r.data?.url || '';
      setTrackingUrl(url);
      try {
        await navigator.clipboard.writeText(url);
        notify.success('New tracking link copied', 'Old link is now invalid.');
      } catch {
        window.prompt('Copy the new link:', url);
      }
    } catch (e) {
      notify.error('Could not regenerate', e?.response?.data?.detail || e.message);
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
      notify.success(`Moved to ${STATUS_LABEL[target] || target}`);
      await load();
      onChanged?.();
    } catch (e) {
      notify.error('Transition rejected', e?.response?.data?.detail || e.message);
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
      notify.success(rating > 0 ? `Closed · thanks for rating ${rating} stars` : `Moved to ${STATUS_LABEL[tgt] || tgt}`);
      await load();
      onChanged?.();
    } catch (e) {
      notify.error('Could not close', e?.response?.data?.detail || e.message);
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
      notify.success(`Moved to ${STATUS_LABEL[tgt] || tgt}`);
      await load();
      onChanged?.();
    } catch (e) {
      notify.error('Transition rejected', e?.response?.data?.detail || e.message);
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
        aria-label="Service case detail"
        style={{ maxWidth: 720 }}
      >
        {/* Header */}
        <header className="svc-drawer-head">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="svc-eyebrow">{merged?.reference || 'Loading…'}</p>
              <h2 className="svc-h1" style={{ fontSize: 19, marginTop: 2 }} data-testid="drawer-title">
                {merged?.title || (loading ? '…' : 'Untitled case')}
              </h2>
              <div className="flex flex-wrap items-center gap-2 mt-2">
                <span className={`svc-pill svc-pill--${pri.tone === 'p1' ? 'danger' : pri.tone === 'p2' ? 'warn' : pri.tone === 'p3' ? 'info' : ''}`} data-testid="drawer-priority">
                  {pri.label}
                </span>
                <span className="svc-pill" data-testid="drawer-status">
                  {STATUS_LABEL[merged?.status] || merged?.status || '—'}
                </span>
                <SLABadge resolveAt={merged?.sla_resolve_at} />
                {existingRating ? (
                  <span
                    className="svc-pill inline-flex items-center gap-0.5"
                    style={{ background: '#fef3c7', color: '#92400e', fontWeight: 700 }}
                    title={merged?.customer_rating_comment || `Customer rated this case ${existingRating}/5`}
                    data-testid="drawer-customer-rating">
                    <span style={{ color: '#f59e0b' }}>★</span> {existingRating}/5
                  </span>
                ) : null}
              </div>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" data-testid="drawer-close" className="svc-icon-btn">
              <X size={16} />
            </button>
          </div>
        </header>

        {/* Tabs */}
        <div className="svc-tabs" style={{ margin: 0, padding: '0 18px' }}>
          <TabButton id="timeline" label="Timeline" icon={Activity} active={tab === 'timeline'} onClick={() => setTab('timeline')} count={events.length} />
          <TabButton id="details" label="Details" icon={Wrench} active={tab === 'details'} onClick={() => setTab('details')} />
          <TabButton id="customer" label="Customer" icon={UserIcon} active={tab === 'customer'} onClick={() => setTab('customer')} />
          <TabButton id="comms" label="Comms" icon={Bell} active={tab === 'comms'} onClick={() => setTab('comms')} />
        </div>

        {/* Body */}
        <div className="svc-drawer-body space-y-4">
          {loading ? (
            <div className="flex items-center gap-2 text-sm svc-muted"><Loader2 size={14} className="animate-spin" /> Loading case…</div>
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
                    {aiBusy ? '…' : aiSummary ? 'Refresh' : 'Generate'}
                  </button>
                </div>
                {aiSummary ? (
                  <div className="space-y-2 text-xs mt-2">
                    <div>
                      <p className="svc-label" style={{ marginBottom: 2 }}>For the customer</p>
                      <p data-testid="drawer-ai-customer-summary" style={{ lineHeight: 1.55 }}>{aiSummary.customer_summary}</p>
                    </div>
                    {aiSummary.engineer_summary ? (
                      <div>
                        <p className="svc-label" style={{ marginBottom: 2 }}>For the engineer</p>
                        <p data-testid="drawer-ai-engineer-summary" style={{ lineHeight: 1.55 }}>{aiSummary.engineer_summary}</p>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-[11.5px] svc-muted mt-2">One-click summary of every event so far — one for the customer, one for the engineer.</p>
                )}
              </div>

              {/* Add note */}
              <div className="svc-card-base p-3">
                <p className="svc-label">Add internal note</p>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  placeholder="Customer called back to confirm engineer access…"
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
                    <Send size={11} /> Add note
                  </button>
                </div>
              </div>

              {/* Timeline */}
              <ol className="svc-timeline" data-testid="drawer-timeline">
                {events.length === 0 ? (
                  <li className="text-sm svc-muted">No timeline events yet.</li>
                ) : events.map((ev) => {
                  const kind = TIMELINE_KIND(ev.type);
                  return (
                    <li key={ev.id} className={kind ? `svc-tl--${kind}` : ''}>
                      <p className="svc-tl-meta">
                        {ev.type === 'state_change'
                          ? `${STATUS_LABEL[ev.from_state] || ev.from_state} → ${STATUS_LABEL[ev.to_state] || ev.to_state}`
                          : ev.type}
                        <span className="svc-tl-meta-time"> · {fmtDate(ev.at)}{ev.actor_name ? ` · ${ev.actor_name}` : ''}</span>
                      </p>
                      {ev.body ? <p className="svc-tl-body">{ev.body}</p> : null}
                      {ev.reason ? <p className="svc-tl-reason">Reason: {ev.reason}</p> : null}
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
                <Field label="Title">
                  <input value={merged.title || ''} onChange={(e) => setEdit('title', e.target.value)} className="svc-input" data-testid="drawer-edit-title" />
                </Field>
                <Field label="Priority">
                  <select value={merged.priority || 'p3'} onChange={(e) => setEdit('priority', e.target.value)} className="svc-select" data-testid="drawer-edit-priority">
                    <option value="p1">P1 — Critical</option>
                    <option value="p2">P2 — High</option>
                    <option value="p3">P3 — Standard</option>
                    <option value="p4">P4 — Low</option>
                  </select>
                </Field>
                <Field label="Site">
                  <input value={merged.site_name || ''} onChange={(e) => setEdit('site_name', e.target.value)} className="svc-input" data-testid="drawer-edit-site" />
              </Field>
              <Field label="Asset">
                <input value={merged.asset_name || ''} onChange={(e) => setEdit('asset_name', e.target.value)} className="svc-input" data-testid="drawer-edit-asset" />
              </Field>
              <Field label="Fault code">
                <input value={merged.fault_code || ''} onChange={(e) => setEdit('fault_code', e.target.value)} className="svc-input" data-testid="drawer-edit-fault" />
              </Field>
              <Field label="Case type">
                <select value={merged.case_type || ''} onChange={(e) => setEdit('case_type', e.target.value)} className="svc-select" data-testid="drawer-edit-case-type">
                  <option value="">—</option>
                  <option value="repair">Repair</option>
                  <option value="ppm">PPM</option>
                  <option value="install">Install</option>
                </select>
              </Field>
              <Field label="Cover type">
                <select value={merged.cover_type || ''} onChange={(e) => setEdit('cover_type', e.target.value)} className="svc-select" data-testid="drawer-edit-cover">
                  <option value="">—</option>
                  <option value="contract">Contract</option>
                  <option value="warranty">Warranty</option>
                  <option value="chargeable">Chargeable</option>
                </select>
              </Field>
              <Field label="Engineer">
                <input
                  value={merged.assigned_engineer_name || ''}
                  onChange={(e) => setEdit('assigned_engineer_name', e.target.value)}
                  placeholder="Unassigned"
                  className="svc-input"
                  data-testid="drawer-edit-engineer"
                />
              </Field>
              <Field label="Estimated minutes">
                <input
                  type="number"
                  value={merged.estimated_minutes || 0}
                  onChange={(e) => setEdit('estimated_minutes', Number(e.target.value))}
                  className="svc-input"
                  data-testid="drawer-edit-est"
                />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Description">
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
                <p>Logged: {fmtDate(doc?.created_at)}{doc?.logged_by_name ? ` · ${doc.logged_by_name}` : ''}</p>
                <p>SLA respond by: {fmtDate(doc?.sla_response_at)}</p>
                <p>Source: {doc?.source || '—'}</p>
                <p>SLA resolve by: {fmtDate(doc?.sla_resolve_at)}</p>
              </div>
            </div>
            </>
          ) : tab === 'customer' ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Customer name">
                <input value={merged.customer_name || ''} onChange={(e) => setEdit('customer_name', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-name" />
              </Field>
              <Field label="Phone">
                <input value={merged.customer_phone || ''} onChange={(e) => setEdit('customer_phone', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-phone" />
              </Field>
              <Field label="Email">
                <input value={merged.customer_email || ''} onChange={(e) => setEdit('customer_email', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-email" />
              </Field>
              <Field label="Site">
                <input value={merged.site_name || ''} onChange={(e) => setEdit('site_name', e.target.value)} className="svc-input" data-testid="drawer-edit-customer-site" />
              </Field>
              <div className="sm:col-span-2 flex flex-wrap gap-3 text-xs pt-1">
                {merged.customer_phone ? <a href={`tel:${merged.customer_phone}`} className="svc-link inline-flex items-center gap-1"><Phone size={11} /> Call</a> : null}
                {merged.customer_email ? <a href={`mailto:${merged.customer_email}`} className="svc-link inline-flex items-center gap-1"><Mail size={11} /> Email</a> : null}
                {merged.site_name ? <span className="inline-flex items-center gap-1 svc-muted"><MapPin size={11} /> {merged.site_name}</span> : null}
              </div>
            </div>
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
                <Save size={11} /> Save changes
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
            <span className="text-[11.5px] font-semibold">Customer tracking</span>
            {trackingUrl ? (
              <span
                className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                style={{ background: '#dbeafe', color: '#1d4ed8' }}
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
                <LinkIcon size={11} /> {trackingUrl ? 'Copy again' : 'Get link'}
              </button>
              {trackingUrl ? (
                <button
                  type="button"
                  onClick={regenerateTrackingLink}
                  className="svc-btn svc-btn-secondary svc-btn-sm"
                  title="Invalidate the old link and mint a fresh one"
                  data-testid="drawer-tracking-link-regenerate"
                >
                  <RefreshCw size={11} /> Regenerate
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
              <span className="text-[11.5px] font-semibold">Service report</span>
              {doc?.service_report_sent_at ? (
                <span
                  className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                  style={{ background: '#dcfce7', color: '#166534' }}
                  data-testid="drawer-service-report-sent"
                >
                  Sent to {doc.service_report_sent_to || 'customer'}
                </span>
              ) : null}
              <div className="ml-auto flex gap-1.5">
                <button
                  type="button"
                  onClick={openServiceReport}
                  className="svc-btn svc-btn-secondary svc-btn-sm"
                  data-testid="drawer-service-report-view"
                >
                  View
                </button>
                <button
                  type="button"
                  onClick={emailServiceReport}
                  disabled={reportBusy === 'email'}
                  className="svc-btn svc-btn-primary svc-btn-sm"
                  data-testid="drawer-service-report-email"
                >
                  <Send size={11} /> {reportBusy === 'email' ? 'Sending…' : (doc?.service_report_sent_at ? 'Resend' : 'Email customer')}
                </button>
              </div>
            </div>
          ) : null}
          {legalNext.length > 0 ? (
            <div className="space-y-2">
              <input
                value={transitionReason}
                onChange={(e) => setTransitionReason(e.target.value)}
                placeholder="Reason / note (optional)"
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
                      {STATUS_LABEL[s] || s}
                      {!isPositive && !isDanger ? <ChevronRight size={11} /> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="text-[11.5px] svc-muted">No further transitions available from this state.</p>
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
          targetLabel={STATUS_LABEL[ratingTarget] || ratingTarget}
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
  return (
    <div
      className="svc-drawer-overlay"
      style={{ zIndex: 1100 }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel?.(); }}
      data-testid="rating-prompt-modal"
    >
      <div className="rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-xl max-w-md w-full p-6"
        style={{ margin: 'auto' }}>
        <h2 className="text-lg font-black mb-1">Rate this engineer's work</h2>
        <p className="text-xs svc-muted mb-4">
          Your rating feeds the partner performance score and helps GymAxis recognise the best engineers. Optional — you can skip.
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
            {['', 'Poor', 'Could be better', 'Solid', 'Great', 'Excellent'][rating]}
          </div>
        )}
        <label className="block">
          <span className="text-[10px] uppercase tracking-wider font-bold svc-muted">Comment (optional)</span>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value.slice(0, 500))}
            placeholder="Anything you'd like to flag to GymAxis or the engineer?"
            rows={3}
            className="svc-input w-full mt-1"
            data-testid="rating-comment"
          />
        </label>
        <div className="flex items-center justify-between gap-2 mt-5 pt-3 border-t border-zinc-100 dark:border-zinc-800">
          <button onClick={onSkip} disabled={busy}
            className="svc-btn-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 disabled:opacity-50"
            data-testid="rating-skip">
            Skip & {targetLabel.toLowerCase()}
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
              {busy ? 'Saving…' : `Submit & ${targetLabel.toLowerCase()}`}
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
  const customerEmail = doc?.customer_email || '';
  const customerName = doc?.customer_name || '';
  return (
    <div className="space-y-3" data-testid="drawer-comms-tab">
      {/* Auto-notify toggle */}
      <div className="svc-card-base p-3" data-testid="drawer-comms-auto-card">
        <div className="flex items-start gap-3">
          <Bell size={14} className="mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="font-bold text-sm">Auto-notify customer on key events</p>
            <p className="text-[11.5px] svc-muted mt-0.5">
              When enabled, GymAxis automatically emails {customerEmail || 'the customer'} as the engineer
              moves to <em>en route</em>, arrives <em>on site</em>, and the case is <em>completed</em>.
              Each event sends at most once per case.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer text-xs">
            <input
              type="checkbox"
              checked={autoNotify}
              onChange={onToggleAutoNotify}
              data-testid="drawer-comms-auto-toggle"
            />
            <span className="font-bold">{autoNotify ? 'On' : 'Off'}</span>
          </label>
        </div>
      </div>

      {/* Manual send */}
      <div className="svc-card-base p-3" data-testid="drawer-comms-send-card">
        <p className="svc-label">Send customer email now</p>
        {!customerEmail ? (
          <p className="text-[11.5px] svc-muted mt-1">
            No customer email on this case. Add one on the <strong>Customer</strong> tab to enable sends.
          </p>
        ) : (
          <p className="text-[11.5px] svc-muted mt-1">
            To: <strong>{customerName ? `${customerName} <${customerEmail}>` : customerEmail}</strong>
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
            ) : templates.map((t) => (
              <option key={t.key} value={t.key}>{t.key}</option>
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
            {sending ? 'Sending…' : 'Send now'}
          </button>
          <button
            type="button"
            onClick={onRefresh}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="drawer-comms-refresh"
          >
            <History size={11} /> Refresh log
          </button>
        </div>
      </div>

      {/* Log */}
      <div className="svc-section" data-testid="drawer-comms-log-section">
        <div className="svc-section-head">
          <div className="svc-section-title inline-flex items-center gap-1.5">
            <History size={13} /> Email history
            <span className="svc-muted text-xs">({commsLog.length})</span>
          </div>
        </div>
        <div className="svc-section-body">
          {commsLoading ? (
            <div className="svc-empty"><Loader2 size={14} className="animate-spin" /> Loading…</div>
          ) : commsLog.length === 0 ? (
            <p className="text-[11.5px] svc-muted italic">No emails have been sent for this case yet.</p>
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
                      <span className="font-bold text-sm truncate">{row.subject || '(no subject)'}</span>
                      <span className="text-[10px] svc-muted tabular-nums">
                        {new Date(row.at).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                      <span className="svc-pill" data-testid={`drawer-comms-log-kind-${row.id}`}>
                        {row.kind === 'case_notify_auto' ? 'auto' : 'manual'}
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
