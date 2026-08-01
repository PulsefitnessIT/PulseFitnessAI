import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import DigestPreferencesCard from '../DigestPreferencesCard';

export default function PreferencesSection() {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useAuth();
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
        <h3 className="account-section-title">{t('settings.pref_digest_title', 'Email digest')}</h3>
        <p className="account-section-sub">{t('settings.pref_digest_sub', 'Choose which weekly and daily roll-ups land in your inbox.')}</p>
        <div className="mt-3">
          <DigestPreferencesCard />
        </div>
      </div>
    </div>
  );
}
