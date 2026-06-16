/**
 * EngineerReviewsWall — Iter 220y.
 *
 * Public, read-only wall of all approved reviews for a partner engineer.
 * Lives at `/engineers/:slug/reviews`. Designed to be linked from the
 * engineer's email signature / business card / LinkedIn — a clean
 * trust-signal surface that loads in <500ms with no auth.
 *
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │  Sarah Patel · Patel Engineering Services                   │
 *   │  ★★★★★  4.8  ·  37 reviews                                  │
 *   │  ─────────────────────────────────────────                  │
 *   │  Rating breakdown      [5★ ████████ 28]                      │
 *   │                         [4★ ███ 6]                           │
 *   │                         [3★ █ 2]                             │
 *   │                                                              │
 *   │  ★★★★★ "Saved our peak hours"  — Lee · CrossFit Soho        │
 *   │  ★★★★☆ "Quick and clean"      — Alex · BoxPark Studio      │
 *   │  ...                                                         │
 *   │  [ Leave a review → ]                                        │
 *   └─────────────────────────────────────────────────────────────┘
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams, Link } from 'react-router-dom';
import {
  Star, ShieldCheck, AlertCircle, Loader2, CalendarOff,
  MessageSquare, ArrowRight, BadgeCheck,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const fmtDate = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch (_e) { return ''; }
};

const StarRow = ({ value, size = 14 }) => (
  <div className="inline-flex items-center gap-0.5" aria-label={`${value} out of 5 stars`}>
    {[1, 2, 3, 4, 5].map((n) => (
      <Star
        key={n}
        size={size}
        className={n <= value ? 'text-amber-500 fill-amber-500' : 'text-zinc-200'}
      />
    ))}
  </div>
);

const DistributionBar = ({ stars, count, total }) => {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div
      className="flex items-center gap-2 text-sm"
      data-testid={`reviews-wall-dist-${stars}`}
    >
      <span className="w-10 text-right text-zinc-700 font-medium tabular-nums">
        {stars}★
      </span>
      <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-amber-400 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-zinc-500 text-xs tabular-nums">{count}</span>
    </div>
  );
};

const ReviewCard = ({ review }) => (
  <article
    className="rounded-2xl border border-zinc-200 bg-white p-5 hover:border-zinc-300 transition-colors"
    data-testid={`reviews-wall-card-${review.id}`}
  >
    <header className="flex items-start justify-between gap-3">
      <div>
        <StarRow value={review.rating} />
        {review.title ? (
          <h3 className="text-base font-bold text-zinc-900 mt-2">{review.title}</h3>
        ) : null}
      </div>
      <time className="text-[11px] text-zinc-500 whitespace-nowrap">
        {fmtDate(review.created_at)}
      </time>
    </header>
    {review.body ? (
      <p className="text-sm text-zinc-700 leading-relaxed mt-2 whitespace-pre-line">
        {review.body}
      </p>
    ) : null}
    <footer className="mt-4 flex items-center gap-2 text-xs text-zinc-500">
      <span className="font-semibold text-zinc-700">
        {review.reviewer_name || 'Anonymous'}
      </span>
      {review.gym_name ? (
        <>
          <span aria-hidden="true">·</span>
          <span>{review.gym_name}</span>
        </>
      ) : null}
    </footer>
    {review.engineer_response ? (
      <div
        className="mt-4 rounded-xl bg-blue-50 border border-blue-100 p-3"
        data-testid={`reviews-wall-response-${review.id}`}
      >
        <p className="text-[11px] uppercase tracking-wider font-bold text-blue-700 mb-1 inline-flex items-center gap-1">
          <MessageSquare size={11} /> Engineer responded
        </p>
        <p className="text-sm text-blue-900 leading-relaxed whitespace-pre-line">
          {review.engineer_response}
        </p>
      </div>
    ) : null}
  </article>
);

export default function EngineerReviewsWall() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setError(null);
      try {
        const r = await axios.get(`${API}/engineers/${encodeURIComponent(slug)}/reviews`);
        if (!cancelled) setData(r.data);
      } catch (e) {
        if (!cancelled) {
          setError(e?.response?.status === 404
            ? 'Engineer not found'
            : (e?.response?.data?.detail || 'Could not load reviews'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50">
        <Loader2 className="animate-spin text-blue-600" size={28} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50 px-4">
        <div className="max-w-md text-center" data-testid="reviews-wall-not-found">
          <AlertCircle size={32} className="text-rose-500 mx-auto mb-3" />
          <h1 className="text-xl font-bold text-zinc-900 mb-1">
            {error || 'Engineer not found'}
          </h1>
          <p className="text-sm text-zinc-500 mb-4">
            The link may be out of date. Try the{' '}
            <Link to="/engineer" className="underline font-semibold">
              find-an-engineer page
            </Link>.
          </p>
        </div>
      </div>
    );
  }

  const { partner, summary, distribution, reviews } = data;
  const total = summary?.count || 0;
  const dist = distribution || { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 };

  return (
    <div className="min-h-screen bg-zinc-50" data-testid="reviews-wall-page">
      <div className="max-w-4xl mx-auto px-4 py-10 sm:py-14">
        {/* Crumb */}
        <Link
          to="/engineer"
          className="text-[12px] text-zinc-500 hover:text-zinc-900 inline-flex items-center gap-1 mb-6"
          data-testid="reviews-wall-back-link"
        >
          <ShieldCheck size={11} /> Pulse Fitness · Partner Engineer reviews
        </Link>

        {/* Hero card */}
        <header
          className="rounded-3xl bg-white border border-zinc-200 p-6 sm:p-10"
          data-testid="reviews-wall-hero"
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 font-bold">
            Reviews for
          </p>
          <h1
            className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-zinc-900 mt-2 tracking-tight"
            data-testid="reviews-wall-engineer-name"
          >
            {partner.full_name || partner.first_name}
          </h1>
          {partner.company_name ? (
            <p className="text-base sm:text-lg text-zinc-600 mt-1">
              {partner.company_name}
            </p>
          ) : null}

          {/* Trust badges */}
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            {partner.level ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 font-bold">
                <BadgeCheck size={12} /> {String(partner.level).replace(/_/g, ' ').replace(/\bengineer\b/gi, '').trim().toUpperCase() || 'PARTNER'} engineer
              </span>
            ) : null}
            {partner.member_since ? (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-600 font-medium">
                Member since {fmtDate(partner.member_since)}
              </span>
            ) : null}
            {partner.availability?.status === 'unavailable' ? (
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 font-bold"
                data-testid="reviews-wall-unavailable-badge"
              >
                <CalendarOff size={12} />
                {partner.availability.resumes_on
                  ? `Back ${fmtDate(`${partner.availability.resumes_on}T00:00:00Z`)}`
                  : 'On leave'}
              </span>
            ) : null}
          </div>

          {/* Rating summary */}
          <div className="mt-8 grid sm:grid-cols-[auto_1fr] gap-8 sm:gap-12 items-center">
            <div data-testid="reviews-wall-summary">
              <div className="text-6xl font-extrabold text-zinc-900 tabular-nums">
                {summary?.average != null ? summary.average.toFixed(1) : '–'}
              </div>
              <StarRow
                value={Math.round(summary?.average || 0)}
                size={18}
              />
              <p className="text-sm text-zinc-500 mt-2">
                {total} {total === 1 ? 'review' : 'reviews'}
              </p>
            </div>
            <div className="space-y-1.5">
              {[5, 4, 3, 2, 1].map((stars) => (
                <DistributionBar
                  key={stars}
                  stars={stars}
                  count={dist[String(stars)] || 0}
                  total={total}
                />
              ))}
            </div>
          </div>

          {/* CTA — leave a review */}
          <div className="mt-8 pt-6 border-t border-zinc-100 flex items-center justify-between gap-4 flex-wrap">
            <p className="text-sm text-zinc-600 max-w-md">
              Worked with {partner.first_name}? Share your experience to help
              other gyms find trusted engineers.
            </p>
            <Link
              to={`/engineer/${partner.id}/review`}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 transition-colors"
              data-testid="reviews-wall-leave-review-btn"
            >
              Leave a review <ArrowRight size={14} />
            </Link>
          </div>
        </header>

        {/* Review list */}
        <section className="mt-8" data-testid="reviews-wall-list">
          {reviews.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-zinc-300 bg-white p-10 text-center">
              <Star size={28} className="text-zinc-300 mx-auto mb-2" />
              <h2 className="text-lg font-bold text-zinc-900">No reviews yet</h2>
              <p className="text-sm text-zinc-500 mt-1 mb-4">
                Be the first to share your experience with {partner.first_name}.
              </p>
              <Link
                to={`/engineer/${partner.id}/review`}
                className="inline-flex items-center gap-2 text-sm font-bold text-blue-700 hover:underline"
                data-testid="reviews-wall-first-review-btn"
              >
                Leave the first review <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {reviews.map((r) => (
                <ReviewCard key={r.id} review={r} />
              ))}
            </div>
          )}
        </section>

        {/* Footer note */}
        <p className="text-[11px] text-zinc-400 mt-10 text-center">
          Pulse Fitness Partner Engineer Network · Reviews are moderated and tied
          to verified jobs.
        </p>
      </div>
    </div>
  );
}
