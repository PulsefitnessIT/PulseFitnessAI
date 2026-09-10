import { useState, useEffect, useCallback } from 'react';
import { Download, X, Share, Plus, Smartphone } from 'lucide-react';
import { useAuth } from '@/App';
import { setBottomBannerVisible } from '@/utils/bottomBanner';
import { useAnyModalOpen } from '@/utils/useAnyModalOpen';

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function isStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

export default function PWAInstallPrompt() {
  const auth = useAuth();
  const anyModalOpen = useAnyModalOpen();
  const onServiceDesk = typeof window !== 'undefined'
    && window.location.pathname.toLowerCase().startsWith('/service-desk');
  const isPulse = auth?.user?.account_type === 'pulse_pro' || auth?.user?.account_type === 'lite';
  // Iter 275 — on the Service Desk surface, brand the install banner as the
  // Service Desk (orange) so it matches the dedicated /service-desk manifest.
  const brand = onServiceDesk ? 'Service Desk' : (isPulse ? 'Pulse Fitness' : 'Pulse Fitness');
  // Iter 215bw — per-brand PWA chrome.
  const brandLetter = onServiceDesk ? 'S' : (isPulse ? 'P' : 'G');
  const brandColour = onServiceDesk ? '#f97316' : (isPulse ? 'var(--pulse-primary)' : 'var(--color-info-ios)');
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showBanner, setShowBanner] = useState(false);
  const [showIOSGuide, setShowIOSGuide] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;
    if (localStorage.getItem('pwa_install_dismissed')) return;

    const handler = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  // Show banner after user logs in — Iter 216h214: stakeholder audit
  // (h212) flagged "PWA prompt too frequent". Two cooldowns:
  //   1. SessionStorage flag — show at most once per browser session.
  //   2. localStorage timestamp — even across sessions, throttle to once
  //      per 7 days unless user actively dismisses (which uses a
  //      separate persistent flag below).
  //   3. Delay raised from 3s → 30s so we wait for engagement signals
  //      (the user is actually using the app, not just navigating away).
  const triggerShow = useCallback(() => {
    if (isStandalone() || dismissed) return;
    if (localStorage.getItem('pwa_install_dismissed')) return;
    if (sessionStorage.getItem('pwa_prompt_shown_session') === '1') return;
    const lastShown = Number(localStorage.getItem('pwa_prompt_last_shown') || 0);
    const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
    if (lastShown && Date.now() - lastShown < SEVEN_DAYS_MS) return;
    setTimeout(() => {
      if (isStandalone() || dismissed) return;
      if (localStorage.getItem('pwa_install_dismissed')) return;
      if (sessionStorage.getItem('pwa_prompt_shown_session') === '1') return;
      setShowBanner(true);
      sessionStorage.setItem('pwa_prompt_shown_session', '1');
      localStorage.setItem('pwa_prompt_last_shown', String(Date.now()));
    }, 30000);
  }, [dismissed]);

  useEffect(() => {
    const handleLogin = () => triggerShow();
    window.addEventListener('pwa-check-install', handleLogin);
    // Also check on mount if user is already logged in
    if (localStorage.getItem('token') || localStorage.getItem('crm_token')) {
      triggerShow();
    }
    return () => window.removeEventListener('pwa-check-install', handleLogin);
  }, [triggerShow]);

  useEffect(() => {
    if (!showBanner || isStandalone()) return undefined;
    setBottomBannerVisible(true);
    return () => setBottomBannerVisible(false);
  }, [showBanner]);

  const handleInstall = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const result = await deferredPrompt.userChoice;
      if (result.outcome === 'accepted') {
        setShowBanner(false);
      }
      setDeferredPrompt(null);
    } else if (isIOS()) {
      setShowIOSGuide(true);
    }
  };

  const handleDismiss = () => {
    setShowBanner(false);
    setDismissed(true);
    localStorage.setItem('pwa_install_dismissed', Date.now().toString());
  };

  if (!showBanner || isStandalone()) return null;

  const canInstall = !!deferredPrompt;
  const showIOS = isIOS() && !canInstall;

  return (
    <>
      {/* Install Banner — hidden while any modal/dialog is open so it never
          sits over a dialog's buttons. */}
      {!anyModalOpen && (
      <div
        className="fixed bottom-4 left-4 right-4 z-40 mx-auto max-w-md animate-in slide-in-from-bottom-4 pointer-events-none"
        data-bottom-banner="pwa"
        data-testid="pwa-install-banner"
      >
        <div className="rounded-2xl p-4 shadow-2xl border pointer-events-auto"
          style={{ background: '#111', borderColor: '#222' }}>
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: brandColour }}>
              <span className="text-white font-bold text-lg">{brandLetter}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white font-semibold text-sm">Add {brand} to Home Screen</p>
              <p className="text-[#888] text-xs mt-0.5 leading-relaxed">
                Quick access, stay signed in, and get a full-screen experience
              </p>
            </div>
            <button onClick={handleDismiss} className="p-1 shrink-0 rounded-lg hover:bg-white/5" data-testid="pwa-dismiss-btn">
              <X size={16} className="text-[#666]" />
            </button>
          </div>

          <div className="flex gap-2 mt-3">
            {(canInstall || !showIOS) && (
              <button
                onClick={handleInstall}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-colors"
                style={{ background: brandColour }}
                data-testid="pwa-install-btn"
              >
                <Download size={15} /> Install App
              </button>
            )}
            {showIOS && (
              <button
                onClick={() => setShowIOSGuide(true)}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white transition-colors"
                style={{ background: brandColour }}
                data-testid="pwa-ios-guide-btn"
              >
                <Smartphone size={15} /> Add to Home Screen
              </button>
            )}
            <button
              onClick={handleDismiss}
              className="px-4 py-2.5 rounded-xl text-sm font-medium text-[#888] hover:text-white transition-colors"
              style={{ background: 'var(--color-surface-dark-2)' }}
              data-testid="pwa-later-btn"
            >
              Later
            </button>
          </div>
        </div>
      </div>
      )}

      {/* iOS Instructions Modal */}
      {showIOSGuide && (
        <div className="fixed inset-0 z-[300] flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowIOSGuide(false)}>
          <div className="w-full max-w-sm mx-4 mb-4 sm:mb-0 rounded-2xl p-5 shadow-2xl"
            style={{ background: 'var(--color-neutral-900)', border: '1px solid #222' }}
            onClick={e => e.stopPropagation()}
            data-testid="pwa-ios-guide">
            <div className="text-center mb-4">
              <div className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center mb-3" style={{ background: brandColour }}>
                <span className="text-white font-bold text-2xl">{brandLetter}</span>
              </div>
              <h3 className="text-white font-semibold text-lg">Install {brand}</h3>
              <p className="text-[#888] text-xs mt-1">Add to your home screen for the best experience</p>
            </div>

            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--color-surface-dark-2)' }}>
                  <Share size={16} style={{ color: brandColour }} />
                </div>
                <div>
                  <p className="text-white text-sm font-medium">1. Tap the Share button</p>
                  <p className="text-[#666] text-xs">At the bottom of Safari</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--color-surface-dark-2)' }}>
                  <Plus size={16} style={{ color: brandColour }} />
                </div>
                <div>
                  <p className="text-white text-sm font-medium">2. Tap "Add to Home Screen"</p>
                  <p className="text-[#666] text-xs">Scroll down in the share menu</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'var(--color-surface-dark-2)' }}>
                  <Download size={16} style={{ color: brandColour }} />
                </div>
                <div>
                  <p className="text-white text-sm font-medium">3. Tap "Add"</p>
                  <p className="text-[#666] text-xs">{brand} will appear on your home screen</p>
                </div>
              </div>
            </div>

            <button
              onClick={() => setShowIOSGuide(false)}
              className="w-full mt-5 py-2.5 rounded-xl text-sm font-semibold text-white"
              style={{ background: brandColour }}
              data-testid="pwa-ios-got-it-btn"
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}
