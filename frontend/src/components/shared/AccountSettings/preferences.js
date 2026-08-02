import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import DigestPreferencesCard from '../DigestPreferencesCard';
import { LANG_PROMPT_SEEN_KEY } from '../LanguagePrompt';

export default function PreferencesSection() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useAuth();
  const [langSuggOn, setLangSuggOn] = useState(() => localStorage.getItem(LANG_PROMPT_SEEN_KEY) !== '1');
  const toggleLangSugg = () => {
    if (langSuggOn) { localStorage.setItem(LANG_PROMPT_SEEN_KEY, '1'); setLangSuggOn(false); }
    else { localStorage.removeItem(LANG_PROMPT_SEEN_KEY); setLangSuggOn(true); }
  };
  return (
    <div className="space-y-6" data-testid="account-section-preferences">
      <div>
        <h3 className="account-section-title">{t('settings.pref_theme_title', 'App theme')}</h3>
        <p className="account-section-sub">
          {t('settings.pref_theme_current', 'Currently')} <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{theme === 'dark' ? t('settings.pref_dark', 'Dark') : t('settings.pref_light', 'Light')}</span>. {t('settings.pref_theme_sub', 'Affects in-app surfaces only — toggle to switch the whole experience including this panel.')}
        </p>
        <button
          type="button"
          onClick={toggleTheme}
          className="account-btn-secondary mt-3"
          data-testid="account-theme-toggle"
        >
          {theme === 'dark' ? t('settings.pref_switch_light', 'Switch to Light') : t('settings.pref_switch_dark', 'Switch to Dark')}
        </button>
      </div>
      <div>
        <h3 className="account-section-title">{t('settings.pref_lang_sugg_title', 'Language suggestions')}</h3>
        <p className="account-section-sub">
          {t('settings.pref_lang_sugg_sub', 'When your browser is set to French or German, we offer a one-tap switch to that language. Turn this back on if you dismissed it earlier.')}
        </p>
        <button
          type="button"
          onClick={toggleLangSugg}
          className="account-btn-secondary mt-3"
          data-testid="account-lang-suggestions-toggle"
        >
          {langSuggOn
            ? t('settings.pref_lang_sugg_disable', 'Turn off language suggestions')
            : t('settings.pref_lang_sugg_enable', 'Show language suggestions again')}
        </button>
        <p className="text-xs mt-2" style={{ color: 'var(--theme-text-muted, #94a3b8)' }} data-testid="account-lang-suggestions-state">
          {langSuggOn
            ? t('settings.pref_lang_sugg_on', 'Language suggestions are on.')
            : t('settings.pref_lang_sugg_off', 'Language suggestions are off.')}
        </p>
      </div>
      <div>
        <h3 className="account-section-title">{t('settings.pref_digest_title', 'Email digest')}</h3>
        <p className="account-section-sub">{t('settings.pref_digest_sub', 'Choose which weekly and daily roll-ups land in your inbox.')}</p>
        <div className="mt-3">
          <DigestPreferencesCard />
        </div>
      </div>
    </div>
  );
}
