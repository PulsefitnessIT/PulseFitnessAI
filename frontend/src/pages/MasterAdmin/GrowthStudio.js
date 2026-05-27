/**
 * GrowthStudio — Master Admin → Growth → Marketing Studio (Iter 220ac).
 *
 * Embeds the full GymAxis Marketing Suite inside Master Admin so the
 * operator can use the same campaign / journey / brand-kit /
 * creative-studio toolset they sell to customers — but pointed at
 * promoting GymAxis itself.
 *
 * Why this matters:
 *   • Marketing agencies quote £3-5k/mo for the same surface.
 *   • We already built it once for customers; reusing it for self-
 *     promotion is a zero-cost growth lever.
 *   • Everything created here flows through the existing
 *     ``crm2_contacts`` / ``mkt_campaigns`` collections, scoped to the
 *     master-admin org. No new infrastructure.
 *
 * Phase 2 (SEO Autopilot — Soro-inspired) will plug in here as a
 * sibling sub-tab once Phase 1 is verified.
 */
import { Suspense, lazy } from 'react';
import { Megaphone, Loader2, ExternalLink, Rocket } from 'lucide-react';

const MarketingSuite = lazy(() => import('@/pages/MarketingSuite'));

export default function GrowthStudio() {
  return (
    <div className="space-y-5" data-testid="growth-studio">
      {/* Hero — explains what this view IS so the operator knows it's
          GymAxis self-promotion (not a customer-facing inbox). */}
      <header
        className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-5 py-4 flex items-center gap-4"
        data-testid="growth-studio-hero"
      >
        <span className="shrink-0 w-12 h-12 rounded-2xl bg-gradient-to-br from-fuchsia-500 to-blue-600 text-white flex items-center justify-center shadow-[0_8px_20px_-8px_rgba(217,70,239,0.6)]">
          <Rocket size={20} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700 dark:text-fuchsia-400">
            Growth · Master Admin
          </p>
          <h2 className="text-xl sm:text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight mt-0.5">
            GymAxis Marketing Studio
          </h2>
          <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 mt-1 max-w-2xl">
            Same toolkit we sell to customers — Campaigns, Journeys,
            Creative Studio, Brand Kit, Forms &amp; Pages, Social — pointed
            at promoting GymAxis itself. Locked brand voice, fonts and
            colours travel with you automatically.
          </p>
        </div>
        <a
          href="/marketing"
          target="_blank"
          rel="noreferrer noopener"
          className="hidden md:inline-flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400 transition-colors"
          data-testid="growth-studio-open-fullscreen"
        >
          <ExternalLink size={12} /> Open full-screen
        </a>
      </header>

      {/* Embedded Marketing Suite — re-uses every existing tab. The
          `embedded` prop suppresses the Suite's own Navbar / unified
          header / ModuleSwitcher so the Master Admin chrome stays
          authoritative. */}
      <Suspense
        fallback={
          <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-10 flex items-center justify-center gap-2 text-zinc-500">
            <Loader2 size={16} className="animate-spin" /> Loading Marketing Studio…
          </div>
        }
      >
        <MarketingSuite embedded />
      </Suspense>

      <p className="text-[11px] text-zinc-400 dark:text-zinc-500 flex items-center gap-1.5">
        <Megaphone size={11} /> Phase 2 — SEO Autopilot (keyword research,
        AI article writer, daily auto-publish, rank dashboard) is queued
        for the next iteration.
      </p>
    </div>
  );
}
