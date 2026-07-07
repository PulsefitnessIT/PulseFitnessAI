/**
 * KPI trend helpers — GymAxis-style live sparklines shared by the Full
 * Operations dashboard (Dashboard/OverviewTab) and the Pulse Pro dashboard
 * (LiteDashboard/LiteOverviewTab). The series is ALWAYS computed live from
 * the real records (no mocked data), bucketed into the last 3 calendar months.
 */

const _recDate = (r) => {
  const v = r?.created_at || r?.date || r?.completed_at || r?.scheduled_date || r?.due_date || r?.timestamp;
  if (!v) return null;
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d;
};

export const monthlySeries = (items, filterFn) => {
  const now = new Date();
  const buckets = [];
  for (let i = 2; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    buckets.push({ y: d.getFullYear(), m: d.getMonth(), label: d.toLocaleString('en-GB', { month: 'short' }), count: 0 });
  }
  (Array.isArray(items) ? items : []).forEach((r) => {
    if (filterFn && !filterFn(r)) return;
    const d = _recDate(r);
    if (!d) return;
    const b = buckets.find((x) => x.y === d.getFullYear() && x.m === d.getMonth());
    if (b) b.count += 1;
  });
  const last = buckets[2].count;
  const prev = buckets[1].count;
  let pct = 0;
  if (prev === 0) pct = last === 0 ? 0 : 100;
  else pct = Math.round(((last - prev) / prev) * 100);
  return { points: buckets, pct };
};

// Tiny inline area sparkline (3 points) + month axis labels.
export const Sparkline = ({ points, color = 'var(--color-brand-blue)' }) => {
  const vals = points.map((p) => p.count);
  const max = Math.max(1, ...vals);
  const W = 240, H = 60, pad = 6;
  const step = (W - pad * 2) / (points.length - 1);
  const xy = points.map((p, i) => [pad + i * step, H - pad - (p.count / max) * (H - pad * 2)]);
  const line = xy.map(([x, y]) => `${x},${y}`).join(' ');
  const area = `${pad},${H - pad} ${line} ${W - pad},${H - pad}`;
  const gid = `spark-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <div className="mt-3" data-testid="kpi-sparkline">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-14" preserveAspectRatio="none">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill={`url(#${gid})`} />
        <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {xy.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.5" fill={color} />)}
      </svg>
      <div className="flex justify-between mt-1 px-1">
        {points.map((p, i) => <span key={i} className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{p.label}</span>)}
      </div>
    </div>
  );
};

export const TrendBadge = ({ pct, invert = false }) => {
  // invert=true → a DROP is good (e.g. fewer open faults), shown green.
  const good = invert ? pct <= 0 : pct >= 0;
  const flat = pct === 0;
  const cls = flat ? 'bg-[var(--theme-surface-2)] text-[var(--theme-text-muted)]' : good ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400';
  const arrow = flat ? '–' : pct > 0 ? '▲' : '▼';
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${cls}`} data-testid="kpi-trend-badge">
      {arrow} {Math.abs(pct)}%
    </span>
  );
};
