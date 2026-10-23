/**
 * CookieConsent — bottom banner that asks for consent on first visit.
 *
 * Iter 215bw — brand-aware colour. Pulse Fitness branded routes (under
 * /pulse, /pulse-pricing, etc.) and Pulse-portal authenticated users
 * see the Pulse blue accent; everywhere else uses Pulse Fitness brand-blue.
 * Detection is purely client-side (route + body class) so the banner
 * doesn't need to wait on any auth context.
 */
import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { setBottomBannerVisible } from '@/utils/bottomBanner';
import { useAnyModalOpen } from '@/utils/useAnyModalOpen';

function detectIsPulse() {
  if (typeof window === 'undefined') return false;
  const path = (window.location?.pathname || '').toLowerCase();
  if (path.startsWith('/pulse')) return true;
  // Some pulse routes are nested or aliased — also honour the body
  // attribute that the AppShell sets when the active brand is Pulse.
  const bodyBrand = document.body?.dataset?.brand;
  if (bodyBrand === 'pulse') return true;
  return false;
}

const CookieConsent = () => {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);
  const anyModalOpen = useAnyModalOpen();
  const isPulse = useMemo(() => detectIsPulse(), []);
  const accent = isPulse ? 'var(--pulse-primary)' : 'var(--color-brand-blue)';
  const accentHover = isPulse ? 'var(--pulse-primary-hover)' : 'var(--color-brand-blue-hover)';

  useEffect(() => {
    const consented = localStorage.getItem('cookie_consent');
    if (!consented) setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible) return undefined;
    setBottomBannerVisible(true);
    return () => setBottomBannerVisible(false);
  }, [visible]);

  const handleAccept = () => {
    localStorage.setItem('cookie_consent', 'accepted');
    localStorage.setItem('cookie_consent_at', new Date().toISOString());
    setVisible(false);
  };

  const handleDecline = () => {
    localStorage.setItem('cookie_consent', 'essential_only');
    localStorage.setItem('cookie_consent_at', new Date().toISOString());
    setVisible(false);
  };

  if (!visible) return null;
  // Yield to any open modal/dialog so we never cover its action buttons.
  if (anyModalOpen) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 sm:bottom-4 sm:right-4 sm:left-auto z-[60] p-3 sm:p-0 pointer-events-none" data-bottom-banner="cookie" data-testid="cookie-consent-banner" data-brand={isPulse ? 'pulse' : 'gymaxis'}>
      <div className="w-full sm:w-[340px] bg-black border border-zinc-800 rounded-xl shadow-2xl p-5 pointer-events-auto" style={{ color: '#ffffff' }}>
        <p className="text-sm leading-relaxed" style={{ color: '#ffffff' }}>
          {t('cookie.message', 'This website uses cookies to ensure you get the best experience on our website.')}
        </p>
        <a href="/privacy" className="inline-block mt-2 text-sm underline underline-offset-2 transition-colors" style={{ color: 'rgba(255,255,255,0.7)' }} onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; }} onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.7)'; }} data-testid="cookie-learn-more">
          {t('cookie.learn_more', 'Learn more')}
        </a>
        <div className="flex items-center justify-between gap-3 mt-4">
          <button onClick={handleDecline} className="text-sm font-medium transition-colors" style={{ color: 'rgba(255,255,255,0.7)' }} onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; }} onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.7)'; }} data-testid="cookie-decline-btn">
            {t('cookie.decline', 'Decline')}
          </button>
          <button
            onClick={handleAccept}
            className="px-5 py-2 text-sm rounded-md font-medium transition-colors"
            style={{ background: accent, color: '#ffffff' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = accentHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = accent; }}
            data-testid="cookie-accept-btn"
          >
            {t('cookie.allow_cookies', 'Allow cookies')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieConsent;
