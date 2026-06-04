/**
 * BillingPage — iter 215dt (Phase 6).
 *
 * Operator quoting & billing console at /service-ops/billing.
 *
 * Filter bar: ready | quoted | invoiced | all
 * Each row → "Open quote" button → QuoteEditor drawer.
 * Editor: header (case + customer), line table (kind/qty/unit/desc),
 *  auto-fill button, totals (subtotal/discount/VAT/gross), Approve & Finalise.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  FileText, Wand2, RefreshCw, Plus, Trash2, X, Save,
  CheckCircle, Send, Sparkles, Loader2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';
import { useLocalization, formatMoneySync, getCachedLocalization } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

function gbp(n) { return formatMoneySync(n); }

export default function BillingPage() {
  useLocalization();  // warm currency cache
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState('ready');
  const [openCase, setOpenCase] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/billing`, { ...auth(), params: { status: filter } });
      setRows(r.data.rows || []);
    } catch (e) { notify.error('Failed to load billing queue', e?.response?.data?.detail || e.message); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <ServiceOpsShell
      icon={FileText}
      title="Quoting & billing"
      subtitle="Build a quote from labour and parts, approve it, and push the line-priced draft straight into the Sage 200 invoice outbox."
      actions={(
        <>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="svc-select svc-select-sm" style={{ width: 'auto' }} data-testid="billing-filter">
            <option value="ready">Ready to quote</option>
            <option value="quoted">Quoted (awaiting finalise)</option>
            <option value="invoiced">Invoiced</option>
            <option value="all">All</option>
          </select>
          <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="billing-refresh">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </>
      )}
      active="billing"
      pageTestId="billing-page"
    >
      <div className="svc-table-wrap">
        <table className="svc-table">
          <thead>
            <tr>
              <th>Case</th>
              <th>Title</th>
              <th>Customer</th>
              <th>State</th>
              <th className="num">Quote total</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="6"><div className="svc-empty"><span className="svc-spinner" /> Loading…</div></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan="6"><div className="svc-empty"><FileText size={20} /><div>No cases in this state.</div></div></td></tr>
            ) : rows.map((r) => {
              const stateTone = r.billing_state === 'invoiced' ? 'good' : r.billing_state === 'quoted' ? 'info' : 'warn';
              return (
                <tr key={r.id} data-testid={`billing-row-${r.reference}`}>
                  <td className="font-bold tabular-nums">{r.reference}</td>
                  <td className="truncate" style={{ maxWidth: '18rem' }}>{r.title}</td>
                  <td className="text-xs svc-muted">{r.customer_name || '—'}</td>
                  <td><span className={`svc-pill svc-pill--${stateTone}`}>{r.billing_state}</span></td>
                  <td className="num">{r.quote ? gbp(r.quote.total) : '—'}</td>
                  <td className="num">
                    <button type="button" onClick={() => setOpenCase(r)} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid={`billing-open-${r.reference}`}>
                      <FileText size={10} /> Open quote
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {openCase ? (
        <QuoteEditor
          caseRow={openCase}
          onClose={() => setOpenCase(null)}
          onChanged={load}
        />
      ) : null}
    </ServiceOpsShell>
  );
}

// ── Quote editor drawer ──────────────────────────────────────────
function QuoteEditor({ caseRow, onClose, onChanged }) {
  const [quote, setQuote] = useState(caseRow.quote || null);
  const [lines, setLines] = useState((caseRow.quote?.lines) || []);
  const [vatRate, setVatRate] = useState(caseRow.quote?.vat_rate ?? 0.20);
  const [discountPct, setDiscountPct] = useState(caseRow.quote?.discount_pct ?? 0);
  const [notes, setNotes] = useState(caseRow.quote?.notes || '');
  const [busy, setBusy] = useState('');

  const totals = useMemo(() => {
    const subtotal = +lines.reduce((sum, l) => sum + (Number(l.qty) || 0) * (Number(l.unit_amount) || 0), 0).toFixed(2);
    const discount = +(subtotal * (discountPct / 100)).toFixed(2);
    const net = Math.max(0, +(subtotal - discount).toFixed(2));
    const vat = +(net * vatRate).toFixed(2);
    const gross = +(net + vat).toFixed(2);
    return { subtotal, discount, net, vat, gross };
  }, [lines, vatRate, discountPct]);

  const isLocked = quote && (quote.status === 'approved' || quote.status === 'invoiced');

  const autoFill = async () => {
    setBusy('autofill');
    try {
      const r = await axios.post(`${API}/svc/billing/${caseRow.id}/quote/auto-fill`, {}, auth());
      const proposed = r.data?.proposed_lines || [];
      if (proposed.length === 0) {
        notify.info('Nothing to auto-fill', 'No chargeable time entries or parts movements yet — add lines manually.');
      } else {
        // Merge: keep any existing manual lines, append proposed lines that
        // we don't already have (matched by part_sku or kind+description).
        const seen = new Set(lines.map((l) => `${l.kind}|${l.part_sku || ''}|${l.description}`));
        const merged = [...lines];
        for (const p of proposed) {
          const key = `${p.kind}|${p.part_sku || ''}|${p.description}`;
          if (!seen.has(key)) { merged.push(p); seen.add(key); }
        }
        setLines(merged);
        notify.success('Auto-fill applied', `${proposed.length} line(s) added`);
      }
    } catch (e) {
      notify.error('Auto-fill failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  const setLine = (i, k, v) => {
    const next = [...lines];
    next[i] = { ...next[i], [k]: v };
    setLines(next);
  };
  const addLine = (kind = 'labour') => {
    setLines([...lines, { kind, qty: kind === 'labour' ? 1 : 1, unit_amount: 0, description: '', tax_code: 'T1' }]);
  };
  const removeLine = (i) => { const next = [...lines]; next.splice(i, 1); setLines(next); };

  const saveDraft = async () => {
    setBusy('save');
    try {
      const r = await axios.put(`${API}/svc/billing/${caseRow.id}/quote`,
        { lines, vat_rate: vatRate, discount_pct: discountPct, notes }, auth());
      setQuote(r.data);
      setLines(r.data.lines || []);
      notify.success(quote ? 'Quote updated' : 'Draft quote saved', r.data.reference);
      onChanged?.();
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  const approve = async () => {
    setBusy('approve');
    try {
      const r = await axios.post(`${API}/svc/billing/${caseRow.id}/quote/approve`, {}, auth());
      setQuote(r.data);
      notify.success('Quote approved');
      onChanged?.();
    } catch (e) {
      notify.error('Approve failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  const finalise = async () => {
    setBusy('finalise');
    try {
      const r = await axios.post(`${API}/svc/billing/${caseRow.id}/invoice/finalise`, {}, auth());
      if (r.data?.ok) {
        notify.success('Invoice queued for Sage', `Outbox status: ${r.data.outbox?.status || 'ready'}`);
        setQuote(r.data.quote);
        onChanged?.();
        onClose?.();
      }
    } catch (e) {
      notify.error('Finalise failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  const voidQuote = async () => {
    if (!window.confirm('Void this quote? You can create a new draft after.')) return;
    setBusy('void');
    try {
      await axios.post(`${API}/svc/billing/${caseRow.id}/quote/void`, {}, auth());
      setQuote(null);
      setLines([]);
      notify.success('Quote voided');
      onChanged?.();
    } catch (e) {
      notify.error('Void failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(''); }
  };

  return (
    <div className="fixed inset-0 z-50 flex" style={{ background: 'rgba(0,0,0,0.45)' }} onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} data-testid="quote-editor">
      <div className="flex-1" />
      <aside className="w-full max-w-3xl h-full overflow-hidden flex flex-col shadow-2xl border-l" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <header className="px-5 py-4 border-b flex items-start justify-between gap-3" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: 'var(--color-brand-blue,#1d4ed8)' }}>{caseRow.reference} · {quote?.reference || 'No quote yet'}</p>
            <h2 className="text-lg font-extrabold truncate" data-testid="quote-title">{caseRow.title}</h2>
            <p className="text-xs opacity-70">{caseRow.customer_name || '—'}{caseRow.site_name ? ` · ${caseRow.site_name}` : ''}</p>
            {quote ? (
              <span className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider" style={{
                background: quote.status === 'invoiced' ? '#dcfce7' : quote.status === 'approved' ? '#dbeafe' : '#f3f4f6',
                color: quote.status === 'invoiced' ? '#166534' : quote.status === 'approved' ? '#1d4ed8' : '#374151',
              }} data-testid="quote-status-pill">{quote.status} · v{quote.version}</span>
            ) : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" data-testid="quote-close" className="p-1.5 rounded hover:bg-black/10"><X size={16} /></button>
        </header>

        <div className="flex-1 overflow-y-auto p-5 space-y-3" data-testid="quote-body">
          {!isLocked ? (
            <button type="button" onClick={autoFill} disabled={busy === 'autofill'} className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-bold text-white disabled:opacity-60" style={{ background: 'var(--color-brand-blue,#1d4ed8)' }} data-testid="quote-autofill">
              {busy === 'autofill' ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
              Auto-fill from labour &amp; parts
            </button>
          ) : null}

          <div className="rounded-md border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
            <table className="w-full text-sm">
              <thead style={{ background: 'var(--theme-surface)' }}>
                <tr className="text-left text-[10px] uppercase tracking-wider opacity-70">
                  <th className="px-2 py-1.5">Kind</th>
                  <th className="px-2 py-1.5">Description</th>
                  <th className="px-2 py-1.5 text-right">Qty</th>
                  <th className="px-2 py-1.5 text-right">Unit {getCachedLocalization().currency_symbol}</th>
                  <th className="px-2 py-1.5 text-right">Line {getCachedLocalization().currency_symbol}</th>
                  <th className="px-2 py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {lines.length === 0 ? (
                  <tr><td colSpan="6" className="px-3 py-6 text-center opacity-60 text-xs">No lines yet — click Auto-fill, or add a line below.</td></tr>
                ) : lines.map((l, i) => {
                  const total = (Number(l.qty) || 0) * (Number(l.unit_amount) || 0);
                  return (
                    <tr key={l.id || i} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`quote-line-${i}`}>
                      <td className="px-2 py-1">
                        <select value={l.kind} disabled={isLocked} onChange={(e) => setLine(i, 'kind', e.target.value)} className="ip" data-testid={`quote-line-kind-${i}`}>
                          <option value="labour">Labour</option>
                          <option value="part">Part</option>
                          <option value="adjustment">Adjustment</option>
                        </select>
                      </td>
                      <td className="px-2 py-1">
                        <input value={l.description || ''} disabled={isLocked} onChange={(e) => setLine(i, 'description', e.target.value)} className="ip" data-testid={`quote-line-desc-${i}`} />
                        {l.part_sku ? <span className="block text-[10px] opacity-60 mt-0.5">SKU {l.part_sku}</span> : null}
                      </td>
                      <td className="px-2 py-1 text-right">
                        <input type="number" step="0.01" value={l.qty} disabled={isLocked} onChange={(e) => setLine(i, 'qty', Number(e.target.value))} className="ip text-right tabular-nums" data-testid={`quote-line-qty-${i}`} />
                      </td>
                      <td className="px-2 py-1 text-right">
                        <input type="number" step="0.01" value={l.unit_amount} disabled={isLocked} onChange={(e) => setLine(i, 'unit_amount', Number(e.target.value))} className="ip text-right tabular-nums" data-testid={`quote-line-unit-${i}`} />
                      </td>
                      <td className="px-2 py-1 text-right tabular-nums" data-testid={`quote-line-total-${i}`}>{gbp(total)}</td>
                      <td className="px-2 py-1 text-right">
                        {!isLocked ? <button type="button" aria-label="Remove" onClick={() => removeLine(i)} className="opacity-60 hover:opacity-100" data-testid={`quote-line-remove-${i}`}><Trash2 size={11} /></button> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {!isLocked ? (
            <div className="flex gap-1.5">
              <button type="button" onClick={() => addLine('labour')} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="quote-add-labour"><Plus size={10} /> Labour</button>
              <button type="button" onClick={() => addLine('part')} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="quote-add-part"><Plus size={10} /> Part</button>
              <button type="button" onClick={() => addLine('adjustment')} className="px-2 py-1 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="quote-add-adjustment"><Plus size={10} /> Adjustment</button>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">VAT rate</span>
              <input type="number" step="0.01" value={vatRate} disabled={isLocked} onChange={(e) => setVatRate(Number(e.target.value))} className="ip mt-1 tabular-nums" data-testid="quote-vat" />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">Discount %</span>
              <input type="number" step="0.5" value={discountPct} disabled={isLocked} onChange={(e) => setDiscountPct(Number(e.target.value))} className="ip mt-1 tabular-nums" data-testid="quote-discount" />
            </label>
          </div>

          <div className="rounded-md border p-3 space-y-1" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="quote-totals">
            <div className="flex justify-between text-xs"><span className="opacity-70">Subtotal</span><span className="tabular-nums" data-testid="quote-subtotal">{gbp(totals.subtotal)}</span></div>
            <div className="flex justify-between text-xs"><span className="opacity-70">Discount ({discountPct}%)</span><span className="tabular-nums">−{gbp(totals.discount)}</span></div>
            <div className="flex justify-between text-xs"><span className="opacity-70">Net</span><span className="tabular-nums" data-testid="quote-net">{gbp(totals.net)}</span></div>
            <div className="flex justify-between text-xs"><span className="opacity-70">VAT ({(vatRate * 100).toFixed(0)}%)</span><span className="tabular-nums">{gbp(totals.vat)}</span></div>
            <div className="flex justify-between text-base font-extrabold pt-1 border-t" style={{ borderColor: 'var(--theme-border)' }}><span>Gross</span><span className="tabular-nums" data-testid="quote-gross">{gbp(totals.gross)}</span></div>
          </div>

          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">Operator notes (internal)</span>
            <textarea value={notes} disabled={isLocked} onChange={(e) => setNotes(e.target.value)} rows={2} className="ip mt-1" data-testid="quote-notes" />
          </label>
        </div>

        <footer className="border-t px-5 py-3 flex flex-wrap gap-2 justify-end" style={{ borderColor: 'var(--theme-border)' }}>
          {quote && quote.status === 'approved' ? (
            <button type="button" onClick={voidQuote} disabled={busy === 'void'} className="px-3 py-1.5 rounded-md border text-xs font-bold disabled:opacity-60" style={{ borderColor: 'var(--theme-border)', color: '#b91c1c' }} data-testid="quote-void">Void quote</button>
          ) : null}
          {quote ? (
            <button
              type="button"
              onClick={async () => {
                const token = localStorage.getItem('token');
                try {
                  const resp = await fetch(`${API}/svc/billing/${caseRow.id}/quote.pdf`, {
                    headers: { Authorization: `Bearer ${token}` },
                  });
                  if (!resp.ok) throw new Error('Download failed');
                  const blob = await resp.blob();
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `quote-${caseRow.reference}.pdf`;
                  document.body.appendChild(a);
                  a.click();
                  a.remove();
                  URL.revokeObjectURL(url);
                } catch (e) {
                  notify.error('PDF download failed');
                }
              }}
              className="px-3 py-1.5 rounded-md border text-xs font-bold inline-flex items-center gap-1"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="quote-download-pdf"
            >
              <FileText size={11} /> Customer PDF
            </button>
          ) : null}
          {!isLocked ? (
            <>
              <button type="button" onClick={saveDraft} disabled={busy === 'save'} className="px-3 py-1.5 rounded-md border text-xs font-bold inline-flex items-center gap-1 disabled:opacity-60" style={{ borderColor: 'var(--theme-border)' }} data-testid="quote-save">
                <Save size={11} /> {busy === 'save' ? 'Saving…' : quote ? 'Update draft' : 'Save draft'}
              </button>
              {quote ? (
                <button type="button" onClick={approve} disabled={busy === 'approve'} className="px-3 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center gap-1 disabled:opacity-60" style={{ background: 'var(--color-brand-blue,#1d4ed8)' }} data-testid="quote-approve">
                  <CheckCircle size={11} /> {busy === 'approve' ? 'Approving…' : 'Approve quote'}
                </button>
              ) : null}
            </>
          ) : null}
          {quote && quote.status === 'approved' ? (
            <button type="button" onClick={finalise} disabled={busy === 'finalise'} className="px-3 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center gap-1 disabled:opacity-60" style={{ background: 'var(--color-success-green,#10b981)' }} data-testid="quote-finalise">
              <Send size={11} /> {busy === 'finalise' ? 'Sending…' : 'Finalise → Sage'}
            </button>
          ) : null}
          {quote && quote.status === 'invoiced' ? (
            <span className="text-xs font-bold inline-flex items-center gap-1" style={{ color: '#10b981' }} data-testid="quote-invoiced-badge">
              <Sparkles size={11} /> Invoice queued — workers will dispatch to Sage
            </span>
          ) : null}
        </footer>
      </aside>

      <style>{`.ip{width:100%;padding:6px 8px;border:1px solid var(--theme-border);border-radius:6px;font-size:13px;background:transparent}.ip:disabled{opacity:.6}`}</style>
    </div>
  );
}
