/* eslint-disable */
/**
 * apply-portal-og.js — post-build static meta rewrite for the MODService build.
 *
 * WHY: Social/link-preview crawlers (WhatsApp, iMessage/SMS, Facebook, X) do
 * NOT execute JavaScript, so the runtime SEO hardening in the SPA never reaches
 * them. They read the STATIC <meta> tags in build/index.html and fetch og:image
 * as-served. This script rewrites those static tags to MOD Service Portal values
 * so the shared card no longer shows the commercial "pulsefitness.ai" branding.
 *
 * SAFETY: runs on EVERY build (chained after `craco build`) but is a strict
 * NO-OP unless REACT_APP_PORTAL_MODE === 'modservice'. The commercial
 * pulsefitness.ai build is therefore byte-for-byte unchanged. Never throws /
 * never fails the build (always exits 0).
 */
const fs = require('fs');
const path = require('path');

function main() {
  const mode = (process.env.REACT_APP_PORTAL_MODE || '').toLowerCase();
  if (mode !== 'modservice') {
    console.log('[apply-portal-og] REACT_APP_PORTAL_MODE is not "modservice" — skipping (commercial build untouched).');
    return;
  }

  const file = process.argv[2] || path.join(__dirname, '..', 'build', 'index.html');
  if (!fs.existsSync(file)) {
    console.log('[apply-portal-og] ' + file + ' not found — skipping.');
    return;
  }

  const ORIGIN = 'https://modservice.pulsefitness.com';
  const TITLE = 'MOD Service Portal — Pulse Fitness';
  const DESC = 'Secure fault reporting and equipment registers for every MOD gym site. Service personnel only.';
  const IMAGE = ORIGIN + '/brand/og-cover-mod.jpg';
  const SITE = 'MOD Service Portal';

  let html = fs.readFileSync(file, 'utf8');

  // Replace the content="" of a <meta property|name="KEY" ...> tag.
  const setMeta = (attr, key, value) => {
    const re = new RegExp(
      '(<meta\\s+' + attr + '=["\']' + key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '["\'][^>]*?content=["\'])[^"\']*(["\'])',
      'i',
    );
    html = html.replace(re, '$1' + value.replace(/\$/g, '$$$$') + '$2');
  };

  setMeta('property', 'og:site_name', SITE);
  setMeta('property', 'og:title', TITLE);
  setMeta('property', 'og:description', DESC);
  setMeta('property', 'og:url', ORIGIN + '/');
  setMeta('property', 'og:image', IMAGE);
  setMeta('name', 'twitter:title', TITLE);
  setMeta('name', 'twitter:description', DESC);
  setMeta('name', 'twitter:image', IMAGE);
  setMeta('name', 'apple-mobile-web-app-title', 'MOD Service');
  setMeta('name', 'description', DESC);
  setMeta('name', 'application-name', SITE);

  // <title>
  html = html.replace(/<title>[^<]*<\/title>/i, '<title>' + TITLE + '</title>');

  // canonical
  html = html.replace(
    /(<link\s+rel=["']canonical["'][^>]*?href=["'])[^"']*(["'])/i,
    '$1' + ORIGIN + '/$2',
  );

  // Belt-and-braces — any remaining commercial host (JSON-LD urls, etc.)
  html = html.replace(/https?:\/\/(www\.)?pulsefitness\.ai/g, ORIGIN);
  // …and any bare domain left over (e.g. a support@pulsefitness.ai email in JSON-LD).
  html = html.replace(/pulsefitness\.ai/g, 'modservice.pulsefitness.com');

  fs.writeFileSync(file, html);
  console.log('[apply-portal-og] MODService OG/meta applied to ' + file);
}

try { main(); } catch (e) {
  console.log('[apply-portal-og] non-fatal error (skipping): ' + (e && e.message));
}
process.exit(0);
