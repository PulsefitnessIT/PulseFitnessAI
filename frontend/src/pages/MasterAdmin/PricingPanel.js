/**
 * Master Admin — Pricing Panel.
 *
 * Single source of truth editor for module + bundle pricing across both
 * brands (GymAxis, Pulse Fitness). Operator switches brand, edits
 * monthly/annual prices in three currencies (GBP/EUR/USD), tunes the
 * per-site volume discount tiers, and saves. The public homepage's
 * pricing page consumes the same data via /api/pricing/public.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  Save, RotateCcw, Sparkles, Plus, Trash2, ChevronDown, ChevronUp, History,
  PoundSterling, Euro, DollarSign, Loader2, Eye, EyeOff,
} from 'lucide-react';
import MarketingAddonsPanel from './MarketingAddonsPanel';
import PricingDriftPanel from './PricingDriftPanel';

const CURRENCIES = [
  { code: 'GBP', label: 'GBP £', icon: PoundSterling },
  { code: 'EUR', label: 'EUR €', icon: Euro },
  { code: 'USD', label: 'USD $', icon: DollarSign },
];

const BRAND_OPTIONS = [
  { id: 'gymaxis', label: 'GymAxis', accent: 'var(--color-brand-cyan)' },
  { id: 'pulse',   label: 'Pulse Fitness', accent: 'var(--color-brand-cyan)' },
];

export default function PricingPanel() {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [brand, setBrand] = useState('gymaxis');
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null); // plan_id currently saving
  const [expandedId, setExpandedId] = useState(null);
  const [showAudit, setShowAudit] = useState(false);
  const [auditLog, setAuditLog] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/pricing?brand=${brand}`, { headers });
      setPlans(r.data?.plans || []);
    } catch (e) {
      notify.error('Failed to load pricing plans');
    } finally {
      setLoading(false);
    }
  }, [API, brand, headers]);

  useEffect(() => { load(); }, [load]);

  const seedDefaults = async () => {
    try {
      const r = await axios.post(`${API}/master-admin/pricing/seed-defaults`, {}, { headers });
      notify.success(`${r.data?.created || 0} plans seeded`);
      load();
    } catch (e) {
      notify.error('Seed failed');
    }
  };

  const updatePlan = (planId, patch) => {
    setPlans((prev) => prev.map((p) => (p.id === planId ? { ...p, ...patch } : p)));
  };

  const updatePrice = (planId, ccy, cycle, value) => {
    setPlans((prev) => prev.map((p) => {
      if (p.id !== planId) return p;
      const prices = { ...(p.prices || {}) };
      prices[ccy] = { ...(prices[ccy] || {}), [cycle]: Number(value) || 0 };
      return { ...p, prices };
    }));
  };

  const updateTier = (planId, tierIdx, patch) => {
    setPlans((prev) => prev.map((p) => {
      if (p.id !== planId) return p;
      const tiers = [...(p.site_tiers || [])];
      tiers[tierIdx] = { ...tiers[tierIdx], ...patch };
      return { ...p, site_tiers: tiers };
    }));
  };

  const addTier = (planId) => {
    setPlans((prev) => prev.map((p) => {
      if (p.id !== planId) return p;
      const last = (p.site_tiers || []).slice(-1)[0];
      const nextMin = last ? Number(last.max_sites || last.min_sites || 1) + 1 : 1;
      return {
        ...p,
        site_tiers: [...(p.site_tiers || []), { min_sites: nextMin, max_sites: null, discount_pct: 0 }],
      };
    }));
  };

  const removeTier = (planId, tierIdx) => {
    setPlans((prev) => prev.map((p) => {
      if (p.id !== planId) return p;
      return { ...p, site_tiers: (p.site_tiers || []).filter((_, i) => i !== tierIdx) };
    }));
  };

  const savePlan = async (plan) => {
    setSaving(plan.id);
    try {
      const body = {
        name: plan.name,
        description: plan.description,
        features: plan.features || [],
        display_order: plan.display_order,
        active: plan.active,
        is_bundle: plan.is_bundle,
        prices: plan.prices,
        site_tiers: plan.site_tiers,
        vat_rate: plan.vat_rate ?? 0.20,
        vat_inclusive: plan.vat_inclusive ?? true,
      };
      await axios.put(`${API}/master-admin/pricing/${plan.id}`, body, { headers });
      notify.success(`${plan.name} saved`);
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to save pricing plan');
    } finally {
      setSaving(null);
    }
  };

  const loadAudit = async () => {
    try {
      const r = await axios.get(`${API}/master-admin/pricing/audit?limit=20`, { headers });
      setAuditLog(r.data?.entries || []);
      setShowAudit(true);
    } catch (e) {
      notify.error('Audit log unavailable');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-zinc-400" size={24} />
      </div>
    );
  }

  return (
    <div data-testid="pricing-panel" className="space-y-6">
      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 bg-zinc-100 rounded-full p-1" data-testid="pricing-brand-tabs">
          {BRAND_OPTIONS.map((b) => (
            <button
              key={b.id}
              onClick={() => setBrand(b.id)}
              className={`px-4 py-1.5 text-sm font-semibold rounded-full transition ${
                brand === b.id ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-600 hover:text-zinc-900'
              }`}
              data-testid={`pricing-brand-${b.id}`}
            >
              {b.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadAudit}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
            data-testid="pricing-audit-btn"
          >
            <History size={13} /> Audit log
          </button>
          {plans.length === 0 && (
            <button
              onClick={seedDefaults}
              className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900"
              data-testid="pricing-seed-btn"
            >
              <Sparkles size={13} /> Seed defaults
            </button>
          )}
        </div>
      </div>

      {plans.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-zinc-200 p-12 text-center text-sm text-zinc-500" data-testid="pricing-empty">
          No plans yet for {brand}. Click <b>Seed defaults</b> to bootstrap Operations / Memberships / CRM / Marketing + bundle.
        </div>
      )}

      {plans.map((p) => (
        <PlanRow
          key={p.id}
          plan={p}
          isExpanded={expandedId === p.id}
          isSaving={saving === p.id}
          onExpand={() => setExpandedId(expandedId === p.id ? null : p.id)}
          onChange={(patch) => updatePlan(p.id, patch)}
          onPriceChange={(ccy, cycle, value) => updatePrice(p.id, ccy, cycle, value)}
          onTierChange={(idx, patch) => updateTier(p.id, idx, patch)}
          onTierAdd={() => addTier(p.id)}
          onTierRemove={(idx) => removeTier(p.id, idx)}
          onSave={() => savePlan(p)}
        />
      ))}

      {/* Iter 216g · Plan B — Marketing add-on packs (email & SMS bolt-ons) */}
      {brand === 'gymaxis' && (
        <>
          <div className="pt-4 mt-2 border-t border-zinc-200">
            <h3 className="text-base font-semibold text-zinc-900 mb-1">Marketing add-on packs</h3>
            <p className="text-xs text-zinc-500 mb-3">Email-volume + SMS bolt-ons that customers attach on top of the base Marketing module.</p>
            <MarketingAddonsPanel />
          </div>

          {/* Iter 216g · Plan D — Pricing drift audit */}
          <div className="pt-4 mt-2 border-t border-zinc-200">
            <PricingDriftPanel />
          </div>
        </>
      )}

      {showAudit && (
        <AuditDrawer entries={auditLog} onClose={() => setShowAudit(false)} />
      )}
    </div>
  );
}


