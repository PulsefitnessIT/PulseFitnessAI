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
import { ArrowLeft, Loader2, TrendingUp, ClipboardList, FileText, PoundSterling, Wrench, Package, Timer, CheckCircle2, MapPin, Download, Mail } from 'lucide-react';
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

const fmtDuration = (mins) => {
  if (mins == null) return '—';
  if (mins < 60) return `${Math.round(mins)}m`;
  const h = mins / 60;
  if (h < 48) return `${h.toFixed(h < 10 ? 1 : 0)}h`;
  return `${Math.round(h / 24)}d`;
};

export default function EngineerAnalyticsPage() {
  const navigate = useNavigate();
  const [range, setRange] = useState('30d');
  const [data, setData] = useState(null);
  const [reports, setReports] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, r] = await Promise.all([
        axios.get(`${API}/svc/engineer/analytics`, { ...auth(), params: { range } }),
        axios.get(`${API}/svc/engineer/analytics/reports`, { ...auth(), params: { range } })
          .catch(() => ({ data: null })),
      ]);
      setData(a.data);
      setReports(r.data);
    } catch (err) {
      notify.error('Failed to load analytics', err?.response?.data?.detail || err?.message);
    } finally { setLoading(false); }
  }, [range]);
  useEffect(() => { load(); }, [load]);

  const cases = useMemo(() => data?.cases || { total: 0, completed: 0, by_status: {} }, [data]);
  const quotes = useMemo(() => data?.quotes || { total: 0, by_status: {}, average_value: 0, earnings: 0 }, [data]);

  // Iter 277b — export / email the report.
  const [exporting, setExporting] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const [emailTo, setEmailTo] = useState('');
  const [emailing, setEmailing] = useState(false);

  const downloadPdf = async () => {
    setExporting(true);
    try {
      const res = await axios.get(`${API}/svc/engineer/analytics/reports.pdf`, {
        ...auth(), params: { range }, responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `performance-report-${range}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      notify.error('Could not generate PDF', err?.response?.data?.detail || err?.message);
    } finally { setExporting(false); }
  };

  const sendEmail = async () => {
    setEmailing(true);
    try {
      const r = await axios.post(`${API}/svc/engineer/analytics/reports/email`,
        { range, to: emailTo.trim() || undefined }, auth());
      notify.success('Report sent', `Emailed to ${r.data?.sent_to || 'your inbox'}`);
      setEmailOpen(false);
      setEmailTo('');
    } catch (err) {
      notify.error('Could not email report', err?.response?.data?.detail || err?.message);
    } finally { setEmailing(false); }
  };

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
                    on ? 'bg-gradient-to-br from-[#0891b2] to-[#0e7490] text-white' : 'text-slate-600 hover:bg-slate-50'
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

            {/* Iter 277 — Field-performance reports */}
            {reports && (
              <>
                <div className="grid grid-cols-2 gap-3" data-testid="analytics-perf-kpis">
                  <KPI
                    icon={Timer}
                    label="Avg response"
                    value={reports.response?.avg_minutes != null ? fmtDuration(reports.response.avg_minutes) : '—'}
                    testid="analytics-kpi-response"
                  />
                  <KPI
                    icon={CheckCircle2}
                    label="First-time fix"
                    value={reports.first_time_fix?.rate_pct != null ? `${reports.first_time_fix.rate_pct}%` : '—'}
                    testid="analytics-kpi-ftf"
                  />
                </div>

                {reports.response?.within_sla_pct != null && (
                  <div className="bg-white rounded-2xl border border-slate-200 p-4 text-sm" data-testid="analytics-response-detail">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-700">Responded within SLA</span>
                      <span className="font-bold text-slate-900 tabular-nums">{reports.response.within_sla_pct}%</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Median {reports.response.median_minutes != null ? fmtDuration(reports.response.median_minutes) : '—'} · {reports.response.sample} job{reports.response.sample === 1 ? '' : 's'} measured
                    </p>
                  </div>
                )}

                {reports.first_time_fix?.total > 0 && (
                  <div className="bg-white rounded-2xl border border-slate-200 p-4" data-testid="analytics-ftf-detail">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-slate-700">Fixed first visit</span>
                      <span className="font-bold text-emerald-600 tabular-nums">{reports.first_time_fix.fixed}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm mt-1">
                      <span className="font-medium text-slate-700">Needed a return visit</span>
                      <span className="font-bold text-amber-600 tabular-nums">{reports.first_time_fix.repeat_visits}</span>
                    </div>
                    <div className="h-2 mt-2 rounded-full bg-slate-100 overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${reports.first_time_fix.rate_pct || 0}%` }} />
                    </div>
                  </div>
                )}

                {/* Most problematic machines */}
                <SectionCard title="Most problematic machines" icon={Wrench} count={reports.problematic_machines?.length || 0}>
                  {(reports.problematic_machines?.length || 0) === 0 ? <Empty label="No machine faults in this range." />
                    : reports.problematic_machines.map((m) => (
                      <button
                        key={m.equipment_id}
                        onClick={() => navigate(`/svc/engineer/machine/${m.equipment_id}`)}
                        className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-slate-50 text-sm text-left"
                        data-testid={`analytics-machine-${m.equipment_id}`}
                      >
                        <span className="min-w-0">
                          <span className="block font-medium text-slate-800 truncate">{m.name}</span>
                          {m.site_name && (
                            <span className="block text-[11px] text-slate-400 truncate inline-flex items-center gap-1">
                              <MapPin size={10} /> {m.site_name}
                            </span>
                          )}
                        </span>
                        <span className="font-bold text-slate-900 tabular-nums shrink-0">{m.jobs}</span>
                      </button>
                    ))}
                </SectionCard>

                {/* Most problematic sites */}
                <SectionCard title="Most problematic sites" icon={MapPin} count={reports.problematic_sites?.length || 0}>
                  {(reports.problematic_sites?.length || 0) === 0 ? <Empty label="No site data in this range." />
                    : reports.problematic_sites.map((s) => (
                      <div key={s.site_name} className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm" data-testid={`analytics-site-${s.site_name}`}>
                        <span className="font-medium text-slate-700 truncate">{s.site_name}</span>
                        <span className="font-bold text-slate-900 tabular-nums">{s.jobs}</span>
                      </div>
                    ))}
                </SectionCard>

                {/* Most used parts */}
                <SectionCard title="Most used parts" icon={Package} count={reports.top_parts?.length || 0}>
                  {(reports.top_parts?.length || 0) === 0 ? <Empty label="No parts fitted in this range." />
                    : reports.top_parts.map((p, i) => (
                      <div key={`${p.part_sku || p.part_name}-${i}`} className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm" data-testid={`analytics-part-${i}`}>
                        <span className="min-w-0">
                          <span className="block font-medium text-slate-800 truncate">{p.part_name}</span>
                          {p.part_sku && <span className="block text-[11px] text-slate-400">{p.part_sku}</span>}
                        </span>
                        <span className="font-bold text-slate-900 tabular-nums shrink-0">{p.qty}</span>
                      </div>
                    ))}
                </SectionCard>
              </>
            )}

            {/* Iter 277b — export / email (moved to bottom; rarely used) */}
            <div className="bg-white rounded-2xl border border-slate-200 p-2 flex items-center gap-2 mt-2" data-testid="analytics-export-bar">
              <button
                onClick={downloadPdf}
                disabled={exporting}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-slate-700 border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
                data-testid="analytics-download-pdf"
              >
                {exporting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Download PDF
              </button>
              <button
                onClick={() => setEmailOpen((v) => !v)}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
                data-testid="analytics-email-toggle"
              >
                <Mail size={13} /> Email report
              </button>
            </div>
            {emailOpen && (
              <div className="bg-white rounded-2xl border border-orange-200 p-3 space-y-2" data-testid="analytics-email-form">
                <p className="text-[11px] text-slate-500">Sends to your own inbox by default — or enter an operator's address to share a summary.</p>
                <input
                  type="email"
                  value={emailTo}
                  onChange={(e) => setEmailTo(e.target.value)}
                  placeholder="recipient@example.com (optional)"
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-orange-500"
                  data-testid="analytics-email-input"
                />
                <button
                  onClick={sendEmail}
                  disabled={emailing}
                  className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
                  data-testid="analytics-email-send"
                >
                  {emailing ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />} Send report
                </button>
              </div>
            )}

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
