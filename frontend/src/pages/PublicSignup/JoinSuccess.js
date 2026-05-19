/**
 * JoinSuccess — /m/:slug/join/success
 *
 * Polls the backend for payment status until paid+member created. The
 * backend webhook (and the polled status endpoint) are both idempotent
 * so duplicate notifications are harmless.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { Check, Loader2, AlertTriangle } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function JoinSuccess() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const sessionId = params.get('session_id');

  const [state, setState] = useState({ status: 'pending', payment_status: 'unpaid', member_id: null });
  const [error, setError] = useState(null);
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    if (!sessionId) {
      setError('Missing session reference. Try the join link again.');
      return;
    }
    let alive = true;
    let timer;
    const poll = async () => {
      try {
        const r = await axios.get(`${API}/public/signup/status/${sessionId}`);
        if (!alive) return;
        setState(r.data || {});
        if (r.data?.payment_status === 'paid') return; // done
        if (attempts < 14) {
          timer = setTimeout(poll, 2500);
          setAttempts((n) => n + 1);
        } else {
          setError('Still confirming with our payment provider. Check your email — you should receive a receipt within a few minutes.');
        }
      } catch (e) {
        setError(e.response?.data?.detail || 'Could not confirm payment.');
      }
    };
    poll();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [sessionId, attempts]);

  return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center px-5" data-testid="join-success">
      <div className="max-w-md w-full bg-white rounded-2xl border border-zinc-200 shadow-sm p-8 text-center">
        {state.payment_status === 'paid' ? (
          <>
            <div className="h-14 w-14 rounded-full bg-emerald-100 text-emerald-600 mx-auto mb-4 flex items-center justify-center">
              <Check size={28} />
            </div>
            <h1 className="text-2xl font-bold text-zinc-900 mb-2">You're a member!</h1>
            <p className="text-sm text-zinc-600 mb-6">
              Welcome aboard. We've sent a receipt and your digital pass to your email — flash the QR at the door on your first visit.
            </p>
            <Link
              to={`/m/${slug}/join`}
              className="inline-block px-4 py-2 text-sm rounded-md border border-zinc-200 text-zinc-700 hover:bg-zinc-50"
              data-testid="join-success-back"
            >
              Back to gym page
            </Link>
          </>
        ) : error ? (
          <>
            <div className="h-14 w-14 rounded-full bg-amber-100 text-amber-600 mx-auto mb-4 flex items-center justify-center">
              <AlertTriangle size={28} />
            </div>
            <h1 className="text-xl font-bold text-zinc-900 mb-2">Hang tight</h1>
            <p className="text-sm text-zinc-600" data-testid="join-success-pending">{error}</p>
          </>
        ) : (
          <>
            <div className="h-14 w-14 rounded-full bg-zinc-100 mx-auto mb-4 flex items-center justify-center">
              <Loader2 size={24} className="text-zinc-400 animate-spin" />
            </div>
            <h1 className="text-xl font-bold text-zinc-900 mb-1">Confirming your payment…</h1>
            <p className="text-sm text-zinc-500">This usually takes under 10 seconds.</p>
          </>
        )}
      </div>
    </div>
  );
}
