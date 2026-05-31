/**
 * The Pulse · today — the platform's signature hero metric.
 *
 * Iter 217 — wraps the existing /api/gym-health-score endpoint
 * (merged in this iter from the previously-duplicate pulse_score
 * route) and renders it as a single animated card on the dashboard
 * header.
 *
 * Design notes (post-feedback):
 *   - Light, paper-toned card — no dark surfaces. Inherits the
 *     same "calm widget" feel as the other dashboard tiles, with
 *     a subtle brand-tinted gradient + soft cyan halo behind the
 *     ring (NOT a heavy glow).
 *   - The ring sweeps in brand cyan → blue and the heartbeat is
 *     a slow, gentle scale loop on the inner halo. No box-shadow.
 *   - Component bars inside the breakdown sit on pure white.
 */
import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import axios from 'axios';
import { useAuth } from '@/App';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/* Iter 220n — brand-aware copy. The component is shared between
 * Pulse Fitness and GymAxis dashboards; only the visible labels +
 * the ring gradient differ. Account type drives the switch:
 *   - 'pulse_pro' / 'lite' → "The Pulse · today" (cyan ring)
 *   - everyone else        → "Gym Health · today" (GymAxis navy→purple)
 */
const BRAND_COPY = {
  pulse: {
    eyebrow: 'The Pulse',
    eyebrow_today: 'The Pulse · today',
    eyebrow_waking: 'The Pulse · waking up',
    loading: 'Reading your Pulse…',
    error: 'Could not load The Pulse',
    not_ready_fallback: "Your Pulse will appear once you've added equipment and logged a little activity.",
    ring_gradient: 'linear-gradient(90deg, #19CDFF, #0055FF)',
    eyebrow_color: '#0055FF',
  },
  gymaxis: {
    eyebrow: 'Gym Health',
    eyebrow_today: 'Gym Health · today',
    eyebrow_waking: 'Gym Health · waking up',
    loading: 'Reading Gym Health…',
    error: 'Could not load Gym Health',
    not_ready_fallback: "Your Gym Health score will appear once you've added equipment and logged a little activity.",
    ring_gradient: 'linear-gradient(90deg, #2563EB, #9D4CDD)',
    eyebrow_color: '#2563EB',
  },
};

/* Bands map the existing endpoint's `rating` field straight through. */
const BAND_STYLES = {
  Excellent:         { fg: '#10B981', soft: 'rgba(16,185,129,0.10)' },
  Good:              { fg: '#19CDFF', soft: 'rgba(25,205,255,0.12)' },
  Fair:              { fg: '#F59E0B', soft: 'rgba(245,158,11,0.10)' },
  'Needs Attention': { fg: '#F97316', soft: 'rgba(249,115,22,0.10)' },
  Critical:          { fg: '#EF4444', soft: 'rgba(239,68,68,0.10)' },
};

/* Curated order — Fault freshness leads because it answers
   "what's hurting me right now?" — the most useful read in a glance. */
const ORDER = [
  'fault_freshness',
  'fault_management',
  'sla_adherence',
  'self_fix_rate',
  'audit_coverage',
  'warranty_health',
  'ai_knowledge',
];

const LABEL = {
  fault_management: 'Fault backlog',
  fault_freshness:  'Fault freshness',
  self_fix_rate:    'Self-fix rate',
  audit_coverage:   'Audit coverage',
  warranty_health:  'Warranty health',
  sla_adherence:    'SLA adherence',
  ai_knowledge:     'Knowledge base',
};

