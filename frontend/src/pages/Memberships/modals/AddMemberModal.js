/**
 * AddMemberModal — Memberships console.
 *
 * Iter 215bv — extracted from MembershipsConsole.js (was inline). Since
 * iter 215bq this modal captures the same 14+ profile fields as the
 * Edit Member drawer (Profile tab) so studios can record everything in
 * one go on creation. Backend persists the full set via
 * POST /api/memberships/members.
 */
import React, { useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ModalShell, Input, ModalActions } from '@/pages/Memberships/_shared';

const POSTCODE_API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function AddMemberModal({ API, headers, onClose }) {
  const [f, setF] = useState({
    first_name: '', last_name: '', email: '', phone: '',
    dob: '',
    address_line1: '', address_line2: '', city: '', postcode: '', country: '',
    emergency_contact_name: '', emergency_contact_phone: '',
    notes: '',
    tags: [],
  });
  const [saving, setSaving] = useState(false);

  // Iter 215et — postcode-on-blur lookup to auto-fill city/country
  const lookupPostcode = async (pc) => {
    const trimmed = (pc || '').trim();
    if (!trimmed || trimmed.replace(/\s+/g, '').length < 5) return;
    try {
      const r = await axios.get(`${POSTCODE_API}/integrations/postcode/lookup`, { params: { postcode: trimmed } });
      if (r.data?.found) {
        setF(prev => ({
          ...prev,
          postcode: r.data.postcode || prev.postcode,
          city: prev.city || r.data.city || '',
          country: prev.country || r.data.country || 'United Kingdom',
        }));
      }
    } catch { /* silent */ }
  };

  const submit = async () => {
    if (!f.email || !f.first_name) { notify.error('Name + email required'); return; }
    setSaving(true);
    try {
      // Drop empty strings so the backend's optional fields stay null.
      const payload = Object.fromEntries(
        Object.entries(f).filter(([, v]) => v !== '' && !(Array.isArray(v) && v.length === 0))
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
        <Input label="Email"      value={f.email}      onChange={(v) => setF({ ...f, email: v })} type="email" required testid="mbr-new-email" />
        <Input label="Phone"      value={f.phone}      onChange={(v) => setF({ ...f, phone: v })} testid="mbr-new-phone" />
      </div>

      <Input label="Date of birth" type="date" value={(f.dob || '').slice(0, 10)} onChange={(v) => setF({ ...f, dob: v })} testid="mbr-new-dob" />

      {/* Address — same shape as the edit drawer */}
      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Address</p>
        <div className="space-y-2">
          <Input label={null} value={f.address_line1} onChange={(v) => setF({ ...f, address_line1: v })} placeholder="Address line 1" testid="mbr-new-addr1" />
          <Input label={null} value={f.address_line2} onChange={(v) => setF({ ...f, address_line2: v })} placeholder="Address line 2 (optional)" testid="mbr-new-addr2" />
          <div className="grid grid-cols-3 gap-2">
            <Input label={null} value={f.city}     onChange={(v) => setF({ ...f, city: v })}     placeholder="City" testid="mbr-new-city" />
            <Input label={null} value={f.postcode} onChange={(v) => setF({ ...f, postcode: v })} onBlur={(e) => lookupPostcode(e.target.value)} placeholder="Postcode" testid="mbr-new-postcode" />
            <Input label={null} value={f.country}  onChange={(v) => setF({ ...f, country: v })}  placeholder="Country" testid="mbr-new-country" />
          </div>
        </div>
      </div>

      {/* Emergency contact */}
      <div className="pt-1">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Emergency contact</p>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Name"  value={f.emergency_contact_name}  onChange={(v) => setF({ ...f, emergency_contact_name: v })}  testid="mbr-new-eg-name" />
          <Input label="Phone" value={f.emergency_contact_phone} onChange={(v) => setF({ ...f, emergency_contact_phone: v })} testid="mbr-new-eg-phone" />
        </div>
      </div>

      <Input
        label="Notes (operator-only)"
        value={f.notes}
        onChange={(v) => setF({ ...f, notes: v })}
        testid="mbr-new-notes"
      />
      <Input
        label="Tags (comma-separated)"
        value={(f.tags || []).join(', ')}
        onChange={(v) => setF({ ...f, tags: v.split(',').map((t) => t.trim()).filter(Boolean) })}
        placeholder="e.g. corporate, vip, swim-only"
        testid="mbr-new-tags"
      />

      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-new-save" />
    </ModalShell>
  );
}
