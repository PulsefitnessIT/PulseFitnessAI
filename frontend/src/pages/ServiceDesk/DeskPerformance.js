import { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import {
  ClipboardList, RotateCcw, AlertTriangle, Timer, UserX, HardHat,
  Clock, Trophy, Gauge, Loader2, TrendingUp, TrendingDown, Minus,
} from 'lucide-react';
import { authConfig } from './authConfig';

const ACCENT = {
  blue: 'bg-cyan-50 text-cyan-600',
  orange: 'bg-orange-50 text-orange-600',
  red: 'bg-red-50 text-red-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-teal-50 text-teal-600',
  emerald: 'bg-emerald-50 text-emerald-600',
};

const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase();

/** Circular First-Time-Fix gauge. Colour shifts green→amber→red by rate. */
function FtfRing({ rate, trend }) {
  const R = 54;
  const C = 2 * Math.PI * R;
  const pct = Math.max(0, Math.min(100, rate));
  const stroke = pct >= 80 ? '#10b981' : pct >= 60 ? '#f59e0b' : '#ef4444';
  const hasTrend = typeof trend === 'number' && trend !== 0;
  const TrendIcon = !hasTrend ? Minus : trend > 0 ? TrendingUp : TrendingDown;
  const trendColour = !hasTrend ? 'text-white/50' : trend > 0 ? 'text-emerald-400' : 'text-red-400';
  return (
    <div className="relative w-[132px] h-[132px] flex-shrink-0" data-testid="desk-ftf-ring">
      <svg width="132" height="132" viewBox="0 0 132 132" className="-rotate-90">
        <circle cx="66" cy="66" r={R} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="11" />
        <circle
          cx="66" cy="66" r={R} fill="none" stroke={stroke} strokeWidth="11" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - pct / 100)}
          style={{ transition: 'stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white">
        <div className="text-3xl font-bold leading-none tracking-tight" data-testid="desk-ftf-rate">{rate}%</div>
        <div className="text-[10px] uppercase tracking-[0.14em] text-white/70 mt-1">First-time fix</div>
        <div className={`flex items-center gap-0.5 mt-1.5 text-[11px] font-semibold ${trendColour}`} data-testid="desk-ftf-trend">
          <TrendIcon className="w-3 h-3" />
          {hasTrend ? `${trend > 0 ? '+' : ''}${trend} pts` : 'flat'}
        </div>
      </div>
    </div>
  );
}

function MiniStat({ icon: Icon, value, label }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-9 h-9 rounded-xl bg-white/10 flex items-center justify-center text-white/90 flex-shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <div className="text-lg font-bold text-white leading-none">{value}</div>
        <div className="text-[11px] text-white/65 truncate">{label}</div>
      </div>
    </div>
  );
}

