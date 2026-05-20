/**
 * Memberships → Promotions tab.
 *
 * Operator-managed promo codes that members paste at Stripe Checkout.
 * Built on Stripe's native Coupon + PromotionCode so the discount is
 * enforced at the gateway (no client-side trust required).
 */
import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  Tag, Plus, Trash2, Calendar, Percent, PoundSterling, Sparkles,
  Loader2, ShieldCheck, BadgeCheck, X,
} from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';
import ListPanel from '@/components/shared/ListPanel';
import DatePicker from '@/components/shared/DatePicker';

const KIND_OPTIONS = [
  { value: 'recurring',  label: 'Memberships' },
  { value: 'class_pack', label: 'Class packs' },
  { value: 'course',     label: 'Courses' },
  { value: 'bundle',     label: 'Bundles' },
  { value: 'fixed_term', label: 'Fixed term' },
  { value: 'payg',       label: 'Pay-as-you-go' },
];

const DURATION_OPTIONS = [
  { value: 'once',      label: 'Once (first invoice only)' },
  { value: 'forever',   label: 'Forever (every invoice)' },
  { value: 'repeating', label: 'Repeating (N months)' },
];

export default function PromotionsTab({ API, headers }) {
  const confirm = useConfirm();
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new'

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: pData }, { data: plansData }] = await Promise.all([
        axios.get(`${API}/memberships/promo-codes`, { headers }),
        axios.get(`${API}/memberships/plans`, { headers }),
      ]);
      setRows(pData?.promo_codes || []);
      setPlans(plansData?.plans || []);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load promotions');
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  useEffect(() => { load(); }, [load]);

  const archive = async (p) => {
    if (!(await confirm({
      title: `Deactivate "${p.code}"?`,
      detail: 'Members will no longer be able to use this code. Existing redemptions remain on record.',
      tone: 'warning', confirmLabel: 'Deactivate',
    }))) return;
    try {
      await axios.delete(`${API}/memberships/promo-codes/${p.id}`, { headers });
      notify.success('Promo code deactivated');
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
  };

  return (
    <div data-testid="mbr-promotions">
      <ListPanel
        data-testid="mbr-promotions-list"
        title="Promotions"
        subtitle="Operator-managed promo codes. Discounts enforced at Stripe — first-month-free, summer launch, loyalty rewards."
        count={{ value: rows.length, label: 'code' }}
        primaryAction={{ label: 'New code', icon: Plus, onClick: () => setEditing('new'), testId: 'mbr-promo-add' }}
        loading={loading}
        empty={{
          when: rows.length === 0,
          icon: Tag,
          title: 'No promotions yet',
          hint: 'Create your first code — first-month-free, summer launch, or loyalty rewards. Members paste it at Stripe Checkout.',
          primaryAction: { label: 'Create your first code', onClick: () => setEditing('new'), testId: 'mbr-promo-empty-create' },
          testId: 'mbr-promo-empty',
        }}
        bodyClassName="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        {rows.map((p) => (
          <PromoCard key={p.id} promo={p} plans={plans} onArchive={() => archive(p)} />
        ))}
      </ListPanel>

      {editing === 'new' && (
        <PromoEditorModal
          API={API} headers={headers} plans={plans}
          onClose={(refresh) => { setEditing(null); if (refresh) load(); }}
        />
      )}
    </div>
  );
}


