/**
 * PartnerAvailabilityCard.js (iter 216h288 — Gap 10)
 *
 * Dashboard widget for a Partner Engineer to flip themselves
 * between "Available" and "Unavailable" (annual leave, parental
 * leave, full diary). Per the BA-audit decision (2C), unavailable
 * engineers are still surfaced on discovery pages but with a yellow
 * "Back on …" badge so existing customers see the relationship is
 * still there — they're just on leave.
 *
 * Backend: PUT /partners/me/availability
 */
import { useState } from 'react';
import axios from 'axios';
import { CalendarOff, Sparkles, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL;

function formatBackOn(iso) {
  if (!iso) return null;
  try {
    return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch { return iso; }
}

export default function PartnerAvailabilityCard({ partner, onChanged }) {
  const initial = partner?.availability || { status: 'available', resumes_on: null, note: null };
  const [status, setStatus] = useState(initial.status || 'available');
  const [resumesOn, setResumesOn] = useState(initial.resumes_on || '');
  const [note, setNote] = useState(initial.note || '');
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(false);

  const isUnavailable = status === 'unavailable';
  const liveBackOn = formatBackOn(initial.resumes_on);

  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const save = async (override) => {
    setBusy(true);
    try {
      const payload = override !== undefined
        ? { available: override, resumes_on: null, note: null }
        : { available: !isUnavailable ? false : true, resumes_on: resumesOn || null, note: (note || '').trim() || null };
      const r = await axios.put(`${API}/api/partners/me/availability`, payload, { headers });
      const newAv = r.data.availability;
      setStatus(newAv.status);
      setResumesOn(newAv.resumes_on || '');
      setNote(newAv.note || '');
      setDraft(false);
      notify.success(newAv.status === 'available'
        ? 'You are accepting work again'
        : 'Marked as unavailable');
      if (onChanged) onChanged(newAv);
    } catch (e) {
      notifyApiError(notify, e, 'Could not update availability');
    } finally { setBusy(false); }
  };

  return (
    <div className={`rounded-xl border overflow-hidden ${
      isUnavailable
        ? 'border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800/60'
        : 'border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900'
    }`}
         data-testid="partner-availability-card">
      <div className="px-4 py-3 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-800">
        {isUnavailable ? (
          <CalendarOff size={16} className="text-amber-600 dark:text-amber-400" />
        ) : (
          <Sparkles size={16} className="text-emerald-600 dark:text-emerald-400" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">
            {isUnavailable ? 'You are marked unavailable' : 'Accepting new work'}
          </p>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {isUnavailable
              ? (liveBackOn ? `Back on ${liveBackOn}` : 'Resume date not set')
              : 'Gyms can find you in the Engineer network'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => save(isUnavailable)}
          disabled={busy}
          className={`px-3 py-1.5 text-[11px] font-bold rounded inline-flex items-center gap-1 disabled:opacity-50 ${
            isUnavailable
              ? 'bg-emerald-600 text-white hover:bg-emerald-700'
              : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700'
          }`}
          data-testid="partner-availability-toggle"
        >
          {busy && <Loader2 size={11} className="animate-spin" />}
          {isUnavailable ? (<><CheckCircle2 size={11} /> Back on now</>) : 'Go unavailable'}
        </button>
      </div>

      {/* Inline editor for the 'back on' date + note. Always available — engineers can
          fine-tune even while currently available (will apply on next 'Go unavailable'). */}
      {(isUnavailable || draft) && (
        <div className="px-4 py-3 space-y-2.5" data-testid="partner-availability-editor">
          <div className="grid sm:grid-cols-2 gap-2.5">
            <label className="block">
              <span className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">Back on (optional)</span>
              <input
                type="date"
                value={resumesOn}
                onChange={(e) => setResumesOn(e.target.value)}
                className="w-full border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1.5 text-sm bg-white dark:bg-zinc-900"
                data-testid="partner-availability-resumes-on"
              />
            </label>
            <label className="block">
              <span className="block text-[11px] font-semibold text-zinc-700 dark:text-zinc-300 mb-1">Public note (optional, 200 chars)</span>
              <input
                type="text"
                value={note}
                maxLength={200}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. On annual leave"
                className="w-full border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1.5 text-sm bg-white dark:bg-zinc-900"
                data-testid="partner-availability-note"
              />
            </label>
          </div>
          {isUnavailable && (
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => save()}
                disabled={busy}
                className="px-2.5 py-1 text-[11px] font-bold text-white rounded disabled:opacity-50 inline-flex items-center gap-1"
                style={{ background: '#0891b2' }}
                data-testid="partner-availability-save"
              >
                {busy ? <Loader2 size={11} className="animate-spin" /> : <AlertTriangle size={11} />} Save details
              </button>
            </div>
          )}
        </div>
      )}

      {!isUnavailable && !draft && (
        <button
          type="button"
          onClick={() => setDraft(true)}
          className="w-full px-4 py-2 text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 text-left border-t border-zinc-100 dark:border-zinc-800"
          data-testid="partner-availability-plan-leave"
        >
          Plan upcoming leave →
        </button>
      )}
    </div>
  );
}