export default function DeskPerformance({ API, onNavigate }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    axios.get(`${API}/service-desk/performance`, authConfig())
      .then((r) => setD(r.data))
      .catch(() => setErr(true));
  }, [API]);

  if (err) return null; // fail quiet — never block the dashboard
  if (!d) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-400 py-6" data-testid="desk-performance-loading">
        <Loader2 size={15} className="animate-spin" /> Loading team performance…
      </div>
    );
  }

  const tiles = [
    { key: 'open_cases', label: 'Open Cases', sub: 'In flight now', icon: ClipboardList, accent: 'blue', goto: 'cases' },
    { key: 'rtf_open', label: 'Return to Fix', sub: 'Need a repeat visit', icon: RotateCcw, accent: 'orange', goto: 'cases', nav: { rtf: '1' } },
    { key: 'sla_breached', label: 'SLA Breached', sub: 'Resolve target passed', icon: AlertTriangle, accent: 'red', goto: 'cases', nav: { sla: 'breached' } },
    { key: 'sla_at_risk', label: 'SLA At-Risk', sub: 'Due within 24h', icon: Timer, accent: 'amber', goto: 'cases', nav: { sla: 'at_risk' } },
    { key: 'unassigned', label: 'Unassigned', sub: 'Awaiting an engineer', icon: UserX, accent: 'violet', goto: 'cases', nav: { assigned: 'unassigned' } },
    { key: 'active_engineers', label: 'Active Engineers', sub: 'On the team', icon: HardHat, accent: 'emerald', goto: 'engineers' },
  ];

  const maxClosed = Math.max(1, ...(d.leaderboard || []).map((r) => r.closed));
  const rankColour = ['bg-amber-400 text-amber-950', 'bg-zinc-300 text-zinc-700', 'bg-orange-300 text-orange-900'];

  return (
    <div className="space-y-4" data-testid="desk-performance">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
          <Gauge className="w-4 h-4 text-[var(--gx-brand-from,#ea580c)]" /> Team Performance
        </h2>
        <span className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Last {d.window_days} days</span>
      </div>

      {/* Hero — FTF gauge + headline throughput */}
      <Card
        className="p-5 sm:p-6 border-0 overflow-hidden relative cursor-pointer transition-transform active:scale-[0.99]"
        style={{ background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 60%, #111827 100%)' }}
        role="button" tabIndex={0}
        onClick={() => onNavigate && onNavigate('analytics')}
        onKeyDown={(e) => { if (e.key === 'Enter') onNavigate && onNavigate('analytics'); }}
        data-testid="desk-performance-hero"
      >
        <div
          className="absolute -right-16 -top-16 w-56 h-56 rounded-full opacity-20 blur-2xl pointer-events-none"
          style={{ background: 'radial-gradient(circle, var(--gx-brand-from,#f97316), transparent 70%)' }}
        />
        <div className="relative flex flex-col sm:flex-row sm:items-center gap-6">
          <FtfRing rate={d.ftf_rate} trend={d.ftf_trend} />
          <div className="flex-1">
            <div className="text-white/90 text-sm font-medium">
              {d.ftf_count} of {d.total_closed_30d} jobs fixed first time
            </div>
            <div className="text-white/55 text-xs mb-4">Higher is better · fewer repeat visits for your engineers</div>
            <div className="grid grid-cols-1 xs:grid-cols-3 gap-4">
              <MiniStat icon={RotateCcw} value={d.rtf_open} label="Return to Fix open" />
              <MiniStat icon={Clock} value={`${d.avg_resolution_hours}h`} label="Avg resolution" />
              <MiniStat icon={ClipboardList} value={d.closed_7d} label="Closed last 7 days" />
            </div>
          </div>
        </div>
      </Card>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
        {tiles.map(({ key, label, sub, icon: Icon, accent, goto, nav }) => (
          <Card
            key={key}
            role="button" tabIndex={0}
            onClick={() => onNavigate && onNavigate(goto, nav)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigate && onNavigate(goto, nav); } }}
            className="group p-4 sm:p-5 cursor-pointer border border-zinc-100 dark:border-zinc-800 transition-all hover:shadow-md hover:-translate-y-0.5"
            data-testid={`desk-perf-${key.replace(/_/g, '-')}`}
          >
            <div className="flex items-start justify-between">
              <div className={`w-9 h-9 rounded-xl ${ACCENT[accent]} flex items-center justify-center`}>
                <Icon className="w-4 h-4" />
              </div>
              {(key === 'sla_breached' && d[key] > 0) && (
                <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-red-100 text-red-600">Action</span>
              )}
            </div>
            <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 mt-3 tabular-nums">{(d[key] ?? 0).toLocaleString()}</div>
            <div className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mt-0.5">{label}</div>
            <div className="text-[11px] text-zinc-400">{sub}</div>
          </Card>
        ))}
      </div>

      {/* Engineer leaderboard */}
      <Card className="p-5" data-testid="desk-leaderboard">
        <div className="flex items-center gap-2 mb-4">
          <Trophy className="w-4 h-4 text-amber-500" />
          <div className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Engineer Leaderboard</div>
          <span className="ml-auto text-[11px] text-zinc-400">by jobs closed</span>
        </div>
        {(!d.leaderboard || d.leaderboard.length === 0) ? (
          <div className="text-sm text-zinc-400 py-4 text-center" data-testid="desk-leaderboard-empty">No closed jobs in this window yet.</div>
        ) : (
          <div className="space-y-3">
            {d.leaderboard.map((r, i) => (
              <button
                key={r.engineer_id}
                type="button"
                onClick={() => onNavigate && onNavigate('engineers')}
                className="w-full flex items-center gap-3 text-left group"
                data-testid={`desk-leaderboard-row-${i}`}
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold flex-shrink-0 ${rankColour[i] || 'bg-zinc-100 text-zinc-500'}`}>{i + 1}</div>
                {r.photo_url ? (
                  <img src={r.photo_url} alt={r.name} className="w-9 h-9 rounded-full object-cover flex-shrink-0 ring-1 ring-zinc-200" loading="lazy" />
                ) : (
                  <div className="w-9 h-9 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">{initials(r.name)}</div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate group-hover:text-[var(--gx-brand-from,#ea580c)] transition-colors">{r.name}</span>
                    <span className="text-sm font-bold text-zinc-900 dark:text-zinc-100 tabular-nums flex-shrink-0">{r.closed}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-[var(--gx-brand-from,#f97316)] to-[var(--gx-brand-to,#fb923c)]"
                        style={{ width: `${(r.closed / maxClosed) * 100}%`, transition: 'width 700ms ease' }}
                      />
                    </div>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${r.ftf_rate >= 80 ? 'bg-emerald-50 text-emerald-600' : r.ftf_rate >= 60 ? 'bg-amber-50 text-amber-600' : 'bg-red-50 text-red-600'}`}>{r.ftf_rate}% FTF</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
