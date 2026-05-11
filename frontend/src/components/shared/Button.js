/**
 * Button — Iter 216h27 (D3 button hierarchy audit).
 *
 * Caps the platform button vocabulary at 3 variants so the UI never
 * drifts back to the 8+ ad-hoc styles we found in the audit:
 *
 *   PRIMARY    — exactly one per screen. The "do the thing" CTA.
 *                Brand cyan background, dark text.
 *   SECONDARY  — supportive actions next to the primary
 *                (Cancel, Bulk import, Refresh). Outline + subtle hover.
 *   TERTIARY   — low-emphasis text-only links. Used for "View all",
 *                "Manage", "Reset filter".
 *
 * Three sizes — sm / md (default) / lg — so layouts stay consistent.
 * Pass an `icon` to render a Lucide icon inline (icon-left). Pass
 * `data-testid` for testing. Avoid wrapping a `<Link>` — use `as="a"`
 * for anchors instead.
 *
 * Example:
 *   <Button variant="primary" icon={Plus} onClick={...}>Add member</Button>
 *   <Button variant="secondary">Bulk import</Button>
 *   <Button variant="tertiary">View all</Button>
 */
import React from 'react';

const SIZE = {
  sm: 'text-xs px-2.5 py-1.5 gap-1',
  md: 'text-sm px-3 py-2 gap-1.5',
  lg: 'text-sm px-4 py-2.5 gap-2',
};

const ICON_SIZE = { sm: 12, md: 14, lg: 16 };

const VARIANT = {
  primary: {
    className: 'inline-flex items-center justify-center rounded-lg font-extrabold transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
    style: { background: 'var(--color-brand-cyan, #00D6E0)', color: 'var(--color-surface-darker, #0A0A0A)' },
    hoverClass: 'hover:brightness-110',
  },
  secondary: {
    className: 'inline-flex items-center justify-center rounded-lg font-bold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
    style: { borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text, #0A0A0A)', background: 'var(--theme-surface, #FFFFFF)' },
    hoverClass: 'hover:bg-zinc-50',
  },
  tertiary: {
    className: 'inline-flex items-center font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed underline-offset-2',
    style: { color: 'var(--theme-text-muted, #71717A)' },
    hoverClass: 'hover:text-zinc-900 hover:underline',
  },
  destructive: {
    className: 'inline-flex items-center justify-center rounded-lg font-bold transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
    style: { background: '#FEE2E2', color: '#B91C1C', borderColor: '#FECACA' },
    hoverClass: 'hover:bg-red-100',
  },
};

export const Button = React.forwardRef(({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconRight: IconRight,
  loading = false,
  disabled = false,
  className = '',
  children,
  as = 'button',
  ...rest
}, ref) => {
  const v = VARIANT[variant] || VARIANT.primary;
  const Component = as;
  return (
    <Component
      ref={ref}
      type={as === 'button' ? (rest.type || 'button') : undefined}
      disabled={as === 'button' ? (disabled || loading) : undefined}
      className={`${v.className} ${SIZE[size] || SIZE.md} ${v.hoverClass} ${className}`}
      style={v.style}
      {...rest}
    >
      {Icon && !loading && <Icon size={ICON_SIZE[size] || 14} aria-hidden />}
      {loading && (
        <svg className="animate-spin" width={ICON_SIZE[size] || 14} height={ICON_SIZE[size] || 14} viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
          <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
      )}
      <span>{children}</span>
      {IconRight && <IconRight size={ICON_SIZE[size] || 14} aria-hidden />}
    </Component>
  );
});
Button.displayName = 'Button';

export default Button;
