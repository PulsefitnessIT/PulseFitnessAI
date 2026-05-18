/**
 * PlanEditorModal — Memberships console.
 *
 * Iter 215bv — extracted from MembershipsConsole.js (was inline, ~270
 * lines). Handles both create and edit. Supports recurring / fixed_term /
 * class_pack / payg / course / bundle plans with smoothing, waivers, and
 * course schedule materialisation.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ModalShell, Input, Select, ModalActions } from '@/pages/Memberships/_shared';

export const PLAN_KINDS = [
  { value: 'recurring',   label: 'Recurring (subscription)' },
  { value: 'fixed_term',  label: 'Fixed term' },
  { value: 'class_pack',  label: 'Class pack (credits)' },
  { value: 'payg',        label: 'Pay as you go (drop-in)' },
  { value: 'course',      label: 'Course (multi-week block)' },
  { value: 'bundle',      label: 'Bundle (sub + extra credits)' },
];

export const BILLING_CYCLES = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'annual',  label: 'Annual' },
  { value: 'oneoff',  label: 'One-off' },
];

export const INCLUDED_OPTIONS = [
  { value: 'unlimited',    label: 'Unlimited classes' },
  { value: 'limited',      label: 'Limited (N per week)' },
  { value: 'credits_only', label: 'Credits only' },
];

export default function PlanEditorModal({ API, headers, plan, defaultKind, onClose }) {
  const isNew = !plan;
  const [f, setF] = useState(() => ({
    name: plan?.name || '',
    // Iter 216h209 — `defaultKind` lets the caller (Credit Packs subtab)
    // pre-select kind=class_pack so operators don't have to discover
    // the dropdown to create a credit/class-pack product.
    kind: plan?.kind || defaultKind || 'recurring',
    billing_cycle: plan?.billing_cycle || 'monthly',
    price_pounds: plan ? (plan.price_pence / 100).toFixed(2) : '',
    upfront_fee_pounds: plan ? ((plan.upfront_fee_pence || 0) / 100).toFixed(2) : '0.00',
    included_classes: plan?.included_classes || 'unlimited',
    credits_count: plan?.credits_count ?? '',
    duration_days: plan?.duration_days ?? '',
    freeze_allowed: plan?.freeze_allowed ?? true,
    freeze_max_days: plan?.freeze_max_days ?? 90,
    cancel_notice_days: plan?.cancel_notice_days ?? 30,
    colour: plan?.colour || 'var(--color-brand-cyan)',
    description: plan?.description || '',
    display_order: plan?.display_order ?? 0,
    waiver_required: plan?.waiver_required ?? false,
    waiver_text: plan?.waiver_text || '',
    smoothed: plan?.smoothed ?? false,
    smoothed_annual_pounds: plan ? ((plan.smoothed_annual_pence || 0) / 100).toFixed(2) : '',
    smoothed_months: plan?.smoothed_months ?? 12,
    per_class_pounds: plan?.per_class_pence ? (plan.per_class_pence / 100).toFixed(2) : '',
    course_template_id: plan?.course_template_id || '',
    course_session_count: plan?.course_session_count ?? 8,
    course_start_date: plan?.course_start_date || '',
    course_excluded_dates: plan?.course_excluded_dates || [],
  }));
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState([]);

  useEffect(() => {
    if (f.kind !== 'course') return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/memberships/classes/templates`, { headers });
        setTemplates(data.templates || []);
      } catch { /* ignore */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.kind]);

  const up = (k) => (v) => setF((prev) => ({ ...prev, [k]: v }));

  const submit = async () => {
    if (!f.name.trim()) { notify.error('Plan name is required'); return; }
    const priceNum = Math.round(Number(f.price_pounds) * 100);
    if (!Number.isFinite(priceNum) || priceNum < 0) { notify.error('Enter a valid price'); return; }
    const payload = {
      name: f.name.trim(),
      kind: f.kind,
      billing_cycle: f.billing_cycle,
      price_pence: priceNum,
      upfront_fee_pence: Math.round(Number(f.upfront_fee_pounds || 0) * 100),
      included_classes: f.included_classes,
      credits_count: f.credits_count === '' ? null : Number(f.credits_count),
      duration_days: f.duration_days === '' ? null : Number(f.duration_days),
      freeze_allowed: f.freeze_allowed,
      freeze_max_days: Number(f.freeze_max_days) || 0,
      cancel_notice_days: Number(f.cancel_notice_days) || 0,
      colour: f.colour,
      description: f.description || null,
      display_order: Number(f.display_order) || 0,
      waiver_required: !!f.waiver_required,
      waiver_text: f.waiver_text || null,
      smoothed: !!f.smoothed,
      smoothed_annual_pence: f.smoothed && f.smoothed_annual_pounds !== ''
        ? Math.round(Number(f.smoothed_annual_pounds) * 100) : null,
      smoothed_months: f.smoothed ? Math.max(1, Math.min(24, Number(f.smoothed_months) || 12)) : 12,
      per_class_pence: f.per_class_pounds !== ''
        ? Math.round(Number(f.per_class_pounds) * 100) : null,
      course_template_id: f.kind === 'course' ? (f.course_template_id || null) : null,
      course_session_count: f.kind === 'course' ? Number(f.course_session_count) || null : null,
      course_start_date: f.kind === 'course' ? (f.course_start_date || null) : null,
      course_excluded_dates: f.kind === 'course' ? (f.course_excluded_dates || []) : [],
    };
    setSaving(true);
    try {
      let created;
      if (isNew) {
        const res = await axios.post(`${API}/memberships/plans`, payload, { headers });
        created = res.data?.plan;
      } else {
        await axios.patch(`${API}/memberships/plans/${plan.id}`, payload, { headers });
      }
      try { if (isNew) window.dispatchEvent(new CustomEvent('gymaxis:plan-created')); } catch (_) {}
      const occCount = created?.course_occurrence_ids?.length;
      if (isNew && payload.kind === 'course' && occCount) {
        notify.success(`Course plan created — ${occCount} weekly session${occCount === 1 ? '' : 's'} scheduled`);
      } else {
        notify.success(isNew ? 'Plan created' : 'Plan updated');
      }
      onClose(true);
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setSaving(false); }
  };

  return (
    <ModalShell title={isNew ? 'New plan' : 'Edit plan'} eyebrow="Product" testId="mbr-plan-editor"
      onClose={() => onClose(false)} wide>
      <Input label="Plan name" value={f.name} onChange={up('name')} required testid="mbr-plan-name" />
      <div className="grid grid-cols-2 gap-3">
        <Select label="Kind" value={f.kind} onChange={up('kind')} options={PLAN_KINDS} testid="mbr-plan-kind" />
        <Select label="Billing cycle" value={f.billing_cycle} onChange={up('billing_cycle')} options={BILLING_CYCLES} testid="mbr-plan-billing" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Input label="Price (£)" value={f.price_pounds} onChange={up('price_pounds')} type="number" required testid="mbr-plan-price" />
        <Input label="Joining fee (£)" value={f.upfront_fee_pounds} onChange={up('upfront_fee_pounds')} type="number" testid="mbr-plan-upfront" />
      </div>
      <Select label="Included classes" value={f.included_classes} onChange={up('included_classes')} options={INCLUDED_OPTIONS} testid="mbr-plan-included" />
      <div className="grid grid-cols-2 gap-3">
        <Input label="Credits (class_pack only)" value={f.credits_count} onChange={up('credits_count')} type="number" testid="mbr-plan-credits" />
        <Input label="Duration days (fixed_term)" value={f.duration_days} onChange={up('duration_days')} type="number" testid="mbr-plan-duration" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <label className="flex items-center gap-2 mt-5 text-sm">
          <input type="checkbox" checked={f.freeze_allowed} onChange={(e) => up('freeze_allowed')(e.target.checked)} data-testid="mbr-plan-freezeable" />
          <span className="text-[color:var(--theme-text-muted)]">Allow freeze</span>
        </label>
        <Input label="Freeze max days" value={f.freeze_max_days} onChange={up('freeze_max_days')} type="number" testid="mbr-plan-freeze-days" />
        <Input label="Notice days" value={f.cancel_notice_days} onChange={up('cancel_notice_days')} type="number" testid="mbr-plan-notice-days" />
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-3 items-end">
        <Input label="Description" value={f.description} onChange={up('description')} testid="mbr-plan-desc" />
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Colour</span>
          <input type="color" value={f.colour} onChange={(e) => up('colour')(e.target.value)} className="mt-1 h-10 w-16 rounded cursor-pointer bg-transparent" data-testid="mbr-plan-colour" />
        </label>
      </div>
      <Input label="Per-class rate (£) — used for monthly invoicing"
        value={f.per_class_pounds} onChange={up('per_class_pounds')} type="number"
        testid="mbr-plan-per-class" />

      {f.kind === 'recurring' && (
        <div className="rounded-lg border border-[color:var(--theme-border)] p-3 space-y-2" data-testid="mbr-plan-smoothed-block">
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={!!f.smoothed}
              onChange={(e) => up('smoothed')(e.target.checked)}
              data-testid="mbr-plan-smoothed-toggle" />
            Pro-rata the annual fee across N months (predictable monthly payment)
          </label>
          {f.smoothed && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Input label="Annual total (£)"
                  value={f.smoothed_annual_pounds} onChange={up('smoothed_annual_pounds')}
                  type="number" testid="mbr-plan-smoothed-annual" />
                <Input label="Spread across (months)"
                  value={f.smoothed_months} onChange={up('smoothed_months')}
                  type="number" testid="mbr-plan-smoothed-months" />
              </div>
              <div className="text-xs text-[color:var(--color-brand-cyan)] font-bold">
                {(() => {
                  const annual = Number(f.smoothed_annual_pounds) || 0;
                  const months = Math.max(1, Number(f.smoothed_months) || 12);
                  const monthly = annual / months;
                  return `Member pays £${monthly.toFixed(2)} × ${months} months = £${(monthly * months).toFixed(2)}/year`;
                })()}
              </div>
              <p className="text-[11px] text-[color:var(--theme-text-muted)]">
                Perfect for yoga / swim / dance academies that run fewer sessions over holidays — the member's monthly Direct Debit never changes.
              </p>
            </>
          )}
        </div>
      )}

      {f.kind === 'course' && (
        <div className="rounded-lg border border-[color:var(--theme-border)] p-3 space-y-2" data-testid="mbr-plan-course-block">
          <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Course block settings</div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">Class template</span>
              <select value={f.course_template_id} onChange={(e) => up('course_template_id')(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-2 text-sm"
                data-testid="mbr-plan-course-template">
                <option value="">— pick a class template —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
            <Input label="Sessions" value={f.course_session_count}
              onChange={up('course_session_count')} type="number"
              testid="mbr-plan-course-sessions" />
          </div>
          <Input label="First session date (YYYY-MM-DD)"
            value={f.course_start_date} onChange={up('course_start_date')}
            type="date" testid="mbr-plan-course-start" />

          <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)] mb-1">
              Skip dates (school holidays, bank holidays)
            </div>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {(f.course_excluded_dates || []).map((d, i) => (
                <span key={d} className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 text-amber-300 px-2 py-0.5 text-xs font-bold"
                  data-testid={`mbr-plan-course-excluded-${d}`}>
                  {d}
                  <button type="button" onClick={() => up('course_excluded_dates')(
                    (f.course_excluded_dates || []).filter((_, j) => j !== i),
                  )} className="opacity-60 hover:opacity-100">×</button>
                </span>
              ))}
            </div>
            <div className="flex gap-1.5">
              <input type="date" id="mbr-excluded-date-picker"
                className="rounded-lg border border-[color:var(--theme-border)] bg-transparent px-2 py-1.5 text-sm"
                data-testid="mbr-plan-course-excluded-input" />
              <button type="button"
                onClick={() => {
                  const el = document.getElementById('mbr-excluded-date-picker');
                  const v = el?.value;
                  if (!v) return;
                  if ((f.course_excluded_dates || []).includes(v)) { el.value = ''; return; }
                  up('course_excluded_dates')([...(f.course_excluded_dates || []), v].sort());
                  el.value = '';
                }}
                className="px-2 py-1 text-xs font-bold rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5">
                Skip this date
              </button>
            </div>
            <p className="mt-2 text-[11px] text-[color:var(--theme-text-muted)]">
              Each skipped date extends the course by one week so pupils still get the full {f.course_session_count || 'N'} sessions.
            </p>
          </div>

          <p className="text-[11px] text-[color:var(--theme-text-muted)]">
            We'll materialise {f.course_session_count || 'N'} weekly occurrences from the date above (skipping excluded dates). Use the Courses subtab to enrol pupils.
          </p>
        </div>
      )}

      <div className="rounded-lg border border-[color:var(--theme-border)] p-3 space-y-2">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={!!f.waiver_required}
            onChange={(e) => up('waiver_required')(e.target.checked)}
            data-testid="mbr-plan-waiver-required" />
          Require members to sign a waiver / PARQ
        </label>
        {f.waiver_required && (
          <textarea rows={4} placeholder="I acknowledge the risks of…"
            value={f.waiver_text} onChange={(e) => up('waiver_text')(e.target.value)}
            className="w-full rounded-lg border border-[color:var(--theme-border)] bg-transparent p-2 text-sm"
            data-testid="mbr-plan-waiver-text" />
        )}
        <p className="text-[11px] text-[color:var(--theme-text-muted)]">Members sign once in their portal. Editing the text triggers re-signature.</p>
      </div>
      <ModalActions onCancel={() => onClose(false)} onSave={submit} saving={saving} testId="mbr-plan-save" />
    </ModalShell>
  );
}
