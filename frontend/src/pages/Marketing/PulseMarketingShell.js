/**
 * PulseMarketingShell — the canonical pulsefitness.ai chrome (black sticky
 * PulseHeader + PulseFooter + LoginModal) for public marketing sub-pages
 * such as the Blog. Replaces the legacy "gx-" MarketingShell so these pages
 * share the exact header, footer, fonts (Proxima Nova) and brand tokens as
 * the main landing page. (Iter 279)
 */
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/App';
import { PulseHeader, PulseFooter, LoginModal, PULSE_LANDING_CSS } from '@/pages/PulseLandingPage';

export default function PulseMarketingShell({ children }) {
  const { theme, toggleTheme, login } = useAuth();
  const { i18n } = useTranslation();
  const [loginOpen, setLoginOpen] = useState(false);

  // Marketing pages render in their own light theme regardless of any
  // authenticated app theme the visitor previously set.
  React.useEffect(() => {
    const html = document.documentElement;
    const previous = html.getAttribute('data-theme');
    html.setAttribute('data-theme', 'light');
    return () => { if (previous) html.setAttribute('data-theme', previous); };
  }, []);

  return (
    <div
      className="min-h-screen bg-white antialiased"
      style={{ fontFamily: "'Proxima Nova', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", color: 'var(--color-surface-dark-panel-alt)' }}
      data-theme="light"
      data-testid="pulse-marketing-shell"
    >
      <style>{PULSE_LANDING_CSS}</style>
      <div className="pulse-landing">
        <PulseHeader onSignIn={() => setLoginOpen(true)} theme={theme} toggleTheme={toggleTheme} i18n={i18n} />
        {children}
        <PulseFooter />
        <LoginModal open={loginOpen} onOpenChange={setLoginOpen} onLogin={(d) => login(d.token, d.user)} />
      </div>
    </div>
  );
}
