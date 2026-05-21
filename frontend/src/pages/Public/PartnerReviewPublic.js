/**
 * PartnerReviewPublic.js (iter 216h286)
 *
 * Public page for a gym contact to submit a star-rating review on a
 * partner engineer after a job. Lives at `/engineer/:partnerId/review`.
 *
 * No login required — landing page is intentionally lean so any gym
 * staff member with the link can leave feedback. Soft-rate-limited
 * server-side (24 h cooldown per reviewer_email + low-star/keyword
 * routes to moderation).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, Link } from 'react-router-dom';
import { Star, ShieldCheck, CheckCircle2, AlertCircle, Loader2, CalendarOff } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

function StarPicker({ value, onChange }) {
  return (
    <div className="flex items-center gap-1" data-testid="review-star-picker">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className="p-1 transition-transform hover:scale-110"
          aria-label={`${n} star${n > 1 ? 's' : ''}`}
          data-testid={`review-star-${n}`}
        >
          <Star
            size={36}
            className={n <= value ? 'text-amber-500 fill-amber-500' : 'text-zinc-300'}
          />
        </button>
      ))}
    </div>
  );
}

export default function PartnerReviewPublic() {
  const { partnerId } = useParams();
  const [engineer, setEngineer] = useState(null);
  const [summary, setSummary] = useState(null);
  const [rating, setRating] = useState(0);
  const [form, setForm] = useState({
    reviewer_name: '', reviewer_email: '', gym_name: '',
    title: '', body: '', job_reference: '',
  });
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/partners/${partnerId}/reviews`);
        setEngineer(r.data.partner);
        setSummary(r.data.summary);
      } catch (e) {
        setError(e?.response?.data?.detail || 'Engineer not found');
      }
    })();
  }, [partnerId]);

  const submit = async (e) => {
    e.preventDefault();
    if (rating < 1) { setError('Pick a rating between 1 and 5 stars'); return; }
    setError(null); setBusy(true);
    try {
      const r = await axios.post(`${API}/partners/${partnerId}/reviews`, { ...form, rating });
      setSubmitted(r.data);
    } catch (e2) {
      setError(e2?.response?.data?.detail || 'Could not submit your review');
    } finally { setBusy(false); }
  };

  if (error && !engineer) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <AlertCircle size={32} className="text-rose-500 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-zinc-900 mb-1">Engineer not found</h1>
          <p className="text-sm text-zinc-500">The link may be out of date. Try the <Link to="/engineer" className="underline">find-an-engineer page</Link>.</p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md text-center" data-testid="review-submitted">
          <CheckCircle2 size={40} className="text-emerald-500 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-zinc-900 mb-1">Thanks for your review</h1>
          <p className="text-sm text-zinc-500 mb-4">{submitted.message}</p>
          <Link to="/engineer" className="text-sm font-bold text-blue-700 hover:underline">Browse other engineers</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50 py-10 px-4">
      <div className="max-w-2xl mx-auto" data-testid="review-public-page">
        <Link to="/engineer" className="text-[12px] text-zinc-500 hover:text-zinc-900 inline-flex items-center gap-1 mb-4">
          <ShieldCheck size={11} /> GymAxis · Partner Engineer review
        </Link>
        <div className="rounded-xl bg-white border border-zinc-200 p-6 sm:p-8">
          {engineer && (
            <div className="mb-6">
              <p className="text-[11px] uppercase tracking-wider text-zinc-500 font-bold">Reviewing</p>
              <h1 className="text-2xl font-bold text-zinc-900" data-testid="review-engineer-name">{engineer.first_name}{engineer.company_name ? ` · ${engineer.company_name}` : ''}</h1>
              {summary && summary.count > 0 && (
                <p className="text-sm text-zinc-500 mt-1 inline-flex items-center gap-1">
                  <Star size={12} className="text-amber-500 fill-amber-500" />
                  {summary.average?.toFixed(1) ?? '–'} from {summary.count} {summary.count === 1 ? 'review' : 'reviews'}
                </p>
              )}
              {/* Iter 216h288 — Gap 10: yellow "Back on …" badge so a
                  reviewer knows the engineer's on leave (still valid to
                  leave a retrospective review on past work though). */}
              {engineer.availability?.status === 'unavailable' && (
                <p className="mt-2 inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-amber-100 text-amber-800 text-[11px] font-bold"
                   data-testid="review-engineer-unavailable">
                  <CalendarOff size={11} />
                  {engineer.availability.resumes_on
                    ? `Currently on leave · back ${new Date(`${engineer.availability.resumes_on}T00:00:00Z`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`
                    : 'Currently on leave'}
                  {engineer.availability.note ? ` · ${engineer.availability.note}` : ''}
                </p>
              )}
            </div>
          )}
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-sm font-bold text-zinc-900 mb-2">Your rating</label>
              <StarPicker value={rating} onChange={setRating} />
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Your name" required value={form.reviewer_name} onChange={(v) => setForm({ ...form, reviewer_name: v })} testId="review-name" />
              <Field label="Your email (kept private)" type="email" value={form.reviewer_email} onChange={(v) => setForm({ ...form, reviewer_email: v })} testId="review-email" />
              <Field label="Gym name" value={form.gym_name} onChange={(v) => setForm({ ...form, gym_name: v })} testId="review-gym" />
              <Field label="Job reference (optional)" value={form.job_reference} onChange={(v) => setForm({ ...form, job_reference: v })} testId="review-job-ref" />
            </div>
            <Field label="Headline" value={form.title} onChange={(v) => setForm({ ...form, title: v })} testId="review-title" />
            <Field label="What did the engineer do? *" required type="textarea" value={form.body} onChange={(v) => setForm({ ...form, body: v })} testId="review-body" />
            {error && (
              <p className="text-sm text-rose-700 inline-flex items-center gap-1" data-testid="review-error">
                <AlertCircle size={13} /> {error}
              </p>
            )}
            <div className="pt-2 flex items-center justify-between">
              <p className="text-[11px] text-zinc-500">Reviews are moderated before going public. We may publish your name and gym (your email stays private).</p>
              <button
                type="submit"
                disabled={busy}
                className="px-5 py-2.5 text-sm font-bold text-white rounded-md disabled:opacity-50 inline-flex items-center gap-2"
                style={{ background: 'var(--color-brand-blue, #0055FF)' }}
                data-testid="review-submit"
              >
                {busy ? <Loader2 size={13} className="animate-spin" /> : <Star size={13} />} {busy ? 'Submitting…' : 'Submit review'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, required, type = 'text', testId }) {
  const Tag = type === 'textarea' ? 'textarea' : 'input';
  return (
    <label className="block">
      <span className="block text-[12px] font-semibold text-zinc-700 mb-1">{label}</span>
      <Tag
        type={type === 'textarea' ? undefined : type}
        rows={type === 'textarea' ? 4 : undefined}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-zinc-200 rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
        data-testid={testId}
      />
    </label>
  );
}
