/**
 * AddMemberModal — Memberships console.
 *
 * Iter 215bv — extracted from MembershipsConsole.js (was inline). Since
 * iter 215bq this modal captures the same 14+ profile fields as the
 * Edit Member drawer (Profile tab) so studios can record everything in
 * one go on creation.
 *
 * Iter 216h200 — Craig's UX pass (May 18 2026):
 *   • Email format validation (server-side + client-side).
 *   • Phone is now mandatory (asterisked + form-level guard).
 *   • Date of birth uses the shared DatePicker (DD/MM/YYYY) instead of
 *     the native `<input type="date">` which Craig flagged as "clunky".
 *   • Postcode auto-uppercases + drives city/country auto-fill on blur.
 *   • Emergency contact phone is now mandatory.
 *   • Notes (operator-only) is collapsed behind a "+ Add note" toggle
 *     so the modal feels lean when not relevant.
 *   • GDPR: explicit T&Cs acceptance (required) + marketing consent
 *     (opt-in). Server rejects POST without `gdpr_consent: true`.
 */
import { useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ModalShell, Input, ModalActions } from '@/pages/Memberships/_shared';
import { COUNTRIES } from '@/utils/crmDropdowns';
import DatePicker from '@/components/shared/DatePicker';
import { ModalErrorBoundary } from '@/components/shared/ModalErrorBoundary';

const POSTCODE_API = process.env.REACT_APP_BACKEND_URL + '/api';
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function AddMemberModal({ API, headers, onClose }) {
  return (
    <ModalErrorBoundary label="Add member" onClose={() => onClose?.(false)}>
      <AddMemberModalInner API={API} headers={headers} onClose={onClose} />
    </ModalErrorBoundary>
  );
}