/* ─────────────────── PlanRow ─────────────────── */

function PlanRow({
  plan, isExpanded, isSaving, onExpand, onChange, onPriceChange,
  onTierChange, onTierAdd, onTierRemove, onSave,
}) {
  const accent = plan.is_bundle ? 'var(--color-brand-cyan)' : 'var(--color-ink)';
  return (
    <div
      className="rounded-xl border border-zinc-200 bg-white overflow-hidden"
      data-testid={`pricing-plan-${plan.module_id}`}
    >
      {/* Header */}
      <div className="flex items-center gap-4 p-4">
        <div
          className="w-2 h-12 rounded"
          style={{ background: plan.active ? accent : 'var(--color-border-strong)' }}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={plan.name || ''}
              onChange={(e) => onChange({ name: e.target.value })}
              className="bg-transparent border-0 text-base font-semibold text-zinc-900 outline-none focus:ring-0 px-0"
              data-testid={`pricing-name-${plan.module_id}`}
            />
            {plan.is_bundle && (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[rgb(var(--rgb-brand-cyan)/0.2)] text-[var(--color-teal-deep)] font-bold">
                Bundle
              </span>
            )}
            <span className="text-[10px] uppercase tracking-wider text-zinc-400">
              {plan.module_id}
            </span>
          </div>
          <input
            type="text"
            value={plan.description || ''}
            onChange={(e) => onChange({ description: e.target.value })}
            placeholder="Short description shown on the public homepage"
            className="w-full bg-transparent border-0 text-sm text-zinc-500 outline-none focus:ring-0 px-0 mt-0.5"
            data-testid={`pricing-desc-${plan.module_id}`}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onChange({ active: !plan.active })}
            className="p-2 rounded-md hover:bg-zinc-100"
            title={plan.active ? 'Hide from homepage' : 'Show on homepage'}
            data-testid={`pricing-toggle-${plan.module_id}`}
          >
            {plan.active ? <Eye size={16} className="text-emerald-600" /> : <EyeOff size={16} className="text-zinc-400" />}
          </button>
          <button
            onClick={onExpand}
            className="p-2 rounded-md hover:bg-zinc-100"
            data-testid={`pricing-expand-${plan.module_id}`}
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          <button
            onClick={onSave}
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)] disabled:opacity-50"
            data-testid={`pricing-save-${plan.module_id}`}
          >
            {isSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* Quick price summary (always visible) */}
      <div className="px-4 pb-4 flex items-center gap-4 text-xs text-zinc-500 border-t border-zinc-100 pt-3">
        {CURRENCIES.map(({ code }) => (
          <div key={code} className="flex items-center gap-1">
            <span className="font-bold text-zinc-700">{code}</span>
            <span>· {formatMoney(plan.prices?.[code]?.monthly || 0, code)}/mo</span>
          </div>
        ))}
      </div>

      {/* Expanded edit area */}
      {isExpanded && (
        <div className="px-4 pb-5 space-y-5 border-t border-zinc-100 bg-zinc-50/50">
          {/* Prices grid */}
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-400 mt-4 mb-2">Prices (minor units · pence/cents)</div>
            <div className="grid grid-cols-3 gap-3">
              {CURRENCIES.map(({ code, label, icon: Icon }) => (
                <div key={code} className="rounded-lg border border-zinc-200 p-3 bg-white">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-zinc-700 mb-2">
                    <Icon size={12} /> {label}
                  </div>
                  <label className="block mb-2">
                    <span className="text-[10px] uppercase text-zinc-500">Monthly</span>
                    <input
                      type="number"
                      value={plan.prices?.[code]?.monthly ?? 0}
                      onChange={(e) => onPriceChange(code, 'monthly', e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 text-sm rounded border border-zinc-200 bg-white text-zinc-900"
                      data-testid={`pricing-${plan.module_id}-${code}-monthly`}
                    />
                  </label>
                  <label className="block">
                    <span className="text-[10px] uppercase text-zinc-500">Annual</span>
                    <input
                      type="number"
                      value={plan.prices?.[code]?.annual ?? 0}
                      onChange={(e) => onPriceChange(code, 'annual', e.target.value)}
                      className="w-full mt-1 px-2 py-1.5 text-sm rounded border border-zinc-200 bg-white text-zinc-900"
                      data-testid={`pricing-${plan.module_id}-${code}-annual`}
                    />
                  </label>
                </div>
              ))}
            </div>
          </div>

          {/* Site discount tiers */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Per-site volume discount</div>
              <button
                onClick={onTierAdd}
                className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--color-teal-deep)] hover:underline"
                data-testid={`pricing-tier-add-${plan.module_id}`}
              >
                <Plus size={12} /> Add tier
              </button>
            </div>
            <div className="space-y-2">
              {(plan.site_tiers || []).map((t, idx) => (
                <div key={idx} className="flex items-center gap-2 text-sm">
                  <span className="text-zinc-500 w-16">From</span>
                  <input
                    type="number"
                    value={t.min_sites ?? 1}
                    onChange={(e) => onTierChange(idx, { min_sites: Number(e.target.value) })}
                    className="w-20 px-2 py-1 text-sm rounded border border-zinc-200"
                  />
                  <span className="text-zinc-500">to</span>
                  <input
                    type="text"
                    placeholder="∞"
                    value={t.max_sites ?? ''}
                    onChange={(e) => onTierChange(idx, { max_sites: e.target.value === '' ? null : Number(e.target.value) })}
                    className="w-20 px-2 py-1 text-sm rounded border border-zinc-200"
                  />
                  <span className="text-zinc-500">sites</span>
                  <span className="text-zinc-500 ml-3">→</span>
                  <input
                    type="number"
                    value={t.discount_pct ?? 0}
                    onChange={(e) => onTierChange(idx, { discount_pct: Number(e.target.value) })}
                    className="w-20 px-2 py-1 text-sm rounded border border-zinc-200"
                  />
                  <span className="text-zinc-500">% off</span>
                  <button
                    onClick={() => onTierRemove(idx)}
                    className="ml-auto p-1 text-zinc-400 hover:text-red-500"
                    title="Remove tier"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {(plan.site_tiers || []).length === 0 && (
                <div className="text-xs text-zinc-400 italic">No discount — flat price for all site counts.</div>
              )}
            </div>
          </div>

          {/* VAT */}
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <label className="flex items-center gap-2">
              <span className="text-zinc-500 font-medium">VAT rate</span>
              <input
                type="number"
                step="0.01"
                value={plan.vat_rate ?? 0.20}
                onChange={(e) => onChange({ vat_rate: Number(e.target.value) })}
                className="w-20 px-2 py-1 text-sm rounded border border-zinc-200"
              />
              <span className="text-zinc-400">(0.20 = 20%)</span>
            </label>
            <label className="flex items-center gap-2 text-zinc-600">
              <input
                type="checkbox"
                checked={plan.vat_inclusive !== false}
                onChange={(e) => onChange({ vat_inclusive: e.target.checked })}
              />
              Prices are VAT-inclusive
            </label>
          </div>
        </div>
      )}
    </div>
  );
}


/* ─────────────────── AuditDrawer ─────────────────── */

function AuditDrawer({ entries, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex" data-testid="pricing-audit-drawer">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <aside className="w-[480px] max-w-full bg-white shadow-2xl overflow-y-auto">
        <div className="p-5 border-b border-zinc-200 sticky top-0 bg-white">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-zinc-900">Pricing audit log</h3>
            <button onClick={onClose} className="text-sm text-zinc-500 hover:text-zinc-900">Close</button>
          </div>
          <p className="text-xs text-zinc-500 mt-1">Last 20 changes</p>
        </div>
        <div className="p-5 space-y-3">
          {entries.length === 0 && (
            <div className="text-sm text-zinc-400 italic">No changes recorded yet.</div>
          )}
          {entries.map((e) => (
            <div key={e.id} className="rounded-lg border border-zinc-200 p-3 text-xs">
              <div className="flex items-center gap-2">
                <span className="font-bold text-zinc-700 uppercase">{e.action}</span>
                <span className="text-zinc-400">{e.at?.slice(0, 19).replace('T', ' ')}</span>
              </div>
              <div className="text-zinc-500 mt-1">
                Plan: <code className="text-[10px]">{e.plan_id}</code>
              </div>
              {e.before && e.after && (
                <div className="text-zinc-500 mt-1 break-all">
                  by <code>{e.by}</code>
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}


/* ─────────────────── helpers ─────────────────── */

function formatMoney(minor, code) {
  const sym = code === 'GBP' ? '£' : code === 'EUR' ? '€' : '$';
  return `${sym}${(Number(minor || 0) / 100).toFixed(2)}`;
}
