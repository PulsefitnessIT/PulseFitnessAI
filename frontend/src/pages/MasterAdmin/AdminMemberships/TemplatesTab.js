import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import {
 Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Plus, Trash2, Copy, Lock } from 'lucide-react';
import { SectionCard, Pill, fmtMoney } from './shared';

const DEFAULT_TPL = {
 name: '',
 kind: 'recurring',
 billing_cycle: 'monthly',
 price_pence: 2900,
 upfront_fee_pence: 0,
 included_classes: 'unlimited',
 credits_count: null,
 duration_days: null,
 freeze_allowed: true,
 freeze_max_days: 90,
 cancel_notice_days: 0,
 grace_period_days: 3,
 vat_pct: 20.0,
 default_contract_rules: '',
 description: '',
 colour: 'var(--color-brand-cyan)',
};

const TemplatesTab = ({ templates, organizations, onCreate, onUpdate, onDelete, onApply }) => {
 const [open, setOpen] = useState(false);
 const [editing, setEditing] = useState(null); // null = new, else tpl object
 const [form, setForm] = useState(DEFAULT_TPL);
 const [applying, setApplying] = useState(null);
 const [applySelection, setApplySelection] = useState([]);
 const [applyLock, setApplyLock] = useState(false);

 const openNew = () => { setEditing(null); setForm(DEFAULT_TPL); setOpen(true); };
 const openEdit = (tpl) => { setEditing(tpl); setForm({ ...DEFAULT_TPL, ...tpl }); setOpen(true); };

 const save = async () => {
 const payload = {
 ...form,
 price_pence: Number(form.price_pence) || 0,
 upfront_fee_pence: Number(form.upfront_fee_pence) || 0,
 credits_count: form.credits_count ? Number(form.credits_count) : null,
 duration_days: form.duration_days ? Number(form.duration_days) : null,
 freeze_max_days: Number(form.freeze_max_days) || 0,
 cancel_notice_days: Number(form.cancel_notice_days) || 0,
 grace_period_days: Number(form.grace_period_days) || 0,
 vat_pct: Number(form.vat_pct) || 0,
 };
 if (editing) await onUpdate(editing.id, payload);
 else await onCreate(payload);
 setOpen(false);
 };

 const confirmApply = async () => {
 await onApply(applying.id, applySelection, applyLock);
 setApplying(null);
 setApplySelection([]);
 setApplyLock(false);
 };

 return (
 <div className="space-y-4" data-testid="memberships-admin-templates">
 <SectionCard
 title="Global Plan Templates"
 action={
 <Button size="sm" className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" onClick={openNew} data-testid="new-template-btn">
 <Plus size={14} className="mr-1" /> New template
 </Button>
 }
 >
 {!templates.length ? (
 <p className="text-sm text-zinc-400 py-6 text-center">No templates yet — create your first global membership template.</p>
 ) : (
 <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
 {templates.map((t) => (
 <div key={t.id} className="border border-zinc-200 rounded-lg p-4 bg-white hover:border-zinc-300 transition-colors" data-testid={`tpl-card-${t.id}`}>
 <div className="flex items-start justify-between mb-2">
 <div>
 <h4 className="font-medium text-zinc-900">{t.name}</h4>
 <div className="flex items-center gap-1.5 mt-1 flex-wrap">
 <Pill tone="blue">{t.billing_cycle}</Pill>
 <Pill tone="zinc">{t.kind}</Pill>
 <Pill tone="violet">{t.included_classes}</Pill>
 </div>
 </div>
 <span className="w-3 h-3 rounded-full mt-1" style={{ background: t.colour }} />
 </div>
 <p className="text-2xl font-semibold text-zinc-900">{fmtMoney(t.price_pence)}<span className="text-xs font-normal text-zinc-400">/{t.billing_cycle === 'annual' ? 'yr' : t.billing_cycle === 'oneoff' ? 'once' : 'mo'}</span></p>
 <p className="text-[11px] text-zinc-500 mt-1">
 VAT {t.vat_pct}% · Freeze {t.freeze_allowed ? `up to ${t.freeze_max_days}d` : 'off'} · Cancel notice {t.cancel_notice_days}d
 </p>
 <div className="flex gap-1 mt-3 pt-3 border-t border-zinc-100">
 <Button size="sm" variant="outline" className="h-7 text-[11px] flex-1" onClick={() => openEdit(t)} data-testid={`tpl-edit-${t.id}`}>Edit</Button>
 <Button size="sm" variant="outline" className="h-7 text-[11px] flex-1" onClick={() => { setApplying(t); setApplySelection([]); }} data-testid={`tpl-apply-${t.id}`}>
 <Copy size={11} className="mr-1" /> Apply
 </Button>
 <Button size="sm" variant="outline" className="h-7 text-[11px] border-red-200 text-red-600" onClick={() => onDelete(t.id)} data-testid={`tpl-delete-${t.id}`}>
 <Trash2 size={11} />
 </Button>
 </div>
 </div>
 ))}
 </div>
 )}
 </SectionCard>

 <Dialog open={open} onOpenChange={setOpen}>
 <DialogContent className="max-w-2xl">
 <DialogHeader><DialogTitle>{editing ? 'Edit template' : 'New plan template'}</DialogTitle></DialogHeader>
 <div className="grid grid-cols-2 gap-3 text-sm">
 <div className="col-span-2">
 <Label>Name</Label>
 <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="tpl-name" />
 </div>
 <div>
 <Label>Kind</Label>
 <select className="w-full border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 rounded-md h-9 px-2 text-sm" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} data-testid="tpl-kind">
 <option value="recurring">Recurring</option>
 <option value="paygo">Pay-as-you-go</option>
 <option value="pack">Pack / Credits</option>
 </select>
 </div>
 <div>
 <Label>Billing cycle</Label>
 <select className="w-full border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 rounded-md h-9 px-2 text-sm" value={form.billing_cycle} onChange={(e) => setForm({ ...form, billing_cycle: e.target.value })} data-testid="tpl-billing">
 <option value="monthly">Monthly</option>
 <option value="annual">Annual</option>
 <option value="oneoff">One-off</option>
 </select>
 </div>
 <div>
 <Label>Price (pence)</Label>
 <Input type="number" value={form.price_pence} onChange={(e) => setForm({ ...form, price_pence: e.target.value })} data-testid="tpl-price" />
 </div>
 <div>
 <Label>Upfront fee (pence)</Label>
 <Input type="number" value={form.upfront_fee_pence} onChange={(e) => setForm({ ...form, upfront_fee_pence: e.target.value })} data-testid="tpl-upfront" />
 </div>
 <div>
 <Label>Included classes</Label>
 <select className="w-full border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 rounded-md h-9 px-2 text-sm" value={form.included_classes} onChange={(e) => setForm({ ...form, included_classes: e.target.value })}>
 <option value="unlimited">Unlimited</option>
 <option value="credits">Credit pack</option>
 <option value="duration">Duration-based</option>
 </select>
 </div>
 <div>
 <Label>Credits count</Label>
 <Input type="number" value={form.credits_count ?? ''} onChange={(e) => setForm({ ...form, credits_count: e.target.value })} />
 </div>
 <div>
 <Label>Freeze max days</Label>
 <Input type="number" value={form.freeze_max_days} onChange={(e) => setForm({ ...form, freeze_max_days: e.target.value })} />
 </div>
 <div>
 <Label>Cancel notice (days)</Label>
 <Input type="number" value={form.cancel_notice_days} onChange={(e) => setForm({ ...form, cancel_notice_days: e.target.value })} />
 </div>
 <div>
 <Label>Grace period (days)</Label>
 <Input type="number" value={form.grace_period_days} onChange={(e) => setForm({ ...form, grace_period_days: e.target.value })} />
 </div>
 <div>
 <Label>VAT %</Label>
 <Input type="number" step="0.1" value={form.vat_pct} onChange={(e) => setForm({ ...form, vat_pct: e.target.value })} />
 </div>
 <div className="col-span-2 flex items-center justify-between border border-zinc-200 dark:border-zinc-700 rounded-md px-3 py-2">
 <span className="text-sm text-zinc-900 dark:text-zinc-100">Freeze allowed</span>
 <Switch checked={form.freeze_allowed} onCheckedChange={(v) => setForm({ ...form, freeze_allowed: v })} data-testid="tpl-freeze-allowed" />
 </div>
 <div className="col-span-2">
 <Label>Default contract rules</Label>
 <textarea
 value={form.default_contract_rules || ''}
 onChange={(e) => setForm({ ...form, default_contract_rules: e.target.value })}
 className="w-full border border-zinc-200 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 rounded-md p-2 text-sm min-h-[60px]"
 placeholder="e.g. 12-month minimum term, auto-renewal after initial period…"
 />
 </div>
 </div>
 <DialogFooter>
 <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
 <Button className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" onClick={save} disabled={!form.name} data-testid="tpl-save">
 {editing ? 'Save changes' : 'Create template'}
 </Button>
 </DialogFooter>
 </DialogContent>
 </Dialog>

 <Dialog open={!!applying} onOpenChange={(o) => !o && setApplying(null)}>
 <DialogContent className="max-w-lg">
 <DialogHeader><DialogTitle>Apply template to organisations</DialogTitle></DialogHeader>
 {applying && (
 <div className="space-y-3 text-sm">
 <div className="p-3 bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 rounded-md">
 <p className="font-medium">{applying.name}</p>
 <p className="text-xs text-zinc-500">{fmtMoney(applying.price_pence)} · {applying.billing_cycle}</p>
 </div>
 <div>
 <Label className="mb-2 block">Select organisations ({applySelection.length} selected)</Label>
 <div className="max-h-60 overflow-y-auto border border-zinc-200 rounded-md divide-y divide-zinc-100">
 {organizations.map((o) => (
 <label key={o.id} className="flex items-center justify-between px-3 py-2 text-sm cursor-pointer hover:bg-zinc-50">
 <div className="flex items-center gap-2">
 <input
 type="checkbox"
 checked={applySelection.includes(o.id)}
 onChange={(e) => setApplySelection((prev) =>
 e.target.checked ? [...prev, o.id] : prev.filter((x) => x !== o.id)
 )}
 data-testid={`apply-org-${o.id}`}
 />
 <span>{o.name}</span>
 </div>
 <Pill tone={o.memberships_tier === 'pro' ? 'violet' : 'zinc'}>{o.memberships_tier}</Pill>
 </label>
 ))}
 </div>
 </div>
 <div className="flex items-center justify-between border border-zinc-100 rounded-md px-3 py-2">
 <span className="flex items-center gap-1.5"><Lock size={12} /> Lock template (prevent org edits)</span>
 <Switch checked={applyLock} onCheckedChange={setApplyLock} data-testid="apply-lock" />
 </div>
 </div>
 )}
 <DialogFooter>
 <Button variant="outline" onClick={() => setApplying(null)}>Cancel</Button>
 <Button
 className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]"
 onClick={confirmApply}
 disabled={!applySelection.length}
 data-testid="apply-confirm"
 >
 Apply to {applySelection.length} {applySelection.length === 1 ? 'org' : 'orgs'}
 </Button>
 </DialogFooter>
 </DialogContent>
 </Dialog>
 </div>
 );
};

export default TemplatesTab;
