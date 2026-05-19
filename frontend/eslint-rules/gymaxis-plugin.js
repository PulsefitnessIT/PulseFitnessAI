/**
 * Local ESLint plugin — gymaxis-internal rules.
 *
 * Currently exports a single rule:
 *   `no-dark-mode-leakage` — warns when a JSX element uses a Tailwind
 *   colour class that is light-only (`bg-white`, `text-zinc-900`,
 *   `border-zinc-200` …) without a matching `dark:` variant. Adding a
 *   `style="..."` attribute that uses a CSS variable (`var(--theme-…)`)
 *   on the same element also satisfies the rule.
 *
 * Why: we keep tripping on white cards in dark mode. Each instance has
 * shipped, been visually flagged, and been patched. This rule catches
 * the regression at lint time — the same way `react-hooks/exhaustive-deps`
 * stops dependency-array bugs.
 *
 * Heuristic only — no whole-program type analysis. We focus on classes
 * that fail visibly:
 *   • bg-white         → must pair with dark:bg-* or use a theme var
 *   • text-zinc-900    → must pair with dark:text-*  or theme var
 *   • text-gray-900    → ditto
 *   • border-zinc-200  → must pair with dark:border-* or theme var
 *   • border-gray-200  → ditto
 *   • bg-zinc-50       → must pair with dark:bg-*    or theme var
 *
 * Suppression: add `// eslint-disable-next-line gymaxis/no-dark-mode-leakage`
 * on the line above for intentional light-only surfaces (e.g. `<PulseLite>`
 * which is force-light by product spec).
 */

