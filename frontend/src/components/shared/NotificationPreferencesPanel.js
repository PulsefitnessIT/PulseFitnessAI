import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Bell, Check, Loader2 } from 'lucide-react';

/**
 * NotificationPreferencesPanel (iter 215c0)
 * Operator-facing email/SMS opt-in/out by category. GDPR + PECR compliant.
 * Member version uses /portal/me/notification-preferences with a member token.
 */
const OPERATOR_CATEGORIES = [
  { key: 'transactional',   label: 'Transactional', desc: 'Password resets, invoice receipts, security alerts. Required.', locked: true },
  { key: 'billing_alerts',  label: 'Billing alerts', desc: 'Failed payment, low balance, trial expiry.' },
  { key: 'product_updates', label: 'Product updates', desc: 'What\'s New, security advisories, breaking changes.' },
  { key: 'weekly_digest',   label: 'Weekly digest', desc: 'Operator weekly summary email.' },
  { key: 'feature_tips',    label: 'Feature tips', desc: 'Nudges, in-app help suggestions, onboarding.' },
  { key: 'marketing',       label: 'Marketing', desc: 'Promotions, partner offers, webinars.' },
  { key: 'sms',             label: 'SMS alerts', desc: 'High-priority SMS for critical alerts.' },
];

const NotificationPreferencesPanel = () => {
  const { API } = useAuth();
  const [prefs, setPrefs] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);

  useEffect(() => {
    const run = async () => {
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API}/me/notification-preferences`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setPrefs(res.data.prefs);
      } catch {
        setPrefs({});
      }
    };
    run();
  }, [API]);

  const toggle = async (key) => {
    if (OPERATOR_CATEGORIES.find(c => c.key === key)?.locked) return;
    setSaving(true);
    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    try {
      const token = localStorage.getItem('token');
      await axios.put(`${API}/me/notification-preferences`,
        { prefs: next },
        { headers: { Authorization: `Bearer ${token}` } });
      setSavedAt(Date.now());
    } catch {
      // revert on error
      setPrefs(prefs);
    } finally {
      setSaving(false);
    }
  };

  if (!prefs) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]" data-testid="notif-prefs-loading">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading preferences…
      </div>
    );
  }

  return (
    <div data-testid="notification-preferences-panel" className="rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] p-6 shadow-sm">
      <div className="flex items-start justify-between mb-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-brand-blue)]/10 flex items-center justify-center">
            <Bell className="w-5 h-5 text-[var(--color-brand-blue)]" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-[var(--theme-text)]">Notification preferences</h3>
            <p className="text-xs text-[var(--color-text-muted)]">Choose which emails &amp; SMS you want to receive.</p>
          </div>
        </div>
        {savedAt && (
          <span className="flex items-center gap-1 text-xs text-emerald-600" data-testid="notif-prefs-saved">
            <Check className="w-3 h-3" /> Saved
          </span>
        )}
      </div>

      <ul className="divide-y divide-[var(--theme-border)]">
        {OPERATOR_CATEGORIES.map(cat => (
          <li key={cat.key} data-testid={`notif-pref-row-${cat.key}`} className="flex items-start justify-between py-3 gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-[var(--theme-text)]">{cat.label}</p>
                {cat.locked && <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-[var(--color-text-muted)]">Required</span>}
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{cat.desc}</p>
            </div>
            <button
              type="button"
              onClick={() => toggle(cat.key)}
              disabled={saving || cat.locked}
              data-testid={`notif-pref-toggle-${cat.key}`}
              aria-checked={!!prefs[cat.key]}
              role="switch"
              className={`relative w-11 h-6 rounded-full transition-colors flex-shrink-0 ${
                prefs[cat.key] ? 'bg-[var(--color-brand-blue)]' : 'bg-slate-300 dark:bg-slate-600'
              } ${cat.locked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                  prefs[cat.key] ? 'translate-x-5' : ''
                }`}
              />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default NotificationPreferencesPanel;
