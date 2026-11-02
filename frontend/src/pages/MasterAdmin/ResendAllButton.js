import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Send } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function ResendAllButton({ count, onDone, testId = 'resend-all-failed' }) {
  const [busy, setBusy] = useState(false);
  if (!count) return null;
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/master-admin/email-events/retry-failed`, {},
        { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
      if (data.failed === 0) toast.success(`${data.sent} email${data.sent === 1 ? '' : 's'} resent`);
      else toast.error(`${data.sent} resent, ${data.failed} still failing`, { description: data.errors?.[0]?.error });
    } catch (e) {
      toast.error('Resend failed', { description: e?.response?.data?.detail || e.message });
    } finally {
      setBusy(false);
      onDone?.();
    }
  };
  return (
    <button type="button" onClick={run} disabled={busy}
      className="inline-flex items-center gap-1.5 rounded-md bg-rose-600 text-white text-[11px] font-bold px-2.5 py-1 hover:bg-rose-700 disabled:opacity-60 disabled:cursor-wait transition"
      data-testid={testId}>
      <Send size={11} className={busy ? 'animate-pulse' : ''} />
      {busy ? 'Resending…' : `Resend all failed (${count})`}
    </button>
  );
}
