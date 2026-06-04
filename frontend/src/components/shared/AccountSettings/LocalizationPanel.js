import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Globe, Loader2 } from 'lucide-react';
import { API, useAuthHeaders } from './shared';
import { invalidateLocalization } from '@/utils/localization';

/**
 * Localization panel (Iter 220p1 — USA readiness).
 * Owner / master admin sets the org's market: country drives currency +
 * timezone + tax vocabulary. Defaults to the UK so nothing changes for
 * existing customers.
 */
export default function LocalizationPanel() {
  const headers = useAuthHeaders();
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ country_code: '', currency: '', timezone: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/org/localization`, { headers: headers() });
      setData(data);
      const loc = data.localization || {};
      setForm({
        country_code: loc.country_code || 'GB',
        currency: loc.currency || 'GBP',
        timezone: loc.timezone || 'Europe/London',
      });
    } catch {
      setData(null);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (!data) return null;

  const countries = data.supported_countries || [];
  const canEdit = !!data.can_edit;
  const selectedCountry = countries.find((c) => c.code === form.country_code) || countries[0] || {};
  const tzOptions = selectedCountry.timezones || [form.timezone];
  const currencyOptions = Object.keys(data.currency_symbols || { GBP: '£' });

  // When the country changes, snap currency + timezone to that country's defaults.
  const onCountry = (code) => {
    const c = countries.find((x) => x.code === code) || {};
    setForm({
      country_code: code,
      currency: c.currency || form.currency,
      timezone: (c.timezones && c.timezones[0]) || c.timezone || form.timezone,
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const { data: res } = await axios.put(`${API}/org/localization`, form, { headers: headers() });
      invalidateLocalization();
      const loc = res.localization || {};
      setData((d) => ({ ...d, localization: loc }));
      toast.success(`Market set to ${loc.country_name} · ${loc.currency}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not update localization');
    }
    setSaving(false);
  };

  const taxLabel = selectedCountry.tax_label || data.localization?.tax_label || 'VAT';

  return (
    <div data-testid="account-section-localization">
      <h3 className="account-section-title flex items-center gap-2"><Globe size={15} /> Region & currency</h3>
      <p className="account-section-sub">
        Your market drives the currency, timezone and tax wording shown on invoices, quotes and dashboards.
      </p>

      <div className="account-card rounded-xl p-5 mt-3 grid sm:grid-cols-3 gap-4">
        <div>
          <label className="text-[11px] uppercase tracking-wider font-semibold block mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>Country</label>
          <select
            value={form.country_code}
            disabled={!canEdit}
            onChange={(e) => onCountry(e.target.value)}
            className="w-full text-sm border rounded-md px-2.5 py-2 bg-transparent disabled:opacity-60"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="localization-country-select"
          >
            {countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </div>

        <div>
          <label className="text-[11px] uppercase tracking-wider font-semibold block mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>Currency</label>
          <select
            value={form.currency}
            disabled={!canEdit}
            onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
            className="w-full text-sm border rounded-md px-2.5 py-2 bg-transparent disabled:opacity-60"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="localization-currency-select"
          >
            {currencyOptions.map((cur) => (
              <option key={cur} value={cur}>{cur} ({data.currency_symbols[cur]})</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-[11px] uppercase tracking-wider font-semibold block mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>Timezone</label>
          <select
            value={form.timezone}
            disabled={!canEdit}
            onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
            className="w-full text-sm border rounded-md px-2.5 py-2 bg-transparent disabled:opacity-60"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="localization-timezone-select"
          >
            {tzOptions.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>

        <div className="sm:col-span-3 flex items-center justify-between flex-wrap gap-2">
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            Tax is shown as <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{taxLabel}</span> for this market.
            {!canEdit && ' Only the Owner can change this.'}
          </p>
          {canEdit && (
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-md text-white disabled:opacity-50"
              style={{ background: 'var(--theme-accent, #2563eb)' }}
              data-testid="localization-save-btn"
            >
              {saving ? <Loader2 size={13} className="animate-spin" /> : null} Save market
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
