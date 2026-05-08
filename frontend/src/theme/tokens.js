/**
 * GymAxis Design Tokens — single source of truth.
 *
 * Use these constants instead of inline hex literals across the app.
 * If you find yourself reaching for `bg-[#0055FF]` or `style={{ color: '#19CDFF' }}`,
 * import from here instead.
 */

export const colors = {
  // ── PRIMARY BRAND ─────────────────────────────────────────────
  // Only two blue accents in the whole platform. Use brandCyan for
  // Pulse operator surfaces (Strategy B), brandBlue for GymAxis
  // marketing + Master Admin.
  brandCyan:       '#19CDFF',  // Pulse Fitness accent (cyan)
  brandCyanHover:  '#66CCFF',  // hover/light cyan (legacy #66ccff)
  brandBlue:       '#0055FF',  // GymAxis accent
  brandBlueHover:  '#0044CC',
  brandBlueDark:   '#003DA5',

  // ── NEUTRALS ──────────────────────────────────────────────────
  ink:             '#0A0C10',  // Body text on light surfaces
  inkAlt:          '#0A0A0A',  // Legacy ultra-black (mostly in CRM)
  inkMuted:        '#52525B',
  textMuted:       '#A1A1AA',  // zinc-400 — the most common muted text
  textFaint:       '#71717A',  // zinc-500
  textFaintAlt:    '#6B7280',  // legacy gray-500

  paper:           '#FFFFFF',
  paperAlt:        '#F4F4F5',
  border:          '#E4E4E7',
  borderAlt:       '#E5E7EB',  // legacy Tailwind border colour
  borderStrong:    '#D4D4D8',

  // ── DARK MODE SURFACES ────────────────────────────────────────
  surfaceDark:     '#0A0A0A',
  surfaceDarkAlt:  '#121212',
  surfaceDarker:   '#05070A',  // even darker, used for Memberships
  surfaceDarkPanel:'#1F1F1F',
  surfaceDarkPanelAlt:'#1B1D1D',
  inkOnDark:       '#FAFAFA',
  inkOnDarkMuted:  '#A3A3A3',
  borderDark:      '#262626',

  // ── SEMANTIC ──────────────────────────────────────────────────
  success:         '#10B981',
  successAlt:      '#34C759',  // legacy iOS-green used heavily in CRM
  successLight:    '#34D399',
  warning:         '#F59E0B',
  warningAlt:      '#FBBF24',
  danger:          '#EF4444',
  dangerAlt:       '#FF3B30',  // legacy iOS-red
  info:            '#3B82F6',
  infoIOS:         '#007AFF',  // legacy iOS-blue — DEPRECATED for new code

  // ── ACCENT PALETTE ────────────────────────────────────────────
  accentPurple:    '#9966FF',  // Marketing
  accentIndigo:    '#5856D6',
};

/**
 * Canonical token names — these are the ONLY colours new code should use.
 * `legacy*` and `*Alt` aliases exist so existing files can migrate incrementally
 * without visual regression.
 */

/**
 * Spacing scale — ALWAYS use these, never raw px.
 * Default card/section padding is `p-5` (20px). Override only with reason.
 */
export const spacing = {
  xs: '0.5rem',  //  8px — chip / icon button gap
  sm: '0.75rem', // 12px
  md: '1rem',    // 16px
  lg: '1.25rem', // 20px — DEFAULT card padding
  xl: '2rem',    // 32px — page section gap
  '2xl': '3rem', // 48px
};

/** Border radii. */
export const radii = {
  sm: '0.375rem',  //  6px — tags / pills
  md: '0.5rem',    //  8px — buttons (square corners)
  lg: '0.75rem',   // 12px — cards (DEFAULT)
  xl: '1rem',      // 16px — modals
  full: '9999px',  // pills / capsules
};

/**
 * Typography hierarchy. Always pair these classes (Tailwind) — don't mix.
 *   H1   -> text-3xl sm:text-4xl font-bold    (page title)
 *   H2   -> text-xl sm:text-2xl font-semibold (section header)
 *   H3   -> text-lg font-semibold             (sub-section / card title)
 *   body -> text-sm                            (default copy)
 *   meta -> text-xs                            (timestamps, captions)
 */
export const typography = {
  h1: 'text-3xl sm:text-4xl font-bold tracking-tight pulse-font-heading',
  h2: 'text-xl sm:text-2xl font-semibold pulse-font-heading',
  h3: 'text-lg font-semibold pulse-font-body',
  body: 'text-sm pulse-font-body',
  meta: 'text-xs pulse-font-body',
};

/** Motion — keep transitions short and ease-out for native feel. */
export const motion = {
  fast: 'transition-colors duration-150 ease-out',
  base: 'transition-all duration-200 ease-out',
  slow: 'transition-all duration-300 ease-out',
};

/**
 * Card preset — the ONE card pattern allowed.
 * Default card uses light-zinc border + theme-aware text colour.
 *
 * Usage:
 *   <div className={cardClass()}>...</div>
 *   <div className={cardClass({ tone: 'subtle' })}>...</div>
 */
export const cardClass = ({ tone = 'default', interactive = false } = {}) => {
  const base = 'rounded-xl border bg-card text-card-foreground transition-shadow duration-150';
  const tones = {
    default: 'border-zinc-200 dark:border-white/10',
    subtle:  'border-zinc-100 dark:border-white/5 bg-zinc-50/40 dark:bg-white/[0.02]',
    accent:  'border-[#19CDFF]/30 bg-[#19CDFF]/5',
  };
  const hover = interactive ? 'hover:shadow-md hover:-translate-y-0.5' : '';
  return `${base} ${tones[tone] || tones.default} ${hover}`.trim();
};

/**
 * The ONE allowed button mapping. Use the shadcn <Button variant=... />
 * component — do NOT add per-call `bg-[#xxx]` overrides.
 *
 *   primary    -> <Button>            (cyan, dark text)  — main CTA
 *   secondary  -> <Button variant="outline">             — supporting action
 *   ghost      -> <Button variant="ghost">               — tertiary / cancel
 *   danger     -> <Button variant="destructive">         — delete / revoke
 *   link       -> <Button variant="link">                — inline text link
 */

const designTokens = { colors, spacing, radii, typography, motion, cardClass };
export default designTokens;
