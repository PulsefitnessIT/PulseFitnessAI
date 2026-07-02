/**
 * EngineerQuotes — list + filter + drill-in.
 *
 * Iter 216h129. Light-mode Pulse Fitness brand.
 *
 * Backend: /api/svc/engineer/quotes
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FileText, Plus, Loader2, RefreshCw, ChevronRight, Send,
  CheckCircle2, XCircle, ReceiptPoundSterling as Receipt, ArrowLeft,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { OutboxStatusPill } from '@/utils/engineerStatusBoot';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STATUS_BADGES = {
  draft:     { label: 'Draft',     bg: 'bg-slate-100 text-slate-700 border-slate-200',     icon: FileText },
  sent:      { label: 'Sent',      bg: 'bg-cyan-50 text-cyan-700 border-cyan-200',          icon: Send },
  accepted:  { label: 'Accepted',  bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  declined:  { label: 'Declined',  bg: 'bg-rose-50 text-rose-700 border-rose-200',          icon: XCircle },
  invoiced:  { label: 'Invoiced',  bg: 'bg-teal-50 text-teal-700 border-teal-200',    icon: Receipt },
  expired:   { label: 'Expired',   bg: 'bg-slate-50 text-slate-500 border-slate-200',       icon: XCircle },
};

const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

const FILTERS = [
  { id: 'all',      label: 'All' },
  { id: 'active',   label: 'Draft + Sent' },
  { id: 'draft',    label: 'Draft' },
  { id: 'sent',     label: 'Sent' },
  { id: 'accepted', label: 'Accepted' },
  { id: 'invoiced', label: 'Invoiced' },
  { id: 'declined', label: 'Declined' },
];

export default function EngineerQuotes() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const loc = useLocalization();
  const fmtGBP = (n) => formatMoney(n, loc, { nullDisplay: '—' });
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const filter = params.get('status') || 'active';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/quotes`, {
        ...auth(),
        params: { status: filter === 'all' ? undefined : filter, limit: 200 },
      });
      setQuotes(r.data.quotes || []);
    } catch (e) {
      notify.error('Failed to load quotes', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const totals = useMemo(() => {
    const pipeline = quotes.filter(q => ['draft', 'sent'].includes(q.status))
                            .reduce((acc, q) => acc + (q.total || 0), 0);
    const accepted = quotes.filter(q => q.status === 'accepted')
                            .reduce((acc, q) => acc + (q.total || 0), 0);
    return { pipeline, accepted, count: quotes.length };
  }, [quotes]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-quotes">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              aria-label="Back to home"
              data-testid="engineer-quotes-back"
            >
              <ArrowLeft size={16} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-700">Pulse Fitness</p>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-extrabold text-slate-900">Quotes</h1>
                <OutboxStatusPill />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              className="p-2 rounded-full border border-slate-200 bg-white hover:bg-slate-50"
              aria-label="Refresh"
              data-testid="engineer-quotes-refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              type="button"
              onClick={() => navigate('/svc/engineer/quotes/new')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white text-sm font-bold shadow hover:shadow-md transition-shadow"
              data-testid="engineer-quotes-new-btn"
            >
              <Plus size={16} /> New quote
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-5 pb-24 space-y-4">
        {/* Pipeline summary */}
        <div className="grid grid-cols-3 gap-2" data-testid="engineer-quotes-kpis">
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Pipeline</p>
            <p className="text-base sm:text-lg font-extrabold text-slate-900 mt-1 tabular-nums truncate">{fmtGBP(totals.pipeline)}</p>
            <p className="text-[11px] text-slate-400 mt-1 truncate">Draft + Sent</p>
          </div>
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Accepted</p>
            <p className="text-base sm:text-lg font-extrabold text-emerald-600 mt-1 tabular-nums truncate">{fmtGBP(totals.accepted)}</p>
          </div>
          <div className="min-w-0 bg-white rounded-2xl border border-slate-200 p-3">
            <p className="text-[10px] uppercase tracking-wide font-bold text-slate-500 truncate">Count</p>
            <p className="text-base sm:text-lg font-extrabold text-slate-900 mt-1 tabular-nums truncate">{totals.count}</p>
          </div>
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2" data-testid="engineer-quotes-filters">
          {FILTERS.map(f => (
            <button
              key={f.id}
              type="button"
              onClick={() => setParams({ status: f.id })}
              className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-colors ${
                filter === f.id
                  ? 'bg-cyan-600 text-white border-cyan-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
              }`}
              data-testid={`engineer-quotes-filter-${f.id}`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden" data-testid="engineer-quotes-list">
          {loading ? (
            <div className="text-center py-16 text-slate-400">
              <Loader2 className="animate-spin mx-auto mb-2" size={20} />
              Loading…
            </div>
          ) : quotes.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <FileText size={32} className="mx-auto mb-3 text-slate-300" />
              <p className="font-semibold text-slate-700 mb-1">No quotes here</p>
              <p className="text-sm text-slate-500 mb-4">Click "New quote" to create your first one.</p>
              <button
                type="button"
                onClick={() => navigate('/svc/engineer/quotes/new')}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-600 text-white text-sm font-bold"
                data-testid="engineer-quotes-empty-new-btn"
              >
                <Plus size={14} /> New quote
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {quotes.map(q => {
                const badge = STATUS_BADGES[q.status] || STATUS_BADGES.draft;
                const Ico = badge.icon;
                return (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/svc/engineer/quotes/${q.id}`)}
                    className="w-full text-left px-5 py-4 hover:bg-slate-50 transition-colors flex items-center gap-4"
                    data-testid={`engineer-quote-row-${q.quote_number}`}
                  >
                    <div className="w-12 h-12 rounded-xl bg-cyan-50 flex items-center justify-center flex-shrink-0">
                      <FileText size={20} className="text-cyan-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <p className="text-sm font-bold text-slate-900">{q.quote_number}</p>
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.bg}`}>
                          <Ico size={10} /> {badge.label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 truncate">
                        {q.customer_name || 'Unknown customer'}
                        {q.valid_until ? ` · Valid until ${fmtDate(q.valid_until)}` : ''}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-base font-bold text-slate-900 tabular-nums">{fmtGBP(q.total)}</p>
                      <p className="text-[10px] text-slate-400">Updated {fmtDate(q.updated_at)}</p>
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
