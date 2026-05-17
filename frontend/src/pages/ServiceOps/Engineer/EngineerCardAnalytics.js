/**
 * EngineerCardAnalytics — iter 216h159.
 *
 * Surface for the `/api/svc/engineer/independence/card-conversions`
 * rollup. Shows each engineer's QR card performance: requests in,
 * cases out, revenue, conversion rate. Highlights the current
 * engineer's own slug so they can see their personal contribution.
 *
 *   /svc/engineer/card-analytics
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Loader2, RefreshCw, QrCode, TrendingUp, Inbox as InboxIcon,
  CheckCircle2, PoundSterling, Crown, Wrench, Mail as MailIcon,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const WINDOW_OPTIONS = [
  { value: 30,  label: '30 days' },
  { value: 90,  label: '90 days' },
  { value: 180, label: '6 months' },
  { value: 365, label: '12 months' },
];

const fmtMoney = (n) => {
  if (n == null || isNaN(n)) return '—';
  return new Intl.NumberFormat('en-GB', {
    style: 'currency', currency: 'GBP', maximumFractionDigits: 0,
  }).format(n);
};

const fmtPct = (n) => {
  if (n == null || isNaN(n)) return '—';
  return `${Math.round(n * 100)}%`;
};

// ── KPI tile ──────────────────────────────────────────────────
const Tile = ({ icon: Icon, label, value, sub, accent, testid }) => (
  <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={testid}>
    <div className="flex items-center justify-between mb-1.5">
      <p className="text-[11px] uppercase tracking-wider font-bold text-slate-500">{label}</p>
      <Icon size={14} className={accent || 'text-slate-400'} />
    </div>
    <p className="text-2xl font-extrabold text-slate-900 tabular-nums">{value}</p>
    {sub ? <p className="text-[11px] text-slate-500 mt-0.5">{sub}</p> : null}
  </div>
);

// ── Main page ─────────────────────────────────────────────────
export default function EngineerCardAnalytics() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [mySlug, setMySlug] = useState(null);
  const [windowDays, setWindowDays] = useState(90);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rolls, card] = await Promise.all([
        axios.get(`${API}/svc/engineer/independence/card-conversions`,
                  { ...auth(), params: { days: windowDays } }),
        axios.get(`${API}/svc/engineer/intake-card`, auth()).catch(() => ({ data: {} })),
      ]);
      setData(rolls.data);
      setMySlug(card.data?.slug || null);
    } catch (e) {
      notify.error('Failed to load card analytics', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [windowDays]);

  useEffect(() => { load(); }, [load]);

  const myRow = useMemo(() => {
    if (!data?.rows || !mySlug) return null;
    return data.rows.find((r) => r.slug === mySlug) || null;
  }, [data, mySlug]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="p-1 -ml-1 rounded-lg hover:bg-slate-100"
            data-testid="card-analytics-back"
            aria-label="Back"
          >
            <ChevronLeft size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <QrCode size={16} /> Card analytics
            </h1>
            <p className="text-[11px] text-slate-500">
              Which QR card converted requests into revenue.
            </p>
          </div>
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="text-xs font-semibold px-2 py-1.5 border border-slate-300 rounded-lg bg-white"
            data-testid="card-analytics-window"
          >
            {WINDOW_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={load}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500"
            data-testid="card-analytics-refresh"
            aria-label="Refresh"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4 space-y-4">
        {loading && !data ? (
          <div className="text-center py-12 text-slate-400">
            <Loader2 size={24} className="animate-spin mx-auto" />
          </div>
        ) : !data ? (
          <p className="text-center text-sm text-slate-500 py-12">No data available</p>
        ) : (
          <>
            {/* Org-wide KPIs */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Tile
                icon={InboxIcon}
                label="Requests received"
                value={data.totals.requests}
                sub={`Last ${data.window_days} days`}
                accent="text-blue-500"
                testid="card-analytics-tile-requests"
              />
              <Tile
                icon={CheckCircle2}
                label="Cases created"
                value={data.totals.cases}
                sub="From supplier-card flow"
                accent="text-emerald-500"
                testid="card-analytics-tile-cases"
              />
              <Tile
                icon={PoundSterling}
                label="Revenue attributed"
                value={fmtMoney(data.totals.revenue)}
                sub="Invoiced + approved"
                accent="text-violet-500"
                testid="card-analytics-tile-revenue"
              />
            </div>

            {/* Your card spotlight */}
            {myRow ? (
              <div className="bg-gradient-to-r from-blue-600 to-violet-600 text-white rounded-2xl p-4 shadow-sm"
                   data-testid="card-analytics-my-row">
                <p className="text-[11px] uppercase tracking-wider font-bold opacity-80 flex items-center gap-1">
                  <Crown size={12} /> Your card · /{mySlug}
                </p>
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <p className="text-[10px] opacity-75">Requests</p>
                    <p className="text-xl font-extrabold tabular-nums">{myRow.requests_total}</p>
                  </div>
                  <div>
                    <p className="text-[10px] opacity-75">Cases</p>
                    <p className="text-xl font-extrabold tabular-nums">{myRow.cases_total}</p>
                  </div>
                  <div>
                    <p className="text-[10px] opacity-75">Revenue</p>
                    <p className="text-xl font-extrabold tabular-nums">{fmtMoney(myRow.revenue_total)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] opacity-75">Conversion</p>
                    <p className="text-xl font-extrabold tabular-nums">{fmtPct(myRow.conversion_rate)}</p>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Per-slug leaderboard */}
            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
              <div className="px-4 py-2.5 border-b border-slate-200">
                <p className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                  <TrendingUp size={12} /> Engineer leaderboard
                </p>
              </div>
              {data.rows.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-8">
                  No card activity in this window. Hand out your QR cards on-site.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr className="text-left text-slate-500">
                        <th className="px-3 py-2 font-semibold">#</th>
                        <th className="px-3 py-2 font-semibold">Engineer / slug</th>
                        <th className="px-3 py-2 font-semibold text-right">Requests</th>
                        <th className="px-3 py-2 font-semibold text-right">Cases</th>
                        <th className="px-3 py-2 font-semibold text-right">
                          <MailIcon size={10} className="inline" /> Email
                        </th>
                        <th className="px-3 py-2 font-semibold text-right">Revenue</th>
                        <th className="px-3 py-2 font-semibold text-right">Conv.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.rows.map((row, i) => {
                        const isMe = row.slug === mySlug;
                        return (
                          <tr
                            key={row.slug}
                            className={isMe ? 'bg-blue-50/50' : ''}
                            data-testid={`card-analytics-row-${row.slug}`}
                          >
                            <td className="px-3 py-2 tabular-nums font-bold text-slate-400">
                              {i + 1}
                            </td>
                            <td className="px-3 py-2">
                              <p className="font-semibold text-slate-900">
                                {row.engineer_name || '(unnamed)'}
                                {isMe ? (
                                  <span className="ml-2 text-[10px] bg-blue-600 text-white px-1.5 py-0.5 rounded">
                                    You
                                  </span>
                                ) : null}
                              </p>
                              <p className="text-[10px] text-slate-400 font-mono">/{row.slug}</p>
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">{row.requests_total}</td>
                            <td className="px-3 py-2 text-right tabular-nums">{row.cases_total}</td>
                            <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                              {row.cases_inbound_email}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums font-bold text-slate-900">
                              {fmtMoney(row.revenue_total)}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              <span className={`px-1.5 py-0.5 rounded ${
                                (row.conversion_rate ?? 0) >= 0.5 ? 'bg-emerald-50 text-emerald-700'
                                : (row.conversion_rate ?? 0) >= 0.25 ? 'bg-amber-50 text-amber-700'
                                : 'bg-slate-100 text-slate-500'
                              }`}>
                                {fmtPct(row.conversion_rate)}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <p className="text-[10px] text-slate-400 text-center pt-2">
              <Wrench size={9} className="inline -mt-0.5 mr-0.5" />
              Revenue = sum of invoiced or approved quotes attributed to each slug.
              Conversion = accepted requests ÷ total requests.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
