/**
 * Staffing → Staff Expenses (manager/finance).
 * Review submitted staff expense claims, approve / return / mark reimbursed,
 * and one-click export approved claims for a month to CSV for payroll.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Download, CheckCircle2, Undo2, BadgePoundSterling, RotateCw, Receipt, FileSpreadsheet, FileArchive, ChevronDown, ChevronRight, Paperclip, AlertTriangle, Copy, ScanLine, Scale } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function ManagerReceiptThumb({ claimId, receiptId, headers }) {
  const [url, setUrl] = useState('');
  const [bad, setBad] = useState(false);
  useEffect(() => {
    let active = true; let obj;
    axios.get(`${API}/new-starter/expenses/review/${claimId}/receipt/${receiptId}`, { headers, responseType: 'blob' })
      .then((r) => { if (!active) return; obj = URL.createObjectURL(r.data); setUrl(obj); })
      .catch(() => setBad(true));
    return () => { active = false; if (obj) URL.revokeObjectURL(obj); };
  }, [claimId, receiptId, headers]);
  if (bad || !url) return <div className="w-14 h-14 rounded-md border border-slate-200 flex items-center justify-center text-slate-300" title="Receipt"><Paperclip size={16} /></div>;
  return (
    <a href={url} target="_blank" rel="noreferrer" title="Open receipt" data-testid={`exp-review-thumb-${receiptId}`}>
      <img src={url} alt="receipt" onError={() => setBad(true)} className="w-14 h-14 rounded-md object-cover border border-slate-200 hover:ring-2 hover:ring-cyan-400" />
    </a>
  );
}
const STATUS = {
  submitted: { label: 'Awaiting approval', c: '#d97706' },
  approved: { label: 'Approved — to pay', c: '#0891b2' },
  reimbursed: { label: 'Reimbursed', c: '#059669' },
  rejected: { label: 'Returned', c: '#dc2626' },
};
const FLAG_META = {
  missing_receipt: { label: 'Missing receipt', icon: Paperclip, c: '#d97706' },
  duplicate: { label: 'Possible duplicate', icon: Copy, c: '#dc2626' },
  low_scan: { label: 'Low-confidence scan', icon: ScanLine, c: '#b45309' },
  amount_mismatch: { label: 'Amount mismatch', icon: Scale, c: '#be123c' },
  over_threshold: { label: 'Over threshold', icon: BadgePoundSterling, c: '#7c3aed' },
};
function FLAG_META_ICON({ id }) {
  const Icon = (FLAG_META[id] || {}).icon || AlertTriangle;
  return <Icon size={12} />;
}

export default function StaffExpenseReview({ headers }) {
  const [months, setMonths] = useState([]);
  const [month, setMonth] = useState('');
  const [claims, setClaims] = useState([]);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [includeReimbursed, setIncludeReimbursed] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [filter, setFilter] = useState('all');
  const [flagThreshold, setFlagThreshold] = useState(500);

  const dl = (blob, filename, type) => {
    const url = URL.createObjectURL(new Blob([blob], { type }));
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([
        axios.get(`${API}/new-starter/expenses/review/export-months`, { headers }),
        axios.get(`${API}/new-starter/expenses/review/pending`, { headers }),
      ]);
      setMonths(m.data.months || []);
      setClaims(p.data.claims || []);
      if (p.data.flag_threshold != null) setFlagThreshold(p.data.flag_threshold);
      if (!month && m.data.months?.length) setMonth(m.data.months[0].month);
    } catch { setErr('Could not load claims.'); }
  }, [headers, month]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action, path) => {
    setBusy(id + action); setErr('');
    try { await axios.post(`${API}/new-starter/expenses/review/${id}/${path}`, {}, { headers }); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Action failed.'); }
    finally { setBusy(''); }
  };

  const downloadCsv = async () => {
    if (!month) return;
    setBusy('export'); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/expenses/review/export`, {
        headers, params: { month, include_reimbursed: includeReimbursed }, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }));
      const a = document.createElement('a');
      a.href = url; a.download = `expenses-${month.replace(/[^A-Za-z0-9]+/g, '-')}.csv`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { setErr('Export failed.'); }
    finally { setBusy(''); }
  };

  const downloadXlsx = async () => {
    if (!month) return;
    setBusy('export-xlsx'); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/expenses/review/export-xlsx`, {
        headers, params: { month, include_reimbursed: includeReimbursed }, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
      const a = document.createElement('a');
      a.href = url; a.download = `Employee-Expenses-${month.replace(/[^A-Za-z0-9]+/g, '-')}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { setErr('Excel export failed.'); }
    finally { setBusy(''); }
  };

  const downloadMonthReceipts = async () => {
    if (!month) return;
    setBusy('zip-month'); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/expenses/review/receipts.zip`, {
        headers, params: { month, include_reimbursed: includeReimbursed }, responseType: 'blob',
      });
      dl(r.data, `Receipts-${month.replace(/[^A-Za-z0-9]+/g, '-')}.zip`, 'application/zip');
    } catch { setErr('No receipts to download for this month.'); }
    finally { setBusy(''); }
  };

  const downloadClaimReceipts = async (c) => {
    setBusy(c.id + 'zip'); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/expenses/review/${c.id}/receipts.zip`, { headers, responseType: 'blob' });
      dl(r.data, `receipts-${(c.staff_name || '').replace(/[^A-Za-z0-9]+/g, '-')}-${(c.claim_month || '').replace(/[^A-Za-z0-9]+/g, '-')}.zip`, 'application/zip');
    } catch { setErr('No receipts attached to this claim.'); }
    finally { setBusy(''); }
  };

  const downloadClaimXlsx = async (c) => {
    setBusy(c.id + 'xlsx'); setErr('');
    try {
      const r = await axios.get(`${API}/new-starter/expenses/review/${c.id}/export-xlsx`, { headers, responseType: 'blob' });
      dl(r.data, `Expense-${(c.staff_name || '').replace(/[^A-Za-z0-9]+/g, '-')}-${(c.claim_month || '').replace(/[^A-Za-z0-9]+/g, '-')}.xlsx`,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    } catch { setErr('Could not build the Pulse template for this claim.'); }
    finally { setBusy(''); }
  };

  return (
    <div data-testid="staff-expense-review">
      <h2 className="text-lg font-bold mb-1 flex items-center gap-2"><Receipt size={18} className="text-cyan-600" /> Expenses</h2>
      <p className="text-sm text-slate-500 mb-4">Approve staff and engineer claims, and export approved claims for payroll.</p>

      {/* Payroll export bar */}
      <div className="p-4 rounded-xl border border-slate-200 bg-white mb-5" data-testid="exp-payroll-export">
        <p className="font-semibold text-slate-800 mb-2 flex items-center gap-2"><BadgePoundSterling size={16} className="text-cyan-600" /> Payroll export</p>
        <div className="flex flex-wrap items-center gap-3">
          <select value={month} onChange={(e) => setMonth(e.target.value)} data-testid="exp-export-month"
            className="px-3 py-2 rounded-lg text-sm border border-slate-300">
            {months.length === 0 && <option value="">No approved claims yet</option>}
            {months.map((m) => <option key={m.month} value={m.month}>{m.month} — {m.approved} approved{m.reimbursed ? `, ${m.reimbursed} paid` : ''} · {gbp(m.total)}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            <input type="checkbox" checked={includeReimbursed} onChange={(e) => setIncludeReimbursed(e.target.checked)} data-testid="exp-export-incl-paid" />
            Include already-reimbursed
          </label>
          <button onClick={downloadCsv} disabled={!month || busy === 'export'} data-testid="exp-export-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-cyan-600 text-white disabled:opacity-50">
            {busy === 'export' ? <RotateCw size={15} className="animate-spin" /> : <Download size={15} />} Download CSV
          </button>
          <button onClick={downloadXlsx} disabled={!month || busy === 'export-xlsx'} data-testid="exp-export-xlsx-btn"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white disabled:opacity-50">
            {busy === 'export-xlsx' ? <RotateCw size={15} className="animate-spin" /> : <FileSpreadsheet size={15} />} Download Excel (Pulse layout)
          </button>
          <button onClick={downloadMonthReceipts} disabled={!month || busy === 'zip-month' || !(months.find((m) => m.month === month)?.receipts)} data-testid="exp-export-receipts-btn"
            title={month && !(months.find((m) => m.month === month)?.receipts) ? 'No receipts attached for this month' : ''}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-slate-700 text-white disabled:opacity-50">
            {busy === 'zip-month' ? <RotateCw size={15} className="animate-spin" /> : <FileArchive size={15} />} Download all receipts (ZIP)
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">Receipts ZIP gives Accounts a full evidence pack for the month, foldered per employee.</p>
      </div>

      {err && <div className="mb-3 p-3 rounded-lg text-sm bg-red-50 text-red-700" data-testid="exp-review-error">{err}</div>}

      <p className="font-semibold text-slate-800 mb-2">Claims to review</p>

      {/* Needs-attention filter */}
      {claims.length > 0 && (() => {
        const count = (f) => f === 'all' ? claims.length
          : f === 'attention' ? claims.filter((c) => (c.flags || []).length > 0).length
          : claims.filter((c) => (c.flags || []).includes(f)).length;
        const chips = [
          { id: 'all', label: 'All' },
          { id: 'attention', label: 'Needs attention' },
          { id: 'missing_receipt', label: 'Missing receipt' },
          { id: 'duplicate', label: 'Duplicate' },
          { id: 'low_scan', label: 'Low-confidence scan' },
          { id: 'amount_mismatch', label: 'Amount mismatch' },
          { id: 'over_threshold', label: `Over ${gbp(flagThreshold)}` },
        ];
        return (
          <div className="flex flex-wrap gap-2 mb-3" data-testid="exp-review-filters">
            {chips.map((ch) => {
              const n = count(ch.id);
              const active = filter === ch.id;
              return (
                <button key={ch.id} onClick={() => setFilter(ch.id)} data-testid={`exp-filter-${ch.id}`}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border ${active ? 'bg-slate-800 text-white border-slate-800' : 'bg-white text-slate-600 border-slate-300'}`}>
                  {ch.id !== 'all' && ch.id !== 'attention' && <FLAG_META_ICON id={ch.id} />}
                  {ch.label}
                  <span className={`ml-0.5 px-1.5 rounded-full text-[10px] ${active ? 'bg-white/20' : 'bg-slate-100'}`}>{n}</span>
                </button>
              );
            })}
          </div>
        );
      })()}

      {(() => {
        const shown = filter === 'all' ? claims
          : filter === 'attention' ? claims.filter((c) => (c.flags || []).length > 0)
          : claims.filter((c) => (c.flags || []).includes(filter));
        return claims.length === 0 ? (
          <div className="p-6 text-center rounded-xl border border-slate-200 text-slate-500 text-sm" data-testid="exp-review-empty">No claims awaiting review.</div>
        ) : shown.length === 0 ? (
          <div className="p-6 text-center rounded-xl border border-slate-200 text-slate-500 text-sm" data-testid="exp-review-filter-empty">No claims match this filter. 🎉</div>
        ) : (
          <div className="space-y-2">
            {shown.map((c) => {
            const s = STATUS[c.status] || STATUS.submitted;
            const lines = c.lines || [];
            const receiptLines = lines.filter((l) => l.receipt_id);
            const isOpen = !!expanded[c.id];
            return (
              <div key={c.id} className="rounded-xl border border-slate-200 bg-white" data-testid={`exp-review-${c.id}`}>
                <div className="p-4 flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <div className="font-semibold text-slate-800">{c.staff_name} · {c.claim_month}</div>
                    <div className="text-xs text-slate-500">{c.department || '—'} · Mileage {gbp(c.mileage_total)} + Expenses {gbp(c.expenses_total)} = <strong>{gbp(c.grand_total)}</strong></div>
                    <div className="text-xs font-semibold mt-0.5" style={{ color: s.c }}>{s.label}
                      {receiptLines.length > 0 && <span className="ml-2 text-slate-400 font-normal"><Paperclip size={11} className="inline" /> {receiptLines.length} receipt{receiptLines.length > 1 ? 's' : ''}</span>}
                    </div>
                    {(c.flags || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-1.5" data-testid={`exp-review-flags-${c.id}`}>
                        {(c.flags || []).map((f) => {
                          const meta = FLAG_META[f] || { label: f, icon: AlertTriangle, c: '#64748b' };
                          const Icon = meta.icon;
                          return (
                            <span key={f} data-testid={`exp-flag-${f}-${c.id}`}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold"
                              style={{ background: `${meta.c}14`, color: meta.c }}>
                              <Icon size={10} /> {meta.label}
                            </span>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
                    <button onClick={() => setExpanded((e) => ({ ...e, [c.id]: !e[c.id] }))} data-testid={`exp-review-toggle-${c.id}`}
                      className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 flex-1 sm:flex-none">
                      {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {isOpen ? 'Hide' : 'View'} detail
                    </button>
                    {c.status === 'submitted' && (
                      <>
                        <button onClick={() => act(c.id, 'approve', 'approve')} disabled={busy} data-testid={`exp-approve-${c.id}`}
                          className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-cyan-600 text-white disabled:opacity-50 flex-1 sm:flex-none">
                          <CheckCircle2 size={14} /> Approve
                        </button>
                        <button onClick={() => act(c.id, 'reject', 'reject')} disabled={busy} data-testid={`exp-reject-${c.id}`}
                          className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 disabled:opacity-50 flex-1 sm:flex-none">
                          <Undo2 size={14} /> Return
                        </button>
                      </>
                    )}
                    {c.status === 'approved' && (
                      <button onClick={() => act(c.id, 'reimburse', 'reimburse')} disabled={busy} data-testid={`exp-reimburse-${c.id}`}
                        className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white disabled:opacity-50 flex-1 sm:flex-none">
                        <BadgePoundSterling size={14} /> Mark reimbursed
                      </button>
                    )}
                  </div>
                </div>
                {isOpen && (
                  <div className="px-4 pb-4 border-t border-slate-100 pt-3" data-testid={`exp-review-detail-${c.id}`}>
                    <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                      <p className="text-xs font-semibold text-slate-600">Expense lines & receipts</p>
                      <div className="flex items-center gap-2">
                        <button onClick={() => downloadClaimXlsx(c)} disabled={busy === c.id + 'xlsx'} data-testid={`exp-review-xlsx-${c.id}`}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white disabled:opacity-50">
                          {busy === c.id + 'xlsx' ? <RotateCw size={12} className="animate-spin" /> : <FileSpreadsheet size={12} />} Pulse template (.xlsx)
                        </button>
                        {receiptLines.length > 0 && (
                          <button onClick={() => downloadClaimReceipts(c)} disabled={busy === c.id + 'zip'} data-testid={`exp-review-receipts-${c.id}`}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 text-slate-700 disabled:opacity-50">
                            {busy === c.id + 'zip' ? <RotateCw size={12} className="animate-spin" /> : <FileArchive size={12} />} Receipts (ZIP)
                          </button>
                        )}
                      </div>
                    </div>
                    {lines.length === 0 ? (
                      <p className="text-xs text-slate-400">No itemised expenses (mileage only).</p>
                    ) : (
                      <div className="space-y-2">
                        {lines.map((l, i) => (
                          <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-slate-50" data-testid={`exp-review-line-${c.id}-${i}`}>
                            {l.receipt_id
                              ? <ManagerReceiptThumb claimId={c.id} receiptId={l.receipt_id} headers={headers} />
                              : <div className="w-14 h-14 rounded-md border border-dashed border-slate-200 flex items-center justify-center text-slate-300 text-[10px] text-center">No receipt</div>}
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium text-slate-800 truncate">{l.description || '—'}</div>
                              <div className="text-xs text-slate-500">{l.date || 'no date'} · {l.nominal || '—'}</div>
                            </div>
                            <div className="text-sm font-semibold text-slate-800 whitespace-nowrap">{gbp(l.total)}{l.no_vat ? '' : ` (VAT ${gbp(l.vat)})`}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          </div>
        );
      })()}
    </div>
  );
}
