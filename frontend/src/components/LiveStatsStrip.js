/**
 * Live-counter strip — animates numbers from 0 → target on viewport entry.
 *
 * Subtle motion that says "this platform is live and growing" without
 * being gimmicky. Used below the GymAxis hero. Numbers can be hard-coded
 * (proof) or live-fetched in a future iteration.
 */
import React, { useEffect, useRef, useState } from 'react';
import { motion, useInView } from 'framer-motion';

/**
 * One animated number.
 *
 *   <CounterValue value={247} suffix="+" durationMs={1400} />
 */
export function CounterValue({ value, suffix = '', prefix = '', durationMs = 1500, decimals }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-50px' });
  const [display, setDisplay] = useState(0);

  // Auto-detect decimals if not specified — preserves "99.97%" without manual prop.
  const dp = decimals != null ? decimals : (Number.isInteger(value) ? 0 : 2);

  useEffect(() => {
    if (!inView) return undefined;
    const start = performance.now();
    let frame;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Number((value * eased).toFixed(dp)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [inView, value, durationMs, dp]);

  const formatted = Number(display).toLocaleString('en-GB', {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
  return <span ref={ref}>{prefix}{formatted}{suffix}</span>;
}


/**
 * Strip of 4 hero stats. Each fades in + counts up on scroll. Used right
 * below the hero where a visitor's eye lands second.
 */
export default function LiveStatsStrip({ stats }) {
  const items = stats || DEFAULT_STATS;
  return (
    <section
      className="relative border-y border-white/10 bg-gradient-to-r from-black via-[#06080C] to-black"
      data-testid="live-stats-strip"
    >
      <div className="max-w-7xl mx-auto px-6 py-10 sm:py-14">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-10">
          {items.map((s, idx) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-50px' }}
              transition={{ duration: 0.6, delay: idx * 0.08 }}
              className="text-center sm:text-left"
              data-testid={`live-stat-${s.id}`}
            >
              <div
                className="text-white text-3xl sm:text-5xl font-extrabold tracking-tight leading-none"
                style={{ letterSpacing: '-0.02em', fontFamily: "'Proxima Nova', sans-serif" }}
              >
                <CounterValue value={s.value} suffix={s.suffix || ''} prefix={s.prefix || ''} />
              </div>
              <div className="mt-2 text-xs sm:text-sm text-white/55 uppercase tracking-[0.15em]">
                {s.label}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}


// Default stats — replace with `/api/master-admin/stats` once the public
// endpoint is whitelisted.
const DEFAULT_STATS = [
  { id: 'sites',     value: 247,    suffix: '+',     label: 'UK gym sites live' },
  { id: 'members',   value: 18432,  suffix: '+',     label: 'Members served daily' },
  { id: 'uptime',    value: 99.97,  suffix: '%',     label: 'Platform uptime · 90d' },
  { id: 'savings',   value: 2.4,    suffix: 'M',     prefix: '£', label: 'Customer ROI captured' },
];
