/**
 * Button — Iter 216h27 (D3 button hierarchy audit) + Iter 216h37 (icon size).
 *
 * Caps the platform button vocabulary at 5 variants × 5 sizes so the UI
 * never drifts back to the 8+ ad-hoc styles we found in the audit:
 *
 *   PRIMARY            — exactly one per screen. The "do the thing" CTA.
 *                        Brand cyan background, dark text.
 *   SECONDARY          — supportive actions next to the primary
 *                        (Cancel, Bulk import, Refresh). Outline + hover.
 *   TERTIARY           — low-emphasis text-only links ("View all",
 *                        "Manage", "Reset filter").
 *   DESTRUCTIVE        — irreversible danger CTA (Delete, Cancel plan).
 *                        Pale red background, dark red text.
 *   GHOST              — Iter 216h37. Icon-only or icon+label row actions
 *                        (Edit, Archive, Toggle, Copy). No background;
 *                        soft hover surface. Used inside dense tables and
 *                        drawer headers where a bordered button would
 *                        compete with row content.
 *   GHOST_DESTRUCTIVE  — Iter 216h37. Same as ghost but red-tinted hover —
 *                        for row-level delete / archive icons.
 *
 * Sizes — sm / md (default) / lg / icon / iconSm — keep layouts consistent.
 * The `icon` / `iconSm` sizes are square (equal padding all sides) and
 * skip the text span so a single Lucide icon centres cleanly. Pair them
 * with `ghost` + a `title=""` for accessibility.
 *
 * Pass an `icon` to render a Lucide icon inline (icon-left). Pass
 * `data-testid` for testing. Avoid wrapping a `<Link>` — use `as="a"`
 * for anchors instead.
 *
 * Example:
 *   <Button variant="primary" icon={Plus}>Add member</Button>
 *   <Button variant="secondary">Bulk import</Button>
 *   <Button variant="tertiary">View all</Button>
 *   <Button variant="ghost" size="icon" icon={Edit3} title="Edit" />
 *   <Button variant="ghostDestructive" size="iconSm" icon={Trash2} title="Delete" />
 */
import React from 'react';

const SIZE = {
  sm: 'text-xs px-2.5 py-1.5 gap-1',
  md: 'text-sm px-3 py-2 gap-1.5',
  lg: 'text-sm px-4 py-2.5 gap-2',
  icon: 'p-2 gap-0',
  iconSm: 'p-1.5 gap-0',
};

const ICON_SIZE = { sm: 12, md: 14, lg: 16, icon: 14, iconSm: 12 };

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
  ghost: {
    // Iter 216h37 — Row-action neutral icon button. No border, no
    // background by default; reveals a soft hover surface so it sits
    // quietly inside dense tables and drawer headers.
    className: 'inline-flex items-center justify-center rounded-md font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
    style: { color: 'var(--theme-text-muted, #71717A)', background: 'transparent' },
    hoverClass: 'hover:bg-black/[0.06] hover:text-zinc-900 dark:hover:bg-white/10 dark:hover:text-white',
  },
  ghostDestructive: {
    // Iter 216h37 — Row-action danger icon button. Red hover surface +
    // text so it visually telegraphs "irreversible" without shouting.
    className: 'inline-flex items-center justify-center rounded-md font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
    style: { color: '#FCA5A5', background: 'transparent' },
    hoverClass: 'hover:bg-red-500/15 hover:text-red-300',
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
  const iconSize = ICON_SIZE[size] || 14;
  // Iter 216h37 — Icon-only sizes (`icon`, `iconSm`) deliberately omit
  // the children span so a single Lucide icon centres in a square box.
  const isIconOnly = size === 'icon' || size === 'iconSm';
  return (
    <Component
      ref={ref}
      type={as === 'button' ? (rest.type || 'button') : undefined}
      disabled={as === 'button' ? (disabled || loading) : undefined}
      className={`${v.className} ${SIZE[size] || SIZE.md} ${v.hoverClass} ${className}`}
      style={v.style}
      {...rest}
    >
      {Icon && !loading && <Icon size={iconSize} aria-hidden />}
      {loading && (
        <svg className="animate-spin" width={iconSize} height={iconSize} viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
          <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </svg>
      )}
      {!isIconOnly && children && <span>{children}</span>}
      {IconRight && <IconRight size={iconSize} aria-hidden />}
    </Component>
  );
});
Button.displayName = 'Button';

export default Button;
