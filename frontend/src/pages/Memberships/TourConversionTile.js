/**
 * TourConversionTile — Booked → Attended → Became-member funnel for the
 * last N days, with conversion percentages.
 *
 * Surfaces the impact of the public sign-up tour-booking flow on actual
 * memberships, so operators can A/B test things like reminder timing or
 * the skip-tour-and-pay-direct path without flying blind.
 *
 * Calls: GET /api/memberships/tour-conversion?days=30
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { TrendingUp, Calendar, UserCheck, UserPlus, RefreshCw, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PERIODS = [
  { id: 7, label: '7d' },
  { id: 30, label: '30d' },
  { id: 90, label: '90d' },
];

const pct = (value) => `${Math.round((value || 0) * 100)}%`;

const TourConversionTile = () => {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API}/memberships/tour-conversion`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        params: { days },
      });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't load conversion.");
    }
    setLoading(false);
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const byStatus = data?.by_status || {};
  const rates = data?.conversion_rates || {};

  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4" data-testid="tour-conversion-tile">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] flex items-center gap-1" style={{ color: 'var(--color-brand-cyan)' }}>
            <TrendingUp size={11} /> Tour conversion
          </p>
          <h3 className="text-base font-semibold mt-0.5" style={{ color: 'var(--theme-text)' }}>
            Booked → Attended → Member
          </h3>
        </div>
        <div className="flex items-center gap-1">
          <div className="flex items-center gap-0.5 bg-white/5 rounded-full p-0.5" data-testid="tour-conversion-period-switch">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                onClick={() => setDays(p.id)}
                className={`px-2 py-1 rounded-full text-[11px] font-medium transition-colors ${
                  days === p.id ? 'bg-white/15 text-white' : 'text-zinc-400 hover:text-white'
                }`}
                data-testid={`tour-conversion-period-${p.id}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-[color:var(--theme-border)] hover:bg-white/5 ml-1"
            data-testid="tour-conversion-refresh"
            title="Refresh"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !data ? (
        <p className="text-xs flex items-center gap-2 py-4" style={{ color: 'var(--theme-text-muted)' }}>
          <Loader2 size={12} className="animate-spin" /> Loading…
        </p>
      ) : error ? (
        <p className="text-xs text-red-500" data-testid="tour-conversion-error">{error}</p>
      ) : (data?.total_booked || 0) === 0 ? (
        <p className="text-xs italic py-3" style={{ color: 'var(--theme-text-muted)' }} data-testid="tour-conversion-empty">
          No tour bookings yet in the last {days} days. Share your public sign-up page to start the funnel.
        </p>
      ) : (
        <>
          {/* Funnel tiles */}
          <div className="grid grid-cols-3 gap-2" data-testid="tour-conversion-funnel">
            <FunnelStep
              icon={Calendar}
              label="Booked"
              value={data.total_booked}
              accent="bg-blue-500"
              testid="tour-conversion-booked"
            />
            <FunnelStep
              icon={UserCheck}
              label="Attended"
              value={byStatus.attended || 0}
              sub={pct(rates.booked_to_attended)}
              accent="bg-emerald-500"
              testid="tour-conversion-attended"
            />
            <FunnelStep
              icon={UserPlus}
              label="Became member"
              value={data.became_member}
              sub={pct(rates.booked_to_member)}
              accent="bg-violet-500"
              testid="tour-conversion-member"
            />
          </div>

          {/* Funnel bar */}
          <div className="mt-3" data-testid="tour-conversion-bar">
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex">
              <div
                className="bg-blue-500"
                style={{ width: '100%' }}
                title={`${data.total_booked} booked`}
              />
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex mt-1">
              <div
                className="bg-emerald-500"
                style={{ width: `${Math.round((rates.booked_to_attended || 0) * 100)}%` }}
                title={`${pct(rates.booked_to_attended)} attended of booked`}
              />
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex mt-1">
              <div
                className="bg-violet-500"
                style={{ width: `${Math.round((rates.booked_to_member || 0) * 100)}%` }}
                title={`${pct(rates.booked_to_member)} members of booked`}
              />
            </div>
          </div>

          {/* Bottom summary */}
          <div className="mt-3 flex items-center justify-between text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
            <span>
              <strong style={{ color: 'var(--theme-text)' }}>{byStatus.no_show || 0}</strong> no-show
              · <strong style={{ color: 'var(--theme-text)' }}>{byStatus.cancelled || 0}</strong> cancelled
              · <strong style={{ color: 'var(--theme-text)' }}>{byStatus.booked || 0}</strong> upcoming
            </span>
            <span data-testid="tour-conversion-attended-to-member">
              Attended → Member <strong style={{ color: 'var(--theme-text)' }}>{pct(rates.attended_to_member)}</strong>
            </span>
          </div>
        </>
      )}
    </div>
  );
};

const FunnelStep = ({ icon: Icon, label, value, sub, accent, testid }) => (
  <div className="rounded-lg border border-[color:var(--theme-border)] bg-white/[0.02] p-2.5" data-testid={testid}>
    <div className="flex items-center gap-1.5">
      <span className={`w-5 h-5 rounded grid place-items-center text-white ${accent}`}>
        <Icon size={11} />
      </span>
      <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
    </div>
    <p className="text-xl font-bold mt-1.5" style={{ color: 'var(--theme-text)' }}>{value}</p>
    {sub != null && (
      <p className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{sub} of booked</p>
    )}
  </div>
);

export default TourConversionTile;
