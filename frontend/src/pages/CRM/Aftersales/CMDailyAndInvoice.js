/** Contracts & Renewals — Coordinator daily view and monthly invoice-run preview. */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Download, Loader2 } from 'lucide-react';

const CARDS = [
  ['expiring_soon', 'Expiring in 90 days'], ['renewals', 'Renewals awaiting action'], ['missing_information', 'Missing contract information'],
  ['awaiting_approval', 'Awaiting approval'], ['service_attention', 'Service visits needing attention'], ['follow_up', 'Follow-ups due'],
  ['import_exceptions', 'Unresolved import exceptions'], ['unverified_billing', 'Billing to verify'], ['sicon_pending', 'Awaiting Sicon reconciliation'],
];

export function CoordinatorDailyView({ API, headers, c, onOpenContract, onOpenExceptions }) {
  const [who, setWho] = useState('');
  const [data, setData] = useState(null);
  const [open, setOpen] = useState('');
  useEffect(() => {
    axios.get(`${API}/crm/v2/aftersales/maintenance-master/daily`, { headers: headers(), params: { coordinator: who } })
      .then(r => setData(r.data)).catch(() => setData({ cards: {}, coordinators: [], error: true }));
  }, [API, headers, who]);
  if (!data) return <Loader2 size={14} className="animate-spin" />;
  const card = open ? data.cards[open] : null;
  return (
    <div data-testid="cm-daily-view" className="mb-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h3 className="text-base font-bold" style={{ color: c.text }}>Today</h3>
        <select value={who} onChange={e => setWho(e.target.value)} data-testid="cm-daily-coordinator"
                className="text-xs px-2 py-1 rounded-lg border" style={{ background: 'transparent', borderColor: c.border, color: c.text }}>
          <option value="">All coordinators</option>
          {data.coordinators.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        {data.error && <span className="text-xs" style={{ color: 'var(--color-danger-alt)' }}>Could not load today's work.</span>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-2">
        {CARDS.map(([k, label]) => {
          const n = data.cards[k]?.count || 0;
          return (
            <button key={k} onClick={() => (k === 'import_exceptions' ? onOpenExceptions() : setOpen(o => (o === k ? '' : k)))}
                    data-testid={`cm-daily-card-${k}`} className="text-left p-2.5 rounded-xl border"
                    style={{ borderColor: open === k ? 'var(--color-brand-cyan)' : c.border }}>
              <div className="text-xl font-bold" style={{ color: n ? c.text : c.textDim }}>{n}</div>
              <div className="text-[11px]" style={{ color: c.textDim }}>{label}</div>
            </button>);
        })}
      </div>
      {card && (
        <div className="mt-2 rounded-xl border text-xs" style={{ borderColor: c.border }} data-testid={`cm-daily-list-${open}`}>
          {(card.items || []).length === 0 ? <div className="p-3" style={{ color: c.textDim }}>Nothing here.</div> : card.items.map((it, i) => (
            <button key={it.id || i} onClick={() => it.contract_number && onOpenContract(it.contract_number)}
                    className="w-full text-left px-3 py-1.5 border-t first:border-t-0 flex justify-between gap-2" style={{ borderColor: c.border, color: c.text }}>
              <span><b>{it.contract_number || it.contract_id?.slice(0, 8)}</b> {it.customer || ''}</span>
              <span style={{ color: c.textDim }}>{it.detail || it.end_date || it.due || ''}{it.bucket ? ` · ${it.bucket}` : ''}</span>
            </button>))}
          {card.count > (card.items || []).length && <div className="px-3 py-1" style={{ color: c.textDim }}>+{card.count - card.items.length} more — use the contract search below.</div>}
        </div>)}
    </div>
  );
}

const gbp = v => (v == null ? '—' : `£${Number(v).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

export function InvoiceRunPreview({ API, headers, c }) {
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/crm/v2/aftersales/maintenance-master/invoice-run`, { headers: headers(), params: { period } })
      .then(r => setData(r.data)).catch(e => { setData(null); toast.error(e.response?.data?.detail || 'Could not build the preview'); })
      .finally(() => setLoading(false));
  }, [API, headers, period]);
  useEffect(() => { load(); }, [load]);
  const exportX = () => axios.get(`${API}/crm/v2/aftersales/maintenance-master/invoice-run/export`, { headers: headers(), params: { period }, responseType: 'blob' })
    .then(r => { const u = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = u; a.download = `invoice-run-preview-${period}.xlsx`; a.click(); URL.revokeObjectURL(u); })
    .catch(() => toast.error('Export failed'));
  const t = data?.totals || {};
  return (
    <div data-testid="cm-invoice-run" className="mb-6 p-4 rounded-xl border" style={{ borderColor: c.border }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div>
          <h2 className="text-lg font-bold" style={{ color: c.text }}>Maintenance invoice run — preview</h2>
          <p className="text-xs" style={{ color: c.textDim }}>Preview only. Nothing is invoiced, posted to Sage or sent to customers.</p>
        </div>
        <div className="flex items-center gap-2">
          <input type="month" value={period} onChange={e => setPeriod(e.target.value)} data-testid="cm-invoice-period"
                 className="text-xs px-2 py-1 rounded-lg border" style={{ background: 'transparent', borderColor: c.border, color: c.text }} />
          <button onClick={exportX} data-testid="cm-invoice-export" className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs border"
                  style={{ borderColor: c.border, color: c.textDim }}><Download size={13} /> Export</button>
        </div>
      </div>
      {loading || !data ? <Loader2 size={14} className="animate-spin" /> : (<>
        <div className="flex flex-wrap gap-4 text-xs mb-2" data-testid="cm-invoice-totals" style={{ color: c.text }}>
          <span>Proposed: <b>{t.proposed}</b></span><span>Net: <b>{gbp(t.net)}</b></span>
          <span>VAT: <b>{data.vat_verified ? `${gbp(t.vat)} (${Math.round(data.vat_pct * 100)}%)` : 'not configured — not calculated'}</b></span>
          {data.vat_verified && <span>Gross: <b>{gbp(t.gross)}</b></span>}
          <span style={{ color: t.needs_information ? 'var(--color-warning-alt)' : c.textDim }}>Needs information: <b>{t.needs_information}</b></span>
          <span style={{ color: c.textDim }}>Already invoiced: {t.already_invoiced}</span>
          <span style={{ color: t.duplicates ? 'var(--color-danger-alt)' : c.textDim }}>Duplicates excluded: {t.duplicates}</span>
        </div>
        <div className="rounded-xl border overflow-x-auto max-h-[28rem]" style={{ borderColor: c.border }}>
          <table className="w-full text-xs" data-testid="cm-invoice-table">
            <thead><tr style={{ color: c.textDim }}>{['Billing date', 'Contract', 'Customer', 'Frequency', 'Amount', 'Sage account', 'DD', 'Status', 'Warnings'].map(h => <th key={h} className="px-2 py-1 text-left">{h}</th>)}</tr></thead>
            <tbody>{data.rows.map((r, i) => (
              <tr key={`${r.contract_id}-${r.billing_date}-${i}`} className="border-t" style={{ borderColor: c.border, color: c.text }}>
                <td className="px-2 py-1 whitespace-nowrap">{r.billing_date}</td><td className="px-2">{r.contract_number}</td><td className="px-2">{r.customer}</td>
                <td className="px-2">{r.frequency || '—'}</td>
                <td className="px-2 whitespace-nowrap">{gbp(r.amount)}{r.amount == null && r.reference_amount != null ? <span style={{ color: c.textDim }}> (workbook {gbp(r.reference_amount)})</span> : ''}</td>
                <td className="px-2">{r.sage_account || '—'}</td><td className="px-2">{r.direct_debit || '—'}</td>
                <td className="px-2">{r.status.replaceAll('_', ' ')}</td>
                <td className="px-2" style={{ color: 'var(--color-warning-alt)' }}>{r.warnings.join('; ')}</td>
              </tr>))}</tbody>
          </table>
          {data.rows.length === 0 && <div className="p-3 text-xs" style={{ color: c.textDim }}>No maintenance billing falls in {period}.</div>}
        </div>
      </>)}
    </div>
  );
}
