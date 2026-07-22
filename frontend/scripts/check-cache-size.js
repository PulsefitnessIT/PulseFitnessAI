#!/usr/bin/env node
/**
 * Disk-bloat guard for the webpack persistent cache.
 *
 * The `/app` volume is small (~9.8G). The webpack filesystem cache
 * (node_modules/.cache) can grow to multiple GB over a long-running dev
 * server and has previously filled the volume to 100%, breaking file
 * writes and builds (July 2026 incident).
 *
 * This check measures the cache and, if it exceeds THRESHOLD_MB, prunes it
 * (safe — webpack simply rebuilds it). It never fails the pipeline; it just
 * reclaims space and reports. Run via `yarn predeploy` (or standalone).
 */
const fs = require('fs');
const path = require('path');

const CACHE_DIR = path.join(__dirname, '..', 'node_modules', '.cache');
const THRESHOLD_MB = 3072; // 3 GB — well under the /app volume ceiling

function dirSizeBytes(dir) {
  let total = 0;
  let stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    let entries;
    try { entries = fs.readdirSync(d, { withFileTypes: true }); } catch (_) { continue; }
    for (const e of entries) {
      const p = path.join(d, e.name);
      try {
        if (e.isDirectory()) stack.push(p);
        else total += fs.statSync(p).size;
      } catch (_) { /* file vanished mid-scan — ignore */ }
    }
  }
  return total;
}

if (!fs.existsSync(CACHE_DIR)) {
  console.log('\u2713 webpack cache: not present (0 MB).');
  process.exit(0);
}

const mb = Math.round(dirSizeBytes(CACHE_DIR) / (1024 * 1024));

if (mb > THRESHOLD_MB) {
  console.warn(`\u26a0 webpack cache is ${mb} MB (> ${THRESHOLD_MB} MB threshold) — pruning to protect the /app volume\u2026`);
  fs.rmSync(CACHE_DIR, { recursive: true, force: true });
  console.log('\u2713 webpack cache pruned. It will rebuild on the next compile.');
} else {
  console.log(`\u2713 webpack cache: ${mb} MB (under ${THRESHOLD_MB} MB threshold).`);
}
process.exit(0);
