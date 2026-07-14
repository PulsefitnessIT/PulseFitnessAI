import { useEffect, useState } from 'react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Field, input } from './shared';

const TOGGLES = [
  { key: 'enabled', label: 'Dealer Warranty Parts enabled' },
  { key: 'over_allowance_approval_required', label: 'Require manager approval when over allowance' },
  { key: 'require_receipt_confirmation', label: 'Require dealer receipt confirmation' },
  { key: 'ai_recommendations_enabled', label: 'AI recommendations enabled' },
  { key: 'multi_currency_enabled', label: 'Multi-currency enabled' },
];

export default function SettingsTab() {
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => { dpApi.getSettings().then(setS).finally(() => setLoading(false)); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const saved = await dpApi.saveSettings({
        ...s,
        default_percentage: Number(s.default_percentage),
        approval_threshold: Number(s.approval_threshold),
      });
      setS(saved); notify.success('Settings saved');
    } catch { notify.error('Failed to save (manager access required)'); }
    finally { setSaving(false); }
  };

  if (loading || !s) return <Spinner />;
  return (
    <div className="max-w-xl space-y-5" data-testid="dp-settings-tab">
      <h3 className="text-sm font-semibold text-slate-500">Dealer Warranty Parts settings</h3>
      <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Default spare parts %"><input type="number" step="0.1" data-testid="dp-settings-pct" className={input} value={s.default_percentage} onChange={(e) => setS({ ...s, default_percentage: e.target.value })} /></Field>
          <Field label="Manager approval threshold (£)"><input type="number" className={input} value={s.approval_threshold} onChange={(e) => setS({ ...s, approval_threshold: e.target.value })} /></Field>
        </div>
        <div className="space-y-2">
          {TOGGLES.map((t) => (
            <label key={t.key} className="flex items-center justify-between py-1.5 text-sm cursor-pointer">
              <span className="text-slate-700">{t.label}</span>
              <button data-testid={`dp-toggle-${t.key}`} onClick={() => setS({ ...s, [t.key]: !s[t.key] })}
                className={`w-11 h-6 rounded-full transition-colors relative ${s[t.key] ? 'bg-[var(--gx-brand-from)]' : 'bg-slate-200'}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${s[t.key] ? 'translate-x-5' : 'translate-x-0.5'}`} />
              </button>
            </label>
          ))}
        </div>
        <button data-testid="dp-settings-save" onClick={save} disabled={saving} className="w-full py-2.5 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg hover:opacity-90 disabled:opacity-50">
          {saving ? 'Saving…' : 'Save settings'}
        </button>
      </div>
    </div>
  );
}
