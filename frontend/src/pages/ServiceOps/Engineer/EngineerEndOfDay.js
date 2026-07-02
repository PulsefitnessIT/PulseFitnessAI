/**
 * EngineerEndOfDay — iter 220cu.
 *
 * One-screen daily timesheet roll-up: hours by category, miles,
 * jobs touched / closed, invoices issued + revenue. Screenshottable
 * for a daily report to a manager.
 *
 * Pulls:
 *   GET /api/svc/engineer/me/today-rollup
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Clock, MapPin, Wrench, CheckCircle2,
  ReceiptPoundSterling as Receipt, PoundSterling, RefreshCw, Sun,
  Briefcase,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';
import { useLocalization, formatMoney } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

function Stat({ icon: Icon, label, value, sub, accent, testid }) {
  return (
    <div
      className="bg-white rounded-2xl border border-slate-200 p-4"
      data-testid={testid}
    >
      <div className="flex items-center justify-between mb-2">
        <Icon size={14} style={{ color: accent || '#0891b2' }} />
      </div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="text-2xl font-extrabold mt-1 text-slate-900 tabular-nums">
        {value}
      </p>
      {sub && (
        <p className="text-[11px] text-slate-500 mt-0.5">{sub}</p>
      )}
    </div>
  );
}

export default function EngineerEndOfDay() {
  const orgBrand = useEngineerOrgBrand();
  const navigate = useNavigate();
  const loc = useLocalization();
  const fmtGBP = (n) => formatMoney(n, loc);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/me/today-rollup`, auth());
      setData(r.data);
    } catch (e) {
      notify.error(
        'Could not load today summary',
        e?.response?.data?.detail || e?.message,
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const date = data?.date
    ? new Date(`${data.date}T00:00:00Z`).toLocaleDateString('en-GB', {
        weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
      })
    : 'Today';

  return (
    <div
      className="min-h-screen bg-slate-50"
      data-testid="engineer-end-of-day"
    >
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="text-slate-500 hover:text-slate-900"
            aria-label="Back"
            data-testid="eod-back"
          >
            <ChevronLeft size={22} />
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
              {orgBrand.label}
            </p>
            <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
              <Sun size={18} className="text-amber-500" />
              End of day · {date}
            </h1>
          </div>
          <button
            type="button"
            onClick={load}
            className="p-2 rounded-full border border-slate-200 bg-white"
            aria-label="Refresh"
            data-testid="eod-refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-5 space-y-4">
        {loading && !data ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : data ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="eod-stats">
              <Stat
                icon={Clock}
                label="Hours total"
                value={`${data.hours_total}h`}
                sub={`On-site ${data.hours_on_site}h · Travel ${data.hours_travel}h · Admin ${data.hours_admin}h`}
                accent="#0891b2"
                testid="eod-hours"
              />
              <Stat
                icon={MapPin}
                label="Miles driven"
                value={`${data.miles} mi`}
                accent="#0e7490"
                testid="eod-miles"
              />
              <Stat
                icon={Briefcase}
                label="Jobs touched"
                value={data.jobs_touched}
                sub={`${data.jobs_closed} closed`}
                accent="#0891b2"
                testid="eod-jobs-touched"
              />
              <Stat
                icon={CheckCircle2}
                label="Jobs closed"
                value={data.jobs_closed}
                accent="#059669"
                testid="eod-jobs-closed"
              />
              <Stat
                icon={Receipt}
                label="Invoices issued"
                value={data.invoices_today}
                accent="#f59e0b"
                testid="eod-invoices"
              />
              <Stat
                icon={PoundSterling}
                label="Revenue today"
                value={fmtGBP(data.revenue_today_gbp)}
                accent="#10b981"
                testid="eod-revenue"
              />
            </div>

            <div
              className="bg-white rounded-2xl border border-slate-200 p-5"
              data-testid="eod-breakdown"
            >
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">
                Time breakdown
              </p>
              <div className="space-y-2">
                {[
                  { k: 'on_site', label: 'On site',    accent: '#0891b2' },
                  { k: 'travel',  label: 'Travel',     accent: '#0e7490' },
                  { k: 'admin',   label: 'Admin',      accent: '#64748b' },
                ].map(({ k, label, accent }) => {
                  const mins = data.minutes_by_category?.[k] || 0;
                  const totalMins = data.hours_total * 60;
                  const pct = totalMins > 0 ? Math.round((mins / totalMins) * 100) : 0;
                  return (
                    <div key={k} data-testid={`eod-bar-${k}`}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-bold text-slate-700">{label}</span>
                        <span className="tabular-nums text-slate-500">
                          {Math.floor(mins / 60)}h {mins % 60}m · {pct}%
                        </span>
                      </div>
                      <div
                        className="h-2 rounded-full overflow-hidden"
                        style={{ background: 'rgba(15,23,42,0.06)' }}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${pct}%`, background: accent }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 p-4 flex items-start gap-3">
              <Wrench size={16} className="text-slate-400 mt-0.5" />
              <p className="text-[11px] text-slate-500 leading-snug">
                This page is your one-screen daily timesheet —
                screenshot it for your manager, or just glance and
                go home. It refreshes from your actual time entries,
                mileage and invoices.
              </p>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-500">No data yet.</p>
        )}
      </main>
    </div>
  );
}
