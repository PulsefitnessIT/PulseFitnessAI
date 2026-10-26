import React, { useState } from 'react';
import { Check, Image as ImageIcon } from 'lucide-react';
import SignatureCanvas from './SignatureCanvas';

const inputCls = 'w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400';
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Build the sign-off payload or return an error message.
export const buildSignoffPayload = ({ draft, signatureData, existing, job }) => {
  if (draft.signature_unavailable) {
    const reason = (draft.signature_reason || '').trim();
    return reason ? { payload: { case_id: job.id, unavailable: true, reason } } : { error: 'Say why the customer could not sign' };
  }
  if (!signatureData) return existing ? { payload: null } : { error: 'Customer signature is required before completing' };
  const name = (draft.signature_name || '').trim();
  if (!name) return { error: "Enter the customer's printed name" };
  const email = (draft.signature_email || '').trim();
  if (email && !EMAIL_RE.test(email)) return { error: 'Enter a valid customer email' };
  return { payload: { case_id: job.id, signed_by_name: name, signed_by_email: email, image_data: signatureData } };
};

export default function CustomerSignOffCard({ draft, setDraft, signatureData, setSignatureData, contact, existing, reopenedAt }) {
  const [showPad, setShowPad] = useState(false);
  const unavailable = !!draft.signature_unavailable;
  const contactEmail = contact?.email || '';
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-2" data-testid="complete-signature-card">
      <p className="text-[11px] uppercase font-bold tracking-wide text-slate-500">Customer sign-off <span className="text-red-500">*</span></p>
      {reopenedAt && !existing && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5" data-testid="complete-signoff-reopened">
          This job was reopened — the earlier sign-off no longer counts. Please capture a fresh customer signature.
        </p>
      )}
      {existing && !signatureData && !unavailable && (
        <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-2 py-1.5" data-testid="complete-signoff-existing">
          {existing.unavailable ? `Recorded: customer unable to sign — ${existing.unavailable_reason}` : `Already signed by ${existing.signed_by_name}`}
        </p>
      )}
      {!unavailable ? (
        <>
          <label className="block text-xs font-semibold text-slate-600">Customer name
            <input className={`${inputCls} mt-1`} value={draft.signature_name || ''} onChange={(e) => setDraft({ signature_name: e.target.value })} placeholder={contact?.name ? `Printed name (e.g. ${contact.name})` : 'Printed name'} data-testid="complete-signed-by" />
          </label>
          <label className="block text-xs font-semibold text-slate-600">Email for the signed report
            <input type="email" className={`${inputCls} mt-1`} value={draft.signature_email || ''} onChange={(e) => setDraft({ signature_email: e.target.value })}
              placeholder={contactEmail ? `Leave blank to use ${contactEmail}` : 'customer@example.com'} data-testid="complete-signed-email" />
            <span className="text-[11px] font-normal text-slate-400">Only if different to the site main contact{contactEmail ? ` (${contactEmail})` : ''}.</span>
          </label>
          <button type="button" onClick={() => setShowPad(true)} className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold" data-testid="complete-open-signature">
            {signatureData ? <><Check size={14} className="text-emerald-600" /> Signature captured · re-sign</> : <><ImageIcon size={14} /> Capture customer signature</>}
          </button>
          {showPad && <SignatureCanvas onSubmit={(d) => { setSignatureData(d); setShowPad(false); }} onCancel={() => setShowPad(false)} />}
          <button type="button" className="text-xs text-slate-500 underline" onClick={() => setDraft({ signature_unavailable: true })} data-testid="complete-sig-unavailable">Customer not available to sign?</button>
        </>
      ) : (
        <>
          <label className="block text-xs font-semibold text-slate-600">Why couldn't the customer sign?
            <input className={`${inputCls} mt-1`} value={draft.signature_reason || ''} onChange={(e) => setDraft({ signature_reason: e.target.value })} placeholder="e.g. Site unmanned, key-holder left" data-testid="complete-sig-reason" />
          </label>
          <button type="button" className="text-xs text-slate-500 underline" onClick={() => setDraft({ signature_unavailable: false })} data-testid="complete-sig-capture-instead">Capture a signature instead</button>
        </>
      )}
    </div>
  );
}
