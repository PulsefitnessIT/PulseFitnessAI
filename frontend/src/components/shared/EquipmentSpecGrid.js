/**
 * EquipmentSpecGrid — shared atomic component for equipment spec/stat
 * tile layouts. Used by:
 *   • Pulse Fitness EquipmentDetailContent
 *   • GymAxis EquipmentInfoTab Overview tab
 *   • Future: Faults Detail Panel, Audit Reviewer, Service Desk drawer
 *
 * Iter 216o — extracted to avoid the same 6-tile grid being copied
 * across portals with subtle drift. Theme-aware (every value uses
 * `var(--theme-*)` tokens) so the same component renders correctly in
 * GymAxis blue and Pulse cyan without any prop other than `accent`.
 *
 * Props:
 *   tiles: Array<{ label: string, value: string|node, mono?: boolean,
 *                  accent?: boolean, testId?: string }>
 *   columns: 2 | 3 (default 3 — collapses to 2 on mobile)
 *   accent: CSS colour for the "accent" tile value (defaults to
 *           --color-brand-blue; pass `var(--color-brand-cyan-hover)`
 *           on Pulse pages).
 */
import React from 'react';

const EquipmentSpecGrid = ({ tiles, columns = 3, accent = 'var(--color-brand-blue)' }) => {
  if (!Array.isArray(tiles) || tiles.length === 0) return null;
  const colClass = columns === 2 ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3';
  return (
    <div className={`grid ${colClass} gap-2 sm:gap-3`} data-testid="equipment-spec-grid">
      {tiles.map((t, i) => {
        const value = t.value ?? '—';
        const isAccent = !!t.accent;
        const isMono = !!t.mono;
        const valueColor = isAccent ? accent : 'var(--theme-text)';
        const valueClass = `font-medium text-sm sm:text-base mt-0.5 truncate${isMono ? ' font-mono' : ''}`;
        const titleStr = typeof t.value === 'string' ? t.value : '';
        return (
          <div
            key={t.label || i}
            className="p-2.5 sm:p-3 bg-[var(--color-ink-alt)] border border-[var(--theme-border)] rounded-lg min-w-0 text-center"
            data-testid={t.testId || `equip-spec-${(t.label || '').toLowerCase().replace(/\W+/g, '-')}`}
          >
            <p className="text-[10px] sm:text-xs uppercase tracking-wide truncate" style={{ color: 'var(--theme-text-muted)' }}>
              {t.label}
            </p>
            <p className={valueClass} style={{ color: valueColor }} title={titleStr}>
              {value || <span className="italic font-normal" style={{ color: 'var(--theme-text-muted)' }}>—</span>}
            </p>
          </div>
        );
      })}
    </div>
  );
};

export default EquipmentSpecGrid;
