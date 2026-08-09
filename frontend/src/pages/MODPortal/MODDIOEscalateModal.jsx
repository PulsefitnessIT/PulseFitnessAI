import { useState } from 'react';
import axios from 'axios';
import { ShieldCheck, X, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';

/**
 * In-platform "Report to DIO" modal. Replaces the old window.prompt().
 * Lets the user add an optional escalation note AND set/confirm the DIO
 * contact email (persisted server-side if the site had none on file).
 */
export function MODDIOEscalateModal({ open, onClose, api, faultId, ticketRef, existingDioEmail = '', onEscalated }) {
  const [note, setNote] = useState('');
  const [email, setEmail] = useState(existingDioEmail || '');
  const [submitting, setSubmitting] = useState(false);
  if (!open) return null;

  const submit = async () => {
    const target = (email || '').trim();
    if (!existingDioEmail && (!target || !target.includes('@'))) {
      notify.error('Enter a DIO contact email to send this escalation to');
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${api}/mod/site/faults/${faultId}/escalate-to-dio`,
        { note: (note || '').slice(0, 2000), dio_email: target || undefined },
        { headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } },
      );
      notify.success('Escalated to DIO', `Sent to ${r.data.escalated_to}.`);
      onEscalated?.(r.data);
      onClose?.();
    } catch (e) {
      notify.error('Escalation failed', e?.response?.data?.detail || 'Could not escalate');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-black/80 backdrop-blur-sm p-4" data-testid="mod-dio-escalate-modal">
      <div className="w-full max-w-md rounded-2xl border bg-white text-zinc-900 shadow-2xl overflow-hidden" style={{ borderColor: '#a5f3fc' }}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-cyan-100 bg-cyan-50">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-cyan-700" />
            <div>
              <div className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-cyan-700">Report to DIO</div>
              <div className="text-sm font-bold text-zinc-900">{ticketRef || 'Escalate fault'}</div>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-full hover:bg-cyan-100 text-cyan-700" data-testid="mod-dio-modal-close"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">DIO contact email {existingDioEmail ? '' : '*'}</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="dio.contact@mod.gov.uk"
              className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-500"
              data-testid="mod-dio-modal-email"
            />
            <p className="text-[11px] text-zinc-500 mt-1">
              {existingDioEmail
                ? 'Pre-filled from the site DIO contract — change it to send elsewhere.'
                : "No DIO contact on file for this site. Enter one — we'll save it so you're not asked again."}
            </p>
          </div>
          <div>
            <label className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">Escalation note (optional)</label>
            <textarea
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value.slice(0, 2000))}
              placeholder="Add any context the DIO needs — impact, urgency, access constraints…"
              className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2.5 text-sm focus:outline-none focus:border-cyan-500"
              data-testid="mod-dio-modal-note"
            />
            <div className="text-[10px] text-zinc-400 text-right mt-0.5">{note.length} / 2000</div>
          </div>
        </div>
        <div className="px-5 py-3 border-t border-zinc-100 flex justify-end gap-2 bg-zinc-50">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-bold border border-zinc-300 text-zinc-700 hover:bg-zinc-100" data-testid="mod-dio-modal-cancel">Cancel</button>
          <button onClick={submit} disabled={submitting} className="px-4 py-2 rounded-lg text-sm font-extrabold bg-cyan-600 hover:bg-cyan-700 text-white flex items-center gap-1.5 disabled:opacity-50" data-testid="mod-dio-modal-submit">
            {submitting ? <><Loader2 size={14} className="animate-spin" /> Sending…</> : <><ShieldCheck size={14} /> Report to DIO</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default MODDIOEscalateModal;
