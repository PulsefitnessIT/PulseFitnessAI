/**
 * MOD Personal-Incident wizard (RIDDOR).
 *
 * Iter 216h117 — P1 #3. Distinct from the Fault wizard because
 * incidents:
 *   • are about a PERSON not a piece of kit;
 *   • route to the base H&S officer (not engineering);
 *   • may be RIDDOR-reportable to the HSE.
 *
 * Triggered from the MOD site dashboard via a dedicated "Report
 * incident" button. Returns the incident_ref + RIDDOR verdict.
 */
import { useState } from 'react';
import axios from 'axios';
import { AlertTriangle, ShieldAlert, Loader2, X, Check } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

const CATEGORIES = [
  { value: 'slip', label: 'Slip' },
  { value: 'trip', label: 'Trip' },
  { value: 'impact', label: 'Impact / collision' },
  { value: 'electric', label: 'Electric shock' },
  { value: 'cardiac', label: 'Cardiac event' },
  { value: 'equipment', label: 'Equipment-related' },
  { value: 'other', label: 'Other' },
];

const SEVERITIES = [
  { value: 'none', label: 'No injury' },
  { value: 'first_aid', label: 'First aid only' },
  { value: 'medical', label: 'Medical attention' },
  { value: 'hospitalised', label: 'Hospitalised' },
  { value: 'life_changing', label: 'Life-changing' },
  { value: 'fatal', label: 'Fatal' },
];

const PARTY_TYPES = [
  { value: 'service', label: 'Service personnel' },
  { value: 'civilian', label: 'Civilian (e.g. PTI)' },
  { value: 'contractor', label: 'Contractor' },
  { value: 'public', label: 'Public / visitor' },
];

const SEVERITY_RIDDOR_HINT = new Set(['hospitalised', 'life_changing', 'fatal']);

