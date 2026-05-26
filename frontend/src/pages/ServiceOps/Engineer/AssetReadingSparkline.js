/**
 * AssetReadingSparkline — Iter 220b
 *
 * Tiny inline SVG sparkline used inside the WorkReportCustomFields
 * widget to surface the trend of a numeric custom field across the
 * asset's recent visits. No charting library — keeps the bundle lean
 * and renders instantly on the engineer's phone.
 */
import { TrendingDown, TrendingUp, Minus } from 'lucide-react';

function fmt(value, captured_at) {
  let when = '';
  if (captured_at) {
    try {
      const d = new Date(captured_at);
      if (!Number.isNaN(d.getTime())) {
        when = d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
      }
    } catch { /* ignore */ }
  }
  return `${value}${when ? ` · ${when}` : ''}`;
}

export default function AssetReadingSparkline({ points, currentValue, testid }) {
  // `points` is oldest-first. Append the current input value (if numeric
  // and non-empty) so the engineer sees where today's reading lands on
  // the trend.
  const safePoints = Array.isArray(points) ? points : [];
  const live = (() => {
    if (currentValue === undefined || currentValue === null || currentValue === '') return null;
    const n = typeof currentValue === 'boolean'
      ? (currentValue ? 1 : 0)
      : Number(currentValue);
    if (Number.isNaN(n)) return null;
    return n;
  })();
  const data = live !== null
    ? [...safePoints.map(p => p.value), live]
    : safePoints.map(p => p.value);
  if (data.length < 2) return null;

  const W = 140;
  const H = 28;
  const PAD = 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = (W - PAD * 2) / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = PAD + i * stepX;
    const y = H - PAD - ((v - min) / span) * (H - PAD * 2);
    return [x, y];
  });
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const first = data[0];
  const last = data[data.length - 1];
  const delta = last - first;
  const tone = Math.abs(delta) < (span * 0.05)
    ? 'flat'
    : delta < 0 ? 'down' : 'up';
  const stroke = tone === 'flat' ? '#64748b' : tone === 'down' ? '#dc2626' : '#059669';
  const Icon = tone === 'flat' ? Minus : tone === 'down' ? TrendingDown : TrendingUp;
  const previous = safePoints[safePoints.length - 1];
  const tooltip = safePoints
    .slice(-5)
    .map(p => fmt(p.value, p.captured_at))
    .join(' · ');

  return (
    <div
      className="mt-1 flex items-center gap-2 rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5"
      data-testid={testid || 'wrf-sparkline'}
      title={tooltip}
    >
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="flex-shrink-0">
        <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        {pts.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={i === pts.length - 1 && live !== null ? 2.5 : 1.5}
            fill={i === pts.length - 1 && live !== null ? '#1d4ed8' : stroke}
          />
        ))}
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-[10px] text-slate-600 truncate">
          <Icon size={10} className="inline mr-0.5" style={{ color: stroke }} />
          {tone === 'flat' ? 'Steady' : tone === 'down' ? 'Trending down' : 'Trending up'}
          {previous && (
            <> · prev <span className="font-bold">{previous.value}</span></>
          )}
        </p>
        <p className="text-[10px] text-slate-400 truncate">
          {safePoints.length}-visit trend{live !== null ? ' incl. today' : ''}
        </p>
      </div>
    </div>
  );
}
