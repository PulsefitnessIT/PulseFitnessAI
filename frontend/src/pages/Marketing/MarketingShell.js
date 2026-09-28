/**
 * Marketing chrome — shared nav + footer + AXIS orbit.
 *
 * Usage: <MarketingShell><YourPageContent /></MarketingShell>
 *
 * The nav has a mobile drawer with body-scroll lock. Module pages use
 * the same shell so navigation is consistent.
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, X, ArrowRight } from 'lucide-react';

import { PulseFitnessLockup } from './PulseFitnessMark';
import TrialSignupModal, { openTrial } from './TrialSignupModal';
import ProductPreviewModal from './ProductPreviewModal';
import StickyCtaBar from './StickyCtaBar';
import MarketingChat from './MarketingChat';

// Iter 220bc — Six-modules → four-modules consolidation. Staffing and
// Reporting fold into Operations / CRM as sub-features. Iter 228c —
// labels run through i18n (slug keeps data-testids stable across langs).
const NAV = (t) => [
  { to: '/platform/service',     slug: 'operations',  label: t('mkt.mod_service', 'Operations') },
  { to: '/platform/crm',         slug: 'crm',         label: t('mkt.mod_crm', 'CRM') },
  { to: '/platform/memberships', slug: 'memberships', label: t('mkt.mod_memberships', 'Memberships') },
  { to: '/platform/marketing',   slug: 'marketing',   label: t('mkt.mod_marketing', 'Marketing') },
  { to: '/pricing',              slug: 'pricing',     label: t('mkt.nav_pricing', 'Pricing') },
];

const LANGS = [['en', 'EN'], ['fr', 'FR'], ['de', 'DE']];

function LangSelect({ className = '', testId }) {
  const { i18n } = useTranslation();
  const current = (i18n.language || 'en').slice(0, 2);
  return (
    <select
      value={LANGS.some(([c]) => c === current) ? current : 'en'}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      className={`text-xs font-bold text-slate-600 bg-transparent border border-slate-200 rounded-full px-2.5 py-1.5 cursor-pointer hover:border-slate-300 transition-colors dark:border-zinc-800 dark:text-zinc-200 ${className}`}
      aria-label="Language"
      data-testid={testId}
    >
      {LANGS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
    </select>
  );
}

export function MarketingNav() {
  const { t } = useTranslation();
  const nav = NAV(t);
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  return (
    <header
      /* Iter 216bn — at the top of the page on mobile we always render
         the glass background. The pure-transparent header-on-scroll-top
         was unreadable when the hamburger landed over a busy hero photo
         (Lee, Feb 2026 production feedback). On xl+ desktop we keep the
         original transparent → glass scroll behaviour. */
      className={`fixed top-0 inset-x-0 z-50 transition-all ${scrolled ? 'gx-glass' : 'gx-glass xl:bg-transparent xl:backdrop-blur-0'}`}
      data-testid="gx-nav"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
        <Link to="/" className="flex items-center font-black tracking-tight text-lg shrink-0" data-testid="gx-nav-logo">
          <PulseFitnessLockup className="h-8 md:h-9 w-auto" />
        </Link>

        <nav className="hidden xl:flex items-center gap-5 text-sm font-medium text-slate-600 min-w-0">
          {nav.map((n) => (
            <Link key={n.to} to={n.to} className="hover:text-slate-900 transition-colors whitespace-nowrap dark:text-zinc-100" data-testid={`gx-nav-${n.slug}`}>{n.label}</Link>
          ))}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <LangSelect className="hidden xl:block" testId="gx-nav-lang" />
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="hidden xl:inline-flex text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors whitespace-nowrap dark:text-zinc-100"
            data-testid="gx-nav-signin"
          >
            {t('mkt.sign_in', 'Sign In')}
          </button>
          <button
            type="button"
            onClick={openTrial}
            className="gx-cta hidden xl:inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-bold whitespace-nowrap"
            data-testid="gx-nav-trial"
          >
            {t('mkt.start_trial', 'Start Free Trial')}<ArrowRight size={14} />
          </button>
          <button
            type="button"
            aria-label={t('mkt.open_menu', 'Open menu')}
            onClick={() => setOpen(true)}
            className="xl:hidden w-10 h-10 rounded-full border border-slate-200 flex items-center justify-center dark:border-zinc-800"
            data-testid="gx-nav-mobile-btn"
          >
            <Menu size={18} />
          </button>
        </div>
      </div>

      {open && createPortal((
        /* Iter 216c — render via portal so the drawer escapes the
           <header>'s containing block. The header has
           `backdrop-filter: blur(20px)` which (per CSS spec) makes
           it the containing block for fixed descendants — so without
           a portal, `inset-0` collapsed to the 64px-tall header bar,
           leaving the drawer's backdrop and panel transparent over
           the page content. (Lee's Feb-2026 production screenshot.) */
        <div className="fixed inset-0 z-[60] xl:hidden" role="dialog" aria-modal="true" data-testid="gx-nav-mobile-drawer" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" />
          <div className="absolute right-0 top-0 bottom-0 w-[80%] max-w-sm bg-white shadow-2xl flex flex-col dark:bg-zinc-900" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 h-16 border-b border-slate-100 dark:border-zinc-800">
              <span className="font-bold text-slate-900 dark:text-zinc-100">{t('mkt.menu', 'Menu')}</span>
              <button onClick={() => setOpen(false)} aria-label={t('mkt.close_menu', 'Close menu')} className="p-2 text-slate-500 hover:text-slate-900 dark:text-zinc-100" data-testid="gx-nav-mobile-close">
                <X size={18} />
              </button>
            </div>
            <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
              {nav.map((n) => (
                <Link
                  key={n.to}
                  to={n.to}
                  onClick={() => setOpen(false)}
                  className="px-4 py-3 rounded-xl text-slate-700 hover:text-slate-900 hover:bg-slate-50 font-semibold dark:bg-zinc-900 dark:text-zinc-100"
                  data-testid={`gx-nav-mobile-${n.slug}`}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
            <div className="px-4 pb-6 pt-3 border-t border-slate-100 space-y-2 dark:border-zinc-800">
              <LangSelect className="w-full !rounded-xl py-2.5" testId="gx-nav-mobile-lang" />
              {/* Iter 216h271 — explicit inline gradient + white text.
                  The previous `gx-cta` class alone evaluated invisible
                  on the mobile menu surface (white-on-white because
                  Tailwind purged the custom class in some builds). */}
              <button
                onClick={() => { setOpen(false); openTrial(); }}
                className="w-full rounded-full px-5 py-3 text-sm font-bold transition-shadow hover:shadow-lg"
                style={{
                  background: 'linear-gradient(135deg, var(--gx-brand-from, #2563EB) 0%, var(--gx-brand-to, #9D4CDD) 100%)',
                  color: '#fff',
                }}
                data-testid="gx-nav-mobile-trial"
              >
                {t('mkt.start_trial', 'Start Free Trial')}
              </button>
              <button onClick={() => { setOpen(false); navigate('/login'); }} className="w-full rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700 dark:border-zinc-800" data-testid="gx-nav-mobile-signin">
                {t('mkt.sign_in', 'Sign In')}
              </button>
            </div>
          </div>
        </div>
      ), document.body)}
    </header>
  );
}

export function MarketingFooter() {
  const { t } = useTranslation();
  const nav = NAV(t);
  return (
    <footer className="border-t border-slate-200 mt-24 dark:border-zinc-800" data-testid="gx-footer">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-14 grid gap-10 lg:grid-cols-5 sm:grid-cols-2" data-testid="gx-footer-grid">
        <div>
          <Link to="/" className="flex items-center font-black text-lg">
            <PulseFitnessLockup className="h-12 w-auto" />
          </Link>
          <p className="mt-3 text-sm text-slate-500 leading-relaxed">{t('mkt.foot_tagline', 'The all-in-one operations platform for gyms, studios, and fitness businesses.')}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">{t('mkt.foot_platform', 'Platform')}</p>
          <ul className="space-y-2 text-sm text-slate-600">
            {nav.filter(n => n.to !== '/pricing').map((n) => <li key={n.to}><Link to={n.to} className="hover:text-slate-900 dark:text-zinc-100">{n.label}</Link></li>)}
            <li><Link to="/platform/staffing" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-staffing">{t('mkt.foot_staffing', 'Staffing')}</Link></li>
            <li><Link to="/platform/reporting" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-reporting">{t('mkt.foot_reporting', 'Reporting')}</Link></li>
            <li><Link to="/features" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-features">{t('mkt.foot_all_features', 'All features')}</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">{t('mkt.foot_company', 'Company')}</p>
          <ul className="space-y-2 text-sm text-slate-600">
            <li><Link to="/about" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-about">{t('mkt.foot_about', 'About')}</Link></li>
            <li><Link to="/pricing" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_pricing', 'Pricing')}</Link></li>
            <li><Link to="/security" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_security', 'Security')}</Link></li>
            <li><Link to="/demo-request" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-demo">{t('mkt.foot_demo', 'Book a demo')}</Link></li>
            <li><Link to="/contact" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_contact', 'Contact')}</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">{t('mkt.foot_resources', 'Resources')}</p>
          <ul className="space-y-2 text-sm text-slate-600">
            <li><Link to="/solutions" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-solutions">{t('mkt.foot_solutions', 'Solutions')}</Link></li>
            <li><Link to="/maintenance" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-maintenance">{t('mkt.foot_maintenance', 'Maintenance by brand')}</Link></li>
            <li><Link to="/equipment" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-equipment">{t('mkt.foot_equipment', 'Servicing by equipment')}</Link></li>
            <li><Link to="/blog" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_blog', 'Blog')}</Link></li>
            <li><Link to="/compare" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_alternatives', 'Alternatives')}</Link></li>
            <li><Link to="/compare/mindbody" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-compare-mindbody">Mindbody alternative</Link></li>
            <li><Link to="/compare/glofox" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-compare-glofox">Glofox alternative</Link></li>
            <li><Link to="/compare/clubready" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-compare-clubready">ClubReady alternative</Link></li>
            <li><Link to="/whats-new" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_whats_new', "What's new")}</Link></li>
            <li><Link to="/status" className="hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_status', 'Status')}</Link></li>
            <li><a href="/downloads/PulseFitnessAI-Operators-Presentation.pdf" target="_blank" rel="noopener noreferrer" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-sales-deck-operators">{t('mkt.foot_deck_operators', 'Operators Sales Presentation')}</a></li>
            <li><a href="/downloads/PulseFitnessAI-Suppliers-Presentation.pdf" target="_blank" rel="noopener noreferrer" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-sales-deck-suppliers">{t('mkt.foot_deck_suppliers', 'Suppliers Sales Presentation')}</a></li>
            <li><Link to="/service-provider/signup" className="hover:text-slate-900 dark:text-zinc-100" data-testid="gx-footer-suppliers">{t('mkt.foot_suppliers', 'For service suppliers')}</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">{t('mkt.foot_get_started', 'Get started')}</p>
          <Link to="/pricing" className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-bold">{t('mkt.foot_see_pricing', 'See pricing')}<ArrowRight size={13} /></Link>
          <button type="button" onClick={openTrial} className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-700 hover:text-slate-900 dark:text-zinc-100">{t('mkt.foot_or_trial', 'Or start a free trial →')}</button>
        </div>
      </div>
      <div className="border-t border-slate-100 dark:border-zinc-800">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-5 text-xs text-slate-400 flex flex-wrap justify-between gap-4 items-center">
          <span>© {new Date().getFullYear()} Pulse Fitness AI. {t('mkt.foot_rights', 'All rights reserved.')}</span>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1" data-testid="gx-footer-legal">
            <Link to="/privacy" className="hover:text-slate-700" data-testid="gx-footer-privacy">{t('mkt.foot_privacy', 'Privacy')}</Link>
            <Link to="/terms" className="hover:text-slate-700" data-testid="gx-footer-terms">{t('mkt.foot_terms', 'Terms')}</Link>
            <Link to="/refunds" className="hover:text-slate-700" data-testid="gx-footer-refunds">{t('mkt.foot_refunds', 'Refunds & cancellation')}</Link>
            <Link to="/legal/dpa" className="hover:text-slate-700" data-testid="gx-footer-dpa">DPA</Link>
            <Link to="/legal/dpia" className="hover:text-slate-700" data-testid="gx-footer-dpia">DPIA</Link>
            <Link to="/security" className="hover:text-slate-700" data-testid="gx-footer-security">{t('mkt.foot_security', 'Security')}</Link>
          </div>
          <span>{t('mkt.foot_made_for', 'Made for fitness operators.')}</span>
        </div>
      </div>
    </footer>
  );
}

export default function MarketingShell({ children }) {
  return (
    <div className="gx-marketing min-h-screen flex flex-col" data-testid="gx-marketing-shell" data-theme="light">
      <MarketingNav />
      <main className="flex-1 pt-16">{children}</main>
      <MarketingFooter />
      <TrialSignupModal />
      <ProductPreviewModal />
      <StickyCtaBar />
      <MarketingChat />
    </div>
  );
}
