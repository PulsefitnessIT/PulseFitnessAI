/**
 * PartnerApplicationDrawer — Iter 219.
 *
 * Slide-out drawer for the master admin to review a single pending
 * Partner Engineer application end-to-end. Previously the only thing
 * an admin could see was a truncated row in the applications table —
 * the rest of the data (insurance expiry, qualifications, cover
 * letter, CV / cert attachments, terms acceptance timestamp) was
 * effectively invisible. Operator feedback (iter 219):
 *   "I need to be able to click into the engineer's application and
 *    see all the details of the application and paperwork submitted
 *    by the engineer. I currently can't see anything."
 *
 * Surfaces:
 *  • Applicant card (name, email, phone, company, years experience)
 *  • Coverage (postcode + travel radius)
 *  • Skills, brands supported, qualifications (full lists, not chips
 *    truncated at 3)
 *  • Compliance block (insurance provider, insurance expiry,
 *    qualification expiry, terms acceptance timestamp + version)
 *  • Cover letter / referral source / referrer engineer (if eref used)
 *  • Attachments with auth-gated download buttons (CV, certs, etc.)
 *  • Reviewer notes — persisted via PATCH /notes
 *  • Approve (with level picker) + Reject (with reason) at the foot.
 *
 * Fetches the full record via GET /api/partners/applications/{id}.
 * Approve/Reject reuse the existing endpoints in `AdminPartners.js`,
 * so audit trail and engineer record creation are unchanged.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  X, Loader2, Mail, Phone, MapPin, Calendar, ShieldCheck, FileText,
  Download, CheckCircle2, XCircle, Award, Briefcase, MessageSquare,
  Sparkles, ChevronDown, Wrench, Tag, AlertTriangle, RefreshCw, Wand2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;

const LEVEL_OPTIONS = [
  { id: 'engineer_partner',  label: 'Engineer Partner (default)' },
  { id: 'verified_partner',  label: 'Verified Partner' },
  { id: 'strategic_partner', label: 'Strategic Partner' },
  { id: 'customer_added',    label: 'Customer-added' },
];

const fmtDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return String(iso);
  }
};

const fmtBytes = (n) => {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

const Pill = ({ children, tone = 'slate' }) => {
  const tones = {
    slate: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
    sky: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
    emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200',
    amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200',
    rose: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-bold tracking-wide ${tones[tone] || tones.slate}`}>
      {children}
    </span>
  );
};

const Section = ({ icon: Icon, title, children, testid }) => (
  <section className="space-y-2" data-testid={testid}>
    <div className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
      {Icon ? <Icon size={12} /> : null}
      <span>{title}</span>
    </div>
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3 text-sm">
      {children}
    </div>
  </section>
);

const FieldRow = ({ icon: Icon, label, value, mono, testid }) => (
  <div className="flex items-start gap-2 py-1.5 first:pt-0 last:pb-0 border-b border-zinc-100 dark:border-zinc-800 last:border-b-0" data-testid={testid}>
    {Icon ? <Icon size={13} className="mt-0.5 text-zinc-400 flex-shrink-0" /> : null}
    <div className="flex-1 min-w-0">
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</div>
      <div className={`text-sm text-zinc-900 dark:text-zinc-100 mt-0.5 break-words ${mono ? 'font-mono' : ''}`}>
        {value || <span className="text-zinc-400">—</span>}
      </div>
    </div>
  </div>
);

export default function PartnerApplicationDrawer({
  applicationId,
  onClose,
  onApproved,
  onRejected,
}) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);   // { application, referrer }
  const [savingNotes, setSavingNotes] = useState(false);
  const [busy, setBusy] = useState(null); // 'approve' | 'reject' | 'resend'
  const [notes, setNotes] = useState('');
  const [level, setLevel] = useState('engineer_partner');
  /* Iter 219b — AI decision helper. Auto-loads on drawer open so the
     admin sees the recommendation immediately. Never blocks the page;
     the deterministic fallback in the backend keeps `suggestion`
     populated even when the LLM is offline. */
  const [suggestion, setSuggestion] = useState(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const load = useCallback(async () => {
    if (!applicationId) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/partners/applications/${applicationId}`, { headers });
      setData(r.data || null);
      setNotes(r.data?.application?.reviewer_notes || '');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load application');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  const loadSuggestion = useCallback(async () => {
    if (!applicationId) return;
    setSuggestionLoading(true);
    try {
      const r = await axios.post(
        `${API}/api/partners/applications/${applicationId}/ai-suggest`,
        {},
        { headers },
      );
      const s = r.data?.suggestion || null;
      setSuggestion(s);
      // Pre-select the suggested level in the footer picker so the
      // admin can act in one click. We don't auto-approve — the human
      // remains the source of truth.
      if (s?.level) setLevel(s.level);
    } catch (e) {
      // Silent — the panel just collapses if the helper is unavailable.
       
      console.debug('AI suggestion failed', e?.response?.status);
    } finally {
      setSuggestionLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadSuggestion(); }, [loadSuggestion]);

  const saveNotes = async () => {
    if (!applicationId) return;
    setSavingNotes(true);
    try {
      await axios.patch(
        `${API}/api/partners/applications/${applicationId}/notes`,
        { notes },
        { headers },
      );
      notify.success('Reviewer notes saved');
    } catch (e) {
      notifyApiError(notify, e, 'Could not save notes');
    } finally {
      setSavingNotes(false);
    }
  };

  const approve = async () => {
    if (!applicationId) return;
    setBusy('approve');
    try {
      // Persist any unsaved notes first so the audit trail is honest.
      if (notes !== (data?.application?.reviewer_notes || '')) {
        await axios.patch(
          `${API}/api/partners/applications/${applicationId}/notes`,
          { notes },
          { headers },
        );
      }
      await axios.post(
        `${API}/api/partners/applications/${applicationId}/approve`,
        { level },
        { headers },
      );
      notify.success(`${app.full_name || 'Applicant'} approved as ${level.replace('_', ' ')}`);
      if (onApproved) onApproved();
      // Iter 219d — keep drawer open and reload so the "Resend
      // approval email" button is immediately accessible (covers the
      // case where the welcome email needs a manual re-send).
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Approve failed');
    } finally {
      setBusy(null);
    }
  };

  const reject = async () => {
    if (!applicationId) return;
    const reason = window.prompt('Reason for rejection (sent to applicant, optional):', notes || '');
    if (reason === null) return; // cancelled
    setBusy('reject');
    try {
      await axios.post(
        `${API}/api/partners/applications/${applicationId}/reject`,
        { reason },
        { headers },
      );
      notify.success(`${app.full_name || 'Applicant'} rejected`);
      if (onRejected) onRejected();
      onClose();
    } catch (e) {
      notifyApiError(notify, e, 'Reject failed');
    } finally {
      setBusy(null);
    }
  };

  /* Iter 219g — One smart button for all sign-in problems. Calls
     the server-side `send-signin-link` endpoint which auto-routes
     between a fresh activation link (engineer hasn't activated yet)
     and a password-reset link (engineer activated but lost the
     password — the case the operator hit when their newly-approved
     engineer asked "how do I sign in?"). The toast message changes
     to reflect what actually went out. */
  const sendSigninLink = async () => {
    if (!applicationId) return;
    setBusy('resend');
    try {
      const r = await axios.post(
        `${API}/api/partners/applications/${applicationId}/send-signin-link`,
        {},
        { headers },
      );
      const kind = r.data?.kind;
      const sentTo = r.data?.sent_to || app.email || 'engineer';
      const msg = kind === 'password_reset'
        ? `Password-reset link sent to ${sentTo}`
        : `Activation link sent to ${sentTo}`;
      notify.success(msg);
    } catch (e) {
      notifyApiError(notify, e, 'Send failed');
    } finally {
      setBusy(null);
    }
  };

  const downloadAttachment = async (attachment) => {
    if (!applicationId || !attachment?.id) return;
    try {
      const r = await axios.get(
        `${API}/api/partners/applications/${applicationId}/attachments/${attachment.id}`,
        { headers, responseType: 'blob' },
      );
      const blob = new Blob([r.data], { type: attachment.content_type || 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.original_filename || 'attachment';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      notifyApiError(notify, e, 'Could not download attachment');
    }
  };

  const app = data?.application || {};
  const referrer = data?.referrer || null;
  const isPending = (app.status || 'pending') === 'pending';

  // Insurance expiry tone — within 30 days = amber, expired = rose.
  const insuranceExpiresAt = app.insurance_expires_at ? new Date(app.insurance_expires_at) : null;
  let insuranceTone = 'slate';
  if (insuranceExpiresAt) {
    const days = (insuranceExpiresAt - new Date()) / (1000 * 60 * 60 * 24);
    if (days < 0) insuranceTone = 'rose';
    else if (days < 30) insuranceTone = 'amber';
    else insuranceTone = 'emerald';
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/55 flex justify-end"
      onClick={onClose}
      data-testid="partner-application-backdrop"
    >
      <aside
        className="bg-zinc-50 dark:bg-zinc-950 w-full sm:max-w-2xl h-full shadow-2xl overflow-y-auto flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="partner-application-drawer"
      >
        <header className="sticky top-0 z-10 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800 px-5 py-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-purple-600 dark:text-purple-400">
              Partner Engineer · Application
            </p>
            <h2 className="text-lg font-extrabold text-zinc-900 dark:text-zinc-100 truncate mt-0.5" data-testid="partner-application-title">
              {app.full_name || (loading ? 'Loading…' : 'Application')}
            </h2>
            <div className="text-[11px] text-zinc-500 truncate">
              {app.email || ''}
              {app.submitted_at ? ` · submitted ${fmtDate(app.submitted_at)}` : ''}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Pill tone={isPending ? 'amber' : (app.status === 'approved' ? 'emerald' : 'rose')}>
                {app.status || 'pending'}
              </Pill>
              {app.years_experience ? <Pill tone="sky">{app.years_experience} yrs</Pill> : null}
              {app.has_insurance ? <Pill tone={insuranceTone}>Insurance on file</Pill> : <Pill tone="rose">No insurance</Pill>}
              {referrer ? <Pill tone="sky">Referred by {referrer.full_name || referrer.referral_code}</Pill> : null}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800"
            aria-label="Close application"
            data-testid="partner-application-close"
          >
            <X size={16} />
          </button>
        </header>

        <div className="p-5 space-y-5 flex-1">
          {loading ? (
            <div className="text-sm text-zinc-500 flex items-center gap-2 py-12 justify-center">
              <Loader2 size={14} className="animate-spin" /> Loading application…
            </div>
          ) : (
            <>
              {/* Iter 219b — AI decision helper. Always renders so the
                  admin sees the model's recommendation up-front. The
                  backend's deterministic fallback keeps this populated
                  even when the LLM is offline. */}
              <AISuggestPanel
                suggestion={suggestion}
                loading={suggestionLoading}
                onRefresh={loadSuggestion}
                onApplyLevel={(lvl) => setLevel(lvl)}
                currentLevel={level}
              />

              {/* Applicant */}
              <Section icon={Briefcase} title="Applicant" testid="partner-application-applicant">
                <FieldRow icon={Mail} label="Email" value={app.email} mono testid="pa-email" />
                <FieldRow icon={Phone} label="Phone" value={app.phone} testid="pa-phone" />
                <FieldRow icon={Tag} label="Company" value={app.company_name} testid="pa-company" />
                <FieldRow icon={Sparkles} label="Years of experience" value={app.years_experience} testid="pa-years" />
                <FieldRow icon={MessageSquare} label="Referral source" value={app.referral_source} testid="pa-referral-source" />
                {referrer ? (
                  <FieldRow
                    icon={ChevronDown}
                    label="Referring engineer"
                    value={`${referrer.full_name || ''} (${referrer.referral_code || ''})${referrer.email ? ` · ${referrer.email}` : ''}`}
                    testid="pa-referrer"
                  />
                ) : null}
              </Section>

              {/* Coverage */}
              <Section icon={MapPin} title="Coverage" testid="partner-application-coverage">
                <FieldRow icon={MapPin} label="Service postcode" value={app.service_postcode} mono testid="pa-postcode" />
                <FieldRow
                  icon={MapPin}
                  label="Travel radius"
                  value={app.travel_radius_km != null ? `${app.travel_radius_km} km` : null}
                  testid="pa-radius"
                />
              </Section>

              {/* Skills, brands, quals */}
              <Section icon={Wrench} title="Skills, brands & qualifications" testid="partner-application-skills">
                <div className="py-1.5 border-b border-zinc-100 dark:border-zinc-800">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1">
                    Brands supported {(app.brands_supported || []).length ? `(${app.brands_supported.length})` : ''}
                  </div>
                  {(app.brands_supported || []).length ? (
                    <div className="flex flex-wrap gap-1" data-testid="pa-brands">
                      {app.brands_supported.map((b, i) => <Pill key={i} tone="sky">{b}</Pill>)}
                    </div>
                  ) : <div className="text-sm text-zinc-400">—</div>}
                </div>
                <div className="py-1.5 border-b border-zinc-100 dark:border-zinc-800">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1">
                    Skills {(app.skills || []).length ? `(${app.skills.length})` : ''}
                  </div>
                  {(app.skills || []).length ? (
                    <div className="flex flex-wrap gap-1" data-testid="pa-skills">
                      {app.skills.map((s, i) => <Pill key={i} tone="slate">{s}</Pill>)}
                    </div>
                  ) : <div className="text-sm text-zinc-400">—</div>}
                </div>
                <div className="py-1.5">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1">
                    Qualifications {(app.qualifications || []).length ? `(${app.qualifications.length})` : ''}
                  </div>
                  {(app.qualifications || []).length ? (
                    <ul className="list-disc list-inside text-sm text-zinc-900 dark:text-zinc-100 space-y-0.5" data-testid="pa-quals">
                      {app.qualifications.map((q, i) => <li key={i}>{q}</li>)}
                    </ul>
                  ) : <div className="text-sm text-zinc-400">—</div>}
                </div>
              </Section>

              {/* Compliance */}
              <Section icon={ShieldCheck} title="Compliance & terms" testid="partner-application-compliance">
                <FieldRow
                  icon={ShieldCheck}
                  label="Has insurance"
                  value={app.has_insurance ? 'Yes' : 'No'}
                  testid="pa-has-insurance"
                />
                <FieldRow icon={Award} label="Insurance provider" value={app.insurance_provider} testid="pa-insurance-provider" />
                <FieldRow
                  icon={Calendar}
                  label="Insurance expiry"
                  value={app.insurance_expires_at ? fmtDate(app.insurance_expires_at) : null}
                  testid="pa-insurance-expiry"
                />
                <FieldRow
                  icon={Calendar}
                  label="Qualifications expiry"
                  value={app.qualifications_expires_at ? fmtDate(app.qualifications_expires_at) : null}
                  testid="pa-quals-expiry"
                />
                <FieldRow
                  icon={CheckCircle2}
                  label="Terms accepted"
                  value={app.terms_accepted_at ? `${fmtDate(app.terms_accepted_at)} · v${app.terms_version || '?'}` : null}
                  testid="pa-terms-accepted"
                />
              </Section>

              {/* Cover letter */}
              {app.cover_letter ? (
                <Section icon={MessageSquare} title="Cover letter" testid="partner-application-cover-letter">
                  <div className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-200" data-testid="pa-cover-letter">
                    {app.cover_letter}
                  </div>
                </Section>
              ) : null}

              {/* Attachments */}
              <Section icon={FileText} title={`Paperwork & attachments${(app.attachments || []).length ? ` · ${app.attachments.length}` : ''}`} testid="partner-application-attachments">
                {(app.attachments || []).length === 0 ? (
                  <div className="text-sm text-zinc-400 flex items-center gap-2">
                    <AlertTriangle size={13} /> No files uploaded. Consider asking the applicant to attach a CV and insurance certificate before approving.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {app.attachments.map((att) => (
                      <li
                        key={att.id || att.original_filename}
                        className="flex items-center justify-between gap-3 p-2 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900"
                        data-testid={`pa-attachment-${att.id || att.original_filename}`}
                      >
                        <div className="flex items-start gap-2 min-w-0">
                          <FileText size={16} className="text-zinc-400 mt-0.5 flex-shrink-0" />
                          <div className="min-w-0">
                            <div className="text-sm font-bold text-zinc-900 dark:text-zinc-100 truncate">
                              {att.original_filename || 'attachment'}
                            </div>
                            <div className="text-[11px] text-zinc-500 truncate">
                              {att.kind ? <span className="uppercase font-bold mr-1">{att.kind}</span> : null}
                              {att.content_type || 'unknown'}{att.size ? ` · ${fmtBytes(att.size)}` : ''}
                              {att.uploaded_at ? ` · ${fmtDate(att.uploaded_at)}` : ''}
                            </div>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => downloadAttachment(att)}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 text-xs font-bold hover:opacity-90"
                          data-testid={`pa-attachment-download-${att.id || att.original_filename}`}
                        >
                          <Download size={12} /> Download
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              {/* Reviewer notes */}
              <Section icon={MessageSquare} title="Reviewer notes (internal)" testid="partner-application-notes">
                <textarea
                  className="w-full min-h-[100px] rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-2 text-sm focus:outline-none focus:border-purple-400"
                  placeholder="Add private notes about this applicant — e.g. references checked, gaps in coverage, follow-ups…"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  onBlur={saveNotes}
                  data-testid="partner-application-notes-input"
                />
                <div className="mt-2 flex items-center justify-end text-[11px] text-zinc-500">
                  {savingNotes ? (
                    <span className="inline-flex items-center gap-1"><Loader2 size={11} className="animate-spin" /> Saving…</span>
                  ) : (
                    <span>Auto-saves on blur. Visible to master admins only.</span>
                  )}
                </div>
              </Section>
            </>
          )}
        </div>

        {/* Sticky decision bar */}
        <footer
          className="sticky bottom-0 bg-white dark:bg-zinc-900 border-t border-zinc-200 dark:border-zinc-800 px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-3"
          data-testid="partner-application-actions"
        >
          {isPending ? (
            <>
              <label className="text-xs font-bold uppercase tracking-wider text-zinc-500 flex items-center gap-2">
                Approve as
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="text-xs border border-zinc-200 dark:border-zinc-700 rounded-md px-2 py-1 bg-white dark:bg-zinc-900"
                  data-testid="partner-application-level-select"
                >
                  {LEVEL_OPTIONS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                </select>
              </label>
              <div className="flex-1" />
              <button
                type="button"
                onClick={reject}
                disabled={busy !== null || loading}
                className="px-4 py-2 rounded-lg border border-rose-300 dark:border-rose-700 text-rose-700 dark:text-rose-300 text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50"
                data-testid="partner-application-reject-btn"
              >
                {busy === 'reject' ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />} Reject
              </button>
              <button
                type="button"
                onClick={approve}
                disabled={busy !== null || loading}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50"
                data-testid="partner-application-approve-btn"
              >
                {busy === 'approve' ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Approve
              </button>
            </>
          ) : (
            <div className="flex items-center gap-2 w-full">
              <div className="text-xs text-zinc-500 flex-1">
                This application has already been {app.status}.
              </div>
              {app.status === 'approved' ? (
                <button
                  type="button"
                  onClick={sendSigninLink}
                  disabled={busy !== null || loading}
                  className="px-3 py-2 rounded-lg border border-emerald-300 dark:border-emerald-700 text-emerald-700 dark:text-emerald-300 text-sm font-bold inline-flex items-center gap-2 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 disabled:opacity-50"
                  data-testid="partner-application-resend-email-btn"
                  title="Sends an activation link if the engineer hasn't signed up yet, or a password-reset link if they already have an account."
                >
                  {busy === 'resend' ? <Loader2 size={14} className="animate-spin" /> : <Mail size={14} />}
                  Send sign-in link
                </button>
              ) : null}
            </div>
          )}
        </footer>
      </aside>
    </div>
  );
}


const DECISION_STYLES = {
  approve:    { cls: 'from-emerald-500 to-emerald-600 text-white', label: 'Suggest approve', icon: CheckCircle2 },
  reject:     { cls: 'from-rose-500 to-rose-600 text-white',       label: 'Suggest reject',  icon: XCircle },
  needs_info: { cls: 'from-amber-500 to-amber-600 text-white',     label: 'Needs more info', icon: AlertTriangle },
};

const LEVEL_LABELS = {
  engineer_partner:  'Engineer Partner',
  verified_partner:  'Verified Partner',
  strategic_partner: 'Strategic Partner',
};

function AISuggestPanel({ suggestion, loading, onRefresh, onApplyLevel, currentLevel }) {
  if (loading && !suggestion) {
    return (
      <section
        className="rounded-xl border border-purple-200 dark:border-purple-900 bg-gradient-to-br from-purple-50 to-fuchsia-50 dark:from-purple-950/40 dark:to-fuchsia-950/30 p-4"
        data-testid="partner-application-ai-suggest"
      >
        <div className="flex items-center gap-2 text-xs text-purple-700 dark:text-purple-300">
          <Loader2 size={13} className="animate-spin" />
          Analysing application against the partner roster…
        </div>
      </section>
    );
  }
  if (!suggestion) return null;
  const style = DECISION_STYLES[suggestion.decision] || DECISION_STYLES.needs_info;
  const Icon = style.icon;
  const confidencePct = Math.round((suggestion.confidence || 0) * 100);
  const isFallback = suggestion.model === 'deterministic-fallback';
  const sameLevel = (suggestion.level || '') === currentLevel;

  return (
    <section
      className="rounded-xl border border-purple-200 dark:border-purple-900 bg-gradient-to-br from-purple-50 to-fuchsia-50 dark:from-purple-950/40 dark:to-fuchsia-950/30 p-4"
      data-testid="partner-application-ai-suggest"
    >
      <div className="flex items-start gap-3">
        <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gradient-to-br ${style.cls} text-[10px] font-extrabold uppercase tracking-wider shadow-sm`}
             data-testid="partner-application-ai-decision">
          <Icon size={11} /> {style.label}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700 dark:text-purple-300 flex items-center gap-1">
              <Wand2 size={10} /> AI Suggest decision
            </span>
            <span className="text-[10px] text-purple-700 dark:text-purple-300 font-mono" data-testid="partner-application-ai-confidence">
              {confidencePct}% confident
            </span>
            {isFallback ? (
              <span className="text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300">
                Heuristic
              </span>
            ) : (
              <span className="text-[10px] text-zinc-500">gpt-4o-mini</span>
            )}
          </div>
          <p className="mt-1 text-sm font-bold text-zinc-900 dark:text-zinc-100" data-testid="partner-application-ai-headline">
            {suggestion.headline || '—'}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh AI suggestion"
          className="p-1.5 rounded-full border border-purple-200 dark:border-purple-800 bg-white/60 dark:bg-zinc-900/60 hover:bg-white dark:hover:bg-zinc-900 disabled:opacity-50"
          data-testid="partner-application-ai-refresh"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="mt-3 grid sm:grid-cols-2 gap-3">
        <div data-testid="partner-application-ai-reasons">
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">Why</div>
          {(suggestion.reasons || []).length ? (
            <ul className="list-disc list-inside text-xs text-zinc-700 dark:text-zinc-200 space-y-0.5">
              {suggestion.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          ) : <div className="text-xs text-zinc-400">No reasoning provided.</div>}
        </div>
        <div data-testid="partner-application-ai-red-flags">
          <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">Red flags</div>
          {(suggestion.red_flags || []).length ? (
            <ul className="list-disc list-inside text-xs text-rose-700 dark:text-rose-300 space-y-0.5">
              {suggestion.red_flags.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          ) : <div className="text-xs text-emerald-700 dark:text-emerald-300">None spotted.</div>}
        </div>
      </div>

      {suggestion.coverage_value ? (
        <div className="mt-3 text-xs text-zinc-700 dark:text-zinc-300 flex items-start gap-2" data-testid="partner-application-ai-coverage">
          <MapPin size={12} className="mt-0.5 text-purple-500" />
          <span><b className="text-purple-700 dark:text-purple-300">Coverage:</b> {suggestion.coverage_value}</span>
        </div>
      ) : null}

      {suggestion.level && !sameLevel ? (
        <div className="mt-3 flex items-center justify-end">
          <button
            type="button"
            onClick={() => onApplyLevel(suggestion.level)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold"
            data-testid="partner-application-ai-apply-level"
          >
            <Sparkles size={11} /> Apply suggested level: {LEVEL_LABELS[suggestion.level] || suggestion.level}
          </button>
        </div>
      ) : null}
    </section>
  );
}
