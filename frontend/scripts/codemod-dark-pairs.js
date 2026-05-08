/**
 * Dark-mode pair codemod (Iter 215i).
 *
 * Walks JSX className strings and adds the matching `dark:` variant
 * for common light-only Tailwind classes when one is missing.
 *
 *   bg-white             → bg-white dark:bg-zinc-900
 *   bg-zinc-50           → bg-zinc-50 dark:bg-zinc-900
 *   bg-zinc-100          → bg-zinc-100 dark:bg-zinc-800
 *   text-zinc-900        → text-zinc-900 dark:text-zinc-100
 *   border-zinc-100      → border-zinc-100 dark:border-zinc-800
 *   border-zinc-200      → border-zinc-200 dark:border-zinc-800
 *
 * Conservative — skips strings that already contain ANY matching
 * `dark:` variant for the same property family. Only edits strings
 * inside JSX className=, className`...`, or `cn(...)` arg literals.
 *
 * Usage:
 *   node scripts/codemod-dark-pairs.js --dry-run src/pages
 *   node scripts/codemod-dark-pairs.js src/pages
 */
const fs = require('fs');
const path = require('path');

const SKIP_DIRS = new Set(['node_modules', 'build', '.next', 'dist', 'theme', 'ui']);

const PAIRS = [
  // [match, dark variant, family — e.g. 'bg' / 'text' / 'border']
  { match: /\bbg-white\b/,           pair: 'dark:bg-zinc-900', family: 'bg' },
  { match: /\bbg-zinc-50\b/,         pair: 'dark:bg-zinc-900', family: 'bg' },
  { match: /\bbg-zinc-100\b/,        pair: 'dark:bg-zinc-800', family: 'bg' },
  { match: /\bbg-gray-50\b/,         pair: 'dark:bg-zinc-900', family: 'bg' },
  { match: /\bbg-gray-100\b/,        pair: 'dark:bg-zinc-800', family: 'bg' },
  { match: /\bbg-slate-50\b/,        pair: 'dark:bg-zinc-900', family: 'bg' },
  { match: /\bbg-slate-100\b/,       pair: 'dark:bg-zinc-800', family: 'bg' },
  { match: /\bbg-neutral-50\b/,      pair: 'dark:bg-zinc-900', family: 'bg' },
  { match: /\bbg-neutral-100\b/,     pair: 'dark:bg-zinc-800', family: 'bg' },
  { match: /\btext-zinc-900\b/,      pair: 'dark:text-zinc-100', family: 'text' },
  { match: /\btext-gray-900\b/,      pair: 'dark:text-zinc-100', family: 'text' },
  { match: /\btext-slate-900\b/,     pair: 'dark:text-zinc-100', family: 'text' },
  { match: /\btext-neutral-900\b/,   pair: 'dark:text-zinc-100', family: 'text' },
  { match: /\bborder-zinc-100\b/,    pair: 'dark:border-zinc-800', family: 'border' },
  { match: /\bborder-zinc-200\b/,    pair: 'dark:border-zinc-800', family: 'border' },
  { match: /\bborder-gray-100\b/,    pair: 'dark:border-zinc-800', family: 'border' },
  { match: /\bborder-gray-200\b/,    pair: 'dark:border-zinc-800', family: 'border' },
  { match: /\bborder-slate-100\b/,   pair: 'dark:border-zinc-800', family: 'border' },
  { match: /\bborder-slate-200\b/,   pair: 'dark:border-zinc-800', family: 'border' },
];

const FAMILY_DARK_RE = {
  bg:     /\bdark:bg-/,
  text:   /\bdark:text-/,
  border: /\bdark:border-/,
};

// Match the contents of any JSX `className="..."` or `className='...'`
// or template literal `className={\`...\`}` and any `cn(...)` arg literal.
// Plain string literal that *probably* contains classNames: starts/ends
// with normal text, has at least one Tailwind-shape token.
const STRING_LITERAL_RE = /(["'`])([^"'`\n]*?)\1/g;

function transformClassName(str) {
  let out = str;
  let touched = false;
  for (const { match, pair, family } of PAIRS) {
    if (!match.test(out)) continue;
    if (FAMILY_DARK_RE[family].test(out)) {
      // Already has SOME dark variant for this family — leave alone.
      // (Operator may have hand-paired a different colour.)
      continue;
    }
    // Append the dark variant once. Prefer a space-separated append.
    out = out + ' ' + pair;
    touched = true;
  }
  return { out, touched };
}

function looksLikeClassName(str) {
  // Heuristic: has at least one Tailwind-utility shape (letters then dash)
  // AND contains one of our target classes. Avoids tagging arbitrary text.
  if (!str || str.length < 4) return false;
  if (!/^[a-zA-Z0-9!:\[\]/\s_-]+$/.test(str)) return false;
  return PAIRS.some(({ match }) => match.test(str));
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
    console.error('Usage: codemod-dark-pairs.js [--dry-run] <path> [<path>...]');
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
        console.log(`${dryRun ? '(dry) ' : ''}${f}: ${n} className strings paired`);
      }
    }
  }
  console.log(`\n${dryRun ? 'Would pair' : 'Paired'} ${total} className strings across ${files} files.`);
}

main();
