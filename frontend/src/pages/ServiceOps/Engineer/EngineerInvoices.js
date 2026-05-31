/**
 * EngineerInvoices — list + filter + drill-in.
 *
 * Iter 216h130. Light-mode GymAxis brand.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ReceiptPoundSterling as Receipt, Plus, Loader2, RefreshCw, ChevronRight, Send,
  CheckCircle2, XCircle, ArrowLeft, FileText, AlertTriangle,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STATUS_BADGES = {
  draft:    { label: 'Draft',    bg: 'bg-slate-100 text-slate-700 border-slate-200',     icon: FileText },
  sent:     { label: 'Sent',     bg: 'bg-blue-50 text-blue-700 border-blue-200',          icon: Send },
  paid:     { label: 'Paid',     bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  overdue:  { label: 'Overdue',  bg: 'bg-amber-50 text-amber-700 border-amber-200',       icon: AlertTriangle },
  void:     { label: 'Void',     bg: 'bg-rose-50 text-rose-700 border-rose-200',          icon: XCircle },
};

const FILTERS = [
  { id: 'all',     label: 'All' },
  { id: 'unpaid',  label: 'Unpaid' },
  { id: 'draft',   label: 'Draft' },
  { id: 'sent',    label: 'Sent' },
  { id: 'paid',    label: 'Paid' },
  { id: 'overdue', label: 'Overdue' },
  { id: 'void',    label: 'Void' },
];

const fmtGBP = (n) => n == null ? '—' : `£${Number(n).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

export default function EngineerInvoices() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const filter = params.get('status') || 'unpaid';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/invoices`, {
        ...auth(),
        params: { status: filter === 'all' ? undefined : filter, limit: 200 },
      });
      setInvoices(r.data.invoices || []);
    } catch (e) {
      notify.error('Failed to load invoices', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const totals = useMemo(() => {
    const outstanding = invoices.filter(i => ['draft', 'sent', 'overdue'].includes(i.status))
                                 .reduce((a, i) => a + (i.total || 0), 0);
    const paid = invoices.filter(i => i.status === 'paid')
                          .reduce((a, i) => a + (i.total || 0), 0);
    return { outstanding, paid, count: invoices.length };
  }, [invoices]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-invoices">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button onClick={() => navigate('/svc/engineer')} className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50" data-testid="engineer-invoices-back">
              <ArrowLeft size={16} />
            </button>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">GymAxis</p>
              <h1 className="text-xl font-extrabold text-slate-900">Invoices</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50" aria-label="Refresh" data-testid="engineer-invoices-refresh">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button onClick={() => navigate('/svc/engineer/invoices/new')} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white text-sm font-bold shadow" data-testid="engineer-invoices-new-btn">
              <Plus size={16} /> New invoice
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-24 space-y-4">
        <div className="grid grid-cols-3 gap-2" data-testid="engineer-invoices-kpis">
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Outstanding</p>
            <p className="text-base sm:text-lg font-extrabold text-amber-600 mt-1 tabular-nums truncate">{fmtGBP(totals.outstanding)}</p>
          </div>
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Paid</p>
            <p className="text-base sm:text-lg font-extrabold text-emerald-600 mt-1 tabular-nums truncate">{fmtGBP(totals.paid)}</p>
          </div>
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Count</p>
            <p className="text-base sm:text-lg font-extrabold text-slate-900 mt-1 tabular-nums truncate">{totals.count}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2" data-testid="engineer-invoices-filters">
          {FILTERS.map(f => (
            <button
              key={f.id}
              onClick={() => setParams({ status: f.id })}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
                filter === f.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200'
              }`}
              data-testid={`engineer-invoices-filter-${f.id}`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden" data-testid="engineer-invoices-list">
          {loading ? (
            <div className="text-center py-16 text-slate-400">
              <Loader2 className="animate-spin mx-auto mb-2" size={20} /> Loading…
            </div>
          ) : invoices.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <Receipt size={32} className="mx-auto mb-3 text-slate-300" />
              <p className="font-semibold text-slate-700 mb-1">No invoices</p>
              <p className="text-sm text-slate-500 mb-4">Click "New invoice" to start.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {invoices.map(i => {
                const badge = STATUS_BADGES[i.status] || STATUS_BADGES.draft;
                const Ico = badge.icon;
                return (
                  <button
                    key={i.id}
                    onClick={() => navigate(`/svc/engineer/invoices/${i.id}`)}
                    className="w-full text-left px-5 py-4 hover:bg-slate-50 flex items-center gap-4"
                    data-testid={`engineer-invoice-row-${i.invoice_number}`}
                  >
                    <div className="w-12 h-12 rounded-xl bg-emerald-50 flex items-center justify-center flex-shrink-0">
                      <Receipt size={20} className="text-emerald-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <p className="text-sm font-bold text-slate-900">{i.invoice_number}</p>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.bg}`}>
                          <Ico size={10} /> {badge.label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 truncate">
                        {i.customer_name || 'Unknown customer'}
                        {i.due_date ? ` · Due ${fmtDate(i.due_date)}` : ''}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-base font-bold text-slate-900 tabular-nums">{fmtGBP(i.total)}</p>
                      <p className="text-[10px] text-slate-400">Issued {fmtDate(i.issue_date)}</p>
                    </div>
                    <ChevronRight size={18} className="text-slate-300 flex-shrink-0" />
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
