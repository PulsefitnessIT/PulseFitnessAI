/**
 * WhatsNewPage — Iter 215by · brand-isolated 215ef
 *
 * Public-facing changelog at /whats-new. Each item declares which
 * brand surface it belongs to (`gymaxis`, `pulse`, or `all`); the
 * renderer filters by the brand the visitor is currently on so we
 * don't leak Pulse Fitness mentions onto GymAxis (or vice versa).
 *
 * To add a release: append to the top of `RELEASES` and tag each
 * item with the smallest brand scope that fits.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Sparkles, Wrench, Shield, Zap } from 'lucide-react';

const RELEASES = [
  {
    version: '215bx',
    date: '2026-02-05',
    title: 'Cross-module data flow + per-tenant PWA',
    icon: Sparkles,
    accent: 'var(--color-brand-blue)',
    items: [
      { text: 'Marketing form leads + Memberships push-to-CRM now flow into the live CRM portal automatically.', brand: 'all' },
      { text: 'New members + their employer are auto-mirrored into the CRM as contacts and companies.', brand: 'all' },
      { text: 'Each tenant gets its own PWA manifest so "Add to Home Screen" installs with the right icon and name.', brand: 'all' },
    ],
  },
  {
    version: '215bw',
    date: '2026-02-04',
    title: 'Brand isolation + per-site polish',
    icon: Shield,
    accent: 'var(--pulse-primary)',
    items: [
      { text: '173 brand-leakage instances fixed — every tenant now uses its own primary colour exclusively.', brand: 'all' },
      { text: 'Cookie consent banner respects each brand colour.', brand: 'all' },
      { text: 'Starter tips: dismissals stick (was returning for master admins).', brand: 'all' },
      { text: 'Take a tour now per-user — different operators on the same browser each see it once.', brand: 'all' },
    ],
  },
  {
    version: '215bv',
    date: '2026-02-04',
    title: 'Memberships console refactor',
    icon: Wrench,
    accent: 'var(--color-success)',
    items: [
      { text: 'MembershipsConsole.js slimmed by 31% — modals + helpers extracted into focused files.', brand: 'all' },
      { text: 'Easier to maintain, no behavioural change for operators.', brand: 'all' },
    ],
  },
  {
    version: '215bu',
    date: '2026-02-03',
    title: 'Modal sticky headers + responsive admin',
    icon: Zap,
    accent: 'var(--color-warning)',
    items: [
      { text: 'Every dialog now has a sticky X-close button — reachable while scrolling long forms.', brand: 'all' },
      { text: 'Master Admin tables scroll horizontally on phones / tablets instead of breaking.', brand: 'all' },
    ],
  },
  {
    version: '215bt',
    date: '2026-02-02',
    title: 'Production-readiness pass',
    icon: Shield,
    accent: 'var(--color-info)',
    items: [
      { text: 'New `/api/health/deep` endpoint reports Mongo, file uploads, Stripe, Resend, LLM keys.', brand: 'gymaxis' },
      { text: '60+ MongoDB indexes added — faster queries at scale.', brand: 'all' },
      { text: 'Friendly empty states across Memberships, CRM, and Marketing.', brand: 'all' },
    ],
  },
];

const WhatsNewPage = () => {
  const isPulse = typeof window !== 'undefined' && window.location.pathname.toLowerCase().startsWith('/pulse');
  const accent = isPulse ? 'var(--pulse-primary)' : 'var(--color-brand-blue)';
  const homeHref = isPulse ? '/pulse' : '/';
  const brandName = isPulse ? 'Pulse Fitness' : 'GymAxis';
  const brandKey = isPulse ? 'pulse' : 'gymaxis';

  // Filter: keep items tagged 'all' or matching the current brand.
  // Drop releases that have no items left (no leakage).
  const visibleReleases = RELEASES
    .map((r) => ({ ...r, items: r.items.filter((it) => it.brand === 'all' || it.brand === brandKey) }))
    .filter((r) => r.items.length > 0);

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900 px-6 py-12" data-testid="whats-new-page" data-brand={brandKey}>
      <div className="max-w-3xl mx-auto">
        <Link to={homeHref} className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-700 mb-6">
          <ArrowLeft size={12} /> Back to {brandName}
        </Link>

        <p className="text-[10px] font-bold uppercase tracking-[0.24em] mb-3" style={{ color: accent }}>
          What's New
        </p>
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-zinc-900 dark:text-zinc-100 mb-2" style={{ letterSpacing: '-0.02em' }}>
          Latest improvements
        </h1>
        <p className="text-base text-zinc-600 dark:text-zinc-400 mb-12">
          Every shipped change, in plain English.
        </p>

        <div className="space-y-10 border-l-2 border-zinc-200 dark:border-zinc-800 pl-6 ml-1">
          {visibleReleases.map((r) => {
            const Icon = r.icon;
            return (
              <article key={r.version} className="relative" data-testid={`whats-new-release-${r.version}`}>
                <span
                  className="absolute -left-[35px] top-1 h-7 w-7 rounded-full flex items-center justify-center"
                  style={{ background: r.accent }}
                >
                  <Icon size={14} className="text-white" />
                </span>
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <h2 className="text-lg font-extrabold tracking-tight text-zinc-900 dark:text-zinc-100">{r.title}</h2>
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">v{r.version}</span>
                </div>
                <p className="text-[11px] text-zinc-500 mb-3">{new Date(r.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
                <ul className="space-y-1.5">
                  {r.items.map((item, i) => (
                    <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed flex items-start gap-2">
                      <span className="mt-1.5 h-1 w-1 rounded-full shrink-0" style={{ background: r.accent }} />
                      {item.text}
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </div>

        <div className="mt-16 pt-8 border-t border-zinc-200 dark:border-zinc-800 text-center text-xs text-zinc-500">
          Want a change? <Link to="/contact" className="underline" style={{ color: accent }}>Send feedback</Link> — we read every message.
        </div>
      </div>
    </div>
  );
};

export default WhatsNewPage;