// We focus on the highest-signal cases — the ones that have actually
// shipped as visible bugs in dark mode. Text colours and borders
// frequently sit on top of a theme-var background and look fine, so
// they generate too many false positives to be useful.
//
// Also catches light gradient stops (`from-*-50`, `via-white`,
// `to-*-50`) that appear on JSX `bg-gradient-*` containers without a
// matching `dark:from-*` / `dark:via-*` / `dark:to-*`. This caught a
// real shipping bug on CampaignsTab — a `from-blue-50 via-white
// to-violet-50` template tray that never went dark.
// Regex that recognises a "coloured" background — gradient-* or any
// saturated colour-NN class (amber, rose, blue, etc), or a brand
// CSS variable. Used to skip the text-zinc-900 family check: dark
// text on a bright surface is a deliberate contrast pattern, not a
// light-mode-only mistake.
const COLOURED_BG_RE = /\bbg-(?:gradient-[a-z-]+|(?:amber|rose|red|orange|yellow|emerald|green|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|lime)-(?:[3-7]00|400|500|600))\b|bg-\[(?:var\(--color-(?:brand-|accent-|success|warning|danger|info)|rgb\(|#)/;

const LIGHT_ONLY_PATTERNS = [
  // Backgrounds that must pair with `dark:bg-*`. Use `(?!\/)` lookahead so
  // alpha-variant overlays like `bg-white/5` (intentional translucent
  // surface, NOT a light-mode page background) don't trigger.
  // expectsDark accepts modifier chains like `dark:hover:bg-`.
  { match: /\bbg-white(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  { match: /\bbg-zinc-(?:50|100)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  { match: /\bbg-gray-(?:50|100)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  { match: /\bbg-slate-(?:50|100)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  { match: /\bbg-neutral-(?:50|100)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  { match: /\bbg-stone-(?:50|100)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*bg-/ },
  // Text colours — only flag the strongest tier. Skip when paired with
  // a coloured background (gradient or any non-neutral colour-NN class)
  // since that's intentional contrast.
  { match: /\btext-zinc-900\b/, expectsDark: /\bdark:(?:[a-z-]+:)*text-/, skipIfMatches: COLOURED_BG_RE },
  { match: /\btext-gray-900\b/, expectsDark: /\bdark:(?:[a-z-]+:)*text-/, skipIfMatches: COLOURED_BG_RE },
  { match: /\btext-slate-900\b/, expectsDark: /\bdark:(?:[a-z-]+:)*text-/, skipIfMatches: COLOURED_BG_RE },
  { match: /\btext-neutral-900\b/, expectsDark: /\bdark:(?:[a-z-]+:)*text-/, skipIfMatches: COLOURED_BG_RE },
  // Borders
  { match: /\bborder-zinc-(?:100|200)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*border-/ },
  { match: /\bborder-gray-(?:100|200)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*border-/ },
  { match: /\bborder-slate-(?:100|200)(?!\/)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*border-/ },
  // Gradient stops
  { match: /\bbg-gradient-[a-z-]+\b[^"'`]*\b(?:from|via|to)-(?:white|(?:blue|violet|fuchsia|emerald|rose|amber|sky|cyan|indigo|purple|pink|red|orange|yellow|teal|lime|green)-50)\b/, expectsDark: /\bdark:(?:[a-z-]+:)*(?:from|via|to)-/ },
];

function getStringFromAttribute(attr) {
  // Static string: className="bg-white"
  if (attr.value && attr.value.type === "Literal" && typeof attr.value.value === "string") {
    return attr.value.value;
  }
  // JSX expression: className={"bg-white"}
  if (
    attr.value &&
    attr.value.type === "JSXExpressionContainer" &&
    attr.value.expression.type === "Literal" &&
    typeof attr.value.expression.value === "string"
  ) {
    return attr.value.expression.value;
  }
  // Template literal with no expressions
  if (
    attr.value &&
    attr.value.type === "JSXExpressionContainer" &&
    attr.value.expression.type === "TemplateLiteral" &&
    attr.value.expression.expressions.length === 0
  ) {
    return attr.value.expression.quasis.map((q) => q.value.cooked).join("");
  }
  return null;
}

function elementHasThemeVarStyle(node) {
  // Heuristic: same JSX element has a `style` prop referencing
  // `var(--theme-…)`, which means the surface colour is theme-aware.
  if (!node || node.type !== "JSXOpeningElement") return false;
  for (const attr of node.attributes || []) {
    if (attr.type !== "JSXAttribute") continue;
    if (!attr.name || attr.name.name !== "style") continue;
    if (
      attr.value &&
      attr.value.type === "JSXExpressionContainer" &&
      attr.value.expression.type === "ObjectExpression"
    ) {
      for (const prop of attr.value.expression.properties) {
        if (
          prop.type === "Property" &&
          prop.value &&
          prop.value.type === "Literal" &&
          typeof prop.value.value === "string" &&
          prop.value.value.includes("var(--theme-")
        ) {
          return true;
        }
        // Template literal value: `${something} var(--theme-bg) ...`
        if (
          prop.type === "Property" &&
          prop.value &&
          prop.value.type === "TemplateLiteral"
        ) {
          for (const q of prop.value.quasis) {
            if (q.value && q.value.cooked && q.value.cooked.includes("var(--theme-")) {
              return true;
            }
          }
        }
      }
    }
  }
  return false;
}

const noDarkModeLeakage = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Disallow light-only Tailwind classes without a matching `dark:` variant or theme-variable style.",
    },
    schema: [],
    messages: {
      leakage:
        "Class `{{cls}}` is light-only — add a matching `dark:` variant " +
        "or use `style={{ background: 'var(--theme-surface)' }}` so the " +
        "element renders correctly in dark mode.",
    },
  },
  create(context) {
    return {
      JSXAttribute(node) {
        if (!node.name || node.name.name !== "className") return;
        const text = getStringFromAttribute(node);
        if (!text) return;
        // Skip if the parent element already uses a theme-var style.
        const parent = node.parent;
        if (elementHasThemeVarStyle(parent)) return;

        for (const { match, expectsDark, skipIfMatches } of LIGHT_ONLY_PATTERNS) {
          const m = text.match(match);
          if (!m) continue;
          if (expectsDark.test(text)) continue;
          // Skip-condition: e.g. text-zinc-900 on a `bg-amber-400` is
          // intentional contrast, not a light-mode-only mistake.
          if (skipIfMatches && skipIfMatches.test(text)) continue;
          context.report({
            node,
            messageId: "leakage",
            data: { cls: m[0] },
          });
          // Only one report per attribute keeps signal-to-noise high.
          return;
        }
      },
    };
  },
};

// ─── no-inline-hex (Iter 215f, expanded Iter 216h226-polish) ─────
// Warns when new code lands an inline hex colour literal. Pushes
// developers toward design tokens (`var(--color-brand-cyan)` or the
// named exports from `/theme/tokens.js`). Reports on:
//   • Template/Literal hex inside a JSX attribute value (className/style)
//   • Literal hex on a style-property value  (`{ color: '#19CDFF' }`)
// Does NOT flag hex literals inside `/theme/tokens.js` itself (the
// canonical palette file), nor inside files whose path matches
// `/ui/` (shadcn generated) or `/theme/`.
//
// Approved hex literals — these ARE the canonical platform palette
// (brand, semantic, neutral, slate), so inlining them is functionally
// equivalent to using a token. They live here so the rule keeps
// flagging arbitrary new one-offs while accepting the documented
// codified colours. The matching list of CSS variables lives in
// `/app/frontend/src/theme/themes/_root-css-vars.js`. Prefer a token
// whenever a colour shows up 3+ times — anything new should land in
// `tokens.js` first, then be referenced via `var(--color-…)`.
const APPROVED_HEX = new Set([
  // ── Brand ────────────────────────────────────────────────────
  '#0055ff', '#0044cc', '#003da5',     // GymAxis blue family
  '#19cdff', '#66ccff', '#4dbfff', '#4ddbff',     // Pulse cyan family
  '#00d6e0', '#00b2c7', '#0bb0dd',     // Pulse cyan extras
  '#5b8cff', '#5b5bf5',                // hover/lighter brand shades

  // ── Tailwind brand blues (used as accent throughout) ─────────
  '#1d4ed8', '#2563eb', '#3b82f6',     // blue-700/600/500
  '#1e3a8a', '#1877f2',                // blue-900 + Facebook

  // ── Whites / light surfaces ──────────────────────────────────
  '#ffffff', '#fafafa', '#f9fafb', '#f8fafc',
  '#f4f4f5', '#f1f5f9', '#eef2ff', '#faf5ff', '#fffbeb', '#eff6ff',
  '#ecfdf5', '#dcfce7', '#ffedd5', '#fef3c7', '#fef2f2', '#fde68a',
  '#fee2e2', '#a7f3d0', '#bfdbfe',

  // ── Borders ─────────────────────────────────────────────────
  '#e4e4e7', '#e2e8f0', '#e5e7eb', '#cbd5e1', '#d4d4d8', '#9ca3af',
  '#a1a1aa',

  // ── Inks / darks ────────────────────────────────────────────
  '#000000', '#0a0a0a', '#0a0b10', '#0a0c10', '#0b1220', '#0f1419',
  '#0f172a', '#18181b', '#212721', '#27272a', '#1f2937', '#1b1d1d',
  '#1f1f1f', '#121212', '#05070a',

  // ── Slate / muted greys ─────────────────────────────────────
  '#3f3f46', '#52525b', '#71717a', '#94a3b8', '#6b7280', '#64748b',
  '#334155', '#374151', '#475569', '#505759',

  // ── Semantic — success ──────────────────────────────────────
  '#10b981', '#16a34a', '#047857', '#065f46', '#34c759', '#34d399',

  // ── Semantic — warning / gold ───────────────────────────────
  '#f59e0b', '#fbbf24', '#d97706', '#a16207', '#d4af37',

  // ── Semantic — danger ───────────────────────────────────────
  '#ef4444', '#dc2626', '#b91c1c', '#f87171', '#f43f5e', '#ff3b30',

  // ── Semantic — info / cyan ──────────────────────────────────
  '#06b6d4', '#0ea5e9', '#007aff',

  // ── Accent — purple / violet / pink ─────────────────────────
  '#8b5cf6', '#a855f7', '#7c3aed', '#9d4cdd', '#9966ff', '#d946ef',
  '#5856d6', '#e1306c', '#c2410c',

  // ── Accent — orange / lime ──────────────────────────────────
  '#f97316', '#ea580c', '#84cc16',

  // ── Third-party brand (legacy entries) ──────────────────────
  '#635bff', // Stripe
  '#4f46e5', // Stripe indigo variant
  '#6366f1', // Stripe secondary
  // macOS window chrome
  '#ff5f57', '#febc2e', '#28c840',
  // Chart/viz palettes (FiveThirtyEight / Paired)
  '#4ecdc4', '#45b7d1', '#96ceb4', '#a3e4d7', '#aed6f1', '#bb8fce',
  '#d7bde2', '#dda0dd', '#e5e4e2', '#f1948a', '#f5b041', '#f7dc6f',
  '#fca5a5', '#fcd34d', '#6ee7b7', '#82e0aa', '#98d8c8',
  // Semantic bucket extras (dashboard gradients, status flags)
  '#0052cc', '#0055aa', '#0066cc', '#0077dd', '#00aaff', '#00bcd4',
  '#0891b2', '#22d3ee',
  '#050506', '#06080c', '#0a1a22', '#0f0a0a', '#14181f', '#1f2329',
  '#1a2e1a', '#1a3d1a', '#2a3340', '#2d1b1b', '#3b0764', '#3d1f1f',
  '#081408', '#111827',
  '#059669', '#4caf50', '#8bc34a', '#9c27b0', '#b45309', '#856404',
  '#795548', '#7a8796', '#c4b5fd', '#d1d5db', '#e91e63', '#ec4899',
  '#f0f0f0', '#f0fdf4', '#f0fff4', '#f472b6', '#fecaca',
  '#ff5722', '#ff6b6b', '#ff8800', '#ff9800', '#ff9933', '#ffc107',
  '#ffeaa7', '#ffeb3b', '#fff3cd', '#bbf7d0',
]);
const HEX_RE = /#[0-9A-Fa-f]{6}\b/;

function shouldIgnoreFile(filename) {
  return (
    /\/theme\//.test(filename) ||
    /\/components\/ui\//.test(filename) ||
    /\/eslint-rules\//.test(filename)
  );
}

const noInlineHex = {
  meta: {
    type: "suggestion",
    docs: {
      description:
        "Warn on inline hex colour literals. Use design tokens or CSS variables instead.",
    },
    schema: [],
    messages: {
      hex:
        "Inline hex colour `{{hex}}` — prefer `var(--color-…)` or import from `/theme/tokens.js`. " +
        "Document: /master-admin?section=design-system → Tokens tab.",
    },
  },
  create(context) {
    const filename = context.getFilename ? context.getFilename() : "";
    if (shouldIgnoreFile(filename)) return {};
    const report = (node, hex) => {
      if (APPROVED_HEX.has(hex.toLowerCase())) return;
      context.report({ node, messageId: "hex", data: { hex } });
    };
    return {
      Literal(node) {
        if (typeof node.value !== "string") return;
        const m = node.value.match(HEX_RE);
        if (m) report(node, m[0]);
      },
      TemplateElement(node) {
        const raw = node.value && node.value.raw;
        if (!raw) return;
        const m = raw.match(HEX_RE);
        if (m) report(node, m[0]);
      },
    };
  },
};


const plugin = {
  rules: {
    "no-dark-mode-leakage": noDarkModeLeakage,
    "no-inline-hex": noInlineHex,
  },
};

export default plugin;
