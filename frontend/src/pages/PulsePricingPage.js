/**
 * Pulse Fitness Service Portal — dedicated Plans & Pricing page.
 *
 * The Lite vs Pro tier comparison was moved off the marketing homepage
 * into its own route at /pulse-pricing so the homepage stays focused on
 * the value story. Reuses the Pulse shell (header, footer, login modal,
 * scoped global CSS) so brand parity with PulseLandingPage is automatic.
 */
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Sparkles } from 'lucide-react';

import PulseUpgradeRequestModal from '@/components/pulse/PulseUpgradeRequestModal';
import PulseModulePricing from '@/components/pulse/PulseModulePricing';
import PulsePricingExtras from '@/components/pulse/PulsePricingExtras';
import { useAuth } from '@/App';
import { useTranslation } from 'react-i18next';

import {
  PulseHeader,
  PulseFooter,
  LoginModal,
  PULSE_LANDING_CSS,
} from './PulseLandingPage';

export default function PulsePricingPage({ onLogin }) {
  const { theme, toggleTheme } = useAuth();
  const { t, i18n } = useTranslation();
  const [loginOpen, setLoginOpen] = useState(false);
  const [loginRedirect, setLoginRedirect] = useState('');
  const [upgradeOpen, setUpgradeOpen] = useState(false);

  // A plan CTA passes the post-login destination (e.g. /choose-plan?module=crm)
  // so existing Lite customers land in Stripe checkout right after signing in.
  const openLogin = (redirect) => {
    setLoginRedirect(typeof redirect === 'string' ? redirect : '');
    setLoginOpen(true);
  };
  const openUpgrade = () => setUpgradeOpen(true);

  // Same theme-lock as the landing page — Pulse marketing surfaces
  // always render in light mode regardless of the authenticated app
  // theme preference.
  useEffect(() => {
    const html = document.documentElement;
    const previous = html.getAttribute('data-theme');
    html.setAttribute('data-theme', 'light');
    return () => {
      if (previous) html.setAttribute('data-theme', previous);
    };
  }, []);

  return (
    <div
      className="min-h-screen bg-white antialiased"
      style={{
        fontFamily: "'Proxima Nova', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        color: 'var(--color-surface-dark-panel-alt)',
      }}
      data-theme="light"
      data-testid="pulse-pricing-page"
    >
      <style>{PULSE_LANDING_CSS}</style>
      <div className="pulse-landing">
        <PulseHeader onSignIn={openLogin} theme={theme} toggleTheme={toggleTheme} i18n={i18n} />

        {/* Page hero — short, focused on plans */}
        <section className="relative pt-20 sm:pt-28 pb-10 overflow-hidden" data-testid="pulse-pricing-hero">
          <div className="pointer-events-none absolute inset-0">
            <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[40rem] h-[40rem] rounded-full bg-[rgb(var(--rgb-pulse-primary)/0.08)] blur-[140px]" />
          </div>
          <div className="relative max-w-5xl mx-auto px-6 text-center">
            <Link
              to="/pulse"
              className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-[var(--color-text-slate)] hover:text-[var(--color-surface-dark-panel-alt)] transition-colors mb-6"
              data-testid="pulse-pricing-back-home"
            >
              <ArrowLeft size={14} /> {t('pulse.pp_back', 'Back to Pulse home')}
            </Link>
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
              className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4"
            >
              <Sparkles size={12} />
              {t('pulse.pp_badge', 'Pulse Plans')}
            </motion.div>
            <motion.h1
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
              className="text-3xl sm:text-5xl lg:text-6xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)] leading-[1.08]"
            >
              {t('pulse.pp_title', 'Pricing that scales with your gym.')}
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.12 }}
              className="mt-5 max-w-2xl mx-auto text-sm sm:text-lg text-[var(--color-text-slate)]"
            >
              {t('pulse.pp_desc', 'Pick the modules you need — Operations, CRM, Marketing and Memberships — each a standalone subscription in your currency. Already a Pulse Fitness equipment customer? Your Lite portal is included free.')}
            </motion.p>
            <div className="mt-8 inline-flex items-center gap-2 text-xs text-[var(--color-text-slate)]">
              <ShieldCheck size={13} className="text-emerald-500" />
              {t('pulse.pp_note', '3-day free trial · all modules unlocked for owners & managers · cancel anytime')}
            </div>
          </div>
        </section>

        {/* Modules — the product (public, multi-currency). Includes the free
            Lite tile for existing Pulse Fitness equipment customers. */}
        <PulseModulePricing onStart={openLogin} />

        {/* ROI calculator · service-provider tiers · FAQ */}
        <PulsePricingExtras onStart={openLogin} />

        <PulseFooter />
        <LoginModal open={loginOpen} onOpenChange={setLoginOpen} onLogin={onLogin} redirectTo={loginRedirect} />
        <PulseUpgradeRequestModal open={upgradeOpen} onClose={() => setUpgradeOpen(false)} />
      </div>
    </div>
  );
}
