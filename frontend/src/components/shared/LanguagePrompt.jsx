/**
 * LanguagePrompt — one-tap browser-language offer.
 *
 * The i18n detector already auto-selects FR/DE for brand-new anonymous
 * visitors (order: localStorage → navigator). This prompt covers the gap
 * that detector can't: a signed-in user whose *account* language is English
 * (the default) but whose browser is set to French or German — App.js forces
 * the saved account language on hydrate, so they'd never see the auto-detect.
 *
 * We offer, we don't force: a small dismissible card in the TARGET language
 * ("Continuer en français ?" / "Auf Deutsch fortfahren?"). One tap switches
 * the UI and — when signed in — persists the choice to the account profile.
 * Shown at most once per browser (localStorage flag), so it never nags.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Globe, X } from 'lucide-react';
import i18n from '@/i18n';
import { useAuth } from '@/App';

const SEEN_KEY = 'pf_lang_prompt_seen';
export const LANG_PROMPT_SEEN_KEY = SEEN_KEY;

const COPY = {
  fr: {
    title: 'Continuer en français ?',
    body: 'Votre navigateur semble être en français. Vous pouvez changer la langue à tout moment.',
    accept: 'Passer en français',
    dismiss: 'Non, merci',
  },
  de: {
    title: 'Auf Deutsch fortfahren?',
    body: 'Ihr Browser ist offenbar auf Deutsch eingestellt. Sie können die Sprache jederzeit ändern.',
    accept: 'Auf Deutsch wechseln',
    dismiss: 'Nein, danke',
  },
};

// Base language of the browser, restricted to the two we offer.
function detectBrowserLang() {
  const raw = (navigator.languages && navigator.languages[0]) || navigator.language || '';
  const base = raw.toLowerCase().split('-')[0];
  return base === 'fr' || base === 'de' ? base : null;
}

export default function LanguagePrompt() {
  const { user, token, API, refreshUser } = useAuth();
  const [lang, setLang] = useState(null);
  const [busy, setBusy] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(SEEN_KEY) === '1') return;
    const browser = detectBrowserLang();
    if (!browser) return;
    const active = (i18n.language || 'en').split('-')[0];
    if (active === browser) return; // already in their language — nothing to offer
    // Small delay so it doesn't fight the initial app paint / other banners.
    const timer = setTimeout(() => setLang(browser), 1200);
    return () => clearTimeout(timer);
  }, [user?.id]);

  const finish = () => {
    localStorage.setItem(SEEN_KEY, '1');
    setLeaving(true);
    setTimeout(() => setLang(null), 220);
  };

  const accept = async () => {
    setBusy(true);
    try {
      i18n.changeLanguage(lang);
      localStorage.setItem('i18nextLng', lang);
      if (user && token) {
        try {
          await axios.patch(`${API}/account/profile`, { language: lang }, { headers: { Authorization: `Bearer ${token}` } });
          refreshUser?.();
        } catch { /* non-blocking — UI already switched */ }
      }
    } finally {
      setBusy(false);
      finish();
    }
  };

  if (!lang) return null;
  const c = COPY[lang];

  return (
    <div
      role="dialog"
      aria-label={c.title}
      data-testid="language-prompt"
      className="fixed bottom-4 left-4 z-[300] max-w-[320px] w-[calc(100%-2rem)] sm:w-[320px]"
      style={{
        transition: 'opacity 220ms ease, transform 220ms ease',
        opacity: leaving ? 0 : 1,
        transform: leaving ? 'translateY(12px)' : 'translateY(0)',
      }}
    >
      <div
        className="rounded-2xl border border-white/15 shadow-2xl p-4"
        style={{
          background: 'rgba(15, 23, 42, 0.92)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          color: '#e2e8f0',
        }}
      >
        <div className="flex items-start gap-3">
          <div className="shrink-0 rounded-xl bg-cyan-500/15 text-cyan-300 p-2">
            <Globe size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-white leading-snug">{c.title}</p>
            <p className="text-[12px] text-slate-300 mt-1 leading-relaxed">{c.body}</p>
          </div>
          <button
            type="button"
            onClick={finish}
            aria-label={c.dismiss}
            data-testid="language-prompt-dismiss"
            className="shrink-0 -mr-1 -mt-1 p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X size={15} />
          </button>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={accept}
            disabled={busy}
            data-testid="language-prompt-accept"
            className="flex-1 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-60 text-slate-900 text-sm font-bold py-2 transition-colors"
          >
            {c.accept}
          </button>
          <button
            type="button"
            onClick={finish}
            data-testid="language-prompt-decline"
            className="rounded-xl px-3 py-2 text-sm font-semibold text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
          >
            {c.dismiss}
          </button>
        </div>
      </div>
    </div>
  );
}
