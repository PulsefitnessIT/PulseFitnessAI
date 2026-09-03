import { useEffect, useState, useCallback } from 'react';
import { ChevronDown, ChevronRight, Scale, TrendingUp, TrendingDown, PlusCircle, CircleSlash, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner } from './shared';

const STATUS_META = {
  under_planned: { label: 'Plan too low', tone: 'bg-red-50 text-red-700 border-red-200', Icon: TrendingUp, hint: 'Used more than planned' },
  over_planned: { label: 'Plan too high', tone: 'bg-amber-50 text-amber-700 border-amber-200', Icon: TrendingDown, hint: 'Used less than planned' },
  used_not_in_plan: { label: 'Used, not in plan', tone: 'bg-indigo-50 text-indigo-700 border-indigo-200', Icon: PlusCircle, hint: 'Real usage the plan misses' },
  in_plan_unused: { label: 'In plan, never used', tone: 'bg-slate-100 text-slate-600 border-slate-200', Icon: CircleSlash, hint: 'No real usage seen' },
  aligned: { label: 'Aligned', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200', Icon: CheckCircle2, hint: 'Matches the plan' },
};

const ACTIONABLE = ['under_planned', 'over_planned', 'used_not_in_plan'];
const fmtQty = (v) => (v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

function DivergenceRow({ row, onApply, applied }) {
  const meta = STATUS_META[row.status] || STATUS_META.aligned;
  const suggest = Number(row.suggested_qty_5y || 0);
  const canApply = ACTIONABLE.includes(row.status) && suggest !== Number(row.plan_per_machine_5y || 0);
  return (
    <tr className={`border-b border-slate-50 ${applied ? 'bg-emerald-50/40' : ''}`} data-testid={`dp-wiz-pva-row-${row.part_code}`}>
      <td className="py-2 px-3 max-w-[260px]">
        <span className="font-mono text-xs text-slate-500">{row.part_code}</span>
        <div className="text-xs text-slate-600 truncate" title={row.description}>{row.description}</div>
      </td>
      <td className="text-right tabular-nums text-slate-600">{fmtQty(row.plan_per_machine_5y)}</td>
      <td className="text-right tabular-nums text-slate-900 font-semibold">{fmtQty(row.actual_per_machine_5y)}</td>
      <td className="text-center">
        <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${meta.tone}`} title={meta.hint}>
          <meta.Icon size={11} /> {meta.label}
        </span>
      </td>
      <td className="text-right px-3">
        {applied ? (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-600" data-testid={`dp-wiz-pva-applied-${row.part_code}`}>
            <CheckCircle2 size={12} /> Plan set to {fmtQty(applied)}
          </span>
        ) : canApply ? (
          <button
            data-testid={`dp-wiz-pva-apply-${row.part_code}`}
            onClick={() => onApply(row)}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--gx-brand-from)] hover:underline">
            <RefreshCw size={11} /> Set plan to {fmtQty(suggest)}
          </button>
        ) : (
          <span className="text-[11px] text-slate-300">—</span>
        )}
      </td>
    </tr>
  );
}

export default function PlanVsActualsPanel({ lines }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [applied, setApplied] = useState({}); // `${group}||${code_norm}` -> qty
  const [expanded, setExpanded] = useState({}); // machine_ref -> bool
  const [showAligned, setShowAligned] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const res = await dpApi.planVsActuals({ lines });
      setData(res);
      const exp = {};
      (res.machines || []).forEach((m) => { exp[m.machine_ref || m.input_ref] = ((m.summary || {}).flagged || 0) > 0; });
      setExpanded(exp);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load Plan vs Actuals. Please retry.');
    } finally { setLoading(false); }
  }, [lines]);

  useEffect(() => { if (open && !data && !loading && !error) load(); }, [open, data, loading, error, load]);

  const applyRow = async (group, row) => {
    const key = `${group}||${row.part_code_norm}`;
    try {
      await dpApi.updateWarrantyPlanPart({
        machine_group: group,
        part_code_norm: row.part_code_norm,
        part_code: row.part_code,
        description: row.description,
        total_qty_5y: row.suggested_qty_5y,
        sales_price: row.sales_price,
        cost_price: row.cost_price,
      });
      setApplied((s) => ({ ...s, [key]: row.suggested_qty_5y }));
      // Keep the table truthful: the plan now equals the suggested value.
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          machines: (prev.machines || []).map((m) => {
            if (m.machine_group !== group) return m;
            return {
              ...m,
              rows: (m.rows || []).map((r) => r.part_code_norm === row.part_code_norm
                ? { ...r, in_plan: true, plan_per_machine_5y: row.suggested_qty_5y, plan_this_order: Math.round(row.suggested_qty_5y * (m.quantity || 1) * 100) / 100, status: 'aligned', divergence_pct: 0 }
                : r),
            };
          }),
        };
      });
      notify.success(`Plan updated — ${row.part_code} set to ${fmtQty(row.suggested_qty_5y)}/machine over 5 years.`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not update the plan');
    }
  };

  const totalActionable = (data?.machines || []).reduce((s, m) => {
    const su = m.summary || {};
    return s + (su.under_planned || 0) + (su.over_planned || 0) + (su.used_not_in_plan || 0);
  }, 0);
  const totalUnused = (data?.machines || []).reduce((s, m) => s + ((m.summary || {}).in_plan_unused || 0), 0);
  const totalAligned = (data?.machines || []).reduce((s, m) => s + ((m.summary || {}).aligned || 0), 0);

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid="dp-wiz-pva-panel">
      <button
        data-testid="dp-wiz-pva-toggle"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-slate-50 text-left">
        {open ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
        <Scale size={15} className="text-[var(--gx-brand-from)]" />
        <span className="text-sm font-bold text-slate-900">Plan vs Actuals</span>
        <span className="text-xs text-slate-500 hidden sm:inline">Where real usage diverges from the 5-year plan</span>
        {data && data.loaded && (
          <span className={`ml-auto text-xs font-semibold px-2 py-0.5 rounded-full ${totalActionable > 0 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`} data-testid="dp-wiz-pva-flagged">
            {totalActionable > 0 ? `${totalActionable} to review${totalUnused ? ` · ${totalUnused} unused` : ''}` : 'All aligned'}
          </span>
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-slate-100">
          {loading ? (
            <div className="py-8 flex justify-center"><Spinner /></div>
          ) : error ? (
            <div className="py-4 flex items-start gap-2 text-xs text-red-600" data-testid="dp-wiz-pva-error">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <div>{error} <button onClick={load} className="ml-1 font-semibold text-[var(--gx-brand-from)] hover:underline" data-testid="dp-wiz-pva-retry">Retry</button></div>
            </div>
          ) : !data ? null : !data.loaded ? (
            <div className="py-4 text-xs text-slate-500 flex items-start gap-2" data-testid="dp-wiz-pva-empty">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-500" /><div>{data.note}</div>
            </div>
          ) : (
            <div className="space-y-3 pt-3">
              <div className="text-xs text-slate-500 flex items-start gap-2">
                <Scale size={13} className="mt-0.5 shrink-0 text-slate-400" />
                <div>
                  Compares Pulse's 5-year plan (expected failures <b>per machine</b>) against real historical usage,
                  scaled to the <b>{(data.machines || []).reduce((s, m) => s + (m.quantity || 0), 0)} machine(s)</b> on this invoice.
                  Flags anything more than <b>{data.over_pct}%</b> above or below the plan, plus parts in the plan but never used, and parts used but not in the plan.
                  {!data.usage_available && <span className="text-amber-600"> No historical usage data yet — import a “Parts Used” spreadsheet to compare.</span>}
                </div>
              </div>

              {(data.machines || []).map((mac) => {
                const ref = mac.machine_ref || mac.input_ref;
                const isOpen = expanded[ref];
                const rows = (mac.rows || []).filter((r) => showAligned || r.status !== 'aligned' || applied[`${mac.machine_group}||${r.part_code_norm}`] !== undefined);
                const s = mac.summary || {};
                return (
                  <div key={ref} className="rounded-lg border border-slate-100" data-testid={`dp-wiz-pva-machine-${ref}`}>
                    <button
                      onClick={() => setExpanded((e) => ({ ...e, [ref]: !e[ref] }))}
                      className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 text-left">
                      {isOpen ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
                      <span className="font-mono text-sm font-semibold text-slate-900">{ref}</span>
                      {mac.machine_group && <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded bg-[var(--gx-brand-from)]/10 text-[var(--gx-brand-from)]">Plan: {mac.machine_group}</span>}
                      <span className="text-xs text-slate-400">×{mac.quantity}</span>
                      {mac.note ? (
                        <span className="ml-auto text-xs text-slate-400">{mac.note}</span>
                      ) : (
                        <span className="ml-auto flex items-center gap-1">
                          {s.under_planned > 0 && <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-red-50 text-red-600">{s.under_planned} low</span>}
                          {s.over_planned > 0 && <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600">{s.over_planned} high</span>}
                          {s.used_not_in_plan > 0 && <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-600">{s.used_not_in_plan} missing</span>}
                          {((s.under_planned || 0) + (s.over_planned || 0) + (s.used_not_in_plan || 0)) === 0 && <span className="text-[11px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-600">aligned</span>}
                        </span>
                      )}
                    </button>
                    {isOpen && !mac.note && (
                      <div className="px-3 pb-3">
                        <div className="overflow-x-auto rounded-lg border border-slate-100">
                          <table className="w-full text-sm">
                            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                              <th className="py-1.5 px-3">Part</th>
                              <th className="text-right">Plan /machine (5yr)</th>
                              <th className="text-right">Actual /machine (5yr)</th>
                              <th className="text-center">Status</th>
                              <th className="text-right px-3">Refine plan</th>
                            </tr></thead>
                            <tbody>
                              {rows.map((r) => (
                                <DivergenceRow key={r.part_code} row={r} onApply={(row) => applyRow(mac.machine_group, row)}
                                  applied={applied[`${mac.machine_group}||${r.part_code_norm}`]} />
                              ))}
                              {rows.length === 0 && <tr><td colSpan={5} className="py-4 text-center text-xs text-slate-400">Everything is aligned with the plan.</td></tr>}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              <label className={`flex items-center gap-2 text-xs cursor-pointer ${totalAligned ? 'text-slate-500' : 'text-slate-300 cursor-not-allowed'}`}>
                <input type="checkbox" data-testid="dp-wiz-pva-show-aligned" checked={showAligned} disabled={!totalAligned} onChange={(e) => setShowAligned(e.target.checked)} className="rounded border-slate-300" />
                Show parts that already match the plan{totalAligned ? ` (${totalAligned})` : ' — none'}
              </label>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
