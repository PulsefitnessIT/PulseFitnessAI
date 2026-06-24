#!/usr/bin/env node
/**
 * Guard against the "dead button" overlay bug.
 *
 * A TRANSPARENT `fixed` wrapper that spans a full screen EDGE
 * (`left-0 right-0`, `left-4 right-4`, `inset-x-0`) but only CENTERS a
 * smaller child (`mx-auto` / `max-w-…`) leaves transparent gutter regions
 * sitting on top of the page. Without `pointer-events-none` on that
 * wrapper, those transparent gutters silently swallow clicks on whatever
 * is beneath them — buttons appear to "do nothing".
 * (Real incident: the Master Admin Onboarding hub, June 2026.)
 *
 * Fix pattern: `pointer-events-none` on the full-edge wrapper +
 * `pointer-events-auto` on the inner visible card.
 *
 * Solid bars (nav headers, sticky footers) are NOT flagged: they either
 * fill the full width (no centered child) or carry their own background
 * (so clicks land on the bar, as intended).
 *
 * Run: `yarn lint:overlays`
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const FULL_EDGE = [/\bleft-0\b[^]*\bright-0\b/, /\bleft-4\b[^]*\bright-4\b/, /\binset-x-0\b/];
// Find the opening tag that carries a className containing `fixed`.
const TAG_RE = /<[a-zA-Z][^>]*\bclassName=\{?\s*[`"'][^`"']*?fixed[^>]*?>/gs;

const offenders = [];

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
      walk(p);
    } else if (/\.(js|jsx|tsx)$/.test(entry.name)) {
      scan(p);
    }
  }
}

function scan(file) {
  const text = fs.readFileSync(file, 'utf8');
  let m;
  while ((m = TAG_RE.exec(text)) !== null) {
    const tag = m[0]; // the full opening tag, incl. className + style attrs
    if (!/\bfixed\b/.test(tag)) continue;
    if (!FULL_EDGE.some((re) => re.test(tag))) continue;
    if (/\bpointer-events-none\b/.test(tag)) continue;       // correctly guarded
    if (/\bbg-[a-z[]/.test(tag) || /background/i.test(tag)) continue; // solid bar — clicks land on it
    // Does it center a smaller child (transparent gutters)? Check the tag
    // itself + the immediately-following child markup.
    const win = tag + text.slice(m.index + tag.length, m.index + tag.length + 320);
    if (!(/\bmx-auto\b/.test(win) || /\bmax-w-/.test(win))) continue;
    const line = text.slice(0, m.index).split('\n').length;
    const cls = (tag.match(/className=\{?\s*[`"']([^`"']*)/) || [, tag.slice(0, 80)])[1];
    offenders.push({ file: path.relative(path.join(__dirname, '..'), file), line, cls: cls.slice(0, 90) });
  }
}

walk(SRC);

if (offenders.length) {
  console.error('\n\u2717 Overlay click-interception risk: TRANSPARENT full-edge `fixed` wrapper centering a child WITHOUT `pointer-events-none`.\n');
  for (const o of offenders) {
    console.error(`  ${o.file}:${o.line}\n    className: "${o.cls}\u2026"`);
  }
  console.error('\n  Fix: add `pointer-events-none` to the wrapper and `pointer-events-auto` to the inner visible card.\n');
  process.exit(1);
}

console.log('\u2713 No overlay click-interception offenders found.');
