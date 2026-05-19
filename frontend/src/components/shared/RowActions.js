/**
 * RowActions — Iter 216h40
 *
 * Cluster for 2-4 row-action icon buttons (Edit / Archive / Delete /
 * Toggle / Copy) that should reveal on hover over the parent row on
 * desktop, but stay visible on touch devices (because hover semantics
 * are gummy on phones/tablets).
 *
 * Pairs with the iter 216h37 `ghost` / `ghostDestructive` Button
 * variants. The parent row MUST have the Tailwind `group` class for
 * group-hover to work; if you forget it the actions just stay hidden
 * on desktop — surfacing the bug fast.
 *
 * Why a cluster component?
 *   • The hover-reveal pattern repeats 8+ times across CRM / Memberships
 *     row UIs and has drifted into 4 slightly different incantations
 *     (`opacity-0 group-hover:opacity-100 transition` / `... transition-opacity`
 *     / `flex items-center gap-1 ...` / etc.). One source of truth.
 *   • Touch devices stick on hover after the first tap, so the
 *     hidden-by-default approach is a UX trap on iPad/iPhone. This
 *     component forces actions visible when (hover: none) via a CSS
 *     media query injected as inline style — no Tailwind plugin needed.
 *
 * Props:
 *   • `children` — usually 2-4 `<Button variant="ghost"... />` icons.
 *   • `alwaysVisible` (bool) — opt out of the hover-reveal; for cases
 *     where the actions need to stay visible (e.g. detail pages).
 *   • `align` — `right` (default) | `left`.
 *   • `gap` — `0.5` | `1` (default) | `1.5` | `2`.
 *   • `className` — extra Tailwind on the wrapper.
 *   • `data-testid` — for tests.
 *
 * Usage:
 *   <div className="group flex items-center justify-between ...">
 *     <RowMeta />
 *     <RowActions data-testid="plan-row-actions">
 *       <Button variant="ghost" size="iconSm" icon={Edit3} title="Edit" />
 *       <Button variant="ghostDestructive" size="iconSm" icon={Trash2} title="Archive" />
 *     </RowActions>
 *   </div>
 */

const GAP = {
  0.5: 'gap-0.5',
  1: 'gap-1',
  1.5: 'gap-1.5',
  2: 'gap-2',
};

const ALIGN = {
  left: 'justify-start',
  right: 'justify-end',
};

const RowActions = ({
  children,
  alwaysVisible = false,
  align = 'right',
  gap = 1,
  className = '',
  ...rest
}) => {
  // Always visible on touch / no-hover devices. The hover-reveal only
  // kicks in on (hover: hover) AND (pointer: fine) — real cursor.
  // We use the `coarse-hover-always-on` global utility class to
  // re-show the cluster on touch, defined inline at the bottom of
  // this file (single global rule, hoisted via a <style> tag).
  const hoverClass = alwaysVisible
    ? 'opacity-100'
    : 'opacity-0 group-hover:opacity-100 row-actions-hover-reveal';

  return (
    <div
      className={`inline-flex items-center shrink-0 ${GAP[gap] || GAP[1]} ${ALIGN[align] || ALIGN.right} ${hoverClass} transition-opacity duration-150 ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
};

// Inject the (hover: none) → opacity-100 rule once. Module-level so
// it runs at import time; idempotent because we tag the style block.
if (typeof document !== 'undefined' && !document.getElementById('row-actions-style')) {
  const style = document.createElement('style');
  style.id = 'row-actions-style';
  style.textContent = `
    @media (hover: none), (pointer: coarse) {
      .row-actions-hover-reveal { opacity: 1 !important; }
    }
  `;
  document.head.appendChild(style);
}

export default RowActions;
