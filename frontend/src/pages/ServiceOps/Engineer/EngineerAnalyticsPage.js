/**
 * EngineerAnalyticsPage — Iter 216h257
 *
 * Filtered analytics surface for field engineers. Consumes
 * GET /api/svc/engineer/analytics?range={7d|30d|90d|ytd|all} and shows:
 *   • Headline KPIs (jobs total / completed / earnings / avg quote value)
 *   • Status breakdown for cases (clickable → drills into list view)
 *   • Status breakdown for quotes
 *
 * Mobile-first since this is the Engineer PWA.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, Loader2, TrendingUp, ClipboardList, FileText, PoundSterling } from 'lucide-react';
import { notify } from '@/components/notifications';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

const RANGES = [
  { id: '7d',  label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: '90d', label: '90 days' },
  { id: 'ytd', label: 'Year to date' },
  { id: 'all', label: 'All time' },
];

const fmtGBP = (n) => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(n || 0);

export default function EngineerAnalyticsPage() {
  const navigate = useNavigate();
  const [range, setRange] = useState('30d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/analytics`, { ...auth(), params: { range } });
      setData(r.data);
    } catch (err) {
      notify.error('Failed to load analytics', err?.response?.data?.detail || err?.message);
    } finally { setLoading(false); }
  }, [range]);
  useEffect(() => { load(); }, [load]);

  const cases = data?.cases || { total: 0, completed: 0, by_status: {} };
  const quotes = data?.quotes || { total: 0, by_status: {}, average_value: 0, earnings: 0 };

  const caseRows = useMemo(() => Object.entries(cases.by_status || {}).sort((a, b) => b[1] - a[1]), [cases]);
  const quoteRows = useMemo(() => Object.entries(quotes.by_status || {}).sort((a, b) => b[1] - a[1]), [quotes]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-analytics-page">
      <header className="sticky top-0 z-20 bg-white border-b border-slate-200">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
          <button
            onClick={() => navigate('/svc/engineer')}
            className="inline-flex items-center gap-1 text-sm font-bold text-slate-600 hover:text-slate-900"
            data-testid="analytics-back"
          >
            <ArrowLeft size={14} /> Back
          </button>
          <h1 className="text-base font-bold text-slate-900">Analytics</h1>
          <div className="w-12" aria-hidden />
        </div>
      </header>

      <main className="max-w-2xl mx-auto p-4 space-y-4">
        {/* Range chips */}
        <div className="bg-white rounded-2xl border border-slate-200 p-2 overflow-x-auto" data-testid="analytics-range">
          <div className="flex gap-1.5 whitespace-nowrap">
            {RANGES.map((r) => {
              const on = range === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => setRange(r.id)}
                  className={`px-3 py-2 rounded-lg text-xs font-bold transition ${
                    on ? 'bg-gradient-to-br from-[#1d4ed8] to-[#6366f1] text-white' : 'text-slate-600 hover:bg-slate-50'
                  }`}
                  data-testid={`analytics-range-${r.id}`}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-10"><Loader2 className="animate-spin text-blue-500" /></div>
        ) : (
          <>
            {/* Headline KPIs */}
            <div className="grid grid-cols-2 gap-3">
              <KPI icon={ClipboardList} label="Jobs total"      value={cases.total}     onClick={() => navigate('/svc/engineer/jobs')} testid="analytics-kpi-jobs" />
              <KPI icon={ClipboardList} label="Jobs completed"  value={cases.completed} onClick={() => navigate('/svc/engineer/jobs?status=closed')} testid="analytics-kpi-completed" />
              <KPI icon={PoundSterling} label="Earnings"        value={fmtGBP(quotes.earnings)} onClick={() => navigate('/svc/engineer/invoices')} testid="analytics-kpi-earnings" />
              <KPI icon={TrendingUp}    label="Avg quote value" value={fmtGBP(quotes.average_value)} testid="analytics-kpi-avg" />
            </div>

            {/* Cases by status */}
            <SectionCard title="Jobs by status" icon={ClipboardList} count={caseRows.length}>
              {caseRows.length === 0 ? <Empty label="No jobs in this range." />
                : caseRows.map(([k, n]) => (
                  <button
                    key={k}
                    onClick={() => navigate(`/svc/engineer/jobs?status=${encodeURIComponent(k)}`)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-50 text-sm"
                    data-testid={`analytics-case-${k}`}
                  >
                    <span className="font-medium text-slate-700 capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className="font-bold text-slate-900 tabular-nums">{n}</span>
                  </button>
                ))}
            </SectionCard>

            {/* Quotes by status */}
            <SectionCard title="Quotes by status" icon={FileText} count={quoteRows.length}>
              {quoteRows.length === 0 ? <Empty label="No quotes in this range." />
                : quoteRows.map(([k, n]) => (
                  <button
                    key={k}
                    onClick={() => navigate(`/svc/engineer/quotes?status=${encodeURIComponent(k)}`)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-slate-50 text-sm"
                    data-testid={`analytics-quote-${k}`}
                  >
                    <span className="font-medium text-slate-700 capitalize">{k}</span>
                    <span className="font-bold text-slate-900 tabular-nums">{n}</span>
                  </button>
                ))}
            </SectionCard>

            <p className="text-[11px] text-center text-slate-400 pt-2 pb-6">
              {data?.range_start ? `Since ${data.range_start.slice(0, 10)}` : 'All-time totals'}
            </p>
          </>
        )}
      </main>
    </div>
  );
}

function KPI({ icon: Icon, label, value, onClick, testid }) {
  const inner = (
    <div className="flex items-start gap-2.5 p-3.5">
      <Icon size={18} className="text-slate-500 mt-0.5" />
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wider font-bold text-slate-500">{label}</p>
        <p className="text-xl font-extrabold text-slate-900 tabular-nums mt-0.5 truncate">{value}</p>
      </div>
    </div>
  );
  return onClick ? (
    <button onClick={onClick} className="bg-white rounded-2xl border border-slate-200 text-left hover:border-blue-300 transition-colors" data-testid={testid}>{inner}</button>
  ) : (
    <div className="bg-white rounded-2xl border border-slate-200" data-testid={testid}>{inner}</div>
  );
}

function SectionCard({ title, icon: Icon, count, children }) {
  return (
    <section className="bg-white rounded-2xl border border-slate-200">
      <header className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <h2 className="text-sm font-bold text-slate-900 inline-flex items-center gap-2">
          <Icon size={14} className="text-slate-500" /> {title}
        </h2>
        <span className="text-[10px] uppercase tracking-wide font-bold text-slate-400">{count} {count === 1 ? 'group' : 'groups'}</span>
      </header>
      <div className="p-2 space-y-1">{children}</div>
    </section>
  );
}

function Empty({ label }) {
  return <p className="text-center text-xs text-slate-400 py-4">{label}</p>;
}
