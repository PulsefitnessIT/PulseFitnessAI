import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Gift, Loader2, CheckCircle2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// Shown in Plan & Billing to Lite owners whose one free Pulse Pro trial is used.
export default function TrialRequestCard() {
  const { user } = useAuth();
  const [trial, setTrial] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const isLiteOwner = (user?.account_type || '').toLowerCase() === 'lite' && (user?.role || '').toLowerCase() === 'owner';
  const headers = { Authorization: `Bearer ${localStorage.getItem('token') || ''}` };

  useEffect(() => {
    if (!isLiteOwner) return;
    axios.get(`${API}/api/me/pro-trial`, { headers }).then((r) => setTrial(r.data)).catch(() => setTrial(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- headers rebuilt each render
  }, [isLiteOwner]);

  if (!isLiteOwner || !trial || trial.available) return null;

  const send = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/me/pro-trial/request`, { note }, { headers });
      setTrial({ ...trial, requested_at: r.data.requested_at });
      notify.success('Request sent', 'The Pulse team will be in touch about another free trial.');
    } catch (e) { notifyApiError(notify, e, 'Could not send the request'); }
    setBusy(false);
  };

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border, #e4e4e7)' }} data-testid="trial-request-card">
      <p className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
        <Gift size={15} /> Free Pulse Pro trial already used
      </p>
      {trial.requested_at ? (
        <p className="text-xs mt-1.5 flex items-center gap-1 text-emerald-600" data-testid="trial-request-sent">
          <CheckCircle2 size={13} /> Request sent {new Date(trial.requested_at).toLocaleDateString()} — we'll be in touch.
        </p>
      ) : (
        <>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted, #71717a)' }}>
            Need more time to try Memberships, Marketing or CRM? Ask the Pulse team for another trial.
          </p>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500}
            placeholder="Optional — tell us what you'd like to try"
            className="mt-2 w-full rounded-md border px-2.5 py-1.5 text-sm bg-transparent" data-testid="trial-request-note" />
          <button type="button" onClick={send} disabled={busy}
            className="mt-2 inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-semibold"
            style={{ background: '#f59e0b', color: '#18181b' }} data-testid="trial-request-btn">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Gift size={14} />} Request another trial
          </button>
        </>
      )}
    </div>
  );
}
