/**
 * Forward-to-a-friend — routed at /c/forward/:id (no auth).
 * Lets a recipient forward the campaign email to someone else
 * (the {{forward_to_friend_link}} target).
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Loader2, Send, CheckCircle2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function PublicForwardPage() {
  const { id } = useParams();
  const [to, setTo] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!to.includes('@')) { setError('Please enter a valid email address.'); return; }
    setBusy(true); setError('');
    try {
      const res = await axios.post(`${API}/comms/public/forward/${id}`, { to, note });
      if (res.data.ok) setSent(true);
      else setError('Sorry, we could not send this right now.');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Sorry, we could not send this right now.');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: '#05070A' }}>
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-white/10 bg-[#0A0C12] p-8 shadow-2xl">
          {sent ? (
            <div className="text-center" data-testid="forward-done">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-cyan-400" />
              <h1 className="text-xl font-bold mb-2" style={{ color: '#fff' }}>Email sent</h1>
              <p className="text-sm text-slate-400">Thanks for sharing — <span className="text-cyan-300">{to}</span> will receive it shortly.</p>
            </div>
          ) : (
            <div data-testid="forward-page">
              <h1 className="text-xl font-bold mb-1" style={{ color: '#fff' }}>Forward to a friend</h1>
              <p className="text-sm text-slate-400 mb-6">Share this email with someone who'd find it useful.</p>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Their email</label>
              <input
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="friend@example.com"
                data-testid="forward-email"
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/10 text-white text-sm mb-4 focus:outline-none focus:border-cyan-400"
              />
              <label className="block text-xs font-semibold text-slate-300 mb-1">Add a note (optional)</label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={3}
                placeholder="Thought you'd like this…"
                data-testid="forward-note"
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/10 text-white text-sm mb-4 focus:outline-none focus:border-cyan-400"
              />
              {error && <p className="text-sm text-rose-400 mb-3" data-testid="forward-error">{error}</p>}
              <button
                onClick={submit}
                disabled={busy}
                data-testid="forward-submit"
                className="w-full py-3 rounded-xl bg-cyan-400 text-slate-900 font-semibold text-sm hover:bg-cyan-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Send email
              </button>
            </div>
          )}
        </div>
        <p className="text-center text-[11px] text-slate-600 mt-4">Powered by Pulse Fitness AI</p>
      </div>
    </div>
  );
}
