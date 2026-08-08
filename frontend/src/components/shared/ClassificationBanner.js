/**
 * MOD Classification Banner.
 *
 * Sticky marking shown on every MOD surface to remind users of the platform's
 * approved classification ceiling. Defaults to OFFICIAL-SENSITIVE for MOD;
 * configurable per-tenant via ``organization.classification``.
 *
 * OFFICIAL-SENSITIVE is styled distinctly (amber) from OFFICIAL (cyan) so the
 * higher marking is unmistakable at a glance.
 */
const LEVEL_STYLES = {
  'OFFICIAL-SENSITIVE': {
    background: '#1a1205',
    color: '#fbbf24',
    border: 'rgba(251,191,36,0.35)',
  },
  'OFFICIAL': {
    background: '#0A0B10',
    color: '#19CDFF',
    border: 'rgba(25,205,255,0.25)',
  },
};

export default function ClassificationBanner({ level = 'OFFICIAL-SENSITIVE', dense = false, rightSlot = null }) {
  const label = (level || 'OFFICIAL-SENSITIVE').toUpperCase();
  const s = LEVEL_STYLES[label] || LEVEL_STYLES['OFFICIAL'];
  return (
    <div
      data-testid="mod-classification-banner"
      data-classification={label}
      role="note"
      aria-label={`Classification: ${label}`}
      className={`w-full font-extrabold uppercase tracking-[0.3em] ${
        dense ? 'text-[10px] py-1' : 'text-[11px] py-1.5'
      } flex items-center justify-center gap-3 px-3 relative`}
      style={{
        background: s.background,
        color: s.color,
        borderTop: `1px solid ${s.border}`,
        borderBottom: `1px solid ${s.border}`,
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
