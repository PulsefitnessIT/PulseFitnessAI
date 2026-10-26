import React from 'react';
import SignaturePad from './SignaturePad';
import { inputCls } from '../ui';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// value: {name, email, role, image, unavailable, reason}
export const signoffBody = (v) => {
  if (v.unavailable) return (v.reason || '').trim() ? { body: { unavailable: true, reason: v.reason.trim() } } : { error: "Say why the customer couldn't sign" };
  if (!v.image) return { error: 'Customer signature is required' };
  if (!(v.name || '').trim()) return { error: "Enter the customer's printed name" };
  if (v.email && !EMAIL_RE.test(v.email.trim())) return { error: 'Enter a valid customer email' };
  return { body: { signed_by_name: v.name.trim(), signed_by_email: (v.email || '').trim(), signed_by_role: (v.role || '').trim(), image_data: v.image } };
};

export default function SignOffFields({ value, onChange, contact, testid = 'signoff' }) {
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <div className="pt-1 space-y-2" data-testid={testid}>
      <p className="text-xs font-semibold text-slate-400 uppercase">Customer sign-off <span className="text-red-500">*</span></p>
      {!value.unavailable ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs font-semibold text-slate-600">Customer name<input className={`${inputCls} mt-1`} placeholder="Printed name" value={value.name || ''} onChange={(e) => set({ name: e.target.value })} data-testid={`${testid}-name`} /></label>
            <label className="text-xs font-semibold text-slate-600">Role<input className={`${inputCls} mt-1`} placeholder="e.g. PTI" value={value.role || ''} onChange={(e) => set({ role: e.target.value })} data-testid={`${testid}-role`} /></label>
          </div>
          <label className="block text-xs font-semibold text-slate-600">Email for the signed report</label>
          <input type="email" className={inputCls} value={value.email || ''} onChange={(e) => set({ email: e.target.value })}
            placeholder={contact?.email ? `Email (blank = ${contact.email})` : 'Email for the signed report'} data-testid={`${testid}-email`} />
          <p className="text-[11px] text-slate-400">Email only if different to the site main contact.</p>
          <SignaturePad onChange={(d) => set({ image: d })} />
          <button type="button" className="text-xs text-slate-500" onClick={() => set({ unavailable: true })} data-testid={`${testid}-unavailable`}>Customer not available to sign?</button>
        </>
      ) : (
        <>
          <input className={inputCls} placeholder="Why couldn't the customer sign?" value={value.reason || ''} onChange={(e) => set({ reason: e.target.value })} data-testid={`${testid}-reason`} />
          <button type="button" className="text-xs text-slate-500" onClick={() => set({ unavailable: false })} data-testid={`${testid}-capture-instead`}>Capture a signature instead</button>
        </>
      )}
    </div>
  );
}
