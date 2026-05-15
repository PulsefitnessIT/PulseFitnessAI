import React from 'react';

/**
 * MOD Classification Banner.
 *
 * Iter 216h115 — sticky banner shown on every MOD surface to remind
 * users of the platform's approved classification ceiling (OFFICIAL by
 * default; configurable per-tenant via ``organization.classification``
 * if MOD ever approves OFFICIAL-SENSITIVE handling).
 *
 * Renders nothing for non-MOD users.
 */
export default function ClassificationBanner({ level = 'OFFICIAL', dense = false, rightSlot = null }) {
  const label = (level || 'OFFICIAL').toUpperCase();
  return (
    <div
      data-testid="mod-classification-banner"
      role="note"
      aria-label={`Classification: ${label}`}
      className={`w-full font-extrabold uppercase tracking-[0.3em] ${
        dense ? 'text-[10px] py-1' : 'text-[11px] py-1.5'
      } flex items-center justify-center gap-3 px-3 relative`}
      style={{
        background: '#0A0B10',
        color: '#19CDFF',
        borderTop: '1px solid rgba(25,205,255,0.25)',
        borderBottom: '1px solid rgba(25,205,255,0.25)',
        letterSpacing: '0.3em',
      }}
    >
      <span aria-hidden="true">◆</span>
      {label}
      <span aria-hidden="true">◆</span>
      {rightSlot && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center" data-testid="mod-classification-right-slot">
          {rightSlot}
        </div>
      )}
    </div>
  );
}
