/**
 * LanguageSwitcher — compact EN/FR/DE globe dropdown for the AUTHENTICATED app
 * (operator module headers + customer/portal headers). Mirrors the marketing
 * Navbar switcher: changes the UI language and, when a user is signed in,
 * persists the choice to their profile so it follows them across devices and
 * localises the emails the platform sends them.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe, Check } from 'lucide-react';
import axios from 'axios';

const LANGS = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'de', label: 'Deutsch', flag: '🇩🇪' },
];

const API = process.env.REACT_APP_BACKEND_URL;

export const LanguageSwitcher = ({ className = '' }) => {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const current = i18n.language?.substring(0, 2) || 'en';

  const choose = (code) => {
    i18n.changeLanguage(code);
    setOpen(false);
    const tk = localStorage.getItem('token');
    if (tk && API) {
      axios.patch(`${API}/api/account/profile`, { language: code },
        { headers: { Authorization: `Bearer ${tk}` } }).catch(() => {});
    }
  };

  return (
    <div className={`relative ${className}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border hover:opacity-80 transition-colors"
        style={{ borderColor: 'var(--theme-border, #e2e8f0)', color: 'var(--theme-text-muted, #64748b)' }}
        data-testid="lang-switcher-btn"
        aria-label="Change language"
      >
        <Globe size={15} />
        <span className="text-xs font-medium uppercase">{current}</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-2 w-40 rounded-lg shadow-xl z-50 overflow-hidden"
            style={{ background: 'var(--theme-surface, #ffffff)', border: '1px solid var(--theme-border, #e2e8f0)' }}
            data-testid="lang-dropdown"
          >
            {LANGS.map((lang) => (
              <button
                key={lang.code}
                onClick={() => choose(lang.code)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  current === lang.code ? 'font-medium' : 'opacity-70 hover:opacity-100'
                }`}
                style={{ color: 'var(--theme-text, #0f172a)' }}
                data-testid={`lang-option-${lang.code}`}
              >
                <span className="text-base">{lang.flag}</span>
                <span className="flex-1 text-left">{lang.label}</span>
                {current === lang.code ? <Check size={14} /> : null}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export default LanguageSwitcher;
