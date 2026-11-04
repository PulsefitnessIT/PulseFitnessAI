/**
 * MODService ".ai" sanitizer — shared by the webpack plugin (craco.config.js)
 * and the post-build pass (modservice/postbuild.js).
 *
 * MOD site networks block any ".ai" URL (deep-content inspection), so the
 * MODService build must not serve a single `pulsefitness.ai` / `gymaxis.ai`
 * string. This only ever runs when REACT_APP_PORTAL_MODE=modservice, so the
 * commercial pulsefitness.ai build is byte-for-byte unaffected.
 *
 *   x@pulsefitness.ai / x@service.pulsefitness.ai  → x@pulsefitness.com
 *   https://www.pulsefitness.ai/...                 → https://modservice.pulsefitness.com/...
 *   regex-escaped forms  pulsefitness\.ai            → pulsefitness\.a[i]  (same match, no literal)
 *   brand phrase "Pulse Fitness AI"                → "Pulse Fitness"
 */
const MOD_HOST = (process.env.REACT_APP_MODSERVICE_HOST || 'modservice.pulsefitness.com').toLowerCase();
const MAIL_DOMAIN = (process.env.REACT_APP_MODSERVICE_MAIL_DOMAIN || 'pulsefitness.com').toLowerCase();

const BRANDS = '(?:pulsefitness|gymaxis)';
const TAIL = '(?![A-Za-z0-9-])';
const ESCAPED_RE = new RegExp(`(${BRANDS})(\\\\+)\\.ai${TAIL}`, 'gi');
const EMAIL_RE = new RegExp(`([A-Za-z0-9._%+-]+)@(?:[A-Za-z0-9-]+\\.)*${BRANDS}\\.ai${TAIL}`, 'gi');
const HOST_RE = new RegExp(`(?:[A-Za-z0-9-]+\\.)*${BRANDS}\\.ai${TAIL}`, 'gi');
// Brand name as display text ("Pulse Fitness AI", "PulseFitness AI", "GymAxis AI").
const BRAND_PHRASE_RE = /\b(Pulse ?Fitness|GymAxis) AI\b/g;
// Detector used for the final assertion (anything the rewrite missed).
const DETECT_RE = new RegExp(`${BRANDS}\\\\*\\.ai${TAIL}`, 'i');

function isModServiceBuild() {
  return (process.env.REACT_APP_PORTAL_MODE || '').trim().toLowerCase() === 'modservice';
}

function sanitize(text) {
  if (!text) return { text, count: 0 };
  BRAND_PHRASE_RE.lastIndex = 0;
  const hasDomain = DETECT_RE.test(text);
  const hasBrand = BRAND_PHRASE_RE.test(text);
  BRAND_PHRASE_RE.lastIndex = 0;
  if (!hasDomain && !hasBrand) return { text, count: 0 };
  let count = 0;
  const bump = (fn) => (...a) => { count += 1; return fn(...a); };
  let out = text;
  if (hasDomain) {
    out = out.replace(ESCAPED_RE, bump((m, brand, slashes) => `${brand}${slashes}.a[i]`));
    out = out.replace(EMAIL_RE, bump((m, local) => `${local}@${MAIL_DOMAIN}`));
    out = out.replace(HOST_RE, bump(() => MOD_HOST));
  }
  if (hasBrand) out = out.replace(BRAND_PHRASE_RE, bump((m, brand) => brand));
  return { text: out, count };
}

function containsAiDomain(text) {
  return DETECT_RE.test(text || '');
}

class ModServiceSanitizePlugin {
  apply(compiler) {
    const { Compilation, sources } = compiler.webpack;
    compiler.hooks.thisCompilation.tap('ModServiceSanitizePlugin', (compilation) => {
      compilation.hooks.processAssets.tap(
        {
          name: 'ModServiceSanitizePlugin',
          // After minification + HTML emit, before real content hashing.
          stage: Compilation.PROCESS_ASSETS_STAGE_OPTIMIZE_INLINE + 1,
        },
        (assets) => {
          for (const name of Object.keys(assets)) {
            if (!/\.(m?js|css|html|json|txt|svg|xml)$/i.test(name.split('?')[0])) continue;
            const asset = compilation.getAsset(name);
            if (!asset) continue;
            const raw = asset.source.source();
            const str = typeof raw === 'string' ? raw : Buffer.from(raw).toString('utf8');
            const { text, count } = sanitize(str);
            if (count) compilation.updateAsset(name, new sources.RawSource(text));
          }
        },
      );
    });
  }
}

module.exports = { MOD_HOST, MAIL_DOMAIN, isModServiceBuild, sanitize, containsAiDomain, ModServiceSanitizePlugin };
