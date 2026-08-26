// Resolve an equipment photo URL to the CURRENT backend host.
//
// Equipment photos are served by our own API at /api/public/equipment/:id/photo.
// Older records stored an ABSOLUTE url with the host baked in (e.g. an old
// preview host). When the app later moves to a different host those URLs 404
// and render as a broken/grey image. This helper strips any baked-in host and
// rebuilds the URL against the live REACT_APP_BACKEND_URL, so both new
// (relative) and legacy (stale absolute) values load correctly. External
// images (manufacturer/CDN links) are passed through untouched.
const API_ORIGIN = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');

export function resolveEquipmentPhoto(url) {
  if (!url || typeof url !== 'string') return url;
  const marker = '/api/public/equipment/';
  const idx = url.indexOf(marker);
  if (idx >= 0) return `${API_ORIGIN}${url.slice(idx)}`;
  return url;
}
