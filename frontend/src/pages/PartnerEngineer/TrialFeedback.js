/*
 * Iter 220ea·31 — Public engineer trial-feedback page.
 *
 * Reached from the day-10 feedback email (tokenised, no login needed).
 * The engineer rates the trial, tells us what worked / what's missing,
 * and chooses whether to continue on the paid plan:
 *   • Continue  → backend creates a Stripe Checkout session, we redirect.
 *   • Step away → trial closed, access paused.
 */
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Loader2, Star, CheckCircle2, Rocket, AlertTriangle } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

export default function TrialFeedback() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [rating, setRating] = useState(0);
  const [worked, setWorked] = useState('');
  const [missing, setMissing] = useState('');
  const [decision, setDecision] = useState(null); // 'accept' | 'decline'
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(null); // 'accept' | 'decline' | 'free_tier'

  const fetchInfo = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/partners/trial/feedback/${token}`);
      setInfo(r.data);
      if (r.data?.already_submitted) setDone(r.data.decision || 'decline');
    } catch (e) {
      setError(e?.response?.data?.detail || 'This feedback link is invalid or has expired.');
    }
    setLoading(false);
  }, [token]);

  useEffect(() => { fetchInfo(); }, [fetchInfo]);

  const submit = async (continuePaid) => {
    if (!rating) { setError('Please give the app a star rating first.'); return; }
    setError(null);
    setDecision(continuePaid ? 'accept' : 'decline');
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/partners/trial/feedback/${token}`, {
        rating, worked_well: worked, missing, continue_paid: continuePaid,
        origin_url: window.location.origin,
      });
      if (r.data?.decision === 'accept' && r.data?.checkout_url) {
        window.location.href = r.data.checkout_url; // → Stripe
        return;
      }
      setDone(r.data?.free_tier ? 'free_tier' : r.data?.decision || 'decline');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Something went wrong — please try again.');
      setDecision(null);
    }
    setSubmitting(false);
  };

  return (
    <div className="min-h-screen bg-[#070B1C] text-white flex items-center justify-center px-4 py-10"
      style={{ backgroundImage: 'radial-gradient(1200px 500px at 50% -10%, rgba(37,99,235,0.35), transparent)' }}
      data-testid="trial-feedback-page">
      <div className="w-full max-w-lg">
        <div className="flex items-center gap-2 mb-6 justify-center">
          <img src="/brand/gymaxis-full-tight.png" alt="GymAxis" className="h-8 bg-white rounded-lg px-3 py-1.5" />
        </div>

        {loading ? (
          <div className="text-center py-16"><Loader2 className="animate-spin mx-auto" /></div>
        ) : error && !info ? (
          <Card>
            <div className="text-center py-6">
              <AlertTriangle className="mx-auto mb-3 text-amber-400" size={32} />
              <p className="text-zinc-200" data-testid="trial-feedback-error">{error}</p>
            </div>
          </Card>
        ) : done ? (
          <Card>
            <div className="text-center py-6" data-testid="trial-feedback-done">
              <CheckCircle2 className="mx-auto mb-3 text-emerald-400" size={40} />
              {done === 'decline' ? (
                <>
                  <h1 className="text-xl font-black mb-2">Thanks for trying GymAxis</h1>
                  <p className="text-zinc-300 text-sm">We've logged your feedback and paused your trial access. If you change your mind, just reply to our email and we'll get you back on.</p>
                </>
              ) : (
                <>
                  <h1 className="text-xl font-black mb-2">You're all set</h1>
                  <p className="text-zinc-300 text-sm">You're at the free tier — no payment needed. Your Engineer App access stays on. Thanks for the feedback!</p>
                </>
              )}
            </div>
          </Card>
        ) : (
          <Card>
            <h1 className="text-2xl font-black tracking-tight mb-1" data-testid="trial-feedback-heading">
              How was your trial, {info?.engineer_name}?
            </h1>
            <p className="text-zinc-400 text-sm mb-6">Two minutes, then choose whether to continue on the plan.</p>

            <Label>Overall rating</Label>
            <div className="flex gap-1.5 mb-5" data-testid="trial-feedback-stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" onClick={() => setRating(n)}
                  className="transition-transform hover:scale-110" data-testid={`trial-star-${n}`}>
                  <Star size={32} className={n <= rating ? 'fill-amber-400 text-amber-400' : 'text-zinc-600'} />
                </button>
              ))}
            </div>

            <Label>What worked well?</Label>
            <textarea value={worked} onChange={(e) => setWorked(e.target.value)} rows={3}
              className="w-full rounded-lg bg-[#0E142E] border border-white/10 px-3 py-2 text-sm mb-5 focus:outline-none focus:border-blue-400"
              placeholder="The bits you'd miss if we took them away…" data-testid="trial-feedback-worked" />

            <Label>What's missing or frustrating?</Label>
            <textarea value={missing} onChange={(e) => setMissing(e.target.value)} rows={3}
              className="w-full rounded-lg bg-[#0E142E] border border-white/10 px-3 py-2 text-sm mb-6 focus:outline-none focus:border-blue-400"
              placeholder="Be honest — this is how we improve." data-testid="trial-feedback-missing" />

            {error && <p className="text-amber-400 text-sm mb-3" data-testid="trial-feedback-inline-error">{error}</p>}

            <div className="space-y-2.5">
              <button type="button" onClick={() => submit(true)} disabled={submitting}
                className="w-full rounded-xl py-3 font-black text-white inline-flex items-center justify-center gap-2 disabled:opacity-60"
                style={{ background: 'linear-gradient(90deg,#2563EB,#9D4CDD)' }}
                data-testid="trial-feedback-continue">
                {submitting && decision === 'accept' ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
                Continue on the plan
              </button>
              <p className="text-center text-[11px] text-zinc-500">£30/mo — drops to free once you refer 10 active sites.</p>
              <button type="button" onClick={() => submit(false)} disabled={submitting}
                className="w-full rounded-xl py-2.5 font-bold text-zinc-300 border border-white/10 hover:bg-white/5 inline-flex items-center justify-center gap-2 disabled:opacity-60"
                data-testid="trial-feedback-decline">
                {submitting && decision === 'decline' ? <Loader2 size={16} className="animate-spin" /> : null}
                No thanks, step away
              </button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

const Card = ({ children }) => (
  <div className="rounded-2xl bg-white/5 backdrop-blur border border-white/10 p-6 shadow-2xl">{children}</div>
);
const Label = ({ children }) => (
  <label className="block text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2">{children}</label>
);
