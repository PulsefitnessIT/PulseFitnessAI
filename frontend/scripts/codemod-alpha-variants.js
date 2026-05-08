/**
 * Alpha-variant codemod (Iter 215g).
 *
 * Handles the cases the main colour codemod had to skip:
 *   `bg-[#19CDFF]/10`  → `bg-[rgb(var(--rgb-brand-cyan)/0.1)]`
 *   `border-[#0055FF]/30` → `border-[rgb(var(--rgb-brand-blue)/0.3)]`
 *
 * Only covers hexes that have an RGB-channel token defined in
 * /app/frontend/src/index.css (search for `--rgb-`). Any hex outside
 * that set is left alone so future Wave-3 batches can expand coverage.
 *
 * Usage:
 *   node scripts/codemod-alpha-variants.js --dry-run src/pages
 *   node scripts/codemod-alpha-variants.js src
 */
const fs = require('fs');
const path = require('path');

const SKIP_DIRS = new Set(['node_modules', 'build', '.next', 'dist', 'theme', 'ui']);

// Map: canonical hex (uppercase) → CSS rgb-channel variable name (no `--` prefix).
const RGB_MAP = {
  '#19CDFF': 'rgb-brand-cyan',
  '#66CCFF': 'rgb-brand-cyan-hover',
  '#0055FF': 'rgb-brand-blue',
  '#0044CC': 'rgb-brand-blue-hover',
  '#0A0C10': 'rgb-ink',
  '#0A0A0A': 'rgb-ink-alt',
  '#A1A1AA': 'rgb-text-muted',
  '#10B981': 'rgb-success',
  '#34C759': 'rgb-success-alt',
  '#F59E0B': 'rgb-warning',
  '#EF4444': 'rgb-danger',
  '#FF3B30': 'rgb-danger-alt',
  '#007AFF': 'rgb-info-ios',
  '#9966FF': 'rgb-accent-purple',
};

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

// Match Tailwind arbitrary variants with slash-opacity in TWO forms:
//   (a) Wave-0 style:  bg-[#19CDFF]/25
//   (b) Wave-1 style:  bg-[var(--color-brand-cyan)]/25   (already codemodded)
// Both get rewritten to the channel-based form: bg-[rgb(var(--rgb-brand-cyan)/0.25)]
const ALPHA_RE_HEX = /(\b[a-z][a-z0-9-]*?-)\[(#[0-9A-Fa-f]{6})\]\/([0-9]{1,3})\b/g;
const ALPHA_RE_VAR = /(\b[a-z][a-z0-9-]*?-)\[var\(--color-([a-z0-9-]+)\)\]\/([0-9]{1,3})\b/g;

// Map color-* → rgb-* so the Wave-1 var() output routes to the channel set.
const COLOR_TO_RGB = {
  'brand-cyan':            'rgb-brand-cyan',
  'brand-cyan-hover':      'rgb-brand-cyan-hover',
  'brand-blue':            'rgb-brand-blue',
  'brand-blue-hover':      'rgb-brand-blue-hover',
  'ink':                   'rgb-ink',
  'ink-alt':               'rgb-ink-alt',
  'text-muted':            'rgb-text-muted',
  'success':               'rgb-success',
  'success-alt':           'rgb-success-alt',
  'warning':               'rgb-warning',
  'danger':                'rgb-danger',
  'danger-alt':            'rgb-danger-alt',
  'info-ios':              'rgb-info-ios',
  'accent-purple':         'rgb-accent-purple',
};

function runFile(file, { dryRun }) {
  const src = fs.readFileSync(file, 'utf8');
  let changes = 0;
  let out = src.replace(ALPHA_RE_HEX, (match, prefix, hex, alpha) => {
    const varName = RGB_MAP[hex.toUpperCase()];
    if (!varName) return match;
    const a = (Number(alpha) / 100).toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    changes += 1;
    return `${prefix}[rgb(var(--${varName})/${a})]`;
  });
  out = out.replace(ALPHA_RE_VAR, (match, prefix, colorName, alpha) => {
    const rgbName = COLOR_TO_RGB[colorName];
    if (!rgbName) return match;
    const a = (Number(alpha) / 100).toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    changes += 1;
    return `${prefix}[rgb(var(--${rgbName})/${a})]`;
  });
  if (changes && !dryRun) fs.writeFileSync(file, out, 'utf8');
  return changes;
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const targets = args.filter(a => !a.startsWith('--'));
  if (!targets.length) {
    console.error('Usage: codemod-alpha-variants.js [--dry-run] <path> [<path>...]');
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
        console.log(`${dryRun ? '(dry) ' : ''}${f}: ${n} alpha variants rewritten`);
      }
    }
  }
  console.log(`\n${dryRun ? 'Would rewrite' : 'Rewrote'} ${total} alpha variants across ${files} files.`);
}

main();
