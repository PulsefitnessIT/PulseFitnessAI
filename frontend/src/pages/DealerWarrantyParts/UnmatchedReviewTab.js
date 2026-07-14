import { useEffect, useState, useCallback } from 'react';
import { AlertTriangle, TrendingUp } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, StatCard, Modal, Field, input, TrendBadge, money } from './shared';

const ACTIONS = [
  { id: 'map_to_bom', label: 'Map to BOM component', needsCode: true },
  { id: 'create_alias', label: 'Create alias → BOM code', needsCode: true },
  { id: 'mark_obsolete', label: 'Mark obsolete' },
  { id: 'not_dealer_relevant', label: 'Not dealer-stock relevant' },
  { id: 'exclude_from_recommendations', label: 'Exclude from recommendations' },
  { id: 'send_for_review', label: 'Send to parts team' },
];

export default function UnmatchedReviewTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(null);
  const [action, setAction] = useState('map_to_bom');
  const [bomCode, setBomCode] = useState('');
  const [note, setNote] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    dpApi.unmatched({ limit: 300 }).then((d) => setRows(d.parts || [])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const open = (r) => { setSel(r); setAction('map_to_bom'); setBomCode(''); setNote(''); };
  const submit = async () => {
    const needsCode = ACTIONS.find((a) => a.id === action)?.needsCode;
    if (needsCode && !bomCode.trim()) { notify.error('BOM component code required'); return; }
    try {
      await dpApi.unmatchedAction(sel.code_norm, { action, bom_code: bomCode, note });
      notify.success('Disposition saved');
      setSel(null); load();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); }
  };

  const highUsage = rows.filter((r) => r.high_usage).length;

  return (
    <div className="space-y-4" data-testid="dp-unmatched-review-tab">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <StatCard label="Unmatched parts" value={rows.length} tone="amber" testid="dp-unmatched-count" />
        <StatCard label="High-usage unmatched" value={highUsage} tone="red" />
        <StatCard label="Total qty at risk" value={rows.reduce((s, r) => s + (r.total_qty || 0), 0).toLocaleString()} tone="slate" />
      </div>

      <div className="rounded-lg bg-amber-50 border border-amber-100 p-3 text-xs text-amber-800 flex items-center gap-2">
        <AlertTriangle size={14} /> These high-usage parts were used historically but don't match the current BOM. Review each before it feeds dealer recommendations — do not ignore.
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-emerald-500 text-sm">🎉 No unmatched parts — everything is mapped to the BOM.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Part</th><th className="text-right">Total qty</th><th className="text-right">Events</th><th className="text-right">Recent 12m</th><th>Trend</th><th className="text-right">Cost</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid={`dp-unmatched-row-${r.code_norm}`} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="py-2.5 px-4 max-w-[280px]">
                    <div className="flex items-center gap-1.5"><span className="font-mono text-xs text-slate-500">{r.code}</span>{r.high_usage && <TrendingUp size={12} className="text-red-500" title="High usage" />}</div>
                    <div className="text-xs text-slate-500 truncate">{r.description}</div>
                  </td>
                  <td className="text-right tabular-nums font-semibold">{r.total_qty?.toLocaleString()}</td>
                  <td className="text-right tabular-nums text-slate-500">{r.usage_count}</td>
                  <td className="text-right tabular-nums text-slate-500">{r.recent_12m}</td>
                  <td><TrendBadge trend={r.trend} /></td>
                  <td className="text-right tabular-nums text-slate-500">{r.total_cost ? money(r.total_cost) : '—'}</td>
                  <td className="text-xs text-slate-500 capitalize">{String(r.review_status || '').replace(/_/g, ' ')}</td>
                  <td className="text-right pr-3"><button data-testid={`dp-unmatched-review-${r.code_norm}`} onClick={() => open(r)} className="text-xs font-semibold text-[var(--gx-brand-from)] hover:underline">Review</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!sel} onClose={() => setSel(null)} title={`Review · ${sel?.code || ''}`} testid="dp-unmatched-modal"
        footer={<>
          <button onClick={() => setSel(null)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-unmatched-submit" onClick={submit} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Save disposition</button>
        </>}>
        {sel && (
          <>
            <div className="rounded-lg bg-slate-50 border border-slate-100 p-3 text-xs text-slate-600 mb-3">
              <div className="font-mono text-slate-700">{sel.code}</div>
              <div>{sel.description}</div>
              <div className="mt-1 text-slate-500">Used <b>{sel.total_qty}</b> across <b>{sel.usage_count}</b> events · {sel.recent_12m} in last 12m</div>
            </div>
            <Field label="Action">
              <select data-testid="dp-unmatched-action" className={input} value={action} onChange={(e) => setAction(e.target.value)}>
                {ACTIONS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
            </Field>
            {ACTIONS.find((a) => a.id === action)?.needsCode && (
              <Field label="BOM component code *"><input data-testid="dp-unmatched-bomcode" className={`${input} font-mono`} value={bomCode} onChange={(e) => setBomCode(e.target.value)} placeholder="e.g. DTS-656T2" /></Field>
            )}
            <Field label="Note"><input className={input} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </>
        )}
      </Modal>
    </div>
  );
}
