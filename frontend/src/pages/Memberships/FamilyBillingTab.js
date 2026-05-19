/**
 * FamilyBillingTab — Phase B (Iter 216aa)
 *
 * Studio operator console for:
 *   1. Tiered sibling discount ladder (rank → pct)
 *   2. Multi-class discount ladder (min_classes → pct)
 *   3. Payment plans (instalment offerings)
 *   4. AI Payment-risk dashboard (heuristic risk score per member)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Users2, Layers, Loader2, Plus, Trash2, Save,
  CheckCircle2, RefreshCw, Brain, CreditCard, Zap,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const RISK_TONES = {
  high:   { bg: 'rgba(239,68,68,0.12)',  fg: '#b91c1c', label: 'High risk' },
  medium: { bg: 'rgba(245,158,11,0.12)', fg: '#b45309', label: 'Medium risk' },
  low:    { bg: 'rgba(16,185,129,0.12)', fg: '#047857', label: 'Low risk' },
};

const fmtGBP = (pence) => `£${(((pence ?? 0) / 100) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function FamilyBillingTab({ API, headers }) {
  const auth = useMemo(() => ({ headers }), [headers]);
  const [loading, setLoading] = useState(true);
  const [siblingTiers, setSiblingTiers] = useState([]);
  const [multiTiers, setMultiTiers] = useState([]);
  const [plans, setPlans] = useState([]);
  const [risk, setRisk] = useState({ rows: [], summary: {} });
  const [savingTiers, setSavingTiers] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sib, mc, pp, rk] = await Promise.all([
        axios.get(`${API}/memberships/billing/sibling-discount`, auth),
        axios.get(`${API}/memberships/billing/multi-class-discount`, auth),
        axios.get(`${API}/memberships/payment-plans`, auth),
        axios.get(`${API}/memberships/billing/payment-risk?limit=50`, auth),
      ]);
      setSiblingTiers(sib.data?.tiers?.length ? sib.data.tiers : [
        { rank: 2, pct: 10 }, { rank: 3, pct: 15 }, { rank: 4, pct: 20 },
      ]);
      setMultiTiers(mc.data?.tiers?.length ? mc.data.tiers : [
        { min_classes: 2, pct: 10 }, { min_classes: 3, pct: 20 },
      ]);
      setPlans(pp.data?.plans || []);
      setRisk({ rows: rk.data?.rows || [], summary: rk.data?.summary || {} });
    } catch (e) {
      notify.error('Failed to load family billing', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [API, auth]);
  useEffect(() => { load(); }, [load]);

  const saveSibling = async () => {
    setSavingTiers(true);
    try {
      await axios.post(`${API}/memberships/billing/sibling-discount`, {
        pct: 0, tiers: siblingTiers,
      }, auth);
      notify.success('Sibling discount saved');
      await load();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally { setSavingTiers(false); }
  };

  const saveMulti = async () => {
    setSavingTiers(true);
    try {
      await axios.post(`${API}/memberships/billing/multi-class-discount`, {
        tiers: multiTiers,
      }, auth);
      notify.success('Multi-class discount saved');
      await load();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally { setSavingTiers(false); }
  };

  const addPlan = async () => {
    const name = window.prompt('Plan name (e.g. "Autumn Term — 3 instalments")');
    if (!name) return;
    const total = parseFloat(window.prompt('Total fee in £ (e.g. 600)') || '0');
    const instalments = parseInt(window.prompt('Number of instalments (2-24)') || '3', 10);
    if (!total || !instalments || instalments < 2) {
      notify.error('Invalid input', 'Need total fee and at least 2 instalments');
      return;
    }
    try {
      await axios.post(`${API}/memberships/payment-plans`, {
        name: name.trim(),
        total_pence: Math.round(total * 100),
        instalments,
        frequency: 'monthly',
      }, auth);
      notify.success('Payment plan created');
      await load();
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    }
  };

  const deletePlan = async (plan) => {
    if (!window.confirm(`Archive payment plan "${plan.name}"?`)) return;
    try {
      await axios.delete(`${API}/memberships/payment-plans/${plan.id}`, auth);
      await load();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground p-6" data-testid="family-billing-loading">
        <Loader2 size={14} className="animate-spin" /> Loading family billing…
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="family-billing-tab">
      <RiskCard risk={risk} onRefresh={load} />

      <DiscountLadderCard
        title="Sibling discount ladder"
        eyebrow="Family loyalty"
        Icon={Users2}
        rankKey="rank"
        rankLabel="Child rank"
        tiers={siblingTiers}
        setTiers={setSiblingTiers}
        onSave={saveSibling}
        saving={savingTiers}
        helpCopy="A flat percent off each child beyond the eldest. Tiered ladder lets you reward larger families without manually tagging accounts."
        rankPrefix={(r) => ({ 2: '2nd', 3: '3rd' }[r] || `${r}th`) + ' child'}
        testid="sibling"
      />

      <DiscountLadderCard
        title="Multi-class discount ladder"
        eyebrow="Engagement"
        Icon={Layers}
        rankKey="min_classes"
        rankLabel="Min classes"
        tiers={multiTiers}
        setTiers={setMultiTiers}
        onSave={saveMulti}
        saving={savingTiers}
        helpCopy="When one student attends N or more classes in a billing period, knock a percent off every class line for that student."
        rankPrefix={(r) => `${r}+ classes`}
        testid="multi"
      />

      <PaymentPlansCard plans={plans} onAdd={addPlan} onDelete={deletePlan} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Risk
// ─────────────────────────────────────────────────────────────────
function RiskCard({ risk, onRefresh }) {
  const summary = risk?.summary || {};
  const rows = risk?.rows || [];
  return (
    <section
      className="rounded-2xl border p-4"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="family-billing-risk"
    >
      <header className="flex items-start justify-between flex-wrap gap-2 mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <Brain size={11} /> AI failed-payment risk
          </p>
          <h3 className="text-base font-bold">Members most likely to fail their next charge</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] opacity-70 inline-flex items-center gap-1">
            <span style={{ background: RISK_TONES.high.bg, color: RISK_TONES.high.fg, padding: '2px 6px', borderRadius: 6, fontWeight: 700 }} data-testid="risk-summary-high">{summary.high ?? 0} high</span>
            <span style={{ background: RISK_TONES.medium.bg, color: RISK_TONES.medium.fg, padding: '2px 6px', borderRadius: 6, fontWeight: 700 }} data-testid="risk-summary-medium">{summary.medium ?? 0} medium</span>
            <span style={{ background: RISK_TONES.low.bg, color: RISK_TONES.low.fg, padding: '2px 6px', borderRadius: 6, fontWeight: 700 }} data-testid="risk-summary-low">{summary.low ?? 0} low</span>
          </span>
          <button type="button" onClick={onRefresh} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="family-billing-risk-refresh">
            <RefreshCw size={11} /> Refresh
          </button>
        </div>
      </header>
      {rows.length === 0 ? (
        <div className="text-center py-6 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="family-billing-risk-empty">
          <CheckCircle2 size={22} className="mx-auto mb-1 text-emerald-500" />
          <p className="text-sm font-bold">All clear</p>
          <p className="text-xs opacity-70 mt-1">No members are flagged as payment-risk right now. We'll surface them as soon as a charge fails or an invoice goes overdue.</p>
        </div>
      ) : (
        <div className="overflow-x-auto" data-testid="family-billing-risk-table">
          <table className="w-full text-xs">
            <thead className="text-left">
              <tr style={{ background: 'var(--theme-surface-2, #f8fafc)' }}>
                <th className="p-2 font-bold uppercase text-[10px] opacity-70">Member</th>
                <th className="p-2 font-bold uppercase text-[10px] opacity-70">Risk</th>
                <th className="p-2 font-bold uppercase text-[10px] opacity-70">Outstanding</th>
                <th className="p-2 font-bold uppercase text-[10px] opacity-70">Past due</th>
                <th className="p-2 font-bold uppercase text-[10px] opacity-70">Why</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const tone = RISK_TONES[r.band] || RISK_TONES.low;
                return (
                  <tr key={r.member_id} style={{ borderTop: '1px solid var(--theme-border, #e2e8f0)' }} data-testid={`family-billing-risk-row-${r.member_id}`}>
                    <td className="p-2">
                      <div className="font-bold">{r.member_name}</div>
                      <div className="opacity-60 text-[11px]">{r.member_email}</div>
                    </td>
                    <td className="p-2">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-bold tabular-nums" style={{ background: tone.bg, color: tone.fg }} data-testid={`family-billing-risk-band-${r.member_id}`}>
                        {r.score}/100 · {tone.label}
                      </span>
                    </td>
                    <td className="p-2 tabular-nums font-bold">{fmtGBP(r.open_balance_pence)}</td>
                    <td className="p-2 tabular-nums">{r.days_past_due ? `${r.days_past_due}d` : '—'}</td>
                    <td className="p-2 max-w-[420px]">
                      <ul className="list-disc list-inside space-y-0.5 text-[11px] opacity-80">
                        {(r.reasons || []).map((reason, idx) => <li key={idx}>{reason}</li>)}
                      </ul>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────
// Discount ladder editor
// ─────────────────────────────────────────────────────────────────
function DiscountLadderCard({
  title, eyebrow, Icon, rankKey, rankLabel, tiers, setTiers, onSave, saving,
  helpCopy, rankPrefix, testid,
}) {
  const updateTier = (idx, key, value) => {
    setTiers((prev) => prev.map((t, i) => i === idx ? { ...t, [key]: parseInt(value, 10) || 0 } : t));
  };
  const remove = (idx) => setTiers((prev) => prev.filter((_, i) => i !== idx));
  const add = () => {
    const last = tiers[tiers.length - 1];
    setTiers((prev) => [...prev, { [rankKey]: (last?.[rankKey] || 1) + 1, pct: (last?.pct || 5) + 5 }]);
  };
  return (
    <section
      className="rounded-2xl border p-4"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid={`family-billing-${testid}-card`}
    >
      <header className="flex items-start justify-between gap-2 flex-wrap mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60">{eyebrow}</p>
          <h3 className="text-base font-bold inline-flex items-center gap-2">
            <Icon size={14} className="text-blue-500" /> {title}
          </h3>
          <p className="text-[11.5px] opacity-70 max-w-xl mt-1">{helpCopy}</p>
        </div>
        <button type="button" onClick={onSave} disabled={saving} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff', opacity: saving ? 0.6 : 1 }} data-testid={`family-billing-${testid}-save`}>
          {saving ? <Loader2 size={11} className="animate-spin" /> : <Save size={11} />}
          Save
        </button>
      </header>
      <div className="space-y-2" data-testid={`family-billing-${testid}-list`}>
        {tiers.map((t, idx) => (
          <div key={idx} className="flex items-center gap-2 p-2 rounded-lg border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`family-billing-${testid}-tier-${idx}`}>
            <span className="text-xs font-bold opacity-70 w-28">{rankPrefix(t[rankKey])}</span>
            <label className="text-[11px] opacity-60">{rankLabel}</label>
            <input type="number" min={2} max={20} value={t[rankKey]} onChange={(e) => updateTier(idx, rankKey, e.target.value)} className="w-16 px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`family-billing-${testid}-rank-${idx}`} />
            <label className="text-[11px] opacity-60">% off</label>
            <input type="number" min={0} max={75} value={t.pct} onChange={(e) => updateTier(idx, 'pct', e.target.value)} className="w-16 px-2 py-1 text-sm rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`family-billing-${testid}-pct-${idx}`} />
            <span className="text-[10px] opacity-60">%</span>
            <button type="button" onClick={() => remove(idx)} className="ml-auto px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} aria-label="Remove tier" data-testid={`family-billing-${testid}-remove-${idx}`}>
              <Trash2 size={11} />
            </button>
          </div>
        ))}
        <button type="button" onClick={add} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1 border-2 border-dashed w-full justify-center" style={{ borderColor: 'var(--theme-border)' }} data-testid={`family-billing-${testid}-add`}>
          <Plus size={11} /> Add tier
        </button>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────
// Payment plans
// ─────────────────────────────────────────────────────────────────
function PaymentPlansCard({ plans, onAdd, onDelete }) {
  return (
    <section
      className="rounded-2xl border p-4"
      style={{ borderColor: 'var(--theme-border, #e2e8f0)', background: 'var(--theme-surface, #fff)' }}
      data-testid="family-billing-plans"
    >
      <header className="flex items-start justify-between gap-2 flex-wrap mb-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-60 inline-flex items-center gap-1">
            <CreditCard size={11} /> Payment plans
          </p>
          <h3 className="text-base font-bold">Instalment offerings</h3>
          <p className="text-[11.5px] opacity-70 max-w-xl mt-1">
            Define a fee once (e.g. £600 termly) and split it across N monthly instalments. Assign to a member from the Members tab — the autopay cron will issue one invoice per period until paid in full.
          </p>
        </div>
        <button type="button" onClick={onAdd} className="px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: '#fff' }} data-testid="family-billing-plan-add">
          <Plus size={11} /> Add plan
        </button>
      </header>
      {plans.length === 0 ? (
        <div className="text-center py-6 px-3 rounded-xl border-2 border-dashed" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid="family-billing-plans-empty">
          <Zap size={22} className="mx-auto mb-1 text-amber-500" />
          <p className="text-sm font-bold">No payment plans yet</p>
          <p className="text-xs opacity-70 mt-1">Add one to start splitting termly fees into manageable monthly chunks.</p>
        </div>
      ) : (
        <ul className="space-y-2" data-testid="family-billing-plan-list">
          {plans.map((p) => (
            <li key={p.id} className="flex items-center gap-3 p-3 rounded-lg border" style={{ borderColor: 'var(--theme-border, #e2e8f0)' }} data-testid={`family-billing-plan-${p.id}`}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold truncate">{p.name}</p>
                <p className="text-[11px] opacity-70 tabular-nums">
                  {fmtGBP(p.total_pence)} · {p.instalments} × {fmtGBP(p.instalment_pence)} ({p.frequency})
                </p>
              </div>
              <button type="button" onClick={() => onDelete(p)} className="px-2 py-1 rounded text-[11px] border" style={{ borderColor: 'var(--theme-border)' }} aria-label="Archive plan" data-testid={`family-billing-plan-delete-${p.id}`}>
                <Trash2 size={11} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
