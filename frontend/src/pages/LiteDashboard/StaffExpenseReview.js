/**
 * Staffing → Staff Expenses (manager/finance).
 * Review submitted staff expense claims, approve / return / mark reimbursed,
 * and one-click export approved claims for a month to CSV for payroll.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Download, CheckCircle2, Undo2, BadgePoundSterling, RotateCw, Receipt } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const gbp = (v) => '£' + Number(v || 0).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const STATUS = {
  submitted: { label: 'Awaiting approval', c: '#d97706' },
  approved: { label: 'Approved — to pay', c: '#0891b2' },
  reimbursed: { label: 'Reimbursed', c: '#059669' },
  rejected: { label: 'Returned', c: '#dc2626' },
};

export default function StaffExpenseReview({ headers }) {
  const [months, setMonths] = useState([]);
  const [month, setMonth] = useState('');
  const [claims, setClaims] = useState([]);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const [includeReimbursed, setIncludeReimbursed] = useState(false);

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([
        axios.get(`${API}/new-starter/expenses/review/export-months`, { headers }),
        axios.get(`${API}/new-starter/expenses/review/pending`, { headers }),
      ]);
      setMonths(m.data.months || []);
      setClaims(p.data.claims || []);
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

  return (
    <div data-testid="staff-expense-review">
      <h2 className="text-lg font-bold mb-1 flex items-center gap-2"><Receipt size={18} className="text-cyan-600" /> Staff Expenses</h2>
      <p className="text-sm text-slate-500 mb-4">Approve staff claims and export approved claims for payroll.</p>

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
        </div>
      </div>

      {err && <div className="mb-3 p-3 rounded-lg text-sm bg-red-50 text-red-700" data-testid="exp-review-error">{err}</div>}

      <p className="font-semibold text-slate-800 mb-2">Claims to review</p>
      {claims.length === 0 ? (
        <div className="p-6 text-center rounded-xl border border-slate-200 text-slate-500 text-sm" data-testid="exp-review-empty">No claims awaiting review.</div>
      ) : (
        <div className="space-y-2">
          {claims.map((c) => {
            const s = STATUS[c.status] || STATUS.submitted;
            return (
              <div key={c.id} className="p-4 rounded-xl border border-slate-200 bg-white flex items-center justify-between gap-3 flex-wrap" data-testid={`exp-review-${c.id}`}>
                <div>
                  <div className="font-semibold text-slate-800">{c.staff_name} · {c.claim_month}</div>
                  <div className="text-xs text-slate-500">{c.department || '—'} · Mileage {gbp(c.mileage_total)} + Expenses {gbp(c.expenses_total)} = <strong>{gbp(c.grand_total)}</strong></div>
                  <div className="text-xs font-semibold mt-0.5" style={{ color: s.c }}>{s.label}</div>
                </div>
                <div className="flex items-center gap-2">
                  {c.status === 'submitted' && (
                    <>
                      <button onClick={() => act(c.id, 'approve', 'approve')} disabled={busy} data-testid={`exp-approve-${c.id}`}
                        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-cyan-600 text-white disabled:opacity-50">
                        <CheckCircle2 size={14} /> Approve
                      </button>
                      <button onClick={() => act(c.id, 'reject', 'reject')} disabled={busy} data-testid={`exp-reject-${c.id}`}
                        className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 disabled:opacity-50">
                        <Undo2 size={14} /> Return
                      </button>
                    </>
                  )}
                  {c.status === 'approved' && (
                    <button onClick={() => act(c.id, 'reimburse', 'reimburse')} disabled={busy} data-testid={`exp-reimburse-${c.id}`}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white disabled:opacity-50">
                      <BadgePoundSterling size={14} /> Mark reimbursed
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