export default function MODIncidentWizard({ onClose, onSubmitted }) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
  const headers = { Authorization: `Bearer ${token}` };
  const [form, setForm] = useState({
    category: 'slip',
    injury_severity: 'first_aid',
    injured_party_type: 'service',
    description: '',
    injured_party_name: '',
    reporter_name: '',
    reporter_email: '',
    reporter_phone: '',
    occurred_at: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [triedSubmit, setTriedSubmit] = useState(false); // highlight missing fields after a blocked submit

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const isRiddorHinted = SEVERITY_RIDDOR_HINT.has(form.injury_severity)
    || (form.injury_severity === 'medical' && ['electric', 'cardiac'].includes(form.category));

  // Which fields are still missing/invalid — shown inline once the user has
  // attempted to submit (triedSubmit), so nothing is a mystery.
  const fieldErrors = {
    description: form.description.trim().length < 20,
    injured_party_name: form.injured_party_name.trim().length < 2,
    reporter_name: form.reporter_name.trim().length < 2,
    reporter_email: !form.reporter_email.includes('@'),
  };
  const firstErrorMsg = () => {
    if (fieldErrors.description) return 'Description must be at least 20 characters.';
    if (fieldErrors.injured_party_name) return 'Injured-party name is required.';
    if (fieldErrors.reporter_name) return 'Reporter name is required.';
    if (fieldErrors.reporter_email) return 'Reporter email looks invalid.';
    return '';
  };
  const showErr = (k) => triedSubmit && fieldErrors[k];

  const submit = async () => {
    setError(null);
    if (Object.values(fieldErrors).some(Boolean)) {
      setTriedSubmit(true);
      const msg = firstErrorMsg();
      setError(msg);
      notify.error(msg);
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/mod/site/incidents`, {
        ...form,
        occurred_at: form.occurred_at || null,
      }, { headers });
      setResult(r.data);
      notify.success(`Incident ${r.data.incident_ref} logged`);
      if (onSubmitted) onSubmitted(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not log incident');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-black/80 backdrop-blur-sm p-4" data-testid="mod-incident-wizard">
      <div className="w-full max-w-lg rounded-2xl overflow-hidden border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <header className="px-5 py-4 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--theme-border)', background: 'rgba(220,38,38,0.08)' }}>
          <div>
            <div className="text-[10px] font-extrabold uppercase tracking-[0.3em] text-rose-500 dark:text-rose-300">
              Pulse Fitness · MOD Service · Personal incident
            </div>
            <h3 className="text-base font-extrabold mt-1" style={{ color: 'var(--theme-text)' }} data-testid="mod-incident-wizard-title">
              Report a personal incident
            </h3>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              For injuries to a person. Equipment-only faults belong in the Fault wizard.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-incident-close">
            <X size={16} />
          </button>
        </header>

        <div className="p-5 space-y-3 max-h-[70vh] overflow-y-auto">
          {result ? (
            <div className="space-y-3" data-testid="mod-incident-result">
              <div className="flex items-center gap-2 text-emerald-500 dark:text-emerald-400 font-bold">
                <Check size={16} /> Incident {result.incident_ref} logged
              </div>
              {result.riddor_reportable ? (
                <div className="rounded-lg border border-rose-400/40 bg-rose-500/10 p-3 text-sm text-rose-600 dark:text-rose-200" data-testid="mod-incident-riddor-warning">
                  <ShieldAlert size={14} className="inline -mt-0.5 mr-1" />
                  This incident has been auto-flagged as <strong>RIDDOR-reportable</strong>. A 7-day
                  follow-up reminder will fire. File F2508 with HSE if you haven't already.
                </div>
              ) : (
                <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>RIDDOR-reportable: <strong style={{ color: 'var(--theme-text)' }}>No</strong></p>
              )}
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Recipients: {result.recipients?.join(', ') || '—'}</p>
              <button onClick={onClose} className="w-full py-2 rounded-md font-bold text-sm border" style={{ background: 'var(--theme-surface-3)', color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} data-testid="mod-incident-done">
                Done
              </button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Category">
                  <select value={form.category} onChange={(e) => set('category', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-category">
                    {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </Field>
                <Field label="Injury severity">
                  <select value={form.injury_severity} onChange={(e) => set('injury_severity', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-severity">
                    {SEVERITIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </Field>
                <Field label="Injured party (name or ID)" required error={showErr('injured_party_name')} hint="required">
                  <input type="text" value={form.injured_party_name} onChange={(e) => set('injured_party_name', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-party-name" />
                </Field>
                <Field label="Party type">
                  <select value={form.injured_party_type} onChange={(e) => set('injured_party_type', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-party-type">
                    {PARTY_TYPES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select>
                </Field>
                <Field label="Reporter name" required error={showErr('reporter_name')} hint="required">
                  <input type="text" value={form.reporter_name} onChange={(e) => set('reporter_name', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-reporter-name" />
                </Field>
                <Field label="Reporter email" required error={showErr('reporter_email')} hint="add a valid email">
                  <input type="email" value={form.reporter_email} onChange={(e) => set('reporter_email', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-reporter-email" />
                </Field>
                <Field label="Reporter phone (optional)">
                  <input type="tel" value={form.reporter_phone} onChange={(e) => set('reporter_phone', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-reporter-phone" />
                </Field>
                <Field label="Occurred at (optional)">
                  <input type="datetime-local" value={form.occurred_at} onChange={(e) => set('occurred_at', e.target.value)} className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)]" data-testid="mod-incident-occurred" />
                </Field>
              </div>
              <Field label="Description" required error={showErr('description')} hint={`needs ${Math.max(0, 20 - form.description.trim().length)} more characters`}>
                <textarea value={form.description} onChange={(e) => set('description', e.target.value)} rows={4} placeholder="What happened? Be factual. (min 20 chars)" className="w-full bg-[var(--theme-surface-2)] border border-[var(--theme-border)] rounded-md px-2 py-1.5 text-sm text-[var(--theme-text)] focus:outline-none focus:border-[var(--color-brand-cyan)] placeholder-[var(--theme-text-muted)]" data-testid="mod-incident-description" />
                <div className="flex justify-between text-[10px] mt-1">
                  <span className={form.description.length >= 20 ? 'text-emerald-500 dark:text-emerald-400' : ''} style={form.description.length >= 20 ? {} : { color: showErr('description') ? '#f43f5e' : 'var(--theme-text-muted)' }}>
                    {form.description.length} / 20 minimum
                  </span>
                  <span className="text-amber-600 dark:text-amber-400/90 font-semibold">
                    ◆ OFFICIAL-SENSITIVE ceiling — no NSN, op names, callsigns or personal data above OFFICIAL-SENSITIVE.
                  </span>
                </div>
              </Field>
              {isRiddorHinted && (
                <div className="rounded-md border border-rose-400/40 bg-rose-500/10 p-2.5 text-[11px] text-rose-600 dark:text-rose-200 flex items-start gap-2" data-testid="mod-incident-riddor-hint">
                  <ShieldAlert size={13} className="mt-0.5 shrink-0" />
                  <div>Based on category + severity, this is likely <strong>RIDDOR-reportable</strong>. The on-call mailbox and DIO will be notified automatically.</div>
                </div>
              )}
              {error && (
                <div className="flex items-start gap-2 text-rose-600 dark:text-rose-300 text-xs" data-testid="mod-incident-error">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {error}
                </div>
              )}
              <button
                type="button"
                onClick={submit}
                disabled={submitting}
                className="w-full py-3 rounded-lg font-extrabold uppercase tracking-wider text-sm bg-rose-500 hover:bg-rose-600 text-white disabled:opacity-50"
                data-testid="mod-incident-submit"
              >
                {submitting ? <Loader2 size={14} className="animate-spin mx-auto" /> : 'Log incident'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children, required, error, hint }) {
  return (
    <div>
      <label className="block text-[10px] font-extrabold uppercase tracking-wider mb-1" style={{ color: error ? '#f43f5e' : 'var(--theme-text-muted)' }}>
        {label}{required ? ' *' : ''}{error && hint ? <span className="normal-case tracking-normal"> · {hint}</span> : ''}
      </label>
      <div className={error ? 'rounded-md ring-1 ring-rose-500/70' : ''}>
        {children}
      </div>
    </div>
  );
}
