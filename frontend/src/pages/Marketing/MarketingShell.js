/**
 * Marketing chrome — shared nav + footer + AXIS orbit.
 *
 * Usage: <MarketingShell><YourPageContent /></MarketingShell>
 *
 * The nav has a mobile drawer with body-scroll lock. Module pages use
 * the same shell so navigation is consistent.
 */
import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Menu, X, ArrowRight } from 'lucide-react';

import { GymAxisLockup } from './GymAxisMark';
import TrialSignupModal, { openTrial } from './TrialSignupModal';
import ProductPreviewModal from './ProductPreviewModal';
import StickyCtaBar from './StickyCtaBar';
import MarketingChat from './MarketingChat';

const NAV = [
  { to: '/platform/service',     label: 'Operations' },
  { to: '/platform/crm',         label: 'CRM' },
  { to: '/platform/memberships', label: 'Memberships' },
  { to: '/platform/marketing',   label: 'Marketing' },
  { to: '/platform/staffing',    label: 'Staffing' },
  { to: '/platform/reporting',   label: 'Reporting' },
  { to: '/pricing',              label: 'Pricing' },
];

export function MarketingNav() {
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
      className={`fixed top-0 inset-x-0 z-50 transition-all ${scrolled ? 'gx-glass' : 'bg-transparent'}`}
      data-testid="gx-nav"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
        <Link to="/" className="flex items-center font-black tracking-tight text-lg shrink-0" data-testid="gx-nav-logo">
          <GymAxisLockup className="h-8 md:h-9 w-auto" />
        </Link>

        <nav className="hidden xl:flex items-center gap-5 text-sm font-medium text-slate-600 min-w-0">
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className="hover:text-slate-900 transition-colors whitespace-nowrap" data-testid={`gx-nav-${n.label.toLowerCase()}`}>{n.label}</Link>
          ))}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <button
            type="button"
            onClick={() => navigate('/login')}
            className="hidden xl:inline-flex text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors whitespace-nowrap"
            data-testid="gx-nav-signin"
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={openTrial}
            className="gx-cta hidden xl:inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-bold whitespace-nowrap"
            data-testid="gx-nav-trial"
          >
            Start Free Trial<ArrowRight size={14} />
          </button>
          <button
            type="button"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
            className="xl:hidden w-10 h-10 rounded-full border border-slate-200 flex items-center justify-center"
            data-testid="gx-nav-mobile-btn"
          >
            <Menu size={18} />
          </button>
        </div>
      </div>

      {open && (
        <div className="fixed inset-0 z-[60] xl:hidden" role="dialog" aria-modal="true" data-testid="gx-nav-mobile-drawer" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" />
          <div className="absolute right-0 top-0 bottom-0 w-[80%] max-w-sm bg-white shadow-2xl flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 h-16 border-b border-slate-100">
              <span className="font-bold text-slate-900">Menu</span>
              <button onClick={() => setOpen(false)} aria-label="Close menu" className="p-2 text-slate-500 hover:text-slate-900" data-testid="gx-nav-mobile-close">
                <X size={18} />
              </button>
            </div>
            <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
              {NAV.map((n) => (
                <Link
                  key={n.to}
                  to={n.to}
                  onClick={() => setOpen(false)}
                  className="px-4 py-3 rounded-xl text-slate-700 hover:text-slate-900 hover:bg-slate-50 font-semibold"
                  data-testid={`gx-nav-mobile-${n.label.toLowerCase()}`}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
            <div className="px-4 pb-6 pt-3 border-t border-slate-100 space-y-2">
              <button onClick={() => { setOpen(false); openTrial(); }} className="gx-cta w-full rounded-full px-5 py-3 text-sm font-bold" data-testid="gx-nav-mobile-trial">
                Start Free Trial
              </button>
              <button onClick={() => { setOpen(false); navigate('/login'); }} className="w-full rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-700" data-testid="gx-nav-mobile-signin">
                Sign In
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-slate-200 mt-24" data-testid="gx-footer">
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-14 grid gap-10 lg:grid-cols-5 sm:grid-cols-2" data-testid="gx-footer-grid">
        <div>
          <Link to="/" className="flex items-center font-black text-lg">
            <GymAxisLockup className="h-12 w-auto" />
          </Link>
          <p className="mt-3 text-sm text-slate-500 leading-relaxed">The all-in-one operations platform for gyms, studios, and fitness businesses.</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">Platform</p>
          <ul className="space-y-2 text-sm text-slate-600">
            {NAV.filter(n => n.to !== '/pricing').map((n) => <li key={n.to}><Link to={n.to} className="hover:text-slate-900">{n.label}</Link></li>)}
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">Company</p>
          <ul className="space-y-2 text-sm text-slate-600">
            <li><Link to="/pricing" className="hover:text-slate-900">Pricing</Link></li>
            <li><Link to="/security" className="hover:text-slate-900">Security</Link></li>
            <li><Link to="/contact" className="hover:text-slate-900">Contact</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">Resources</p>
          <ul className="space-y-2 text-sm text-slate-600">
            <li><Link to="/blog" className="hover:text-slate-900">Blog</Link></li>
            <li><Link to="/compare" className="hover:text-slate-900">Alternatives</Link></li>
            <li><Link to="/whats-new" className="hover:text-slate-900">What&apos;s new</Link></li>
            <li><Link to="/status" className="hover:text-slate-900">Status</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400 mb-4">Get started</p>
          <Link to="/pricing" className="gx-cta inline-flex items-center gap-1.5 rounded-full px-5 py-2.5 text-sm font-bold">See pricing<ArrowRight size={13} /></Link>
          <button type="button" onClick={openTrial} className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-slate-700 hover:text-slate-900">Or start a free trial →</button>
        </div>
      </div>
      <div className="border-t border-slate-100">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-5 text-xs text-slate-400 flex flex-wrap justify-between gap-4 items-center">
          <span>© {new Date().getFullYear()} GymAxis AI. All rights reserved.</span>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1" data-testid="gx-footer-legal">
            <Link to="/privacy" className="hover:text-slate-700" data-testid="gx-footer-privacy">Privacy</Link>
            <Link to="/terms" className="hover:text-slate-700" data-testid="gx-footer-terms">Terms</Link>
            <Link to="/refunds" className="hover:text-slate-700" data-testid="gx-footer-refunds">Refunds &amp; cancellation</Link>
            <Link to="/security" className="hover:text-slate-700" data-testid="gx-footer-security">Security</Link>
          </div>
          <span>Made for fitness operators.</span>
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
