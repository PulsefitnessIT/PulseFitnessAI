/**
 * NotFoundPage — Iter 215by
 *
 * Branded 404 page. Detects the active brand (Pulse Fitness vs GymAxis)
 * from the URL path so the visitor sees the right logo, accent colour,
 * and CTA. Covers truly unknown routes — paid by the App-router fallback
 * `<Route path="*" element={<NotFoundPage />} />`.
 */
import { Link } from 'react-router-dom';
import { Home, ArrowLeft, Search } from 'lucide-react';

const NotFoundPage = () => {
  const isPulse = typeof window !== 'undefined' && window.location.pathname.toLowerCase().startsWith('/pulse');
  const accent = isPulse ? 'var(--pulse-primary)' : 'var(--color-brand-blue)';
  const homeHref = isPulse ? '/pulse' : '/';
  const brandName = isPulse ? 'Pulse Fitness' : 'GymAxis';

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6 py-16 bg-white dark:bg-zinc-900"
      data-testid="not-found-page"
      data-brand={isPulse ? 'pulse' : 'gymaxis'}
    >
      <div className="max-w-md w-full text-center">
        <div
          className="mx-auto h-16 w-16 rounded-2xl flex items-center justify-center mb-6 shadow-sm"
          style={{ background: accent }}
        >
          <span className="text-white text-2xl font-extrabold tracking-tight">{isPulse ? 'P' : 'G'}</span>
        </div>
        <p
          className="text-[10px] font-bold uppercase tracking-[0.24em] mb-3"
          style={{ color: accent }}
        >
          {brandName} · 404
        </p>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-zinc-900 dark:text-zinc-100 mb-3" style={{ letterSpacing: '-0.02em' }}>
          We can't find that page.
        </h1>
        <p className="text-base text-zinc-600 dark:text-zinc-400 mb-8 leading-relaxed">
          The link you followed may be broken or the page may have been moved. Let's get you back on track.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to={homeHref}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-sm font-bold text-white transition-colors"
            style={{ background: accent }}
            data-testid="not-found-home-btn"
          >
            <Home size={15} /> Back to {brandName}
          </Link>
          <button
            onClick={() => window.history.back()}
            className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-sm font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors"
            data-testid="not-found-back-btn"
          >
            <ArrowLeft size={15} /> Go back
          </button>
        </div>
        <div className="mt-10 pt-6 border-t border-zinc-200 dark:border-zinc-800 text-xs text-zinc-500">
          <p className="flex items-center justify-center gap-1.5">
            <Search size={12} />
            Looking for help? <Link to="/help" className="underline" style={{ color: accent }}>Visit our Help Centre</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default NotFoundPage;