export const PulseScoreCard = ({ siteId }) => {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { user } = useAuth() || {};
  // Iter 220n — switch copy + ring gradient by brand. Pulse customers
  // see "The Pulse"; everyone else (GymAxis ops) sees "Gym Health".
  const isPulse = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
  const COPY = isPulse ? BRAND_COPY.pulse : BRAND_COPY.gymaxis;

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    const url = `${API}/gym-health-score${siteId ? `?site_id=${siteId}` : ''}`;
    setLoading(true);
    axios.get(url, { headers })
      .then(r => { setData(r.data); setError(null); })
      .catch(e => setError(e.response?.data?.detail || COPY.error))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  if (loading) {
    return (
      <div
        data-testid="pulse-score-card"
        className="rounded-2xl border border-[#E2E8F0] bg-white p-5 mb-4 text-sm text-slate-500"
      >
        {COPY.loading}
      </div>
    );
  }
  if (error || !data) {
    return (
      <div
        data-testid="pulse-score-card"
        className="rounded-2xl border border-[#E2E8F0] bg-white p-5 mb-4 text-sm text-slate-500"
      >
        {error || COPY.error}
      </div>
    );
  }

  // Not-ready (onboarding incomplete) — soft, encouraging state.
  if (data.not_ready) {
    return (
      <div
        data-testid="pulse-score-card"
        className="rounded-2xl border border-[#E2E8F0] bg-gradient-to-br from-[#F0F9FF] via-white to-[#EFF6FF] p-5 mb-4"
      >
        <div className="text-xs uppercase tracking-[0.18em] font-mono font-semibold mb-1" style={{ color: COPY.eyebrow_color }}>
          {COPY.eyebrow_waking}
        </div>
        <div className="text-lg font-bold text-slate-800 mb-1 pulse-font-heading">
          We're getting to know your site.
        </div>
        <div className="text-sm text-slate-600 pulse-font-body">
          {data.message || COPY.not_ready_fallback}
        </div>
      </div>
    );
  }

  const band = BAND_STYLES[data.rating] || BAND_STYLES.Fair;

  // SVG ring geometry — r=58, circumference ≈ 364.4.
  const R = 58;
  const C = 2 * Math.PI * R;
  const sweep = (data.score / 100) * C;

  // Breakdown rows in our preferred order, filtered to what the API returned.
  const rows = ORDER
    .filter(k => data.breakdown && data.breakdown[k])
    .map(k => ({ key: k, ...data.breakdown[k] }));

  return (
    <div
      data-testid="pulse-score-card"
      style={{ '--pulse-fg': band.fg, '--pulse-soft': band.soft }}
      className="rounded-2xl border border-[#E2E8F0] bg-gradient-to-br from-white via-[#F8FBFF] to-[#F0F9FF] mb-4 overflow-hidden"
    >
      <style>{`
        @keyframes pulse-breath {
          0%, 100% { transform: scale(1);    opacity: 0.55; }
          25%      { transform: scale(1.06); opacity: 0.85; }
          50%      { transform: scale(1);    opacity: 0.55; }
          70%      { transform: scale(1.03); opacity: 0.75; }
        }
        .pulse-breath { animation: pulse-breath 2.6s ease-in-out infinite; }
      `}</style>

      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        data-testid="pulse-score-toggle"
        className="w-full flex items-center justify-between gap-5 p-5 text-left hover:bg-[#F0F9FF]/60 transition-colors"
      >
        <div className="flex items-center gap-5 min-w-0">
          {/* Animated ring */}
          <div className="relative shrink-0" style={{ width: 128, height: 128 }}>
            <div
              className="absolute inset-3 rounded-full pulse-breath"
              style={{ background: 'var(--pulse-soft)' }}
            />
            <svg width="128" height="128" viewBox="0 0 128 128" className="relative">
              <circle cx="64" cy="64" r={R} fill="none" stroke="#E2E8F0" strokeWidth="6" />
              <circle
                cx="64" cy="64" r={R}
                fill="none"
                stroke="var(--pulse-fg)"
                strokeWidth="6"
                strokeLinecap="round"
                strokeDasharray={`${sweep} ${C}`}
                transform="rotate(-90 64 64)"
                style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)' }}
              />
              <text
                x="64" y="62"
                textAnchor="middle"
                style={{
                  fill: '#0B0F1A',
                  fontFamily: 'Montserrat, system-ui, sans-serif',
                  fontWeight: 900,
                  fontSize: 34,
                  letterSpacing: '-0.02em',
                }}
              >{data.score}</text>
              <text
                x="64" y="82"
                textAnchor="middle"
                style={{
                  fill: '#94A3B8',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 9,
                  letterSpacing: '0.14em',
                }}
              >/ 100</text>
            </svg>
          </div>

          <div className="min-w-0">
            <div className="text-xs uppercase tracking-[0.18em] font-mono font-semibold mb-1" style={{ color: 'var(--pulse-fg)' }}>
              {COPY.eyebrow_today}
            </div>
            <h3
              className="text-2xl sm:text-3xl font-bold leading-tight mb-1 pulse-font-heading"
              style={{ color: '#0B0F1A' }}
              data-testid="pulse-score-band"
            >
              {data.rating}.
            </h3>
            <p className="text-sm text-slate-600 pulse-font-body">
              A live read of how well this site is running. {open ? 'Hiding' : 'Tap'} the breakdown to see why.
            </p>
          </div>
        </div>

        <div className="shrink-0 rounded-full p-2" style={{ background: 'var(--pulse-soft)' }}>
          {open
            ? <ChevronUp size={20} style={{ color: 'var(--pulse-fg)' }} />
            : <ChevronDown size={20} style={{ color: 'var(--pulse-fg)' }} />
          }
        </div>
      </button>

      {open && (
        <div
          data-testid="pulse-score-breakdown"
          className="border-t border-[#E2E8F0] bg-white/70 p-5 pt-4 grid sm:grid-cols-2 gap-3"
        >
          {rows.map(r => {
            const pct = r.max > 0 ? (r.score / r.max) * 100 : 0;
            const widthPct = Math.max(2, Math.min(100, pct));
            return (
              <div
                key={r.key}
                data-testid={`pulse-component-${r.key}`}
                className="rounded-xl border border-[#E2E8F0] bg-white p-3"
              >
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <div className="font-semibold text-sm text-slate-900 pulse-font-heading">
                    {LABEL[r.key] || r.key}
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-mono text-slate-400">
                      / {r.max}
                    </span>
                    <span className="font-bold text-base pulse-font-heading" style={{ color: 'var(--pulse-fg)' }}>
                      {r.score}
                    </span>
                  </div>
                </div>
                <div className="h-1.5 rounded-full bg-[#EEF2F7] overflow-hidden mb-2">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${widthPct}%`,
                      background: COPY.ring_gradient,
                      transition: 'width 1s cubic-bezier(.4,0,.2,1)',
                    }}
                  />
                </div>
                <div className="text-xs text-slate-500 pulse-font-body">
                  {r.detail}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PulseScoreCard;