function PromoCard({ promo, plans, onArchive }) {
  const planNames = (promo.applicable_plan_ids || [])
    .map((id) => plans.find((p) => p.id === id)?.name)
    .filter(Boolean);
  const remaining = promo.max_redemptions != null
    ? Math.max(0, promo.max_redemptions - (promo.redemptions_count || 0))
    : null;
  const expired = promo.valid_until
    ? new Date(promo.valid_until) < new Date()
    : false;

  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-4 group"
      data-testid={`mbr-promo-${promo.id}`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Tag size={12} className="text-[var(--color-brand-cyan)]" />
            <code className="text-base font-extrabold tracking-wide text-zinc-900 dark:text-white truncate">{promo.code}</code>
          </div>
          <p className="text-xs text-[color:var(--theme-text-muted)] mt-0.5 truncate">{promo.name}</p>
        </div>
        <RowActions>
          <Button variant="ghostDestructive" size="iconSm" onClick={onArchive} icon={Trash2} title="Deactivate" data-testid={`mbr-promo-archive-${promo.id}`} />
        </RowActions>
      </div>

      <div className="text-2xl font-extrabold tracking-tight text-emerald-500 mt-2 flex items-center gap-1">
        {promo.percent_off
          ? <><Percent size={18} /> {promo.percent_off}% off</>
          : <><PoundSterling size={18} /> £{((promo.amount_off_pence || 0) / 100).toFixed(2)} off</>}
      </div>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {promo.duration === 'once' && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-zinc-500/15 text-[color:var(--theme-text-muted)]">First invoice only</span>
        )}
        {promo.duration === 'forever' && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-fuchsia-500/15 text-fuchsia-400">Every invoice</span>
        )}
        {promo.duration === 'repeating' && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-purple-500/15 text-purple-400">{promo.duration_in_months}× months</span>
        )}
        {promo.first_time_only && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-blue-500/15 text-blue-400">First-time only</span>
        )}
        {planNames.length > 0 && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-amber-500/15 text-amber-400" title={planNames.join(', ')}>
            {planNames.length} plan{planNames.length === 1 ? '' : 's'} only
          </span>
        )}
        {(promo.applicable_kinds || []).length > 0 && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-cyan-500/15 text-cyan-400">
            {(promo.applicable_kinds || []).join(', ')}
          </span>
        )}
        {expired && (
          <span className="text-[10px] font-bold rounded px-1.5 py-0.5 bg-red-500/15 text-red-300">Expired</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div className="rounded bg-white/[0.04] p-2 border border-[color:var(--theme-border)]">
          <div className="text-[10px] uppercase tracking-wider text-[color:var(--theme-text-muted)] flex items-center gap-1">
            <BadgeCheck size={9} /> Redemptions
          </div>
          <p className="text-sm font-bold mt-0.5">
            {promo.redemptions_count || 0}
            {promo.max_redemptions != null && (
              <span className="text-[color:var(--theme-text-muted)] font-normal"> / {promo.max_redemptions}</span>
            )}
          </p>
          {remaining != null && remaining < 5 && remaining > 0 && (
            <p className="text-[10px] text-amber-500 mt-0.5">Only {remaining} left</p>
          )}
        </div>
        <div className="rounded bg-white/[0.04] p-2 border border-[color:var(--theme-border)]">
          <div className="text-[10px] uppercase tracking-wider text-[color:var(--theme-text-muted)] flex items-center gap-1">
            <Calendar size={9} /> Expires
          </div>
          <p className="text-sm font-bold mt-0.5 truncate">
            {promo.valid_until ? new Date(promo.valid_until).toLocaleDateString() : 'Never'}
          </p>
        </div>
      </div>
    </div>
  );
}


