/**
 * useUtmAttribution — Iter 220o
 *
 * Reads URL search params on mount and stashes UTM-shaped values into
 * sessionStorage so a multi-step user journey (landing → "How it
 * works" → back to top → "Start application") preserves the original
 * attribution even after the URL is replaced.
 *
 * Returns:
 *   {
 *     utm: { source, medium, campaign, content, term, referrer_url },
 *     isInstagram: bool      // convenience flag for hero-copy swap
 *     applyHref: string      // /partners/engineers/apply with UTM
 *                            //   carried forward as query params
 *   }
 *
 * Persistence rule: the FIRST landing wins. A later visit with no UTM
 * doesn't wipe the attribution; only an explicit `?utm_source=` does.
 * (Matches Google Analytics' first-touch attribution semantics — gives
 * Instagram credit even if the user comes back via a bookmark later.)
 */
import { useEffect, useMemo } from 'react';

const STORAGE_KEY = 'gx_utm_attribution';

const KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

function safeParseSession() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readFromUrl() {
  if (typeof window === 'undefined') return null;
  try {
    const sp = new URLSearchParams(window.location.search);
    const found = {};
    let any = false;
    for (const k of KEYS) {
      const v = sp.get(k);
      if (v && v.length <= 200) {
        found[k] = v.toLowerCase();
        any = true;
      }
    }
    if (!any) return null;
    found.referrer_url = document.referrer ? document.referrer.slice(0, 500) : '';
    found.landed_at = new Date().toISOString();
    return found;
  } catch {
    return null;
  }
}

export function useUtmAttribution() {
  // Capture on mount — first landing wins.
  useEffect(() => {
    const fromUrl = readFromUrl();
    if (!fromUrl) return;
    const existing = safeParseSession();
    // First-touch semantics: only overwrite if no existing attribution.
    if (!existing) {
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(fromUrl));
      } catch {
        // sessionStorage disabled (Safari private mode etc.) — silent fallback.
      }
      // Fire-and-forget conversion ping. Best-effort: a failure is fine.
      try {
        const url = `${process.env.REACT_APP_BACKEND_URL}/api/partners/track-source`;
        fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            utm_source: fromUrl.utm_source || null,
            utm_medium: fromUrl.utm_medium || null,
            utm_campaign: fromUrl.utm_campaign || null,
            utm_content: fromUrl.utm_content || null,
            referrer_url: fromUrl.referrer_url || null,
            landing_path: typeof window !== 'undefined' ? window.location.pathname : null,
          }),
          keepalive: true,
        }).catch(() => { /* swallow — analytics never blocks UX */ });
      } catch { /* noop */ }
    }
  }, []);

  return useMemo(() => {
    const utm = safeParseSession() || readFromUrl() || {};
    const isInstagram = (utm.utm_source || '').toLowerCase() === 'instagram';

    // Build a UTM-preserving apply link so the multi-page funnel keeps
    // its attribution intact across the marketing → apply hop.
    let applyHref = '/partners/engineers/apply';
    const carry = KEYS.filter(k => utm[k]).map(k => `${k}=${encodeURIComponent(utm[k])}`);
    if (carry.length) applyHref += `?${carry.join('&')}`;

    return { utm, isInstagram, applyHref };
  }, []);
}

export default useUtmAttribution;
