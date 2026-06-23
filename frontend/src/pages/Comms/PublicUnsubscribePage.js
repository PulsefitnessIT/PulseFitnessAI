/**
 * Public one-click Unsubscribe — routed at /unsubscribe/:token (no auth).
 * Linked from the {{unsubscribe_link}} merge tag. Unsubscribes on mount,
 * confirms, and links through to the granular preference centre + a
 * resubscribe option.
 */
import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle2, Loader2, MailX, Undo2 } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function PublicUnsubscribePage() {
  const { token } = useParams();
  const [state, setState] = useState('loading'); // loading | done | error | resubscribed
  const [data, setData] = useState(null);

  useEffect(() => {
    axios.post(`${API}/comms/public/unsubscribe/${token}`)
      .then(res => { setData(res.data); setState('done'); })
      .catch(() => setState('error'));
  }, [token]);

  const resubscribe = async () => {
    try {
      await axios.post(`${API}/comms/public/preferences/${token}`, {
        unsubscribed_all: false, opted_out_categories: [],
      });
      setState('resubscribed');
    } catch {
      setState('error');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: '#05070A' }}>
      <div className="w-full max-w-lg">
        <div className="flex items-center gap-3 mb-5">
          {data?.org_logo
            ? <img src={data.org_logo} alt={data.org_name} className="h-9 max-w-[160px] object-contain" />
            : <span className="text-lg font-bold" style={{ color: '#fff' }}>{data?.org_name || 'Pulse Fitness'}</span>}
        </div>
        <div className="rounded-2xl border border-white/10 bg-[#0A0C12] p-8 shadow-2xl text-center">
          {state === 'loading' && (
            <div className="py-8" data-testid="unsub-loading">
              <Loader2 className="w-7 h-7 animate-spin text-cyan-400 mx-auto" />
            </div>
          )}

          {state === 'error' && (
            <div data-testid="unsub-error">
              <MailX className="w-10 h-10 mx-auto mb-4 text-rose-400" />
              <p className="text-slate-300">This link is invalid or has expired.</p>
            </div>
          )}

          {state === 'done' && (
            <div data-testid="unsub-done">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-cyan-400" />
              <h1 className="text-xl font-bold mb-2" style={{ color: '#fff' }}>You've been unsubscribed</h1>
              <p className="text-sm text-slate-400 mb-1">
                <span className="text-cyan-300">{data?.email}</span> will no longer receive emails from {data?.org_name}.
              </p>
              <p className="text-xs text-slate-500 mb-6">Changed your mind? You can resubscribe or fine-tune which emails you get.</p>
              <div className="flex flex-col gap-3">
                <Link
                  to={`/preferences/${token}`}
                  data-testid="unsub-manage-prefs-link"
                  className="w-full py-3 rounded-xl border border-white/15 text-sm font-semibold hover:bg-white/[0.06] transition-colors"
                  style={{ color: '#fff' }}
                >
                  Manage email preferences
                </Link>
                <button
                  onClick={resubscribe}
                  data-testid="unsub-resubscribe-btn"
                  className="w-full py-2.5 rounded-xl text-slate-400 text-sm hover:text-white transition-colors flex items-center justify-center gap-2"
                >
                  <Undo2 className="w-4 h-4" /> Resubscribe
                </button>
              </div>
            </div>
          )}

          {state === 'resubscribed' && (
            <div data-testid="unsub-resubscribed">
              <CheckCircle2 className="w-12 h-12 mx-auto mb-4 text-emerald-400" />
              <h1 className="text-xl font-bold mb-2" style={{ color: '#fff' }}>Welcome back</h1>
              <p className="text-sm text-slate-400">You've been resubscribed and will continue to receive emails.</p>
            </div>
          )}
        </div>
        <p className="text-center text-[11px] text-slate-600 mt-4">Powered by Pulse Fitness AI</p>
      </div>
    </div>
  );
}
