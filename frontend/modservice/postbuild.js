#!/usr/bin/env node
/**
 * MODService post-build pass. No-op unless REACT_APP_PORTAL_MODE=modservice.
 *
 * CRA copies public/ into build/ outside webpack, so robots / security.txt /
 * sitemap / decks etc. never pass through ModServiceSanitizePlugin. This:
 *   1. drops commercial-only files (sitemap, llms.txt, sales decks, briefs)
 *   2. writes MOD-specific robots.txt, security.txt and manifest.json
 *   3. rewrites any remaining .ai references in every text file
 *   4. removes binaries that still embed a .ai domain
 *   5. FAILS the build if a single .ai reference survives.
 */
const fs = require('fs');
const path = require('path');

require('dotenv').config({ path: path.resolve(__dirname, '..', '.env') });
const { MOD_HOST, MAIL_DOMAIN, isModServiceBuild, sanitize, containsAiDomain } = require('./sanitize');

if (!isModServiceBuild()) {
  console.log('[modservice-postbuild] not a MODService build - skipped');
  process.exit(0);
}

const BUILD = path.resolve(__dirname, '..', 'build');
if (!fs.existsSync(BUILD)) {
  console.error('[modservice-postbuild] build/ not found');
  process.exit(1);
}

const rm = (rel) => {
  const p = path.join(BUILD, rel);
  if (fs.existsSync(p)) { fs.rmSync(p, { recursive: true, force: true }); console.log(`  removed ${rel}`); }
};

console.log(`[modservice-postbuild] sanitising build for ${MOD_HOST}`);

// 1. Commercial-only artefacts — not part of the MOD portal.
['sitemap.xml', 'llms.txt', 'downloads', 'decks',
  'Pulse_Fitness_AI_x_Sicon_Integration_Brief.pdf', 'Pulse_Fitness_AI_x_Sicon_Integration_Brief.docx',
].forEach(rm);

// 2. MOD-specific replacements.
fs.writeFileSync(path.join(BUILD, 'robots.txt'), 'User-agent: *\nDisallow: /\n');
fs.mkdirSync(path.join(BUILD, '.well-known'), { recursive: true });
fs.writeFileSync(path.join(BUILD, '.well-known', 'security.txt'), [
  `Contact: mailto:security@${MAIL_DOMAIN}`,
  'Expires: 2027-01-01T00:00:00.000Z',
  'Preferred-Languages: en',
  `Canonical: https://${MOD_HOST}/.well-known/security.txt`,
  '',
].join('\n'));
fs.copyFileSync(path.join(__dirname, 'manifest.json'), path.join(BUILD, 'manifest.json'));

// 3 + 4. Walk everything.
const TEXT_EXT = /\.(html?|m?js|css|json|txt|xml|svg|md|map|webmanifest|csv)$/i;
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
  const p = path.join(dir, d.name);
  return d.isDirectory() ? walk(p) : [p];
});

let rewrittenFiles = 0;
let rewrites = 0;
const leftovers = [];
for (const file of walk(BUILD)) {
  const rel = path.relative(BUILD, file);
  if (TEXT_EXT.test(file)) {
    const src = fs.readFileSync(file, 'utf8');
    const { text, count } = sanitize(src);
    if (count) { fs.writeFileSync(file, text); rewrittenFiles += 1; rewrites += count; }
    if (containsAiDomain(text)) leftovers.push(rel);
  } else if (containsAiDomain(fs.readFileSync(file).toString('latin1'))) {
    fs.rmSync(file, { force: true });
    console.log(`  removed binary with .ai reference: ${rel}`);
  }
}

console.log(`[modservice-postbuild] ${rewrites} reference(s) rewritten in ${rewrittenFiles} file(s)`);
if (leftovers.length) {
  console.error('[modservice-postbuild] FAILED - .ai references remain in:', leftovers);
  process.exit(1);
}
console.log('[modservice-postbuild] OK - zero .ai domain references in build/');
