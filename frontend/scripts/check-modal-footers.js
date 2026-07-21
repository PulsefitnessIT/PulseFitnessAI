#!/usr/bin/env node
/**
 * Guard against the "content cut off behind the Save footer" bug.
 *
 * A `sticky bottom-0` action footer placed INSIDE a scrolling container
 * (`overflow-y-auto` / `overflow-auto`) floats OVER the last field at max
 * scroll — the user can never scroll far enough to see it. (Real incident:
 * Memberships "Add member" / "New ad" modals, July 2026.)
 *
 * Correct pattern: a fixed-height flex column where the footer is a
 * `flex-shrink-0` SIBLING of the scroll body — i.e. the shared
 * `components/shared/Modal.jsx` primitive (`<Modal footer={…}>`), so ONLY
 * the body scrolls and the footer can never overlap.
 *
 * This check flags every `sticky bottom-0` occurrence in the source tree.
 * They are almost always this footer anti-pattern; if you have a genuine,
 * safe use, add a `sticky-footer-ok` comment on the same or previous line
 * to opt out explicitly.
 *
 * Run: `yarn lint:modals`
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'src');
const STICKY_RE = /\bsticky\b[^"'`]*\bbottom-0\b/;
const OPT_OUT = /sticky-footer-ok/;

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
  const lines = fs.readFileSync(file, 'utf8').split('\n');
  lines.forEach((line, i) => {
    if (!STICKY_RE.test(line)) return;
    // Explicit opt-out on this line or the line above.
    if (OPT_OUT.test(line) || (i > 0 && OPT_OUT.test(lines[i - 1]))) return;
    offenders.push({
      file: path.relative(path.join(__dirname, '..'), file),
      line: i + 1,
      snippet: line.trim().slice(0, 100),
    });
  });
}

walk(SRC);

if (offenders.length) {
  console.error('\n\u2717 Modal footer cut-off risk: `sticky bottom-0` footer found (floats over the last field at max scroll).\n');
  for (const o of offenders) {
    console.error(`  ${o.file}:${o.line}\n    ${o.snippet}\u2026`);
  }
  console.error('\n  Fix: use the shared <Modal footer={<ModalFooter/>}> primitive (components/shared/Modal.jsx),');
  console.error('  or make the footer a `flex-shrink-0` sibling of a `flex-1 overflow-y-auto` body.');
  console.error('  Genuinely-safe use? Add a `sticky-footer-ok` comment to opt out.\n');
  process.exit(1);
}

console.log('\u2713 No modal footer cut-off offenders found.');
