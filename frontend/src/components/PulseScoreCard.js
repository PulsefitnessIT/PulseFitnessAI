/**
 * The Pulse Score — signature hero metric.
 *
 * Iter 217 — one number, one promise. Composes 5 sub-scores into a
 * single 0-100 operational pulse, rendered as an animated ring with
 * a slow heartbeat. Click anywhere on the card to expand a drawer
 * showing each component, its weight, and the raw inputs.
 *
 * Why we built it this way:
 *   - The "ring" is two concentric SVG circles: a faint track + an
 *     arc that sweeps in proportion to the score. No external lib.
 *   - The pulse is a CSS @keyframes scale+opacity loop on the
 *     inner halo. Restarts cleanly on score changes because we key
 *     the wrapper on `score`.
 *   - Band colour is computed in JS once; we pass three CSS vars
 *     down (--pulse-bg, --pulse-fg, --pulse-glow) so the ring +
 *     glow + label all stay in sync.
 *   - Drawer rows are bog-standard divs — keeps the bundle thin
 *     and the design owned by us, not by a chart lib's defaults.
 */
import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BAND = {
  excellent: { bg: 'rgba(16,185,129,0.10)', fg: '#10B981', glow: 'rgba(16,185,129,0.45)', label: 'Excellent' },
  good:      { bg: 'rgba(25,205,255,0.10)', fg: '#19CDFF', glow: 'rgba(25,205,255,0.45)', label: 'Good' },
  fair:      { bg: 'rgba(245,158,11,0.10)', fg: '#F59E0B', glow: 'rgba(245,158,11,0.45)', label: 'Fair' },
  poor:      { bg: 'rgba(239,68,68,0.10)',  fg: '#EF4444', glow: 'rgba(239,68,68,0.45)',  label: 'Needs attention' },
};

const COMPONENT_META = {
  fault_freshness: { label: 'Fault freshness',  hint: 'Median age of open faults', detailFmt: (d) => d.open_faults === 0 ? 'No open faults' : `${d.open_faults} open · median ${d.median_age_days}d` },
  self_fix_rate:   { label: 'Self-fix rate',    hint: 'Resolved on-base, no call-out', detailFmt: (d) => d.resolved_30d === 0 ? 'No closures in last 30d' : `${d.self_fix_pct}% of ${d.resolved_30d} closures` },
  audit_coverage:  { label: 'Audit coverage',   hint: 'Machines checked in last 7 days', detailFmt: (d) => d.equipment_count === 0 ? 'No equipment' : `${d.covered_pct}% of ${d.equipment_count} machines` },
  warranty_health: { label: 'Warranty health',  hint: 'Equipment under cover',  detailFmt: (d) => d.equipment_count === 0 ? 'No equipment' : `${d.in_warranty_pct}% in warranty / service contract` },
  sla_adherence:   { label: 'SLA adherence',    hint: 'Acknowledged within 24h', detailFmt: (d) => d.faults_30d === 0 ? 'No faults in last 30d' : `${d.ack_within_24h_pct}% of ${d.faults_30d} faults` },
};

