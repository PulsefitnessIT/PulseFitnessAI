/**
 * Theme-aware surface codemod (Iter 215j).
 *
 * Replaces hardcoded dark-only surfaces with theme-aware CSS variables
 * that adapt to light/dark mode automatically.
 *
 *   bg-[var(--color-surface-dark-alt)]      → bg-[var(--theme-surface)]
 *   bg-[var(--color-ink-alt)]               → bg-[var(--theme-surface)]
 *   bg-[var(--color-surface-dark)]          → bg-[var(--theme-bg)]
 *   bg-[var(--color-surface-dark-panel)]    → bg-[var(--theme-surface)]
 *   bg-[var(--color-surface-dark-panel-alt)]→ bg-[var(--theme-surface)]
 *   border-white/10                         → border-[var(--theme-border)]
 *   text-white                              → text-[var(--theme-text)]   (only when paired with a theme-surface bg)
 *   text-zinc-400                           → text-[var(--theme-text-muted)]   (likewise)
 *
 * Conservative: text colour rewrites only happen when the SAME className
 * string also references a theme-surface bg, so we don't accidentally
 * flip text colour on a brand-cyan button.
 *
 * Usage:
 *   node scripts/codemod-theme-surface.js --dry-run src/pages/LiteDashboard
 *   node scripts/codemod-theme-surface.js src/pages/LiteDashboard
 */
const fs = require('fs');
const path = require('path');

const SKIP_DIRS = new Set(['node_modules', 'build', '.next', 'dist', 'theme', 'ui']);

const SURFACE_PAIRS = [
  // Direct surface swaps — always safe.
  { from: /bg-\[var\(--color-surface-dark-alt\)\]/g,        to: 'bg-[var(--theme-surface)]' },
  { from: /bg-\[var\(--color-surface-dark-panel-alt\)\]/g,  to: 'bg-[var(--theme-surface)]' },
  { from: /bg-\[var\(--color-surface-dark-panel\)\]/g,      to: 'bg-[var(--theme-surface)]' },
  { from: /bg-\[var\(--color-ink-alt\)\]/g,                 to: 'bg-[var(--theme-surface)]' },
  { from: /bg-\[var\(--color-surface-dark\)\]/g,            to: 'bg-[var(--theme-bg)]' },
  { from: /bg-\[var\(--color-surface-dark-1\)\]/g,          to: 'bg-[var(--theme-bg)]' },
  { from: /bg-\[var\(--color-surface-dark-2\)\]/g,          to: 'bg-[var(--theme-surface)]' },
  { from: /bg-\[var\(--color-surface-dark-3\)\]/g,          to: 'bg-[var(--theme-surface-hover)]' },
];

// Border swaps — `border-white/10` is the most common dark-only border.
const BORDER_PAIRS = [
  { from: /\bborder-white\/10\b/g,  to: 'border-[var(--theme-border)]' },
  { from: /\bborder-white\/15\b/g,  to: 'border-[var(--theme-border)]' },
  { from: /\bborder-white\/20\b/g,  to: 'border-[var(--theme-border)]' },
];

// Text swaps — only safe when paired with a theme surface in the same string
// AND no coloured background (gradients, brand-cyan buttons, etc.).
const TEXT_PAIRS = [
  { from: /\btext-white\b/g,       to: 'text-[var(--theme-text)]' },
  { from: /\btext-zinc-100\b/g,    to: 'text-[var(--theme-text)]' },
  { from: /\btext-zinc-200\b/g,    to: 'text-[var(--theme-text)]' },
  { from: /\btext-zinc-300\b/g,    to: 'text-[var(--theme-text-muted)]' },
  { from: /\btext-zinc-400\b/g,    to: 'text-[var(--theme-text-muted)]' },
];

const COLOURED_BG_RE = /\bbg-(?:gradient-[a-z-]+|(?:amber|rose|red|orange|yellow|emerald|green|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|lime)-(?:[3-7]00|400|500|600))\b|bg-\[(?:var\(--color-(?:brand-|accent-|success|warning|danger|info)|rgb\(|#)/;
const STRING_LITERAL_RE = /(["'`])([^"'`\n]*?)\1/g;

function transformClassName(str) {
  let out = str;
  let touched = false;

  // Always-safe surface and border swaps.
  for (const { from, to } of [...SURFACE_PAIRS, ...BORDER_PAIRS]) {
    if (from.test(out)) {
      out = out.replace(from, to);
      touched = true;
      // Re-create the regex (g flag with test() advances lastIndex).
      from.lastIndex = 0;
    }
  }

  // Conditional text swaps — only if the className already references
  // a theme surface AND has no coloured/brand background.
  const referencesThemeSurface = /\bbg-\[var\(--theme-/.test(out);
  if (referencesThemeSurface && !COLOURED_BG_RE.test(out)) {
    for (const { from, to } of TEXT_PAIRS) {
      if (from.test(out)) {
        out = out.replace(from, to);
        touched = true;
        from.lastIndex = 0;
      }
    }
  }

  return { out, touched };
}

function looksLikeClassName(str) {
  if (!str || str.length < 4) return false;
  if (!/^[a-zA-Z0-9!:\[\]/\s_().,#-]+$/.test(str)) return false;
  return /\b(?:bg|border|text)-/.test(str);
}

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(full, files);
    } else if (entry.isFile() && /\.(jsx?|tsx?)$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

function runFile(file, { dryRun }) {
  const src = fs.readFileSync(file, 'utf8');
  let changes = 0;
  const out = src.replace(STRING_LITERAL_RE, (match, quote, body) => {
    if (!looksLikeClassName(body)) return match;
    const { out: newBody, touched } = transformClassName(body);
    if (!touched) return match;
    changes += 1;
    return `${quote}${newBody}${quote}`;
  });
  if (changes && !dryRun) fs.writeFileSync(file, out, 'utf8');
  return changes;
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const targets = args.filter(a => !a.startsWith('--'));
  if (!targets.length) {
    console.error('Usage: codemod-theme-surface.js [--dry-run] <path> [<path>...]');
    process.exit(1);
  }
  let total = 0, files = 0;
  for (const t of targets) {
    const stat = fs.statSync(t);
    const list = stat.isDirectory() ? walk(t) : [t];
    for (const f of list) {
      const n = runFile(f, { dryRun });
      if (n) {
        files += 1;
        total += n;
        console.log(`${dryRun ? '(dry) ' : ''}${f}: ${n} className strings updated`);
      }
    }
  }
  console.log(`\n${dryRun ? 'Would update' : 'Updated'} ${total} className strings across ${files} files.`);
}

main();
