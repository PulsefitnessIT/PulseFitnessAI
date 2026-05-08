/**
 * Spacing standardisation codemod (Iter 215g).
 *
 * Moves `<Card>` padding toward the p-5 default documented in the
 * Design System. Conservative:
 *   • Only touches `<Card ...>` JSX openings.
 *   • Only rewrites `p-3` / `p-4` to `p-5` (the most common "accidental"
 *     deviations from default).
 *   • LEAVES `p-6` / `p-8` / `p-10` / `p-12` alone — those are usually
 *     deliberate (CardContent parity, hero callouts, empty states).
 *   • Skips responsive variants (`md:p-4`) to avoid breaking breakpoints.
 *
 * Usage:
 *   node scripts/codemod-spacing.js --dry-run src/pages
 *   node scripts/codemod-spacing.js src/pages
 */
const fs = require('fs');
const path = require('path');

const SKIP_DIRS = new Set(['node_modules', 'build', '.next', 'dist', 'ui', 'theme']);

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

// Matches `<Card ... className="..."` up to the closing quote. Captures
// the entire className value so we can inspect it.
const CARD_OPEN = /<Card\b([^>]*?)className="([^"]*)"/g;

// Replace standalone `p-3` or `p-4` with `p-5`. Only exact token match,
// not inside `md:p-4` or `pt-4`.
function normalizePadding(className) {
  return className.replace(/\bp-3\b/g, 'p-5').replace(/\bp-4\b/g, 'p-5');
}

function runFile(file, { dryRun }) {
  const src = fs.readFileSync(file, 'utf8');
  let changes = 0;
  const out = src.replace(CARD_OPEN, (match, pre, className) => {
    const normalized = normalizePadding(className);
    if (normalized === className) return match;
    changes += 1;
    return `<Card${pre}className="${normalized}"`;
  });
  if (changes && !dryRun) fs.writeFileSync(file, out, 'utf8');
  return changes;
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const targets = args.filter(a => !a.startsWith('--'));
  if (!targets.length) {
    console.error('Usage: codemod-spacing.js [--dry-run] <path> [<path>...]');
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
        console.log(`${dryRun ? '(dry) ' : ''}${f}: ${n} Card paddings normalised`);
      }
    }
  }
  console.log(`\n${dryRun ? 'Would normalise' : 'Normalised'} ${total} Card paddings across ${files} files.`);
}

main();
