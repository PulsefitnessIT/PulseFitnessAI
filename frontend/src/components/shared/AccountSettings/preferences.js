import { useAuth } from '@/App';
import DigestPreferencesCard from '../DigestPreferencesCard';

export default function PreferencesSection() {
  const { theme, toggleTheme } = useAuth();
  return (
    <div className="space-y-6" data-testid="account-section-preferences">
      <div>
        <h3 className="account-section-title">App theme</h3>
        <p className="account-section-sub">
          Currently <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{theme === 'dark' ? 'Dark' : 'Light'}</span>. Affects in-app surfaces only — toggle to switch the whole experience including this panel.
        </p>
        <button
          type="button"
          onClick={toggleTheme}
          className="account-btn-secondary mt-3"
          data-testid="account-theme-toggle"
        >
          Switch to {theme === 'dark' ? 'Light' : 'Dark'}
        </button>
      </div>
      <div>
        <h3 className="account-section-title">Email digest</h3>
        <p className="account-section-sub">Choose which weekly and daily roll-ups land in your inbox.</p>
        <div className="mt-3">
          <DigestPreferencesCard />
        </div>
      </div>
    </div>
  );
}

