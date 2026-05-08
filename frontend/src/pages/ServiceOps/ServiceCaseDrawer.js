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
  Wrench, Activity, Save, Send, ChevronRight, Sparkles, CheckCircle2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
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

  const doTransition = async (target) => {
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
              <Field label="Cover type">
                <select value={merged.cover_type || ''} onChange={(e) => setEdit('cover_type', e.target.value)} className="svc-select" data-testid="drawer-edit-cover">
                  <option value="">—</option>
                  <option value="contract">Contract</option>
                  <option value="warranty">Warranty</option>
                  <option value="chargeable">Chargeable</option>
                  <option value="ppm">PPM</option>
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
          ) : (
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
    </div>
  );

  return createPortal(drawer, document.body);
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="svc-label">{label}</span>
      {children}
    </label>
  );
}
