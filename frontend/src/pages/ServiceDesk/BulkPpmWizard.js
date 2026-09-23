/**
 * Bulk PPM Scheduling Wizard.
 *
 * A guided flow to plan preventative maintenance across many sites at once:
 *   1) Customer + sites     2) Service, frequency & lead engineer
 *   3) AI-grouped runs (nearby sites together, in a sensible order)
 *   4) Dates — auto-laid onto the calendar, every row editable before confirm.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Loader2, ChevronRight, ChevronLeft, Sparkles, MapPin, Check, X, CalendarDays, Users,
} from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const FREQS = [
  { v: 'monthly', label: 'Monthly' }, { v: 'quarterly', label: 'Quarterly' },
  { v: 'six_monthly', label: '6-monthly' }, { v: 'annual', label: 'Annual' },
];
const STEPS = ['Sites', 'Service', 'Group', 'Dates'];
const iso = (d) => d.toISOString().slice(0, 10);

function nextWorkingDay(d) {
  const x = new Date(d);
  while (x.getDay() === 0 || x.getDay() === 6) x.setDate(x.getDate() + 1);
  return x;
}
function addWorkingDays(d, n) {
  const x = new Date(d);
  let left = n;
  while (left > 0) { x.setDate(x.getDate() + 1); if (x.getDay() !== 0 && x.getDay() !== 6) left -= 1; }
  return x;
}

export default function BulkPpmWizard({ onClose, onDone }) {
  const [step, setStep] = useState(0);
  const [customers, setCustomers] = useState([]);
  const [customerOrgId, setCustomerOrgId] = useState('');
  const [sites, setSites] = useState([]);
  const [selected, setSelected] = useState([]);
  const [serviceTypes, setServiceTypes] = useState([]);
  const [serviceType, setServiceType] = useState('Preventative Maintenance Service');
  const [frequency, setFrequency] = useState('annual');
  const [engineers, setEngineers] = useState([]);
  const [leadEngineer, setLeadEngineer] = useState('');
  const [groups, setGroups] = useState([]);
  const [groupEngine, setGroupEngine] = useState('');
  const [grouping, setGrouping] = useState(false);
  const [startDate, setStartDate] = useState(() => iso(nextWorkingDay(new Date())));
  const [perDay, setPerDay] = useState(2);
  const [gapDays, setGapDays] = useState(1);
  const [plan, setPlan] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try { const r = await api.get('/svc/desk/customers'); setCustomers(r.data?.customers || []); } catch { /* noop */ }
      try { const r = await api.get('/svc/ppm/service-types'); setServiceTypes(r.data?.service_types || []); } catch { /* noop */ }
      try { const r = await api.get('/svc/desk/engineers'); setEngineers(r.data?.engineers || []); } catch { /* noop */ }
    })();
  }, []);

  useEffect(() => {
    setSites([]); setSelected([]);
    if (!customerOrgId) return;
    (async () => {
      try { const r = await api.get('/svc/desk/customer-sites', { params: { organization_id: customerOrgId } }); setSites(r.data?.sites || []); }
      catch { setSites([]); }
    })();
  }, [customerOrgId]);

  const engName = useCallback((id) => engineers.find((e) => e.id === id)?.full_name || '', [engineers]);
  const toggleSite = (id) => setSelected((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const allSelected = sites.length > 0 && selected.length === sites.length;

  const runGrouping = async () => {
    setGrouping(true);
    try {
      const r = await api.post('/svc/ppm/plan/group', { customer_org_id: customerOrgId, site_ids: selected });
      const g = (r.data?.groups || []).map((x) => ({ ...x, engineer_id: leadEngineer }));
      setGroups(g);
      setGroupEngine(r.data?.engine || 'fallback');
    } catch { notify.error('Could not group the sites'); }
    finally { setGrouping(false); }
  };

  // Auto-lay every site onto a date, run by run.
  const autoPlan = useCallback(() => {
    let cursor = nextWorkingDay(new Date(startDate));
    const rows = [];
    groups.forEach((g, gi) => {
      if (gi > 0) cursor = addWorkingDays(cursor, Math.max(1, Number(gapDays) || 1));
      (g.sites || []).forEach((s, si) => {
        if (si > 0 && si % Math.max(1, Number(perDay) || 1) === 0) cursor = addWorkingDays(cursor, 1);
        rows.push({
          site_id: s.id, site_name: s.name, group: g.name, machine_count: s.machine_count,
          date: iso(cursor), engineer_id: g.engineer_id || leadEngineer,
        });
      });
      cursor = addWorkingDays(cursor, 1);
    });
    setPlan(rows);
  }, [groups, startDate, perDay, gapDays, leadEngineer]);

  useEffect(() => { if (step === 3 && groups.length) autoPlan(); }, [step]); // eslint-disable-line

  const setPlanRow = (i, k, v) => setPlan((p) => p.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  const setGroupEng = (gi, id) => setGroups((p) => p.map((g, idx) => (idx === gi ? { ...g, engineer_id: id } : g)));

  const canNext = useMemo(() => {
    if (step === 0) return customerOrgId && selected.length > 0;
    if (step === 1) return !!serviceType;
    if (step === 2) return groups.length > 0;
    return true;
  }, [step, customerOrgId, selected, serviceType, groups]);

  const confirm = async () => {
    setSaving(true);
    try {
      const assignments = plan.map((r) => ({
        site_id: r.site_id, date: r.date,
        engineer_id: r.engineer_id || '', engineer_name: engName(r.engineer_id),
      }));
      const r = await api.post('/svc/ppm/schedules/bulk', {
        customer_org_id: customerOrgId, service_type: serviceType, frequency, assignments,
      });
      notify.success(`Scheduled ${r.data?.schedules_created || assignments.length} site visit(s)`);
      await onDone?.();
    } catch (e) { notify.error('Could not schedule', e?.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} data-testid="bulk-wizard">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 w-full max-w-2xl max-h-[92vh] flex flex-col shadow-2xl">
        <div className="px-5 py-3.5 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <h3 className="text-base font-bold flex items-center gap-2"><CalendarDays size={16} /> Bulk maintenance planner</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700" data-testid="bulk-wizard-close"><X size={18} /></button>
        </div>

        {/* stepper */}
        <div className="px-5 pt-3 flex items-center gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`flex items-center gap-1.5 text-xs font-semibold ${i === step ? 'text-[var(--color-brand-blue,#2563eb)]' : i < step ? 'text-emerald-600' : 'text-zinc-400'}`}>
                <span className={`w-5 h-5 rounded-full grid place-items-center text-[10px] ${i === step ? 'bg-[var(--color-brand-blue,#2563eb)] text-white' : i < step ? 'bg-emerald-500 text-white' : 'bg-zinc-200 dark:bg-zinc-700'}`}>{i < step ? '✓' : i + 1}</span>
                {s}
              </div>
              {i < STEPS.length - 1 && <ChevronRight size={12} className="text-zinc-300" />}
            </div>
          ))}
        </div>

        <div className="p-5 overflow-auto flex-1">
          {/* STEP 0 — customer + sites */}
          {step === 0 && (
            <div className="space-y-4" data-testid="bulk-step-sites">
              <div>
                <Label className="text-xs">Customer</Label>
                <select value={customerOrgId} onChange={(e) => setCustomerOrgId(e.target.value)}
                  className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="bulk-customer">
                  <option value="">— Select customer —</option>
                  {customers.map((c) => <option key={c.organization_id} value={c.organization_id}>{c.name}{c.site_count != null ? ` · ${c.site_count} sites` : ''}</option>)}
                </select>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Sites ({selected.length}/{sites.length})</Label>
                  <button onClick={() => setSelected(allSelected ? [] : sites.map((s) => s.id))} disabled={!sites.length}
                    className="text-xs font-semibold text-[var(--color-brand-blue,#2563eb)]" data-testid="bulk-selectall">
                    {allSelected ? 'Clear all' : 'Select all'}
                  </button>
                </div>
                <div className="mt-1 max-h-64 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800" data-testid="bulk-sitelist">
                  {sites.length === 0 ? <p className="p-3 text-xs text-zinc-400">Pick a customer to list its sites</p> : sites.map((s) => (
                    <label key={s.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800" data-testid={`bulk-site-${s.id}`}>
                      <input type="checkbox" checked={selected.includes(s.id)} onChange={() => toggleSite(s.id)} />
                      <span className="flex-1 truncate">{s.name}</span>
                      {s.equipment_count != null && <span className="text-[11px] text-zinc-400 shrink-0">{s.equipment_count} machines</span>}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* STEP 1 — service + frequency + lead engineer */}
          {step === 1 && (
            <div className="space-y-4" data-testid="bulk-step-service">
              <div>
                <Label className="text-xs">Service type</Label>
                <select value={serviceType} onChange={(e) => setServiceType(e.target.value)}
                  className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="bulk-service">
                  {serviceTypes.map((s) => <option key={s.id} value={s.name}>{`${s.name}${s.calibrate_treadmills ? ' (PM + treadmill calibration)' : (s.requires_calibration ? ' (calibration)' : '')}`}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Frequency</Label>
                  <select value={frequency} onChange={(e) => setFrequency(e.target.value)}
                    className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="bulk-frequency">
                    {FREQS.map((f) => <option key={f.v} value={f.v}>{f.label}</option>)}
                  </select>
                </div>
                <div>
                  <Label className="text-xs flex items-center gap-1"><Users size={12} /> Lead engineer</Label>
                  <select value={leadEngineer} onChange={(e) => setLeadEngineer(e.target.value)}
                    className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="bulk-engineer">
                    <option value="">— Assign later —</option>
                    {engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                  </select>
                </div>
              </div>
              <p className="text-[11px] text-zinc-500">The lead engineer is applied to every run; you can override the engineer per run in the next step.</p>
            </div>
          )}

          {/* STEP 2 — AI grouping */}
          {step === 2 && (
            <div className="space-y-3" data-testid="bulk-step-group">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-zinc-500">Group nearby sites so they're serviced together, in a sensible order.</p>
                <Button size="sm" onClick={runGrouping} disabled={grouping} data-testid="bulk-run-grouping"
                  className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)]">
                  {grouping ? <Loader2 size={13} className="animate-spin mr-1.5" /> : <Sparkles size={13} className="mr-1.5" />}
                  {groups.length ? 'Re-group with AI' : 'Group sites with AI'}
                </Button>
              </div>
              {groupEngine === 'fallback' && groups.length > 0 && (
                <p className="text-[11px] text-amber-600">Grouped by postcode/town from the address text (AI unavailable or sites lack address detail).</p>
              )}
              {groups.length === 0 ? (
                <div className="rounded-lg border border-dashed border-zinc-300 dark:border-zinc-700 p-6 text-center text-xs text-zinc-400">
                  Press “Group sites with AI” to cluster the {selected.length} selected sites into runs.
                </div>
              ) : (
                <div className="space-y-2">
                  {groups.map((g, gi) => (
                    <div key={gi} className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3" data-testid={`bulk-group-${gi}`}>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <MapPin size={13} className="text-[var(--color-brand-blue,#2563eb)] shrink-0" />
                          <span className="text-sm font-bold truncate">{g.name}</span>
                          <span className="text-[10px] text-zinc-400 shrink-0">{(g.sites || []).length} sites</span>
                        </div>
                        <select value={g.engineer_id || ''} onChange={(e) => setGroupEng(gi, e.target.value)}
                          className="h-8 rounded-md border border-zinc-200 dark:border-zinc-700 bg-transparent px-2 text-xs" data-testid={`bulk-group-eng-${gi}`}>
                          <option value="">Lead engineer</option>
                          {engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                        </select>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {(g.sites || []).map((s) => (
                          <span key={s.id} className="text-[11px] bg-zinc-100 dark:bg-zinc-800 rounded px-2 py-0.5">{s.name}{s.machine_count ? ` · ${s.machine_count}` : ''}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* STEP 3 — dates */}
          {step === 3 && (
            <div className="space-y-3" data-testid="bulk-step-dates">
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Start date</Label>
                  <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1" data-testid="bulk-startdate" />
                </div>
                <div>
                  <Label className="text-xs">Sites per day</Label>
                  <Input type="number" min="1" value={perDay} onChange={(e) => setPerDay(e.target.value)} className="mt-1" data-testid="bulk-perday" />
                </div>
                <div>
                  <Label className="text-xs">Days between runs</Label>
                  <Input type="number" min="0" value={gapDays} onChange={(e) => setGapDays(e.target.value)} className="mt-1" data-testid="bulk-gapdays" />
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={autoPlan} data-testid="bulk-autoplan">
                <Sparkles size={13} className="mr-1.5" /> Auto-lay dates
              </Button>
              <div className="max-h-72 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700" data-testid="bulk-plan-table">
                <table className="w-full text-xs">
                  <thead className="bg-zinc-50 dark:bg-zinc-800 sticky top-0">
                    <tr className="text-left text-zinc-500">
                      <th className="px-2 py-1.5 font-semibold">Site</th>
                      <th className="px-2 py-1.5 font-semibold">Run</th>
                      <th className="px-2 py-1.5 font-semibold">Date</th>
                      <th className="px-2 py-1.5 font-semibold">Engineer</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                    {plan.map((r, i) => (
                      <tr key={r.site_id} data-testid={`bulk-plan-row-${i}`}>
                        <td className="px-2 py-1.5 truncate max-w-[160px]">{r.site_name}{r.machine_count ? <span className="text-zinc-400"> · {r.machine_count}</span> : ''}</td>
                        <td className="px-2 py-1.5 text-zinc-500 truncate max-w-[120px]">{r.group}</td>
                        <td className="px-2 py-1.5"><input type="date" value={r.date} onChange={(e) => setPlanRow(i, 'date', e.target.value)} className="h-7 rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-1.5 text-xs" data-testid={`bulk-plan-date-${i}`} /></td>
                        <td className="px-2 py-1.5">
                          <select value={r.engineer_id || ''} onChange={(e) => setPlanRow(i, 'engineer_id', e.target.value)} className="h-7 rounded border border-zinc-200 dark:border-zinc-700 bg-transparent px-1 text-xs" data-testid={`bulk-plan-eng-${i}`}>
                            <option value="">—</option>
                            {engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-zinc-500">{plan.length} visit(s) will be created. Edit any date or engineer above before confirming.</p>
            </div>
          )}
        </div>

        <div className="px-5 py-3.5 border-t border-zinc-200 dark:border-zinc-800 flex justify-between gap-2">
          <Button variant="ghost" size="sm" onClick={() => (step === 0 ? onClose?.() : setStep(step - 1))} data-testid="bulk-back">
            <ChevronLeft size={14} className="mr-1" /> {step === 0 ? 'Cancel' : 'Back'}
          </Button>
          {step < 3 ? (
            <Button size="sm" disabled={!canNext} onClick={() => setStep(step + 1)} data-testid="bulk-next"
              className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)]">
              Next <ChevronRight size={14} className="ml-1" />
            </Button>
          ) : (
            <Button size="sm" disabled={saving || plan.length === 0} onClick={confirm} data-testid="bulk-confirm"
              className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)]">
              {saving ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Check size={14} className="mr-1.5" />} Confirm &amp; schedule
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