function AddMemberModalInner({ API, headers, onClose }) {
  const [f, setF] = useState({
    first_name: '', last_name: '', email: '', phone: '',
    dob: '',
    address_line1: '', address_line2: '', city: '', postcode: '', country: '',
    emergency_contact_name: '', emergency_contact_phone: '',
    notes: '',
    tags: [],
    gdpr_consent: false,
    marketing_consent: false,
  });
  const [showNotes, setShowNotes] = useState(false);
  const [emailErr, setEmailErr] = useState('');
  const [saving, setSaving] = useState(false);

  // Iter 215et — postcode-on-blur lookup to auto-fill city/country.
  // Iter 216h200 — also canonicalises the postcode to uppercase so the
  // value is consistent for search + reporting.
  const lookupPostcode = async (pc) => {
    const trimmed = (pc || '').trim().toUpperCase();
    if (!trimmed) return;
    setF(prev => ({ ...prev, postcode: trimmed }));
    if (trimmed.replace(/\s+/g, '').length < 5) return;
    try {
      const r = await axios.get(`${POSTCODE_API}/integrations/postcode/lookup`, { params: { postcode: trimmed } });
      if (r.data?.found) {
        setF(prev => ({
          ...prev,
          postcode: (r.data.postcode || prev.postcode).toUpperCase(),
          city: prev.city || r.data.city || '',
          country: prev.country || r.data.country || 'United Kingdom',
        }));
      }
    } catch { /* silent — server will revalidate on POST */ }
  };

  const submit = async () => {
    // Iter 216h200 — client-side form gate so the server only sees
    // clean data. Each branch surfaces a specific testable message.
    if (!f.first_name.trim()) { notify.error('First name required'); return; }
    if (!f.email.trim()) { notify.error('Email required'); return; }
    if (!EMAIL_RE.test(f.email.trim())) {
      setEmailErr('Enter a valid email address (e.g. name@example.com)');
      notify.error('Invalid email format');
      return;
    }
    if (!f.phone.trim()) { notify.error('Phone number required'); return; }
    if (!f.emergency_contact_phone.trim()) {
      notify.error('Emergency contact phone required'); return;
    }
    if (!f.gdpr_consent) {
      notify.error('Member must accept T&Cs (GDPR) before saving'); return;
    }
    setEmailErr('');
    setSaving(true);
    try {
      // Drop empty strings so the backend's optional fields stay null,
      // but always send the consent booleans (even when false).
      const payload = Object.fromEntries(
        Object.entries(f).filter(([k, v]) => {
          if (k === 'gdpr_consent' || k === 'marketing_consent') return true;
          return v !== '' && !(Array.isArray(v) && v.length === 0);
        })
      );
      await axios.post(`${API}/memberships/members`, payload, { headers });
      try { window.dispatchEvent(new CustomEvent('gymaxis:member-added')); } catch (_) {}
      notify.success('Member added');
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell onClose={() => onClose(false)} title="Add member" eyebrow="New record" testId="mbr-add-modal" wide>
      {/* Identity */}
      <div className="grid grid-cols-2 gap-3">
        <Input label="First name" value={f.first_name} onChange={(v) => setF({ ...f, first_name: v })} required testid="mbr-new-first" />
        <Input label="Last name"  value={f.last_name}  onChange={(v) => setF({ ...f, last_name: v })} testid="mbr-new-last" />
        <div>
          <Input
            label="Email"
            value={f.email}
            onChange={(v) => { setF({ ...f, email: v }); if (emailErr) setEmailErr(''); }}
            onBlur={(e) => {
              const v = (e?.target?.value || '').trim();
              if (v && !EMAIL_RE.test(v)) setEmailErr('Enter a valid email address');
            }}
            type="email"
            required
            testid="mbr-new-email"
          />
          {emailErr && (
            <p data-testid="mbr-new-email-error" className="text-[11px] mt-1 text-red-400 font-semibold">
              {emailErr}
            </p>
          )}
        </div>
        <Input label="Phone" value={f.phone} onChange={(v) => setF({ ...f, phone: v })} required placeholder="+44 7700 900000" testid="mbr-new-phone" />
      </div>

      {/* Date of birth — Iter 216h200 uses the shared DatePicker for DD/MM/YYYY consistency. */}
      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Date of birth</p>
        <DatePicker
          value={(f.dob || '').slice(0, 10)}
          onChange={(iso) => setF({ ...f, dob: iso })}
          maxDate={new Date().toISOString().slice(0, 10)}
          testid="mbr-new-dob"
        />
      </div>

      {/* Address — same shape as the edit drawer */}
      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Address</p>
        <div className="space-y-2">
          <Input label={null} value={f.address_line1} onChange={(v) => setF({ ...f, address_line1: v })} placeholder="Address line 1" testid="mbr-new-addr1" />
          <Input label={null} value={f.address_line2} onChange={(v) => setF({ ...f, address_line2: v })} placeholder="Address line 2 (optional)" testid="mbr-new-addr2" />
          <div className="grid grid-cols-3 gap-2">
            <Input label={null} value={f.city}     onChange={(v) => setF({ ...f, city: v })}     placeholder="City" testid="mbr-new-city" />
            <Input
              label={null}
              value={f.postcode}
              onChange={(v) => setF({ ...f, postcode: v.toUpperCase() })}
              onBlur={(e) => lookupPostcode(e.target.value)}
              placeholder="Postcode (e.g. SW1A 1AA)"
              testid="mbr-new-postcode"
            />
            <Input label={null} value={f.country}  onChange={(v) => setF({ ...f, country: v })}  placeholder="Country" list="mbr-new-country-list" testid="mbr-new-country" />
          </div>
          <datalist id="mbr-new-country-list">
            {COUNTRIES.map((c) => <option key={c} value={c} />)}
          </datalist>
        </div>
      </div>

      {/* Emergency contact */}
      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Emergency contact</p>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name"  value={f.emergency_contact_name}  onChange={(v) => setF({ ...f, emergency_contact_name: v })}  testid="mbr-new-eg-name" />
          <Input label="Phone" value={f.emergency_contact_phone} onChange={(v) => setF({ ...f, emergency_contact_phone: v })} required testid="mbr-new-eg-phone" />
        </div>
      </div>

      {/* Notes — Iter 216h200 collapsed by default per Craig's "hide if not relevant". */}
      <div className="pt-1">
        {showNotes ? (
          <Input
            label="Notes (operator-only)"
            value={f.notes}
            onChange={(v) => setF({ ...f, notes: v })}
            testid="mbr-new-notes"
          />
        ) : (
          <button
            type="button"
            data-testid="mbr-new-notes-toggle"
            onClick={() => setShowNotes(true)}
            className="text-[11px] font-semibold text-[color:var(--color-brand-cyan)] hover:underline"
          >
            + Add an operator-only note
          </button>
        )}
      </div>

      <Input
        label="Tags (comma-separated)"
        value={(f.tags || []).join(', ')}
        onChange={(v) => setF({ ...f, tags: v.split(',').map((t) => t.trim()).filter(Boolean) })}
        placeholder="e.g. corporate, vip, swim-only"
        testid="mbr-new-tags"
      />

      {/* GDPR consent — Iter 216h200. T&Cs required; marketing opt-in. */}
      <div className="pt-1 border-t border-[color:var(--theme-border)] mt-2">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2 mt-2">Consent</p>
        <label className="flex items-start gap-2 text-xs leading-snug cursor-pointer mb-2" data-testid="mbr-new-gdpr-label">
          <input
            type="checkbox"
            checked={f.gdpr_consent}
            onChange={(e) => setF({ ...f, gdpr_consent: e.target.checked })}
            className="mt-0.5"
            data-testid="mbr-new-gdpr-consent"
            aria-required
          />
          <span>
            <span className="font-semibold">Member accepts the Terms &amp; Conditions and Privacy Policy.</span>
            {' '}<span className="text-[color:var(--theme-text-muted)]">Required. Records the operator + timestamp on save.</span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-xs leading-snug cursor-pointer" data-testid="mbr-new-marketing-label">
          <input
            type="checkbox"
            checked={f.marketing_consent}
            onChange={(e) => setF({ ...f, marketing_consent: e.target.checked })}
            className="mt-0.5"
            data-testid="mbr-new-marketing-consent"
          />
          <span>
            <span className="font-semibold">Member opts in to marketing communications.</span>
            {' '}<span className="text-[color:var(--theme-text-muted)]">Optional. Member can revoke any time from their portal.</span>
          </span>
        </label>
      </div>

      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-new-save" />
    </ModalShell>
  );
}
