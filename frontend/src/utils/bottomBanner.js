/**
 * bottomBanner — ref-counted body class so bottom-docked banners
 * (CookieConsent, PWA install prompt) reserve scroll space and never
 * permanently cover a page's bottom CTA. See index.css `.has-bottom-banner`.
 */
let count = 0;

export function setBottomBannerVisible(visible) {
  if (typeof document === 'undefined') return;
  count = Math.max(0, count + (visible ? 1 : -1));
  document.body.classList.toggle('has-bottom-banner', count > 0);
}
