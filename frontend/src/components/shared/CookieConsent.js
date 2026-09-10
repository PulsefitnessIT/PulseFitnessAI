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
import { Shield } from 'lucide-react';
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
    <div className="fixed bottom-0 left-0 right-0 z-40 p-4 pointer-events-none" data-bottom-banner="cookie" data-testid="cookie-consent-banner" data-brand={isPulse ? 'pulse' : 'gymaxis'}>
      <div className="max-w-4xl mx-auto bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4 pointer-events-auto">
        <Shield size={20} className="shrink-0 mt-1 sm:mt-0" style={{ color: accent }} />
        <div className="flex-1">
          <p className="text-sm text-zinc-300 leading-relaxed">
            {t('cookie.message', 'We use essential cookies to keep you signed in and provide core functionality. We do not use tracking or advertising cookies.')}
            {' '}<a href="/privacy" className="hover:underline" style={{ color: accent }}>{t('cookie.privacy_policy', 'Privacy Policy')}</a>
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button onClick={handleDecline} className="px-4 py-2 text-sm text-zinc-400 dark:text-zinc-500 hover:text-white border border-zinc-700 rounded-lg transition-colors" data-testid="cookie-decline-btn">
            {t('cookie.essential_only', 'Essential Only')}
          </button>
          <button
            onClick={handleAccept}
            className="px-4 py-2 text-sm text-white rounded-lg font-medium transition-colors"
            style={{ background: accent }}
            onMouseEnter={(e) => { e.currentTarget.style.background = accentHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = accent; }}
            data-testid="cookie-accept-btn"
          >
            {t('cookie.accept_all', 'Accept All')}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CookieConsent;
