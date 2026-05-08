/**
 * Hex-to-token codemod (Iter 215f).
 *
 * Usage (from /app/frontend):
 *   node scripts/codemod-colours.js --dry-run src/pages/CRM
 *   node scripts/codemod-colours.js src/pages/CRM
 *
 * Conservative: only replaces *exact* hex literals found in the canonical
 * mapping below. Alpha variants (`bg-[#0055FF]/10`) are left alone because
 * CSS variables don't combine cleanly with Tailwind's slash-opacity syntax.
 * Same for hex in SVG fill/stroke props — those are preserved.
 *
 * Run per-folder and visually diff the output before committing. This
 * is a helper, not a magic wand.
 */
const fs = require('fs');
const path = require('path');

// Mapping: canonical hex (uppercased) → CSS variable.
const MAPPING = {
  '#19CDFF': 'var(--color-brand-cyan)',
  '#66CCFF': 'var(--color-brand-cyan-hover)',
  '#4DBFFF': 'var(--color-brand-cyan-light)',
  '#0055FF': 'var(--color-brand-blue)',
  '#0044CC': 'var(--color-brand-blue-hover)',
  '#003DA5': 'var(--color-brand-blue-dark)',
  '#005BB5': 'var(--color-brand-blue-deep)',
  '#0A0C10': 'var(--color-ink)',
  '#0A0A0A': 'var(--color-ink-alt)',
  '#52525B': 'var(--color-ink-muted)',
  '#A1A1AA': 'var(--color-text-muted)',
  '#71717A': 'var(--color-text-faint)',
  '#6B7280': 'var(--color-text-faint-alt)',
  '#6E7476': 'var(--color-text-slate)',
  '#F4F4F5': 'var(--color-paper-alt)',
  '#F3F4F6': 'var(--color-neutral-100)',
  '#FAFAFA': 'var(--color-neutral-50)',
  '#FFFFFF': 'var(--color-white)',
  '#E4E4E7': 'var(--color-border)',
  '#E5E7EB': 'var(--color-border-alt)',
  '#D4D4D8': 'var(--color-border-strong)',
  '#121212': 'var(--color-surface-dark-alt)',
  '#141414': 'var(--color-surface-dark-1)',
  '#1A1A1A': 'var(--color-surface-dark-2)',
  '#262626': 'var(--color-surface-dark-3)',
  '#171717': 'var(--color-neutral-900)',
  '#0F0F0F': 'var(--color-neutral-950)',
  '#05070A': 'var(--color-surface-darker)',
  '#1F1F1F': 'var(--color-surface-dark-panel)',
  '#1B1D1D': 'var(--color-surface-dark-panel-alt)',
  '#10B981': 'var(--color-success)',
  '#34C759': 'var(--color-success-alt)',
  '#F59E0B': 'var(--color-warning)',
  '#EF4444': 'var(--color-danger)',
  '#FF3B30': 'var(--color-danger-alt)',
  '#FF9500': 'var(--color-accent-amber)',
  '#007AFF': 'var(--color-info-ios)',
  '#3B82F6': 'var(--color-info)',
  '#9966FF': 'var(--color-accent-purple)',
  '#8B5CF6': 'var(--color-accent-violet)',
  '#AF52DE': 'var(--color-accent-magenta)',
  '#5856D6': 'var(--color-accent-indigo)',
  // Tailwind-equivalent neutrals surfaced during Wave 2 sweep
  '#22C55E': 'var(--color-success-alt-2)',
  '#34D399': 'var(--color-success-light)',
  '#FBBF24': 'var(--color-warning-alt)',
  '#0DB8E8': 'var(--color-brand-cyan-deep)',
  '#18181B': 'var(--color-neutral-950-alt)',
  '#F97316': 'var(--color-orange)',
  '#EAB308': 'var(--color-yellow)',
  '#2563EB': 'var(--color-blue-600)',
  '#E0E0E0': 'var(--color-border-light)',
  '#F8F9FA': 'var(--color-neutral-25)',
  '#0F1419': 'var(--color-ink-deep)',
  '#EFF6FF': 'var(--color-info-bg)',
  // Iter 215h — additional one-off holdouts surfaced by ESLint warnings
  '#3377FF':   'var(--color-brand-blue-alt)',
  '#0044DD':   'var(--color-brand-blue-alt2)',
  '#F43F5E':   'var(--color-rose)',
  '#393E41':   'var(--color-neutral-700)',
  '#FFD700':   'var(--color-gold)',
  '#CD7F32':   'var(--color-bronze)',
  '#C0C0C0':   'var(--color-silver)',
  '#0A6F8C':   'var(--color-teal-deep)',
  '#0A0B10':   'var(--color-ink-2)',
  '#A3A3A3':   'var(--color-neutral-400)',
  '#06B6D4':   'var(--color-cyan-500)',
  '#F9FAFB':   'var(--color-neutral-25-alt)',
  '#F5F5F5':   'var(--color-neutral-75)',
  '#DBEAFE':   'var(--color-blue-100)',
  '#BFDBFE':   'var(--color-blue-200)',
  '#525252':   'var(--color-neutral-600)',
  '#1E3A5F':   'var(--color-navy-800)',
  '#1A2332':   'var(--color-navy-900)',
  '#1A1A2E':   'var(--color-ink-navy)',
  '#0D1117':   'var(--color-ink-coal)',
  '#9CA3AF':   'var(--color-neutral-400-alt)',
  '#94A3B8':   'var(--color-slate-400)',
  '#FEF2F2':   'var(--color-rose-50)',
  '#F0F7FF':   'var(--color-blue-50)',
  '#A78BFA':   'var(--color-violet-400)',
  '#7C3AED':   'var(--color-violet-600)',
  '#212721':   'var(--color-pulse-black)',
  '#14B8A6':   'var(--color-teal-500)',
  '#2B2E30':   'var(--color-dark-panel-3)',
  '#1A1D23':   'var(--color-ink-coal-alt)',
  // Final long-tail
  '#FF66CC':   'var(--color-pink)',
  '#FF6633':   'var(--color-orange-warm)',
  '#F9F9F9':   'var(--color-neutral-10)',
  '#30D158':   'var(--color-success-ios)',
  '#2A2A2A':   'var(--color-surface-dark-4)',
  '#0B0F14':   'var(--color-ink-midnight)',
  '#0A1628':   'var(--color-navy-950)',
  '#062B21':   'var(--color-emerald-dark)',
  '#0088FF':   'var(--color-blue-500)',
};

const HEX_ALL_RE = /#[0-9A-Fa-f]{6}(?!\/)/g;   // ignore `#xxx/NN` alpha form
const SKIP_DIRS = new Set(['node_modules', 'build', '.next', 'dist', 'theme', 'ui']);

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
  const out = src.replace(HEX_ALL_RE, (hex) => {
    const up = hex.toUpperCase();
    const rep = MAPPING[up];
    if (!rep) return hex;
    changes += 1;
    return rep;
  });
  if (changes && !dryRun) fs.writeFileSync(file, out, 'utf8');
  return changes;
}

function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  const targets = args.filter(a => !a.startsWith('--'));
  if (!targets.length) {
    console.error('Usage: codemod-colours.js [--dry-run] <path> [<path>...]');
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
        console.log(`${dryRun ? '(dry) ' : ''}${f}: ${n} replacements`);
      }
    }
  }
  console.log(`\n${dryRun ? 'Would replace' : 'Replaced'} ${total} hex literals across ${files} files.`);
}

main();