function PromoEditorModal({ API, headers, plans, onClose }) {
  const [f, setF] = useState({
    code: '',
    name: '',
    discount_type: 'percent', // 'percent' | 'amount'
    percent_off: '25',
    amount_off_pounds: '5.00',
    first_time_only: false,
    duration: 'once',
    duration_in_months: '',
    max_redemptions: '',
    valid_until: '',
    applicable_plan_ids: [],
    applicable_kinds: [],
  });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!f.code.trim()) { notify.error('Code is required'); return; }
    if (!f.name.trim()) { notify.error('Internal name is required'); return; }

    const payload = {
      code: f.code.trim().toUpperCase(),
      name: f.name.trim(),
      first_time_only: f.first_time_only,
      duration: f.duration,
    };
    if (f.discount_type === 'percent') {
      const pct = parseInt(f.percent_off, 10);
      if (!Number.isFinite(pct) || pct < 1 || pct > 100) {
        notify.error('Percent must be 1-100'); return;
      }
      payload.percent_off = pct;
    } else {
      const pounds = parseFloat(f.amount_off_pounds);
      if (!Number.isFinite(pounds) || pounds <= 0) {
        notify.error('Enter a valid £ amount'); return;
      }
      payload.amount_off_pence = Math.round(pounds * 100);
    }
    if (f.duration === 'repeating') {
      const m = parseInt(f.duration_in_months, 10);
      if (!Number.isFinite(m) || m < 1) {
        notify.error('Months must be at least 1'); return;
      }
      payload.duration_in_months = m;
    }
    if (f.max_redemptions) {
      const m = parseInt(f.max_redemptions, 10);
      if (Number.isFinite(m) && m > 0) payload.max_redemptions = m;
    }
    if (f.valid_until) payload.valid_until = new Date(f.valid_until).toISOString();
    if (f.applicable_plan_ids.length) payload.applicable_plan_ids = f.applicable_plan_ids;
    if (f.applicable_kinds.length) payload.applicable_kinds = f.applicable_kinds;

    setSaving(true);
    try {
      await axios.post(`${API}/memberships/promo-codes`, payload, { headers });
      notify.success('Promo code created — Stripe is now enforcing it');
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to create promo');
    }
    setSaving(false);
  };

  const togglePlan = (id) => up('applicable_plan_ids')(
    f.applicable_plan_ids.includes(id)
      ? f.applicable_plan_ids.filter((x) => x !== id)
      : [...f.applicable_plan_ids, id],
  );
  const toggleKind = (k) => up('applicable_kinds')(
    f.applicable_kinds.includes(k)
      ? f.applicable_kinds.filter((x) => x !== k)
      : [...f.applicable_kinds, k],
  );

  return createPortal((
    // Iter 215d6.1 — promo editor now uses the same mobile safe-zone
    // pattern as ModalShell so its X close + action footer are always
    // visible between the Navbar and MobileBottomNav. Portaled to
    // document.body (215d6.2) to escape transformed ancestors.
    <div className="fixed inset-0 z-[100] bg-black/60" onClick={() => onClose(false)}>
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex items-stretch sm:items-center justify-center p-3 sm:p-4">
      <div className="bg-[color:var(--theme-surface)] dark:bg-zinc-900 border border-[color:var(--theme-border)] rounded-2xl shadow-2xl w-full max-w-lg h-full sm:h-auto sm:max-h-[calc(100vh-6rem)] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        data-testid="mbr-promo-editor">
        <div className="flex-shrink-0 px-5 py-4 border-b border-[color:var(--theme-border)] flex items-center justify-between bg-[color:var(--theme-surface)] dark:bg-zinc-900">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)]">Promo</p>
            <h2 className="text-lg font-extrabold">New code</h2>
          </div>
          <button
            onClick={() => onClose(false)}
            className="h-9 w-9 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] bg-[color:var(--theme-bg,transparent)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-[color:var(--color-brand-cyan)] focus:ring-offset-1 transition-colors shrink-0"
            aria-label="Close"
            data-testid="mbr-promo-close"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          <Field label="Code" hint="Auto-uppercased. e.g. SUMMER25, FIRSTMONTH, LAUNCH50">
            <input value={f.code} onChange={(e) => up('code')(e.target.value.toUpperCase())}
              maxLength={32}
              placeholder="SUMMER25"
              className="w-full px-3 py-2 rounded-md text-sm font-mono uppercase tracking-wide border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
              data-testid="mbr-promo-code-input" />
          </Field>

          <Field label="Internal name" hint="What this campaign is for — only operators see this">
            <input value={f.name} onChange={(e) => up('name')(e.target.value)}
              placeholder="Summer launch — 25% off first month"
              className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
              data-testid="mbr-promo-name-input" />
          </Field>

          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-1.5">Discount type</p>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => up('discount_type')('percent')}
                className={`px-3 py-2 rounded-md text-xs font-bold border transition ${
                  f.discount_type === 'percent'
                    ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]'
                    : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:text-zinc-900 dark:hover:text-white'
                }`}
                data-testid="mbr-promo-type-percent">
                <Percent size={11} className="inline mr-1" /> Percent off
              </button>
              <button onClick={() => up('discount_type')('amount')}
                className={`px-3 py-2 rounded-md text-xs font-bold border transition ${
                  f.discount_type === 'amount'
                    ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]'
                    : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:text-zinc-900 dark:hover:text-white'
                }`}
                data-testid="mbr-promo-type-amount">
                <PoundSterling size={11} className="inline mr-1" /> Fixed £ off
              </button>
            </div>
          </div>

          {f.discount_type === 'percent' ? (
            <Field label="Percent off (1-100)">
              <input value={f.percent_off} onChange={(e) => up('percent_off')(e.target.value)}
                type="number" min="1" max="100"
                className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="mbr-promo-percent-input" />
            </Field>
          ) : (
            <Field label="Amount off (£)">
              <input value={f.amount_off_pounds} onChange={(e) => up('amount_off_pounds')(e.target.value)}
                type="number" min="0.01" step="0.01"
                className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="mbr-promo-amount-input" />
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Applies to" hint="How many invoices get the discount">
              <select value={f.duration} onChange={(e) => up('duration')(e.target.value)}
                className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="mbr-promo-duration">
                {DURATION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
            {f.duration === 'repeating' && (
              <Field label="For how many months">
                <input value={f.duration_in_months} onChange={(e) => up('duration_in_months')(e.target.value)}
                  type="number" min="1" max="24" placeholder="3"
                  className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
                  data-testid="mbr-promo-months" />
              </Field>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Max redemptions" hint="Leave blank for unlimited">
              <input value={f.max_redemptions} onChange={(e) => up('max_redemptions')(e.target.value)}
                type="number" min="1" placeholder="No limit"
                className="w-full px-3 py-2 rounded-md text-sm border border-[color:var(--theme-border)] bg-transparent focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="mbr-promo-max-redemptions" />
            </Field>
            <Field label="Expires">
              {/* Iter 216h255 — shared DatePicker for date-field
                  consistency across the Memberships module. */}
              <DatePicker
                value={(f.valid_until || '').slice(0, 10)}
                onChange={(iso) => up('valid_until')(iso)}
                minDate={new Date().toISOString().slice(0, 10)}
                testid="mbr-promo-valid-until"
              />
            </Field>
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={f.first_time_only}
              onChange={(e) => up('first_time_only')(e.target.checked)}
              data-testid="mbr-promo-first-time-only" />
            <span>
              <strong className="text-zinc-900 dark:text-white">First-time members only</strong>
              <span className="text-[color:var(--theme-text-muted)] ml-1">— blocks members who already have a paid history</span>
            </span>
          </label>

          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-1.5 flex items-center gap-1">
              <ShieldCheck size={10} /> Limit to specific plans (optional)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {plans.length === 0 && (
                <span className="text-xs text-[color:var(--theme-text-muted)]">No plans yet — leave blank to apply to all.</span>
              )}
              {plans.map((p) => {
                const active = f.applicable_plan_ids.includes(p.id);
                return (
                  <button key={p.id} onClick={() => togglePlan(p.id)}
                    className={`px-2 py-1 rounded-full text-[10px] font-bold border transition ${
                      active ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]'
                             : 'bg-transparent text-[color:var(--theme-text-muted)] border-[color:var(--theme-border)] hover:text-zinc-900 dark:hover:text-white'
                    }`}
                    data-testid={`mbr-promo-plan-${p.id}`}>
                    {p.name}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-1.5 flex items-center gap-1">
              <Sparkles size={10} /> Limit to plan types (optional)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {KIND_OPTIONS.map((k) => {
                const active = f.applicable_kinds.includes(k.value);
                return (
                  <button key={k.value} onClick={() => toggleKind(k.value)}
                    className={`px-2 py-1 rounded-full text-[10px] font-bold border transition ${
                      active ? 'bg-purple-500 text-white border-purple-500'
                             : 'bg-transparent text-[color:var(--theme-text-muted)] border-[color:var(--theme-border)] hover:text-zinc-900 dark:hover:text-white'
                    }`}
                    data-testid={`mbr-promo-kind-${k.value}`}>
                    {k.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        {/* Sticky footer with actions */}
        <div className="flex-shrink-0 px-5 py-4 border-t border-[color:var(--theme-border)] flex justify-end gap-2 bg-[color:var(--theme-surface)] dark:bg-zinc-900">
          <button onClick={() => onClose(false)}
            className="px-3 py-2 rounded-md text-sm font-bold text-[color:var(--theme-text-muted)] hover:text-zinc-900 dark:hover:text-white"
            data-testid="mbr-promo-cancel">
            Cancel
          </button>
          <button onClick={submit} disabled={saving}
            className="px-4 py-2 rounded-md text-sm font-extrabold flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-promo-save">
            {saving ? <><Loader2 size={12} className="animate-spin" /> Saving…</> : <><BadgeCheck size={12} /> Create code</>}
          </button>
        </div>
      </div>
      </div>
    </div>
  ), document.body);
}


function Field({ label, hint, children }) {
  return (
    <label className="block">
      <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] mb-1">{label}</p>
      {children}
      {hint && <p className="text-[10px] text-[color:var(--theme-text-muted)] mt-1">{hint}</p>}
    </label>
  );
}