export const PulseScoreCard = ({ siteId }) => {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };
    const url = `${API}/pulse-score/me${siteId ? `?site_id=${siteId}` : ''}`;
    setLoading(true);
    axios.get(url, { headers })
      .then(r => { setData(r.data); setError(null); })
      .catch(e => setError(e.response?.data?.detail || 'Could not load Pulse Score'))
      .finally(() => setLoading(false));
  }, [siteId]);

  if (loading || error || !data) {
    return (
      <div
        data-testid="pulse-score-card"
        className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-surface)] p-5 mb-4"
      >
        <div className="text-sm text-[var(--theme-text-muted)] pulse-font-body">
          {error ? error : 'Reading your Pulse…'}
        </div>
      </div>
    );
  }

  const band = BAND[data.band] || BAND.fair;
  // SVG ring: r=58, circumference = 2πr ≈ 364.4. Sweep length = score%.
  const R = 58;
  const C = 2 * Math.PI * R;
  const sweep = (data.score / 100) * C;

  return (
    <div
      data-testid="pulse-score-card"
      style={{
        // Brand-token vars consumed by the inline SVG + halo
        '--pulse-bg': band.bg,
        '--pulse-fg': band.fg,
        '--pulse-glow': band.glow,
      }}
      className="rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-surface)] mb-4 overflow-hidden"
    >
      {/* keyframes scoped to this component */}
      <style>{`
        @keyframes pulse-heartbeat {
          0%   { transform: scale(1);    opacity: 0.7; }
          25%  { transform: scale(1.08); opacity: 0.95; }
          50%  { transform: scale(1);    opacity: 0.7; }
          70%  { transform: scale(1.04); opacity: 0.85; }
          100% { transform: scale(1);    opacity: 0.7; }
        }
        .pulse-halo { animation: pulse-heartbeat 2.4s ease-in-out infinite; }
      `}</style>

      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        data-testid="pulse-score-toggle"
        className="w-full flex items-center justify-between gap-5 p-5 text-left hover:bg-[var(--theme-surface-hover)] transition-colors"
      >
        <div className="flex items-center gap-5 min-w-0">
          {/* Animated ring */}
          <div className="relative shrink-0" style={{ width: 132, height: 132 }}>
            {/* breathing halo behind the ring */}
            <div
              className="absolute inset-2 rounded-full pulse-halo"
              style={{
                background: 'var(--pulse-bg)',
                boxShadow: `0 0 32px 6px var(--pulse-glow)`,
              }}
            />
            <svg width="132" height="132" viewBox="0 0 132 132" className="relative">
              <circle cx="66" cy="66" r={R} fill="none" stroke="var(--theme-border)" strokeWidth="6" />
              <circle
                cx="66" cy="66" r={R}
                fill="none"
                stroke="var(--pulse-fg)"
                strokeWidth="6"
                strokeLinecap="round"
                strokeDasharray={`${sweep} ${C}`}
                transform="rotate(-90 66 66)"
                style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)' }}
              />
              <text
                x="66" y="64"
                textAnchor="middle"
                style={{
                  fill: 'var(--theme-text)',
                  fontFamily: 'Montserrat, system-ui, sans-serif',
                  fontWeight: 900,
                  fontSize: 36,
                  letterSpacing: '-0.02em',
                }}
              >{data.score}</text>
              <text
                x="66" y="84"
                textAnchor="middle"
                style={{
                  fill: 'var(--theme-text-muted)',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: 9,
                  letterSpacing: '0.14em',
                }}
              >/ 100</text>
            </svg>
          </div>

          <div className="min-w-0">
            <div className="text-xs uppercase tracking-[0.18em] font-mono font-semibold mb-1" style={{ color: 'var(--pulse-fg)' }}>
              The Pulse · today
            </div>
            <h3
              className="text-2xl sm:text-3xl font-bold pulse-font-heading leading-tight mb-1"
              style={{ color: 'var(--theme-text)' }}
              data-testid="pulse-score-band"
            >
              {band.label}.
            </h3>
            <p className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
              A single live read of how well this site is running. {open ? 'Hiding' : 'Tap'} the breakdown to see why.
            </p>
          </div>
        </div>

        <div className="shrink-0 rounded-full p-2" style={{ background: 'var(--pulse-bg)' }}>
          {open
            ? <ChevronUp size={20} style={{ color: 'var(--pulse-fg)' }} />
            : <ChevronDown size={20} style={{ color: 'var(--pulse-fg)' }} />
          }
        </div>
      </button>

      {open && (
        <div data-testid="pulse-score-breakdown" className="border-t border-[var(--theme-border)] p-5 pt-4 grid sm:grid-cols-2 gap-3">
          {Object.entries(data.components).map(([key, comp]) => {
            const meta = COMPONENT_META[key] || { label: key, hint: '', detailFmt: () => '' };
            const sweepW = Math.max(2, comp.score);
            return (
              <div
                key={key}
                data-testid={`pulse-component-${key}`}
                className="rounded-xl border border-[var(--theme-border)] bg-[var(--theme-surface-hover)] p-3"
              >
                <div className="flex items-baseline justify-between gap-3 mb-1">
                  <div className="font-semibold text-sm pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
                    {meta.label}
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-xs font-mono" style={{ color: 'var(--theme-text-muted)' }}>
                      ×{Math.round(comp.weight * 100)}%
                    </span>
                    <span className="font-bold text-base pulse-font-heading" style={{ color: 'var(--pulse-fg)' }}>
                      {comp.score}
                    </span>
                  </div>
                </div>
                <div className="h-1.5 rounded-full bg-[var(--theme-border)] overflow-hidden mb-2">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${sweepW}%`,
                      background: `linear-gradient(90deg, var(--pulse-fg), var(--pulse-fg))`,
                      transition: 'width 1s cubic-bezier(.4,0,.2,1)',
                    }}
                  />
                </div>
                <div className="text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
                  {meta.hint} · <span style={{ color: 'var(--theme-text)' }}>{meta.detailFmt(comp.detail)}</span>
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
