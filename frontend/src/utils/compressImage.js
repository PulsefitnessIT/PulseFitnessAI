/**
 * compressImage — Iter 220db.
 *
 * Field engineers shoot high-res 12 MP photos that take forever to
 * upload over patchy 4G. We resize / re-encode client-side before
 * hitting ``/files/upload``. Typical 4 MB photo lands as ~250 KB
 * without visible quality loss for fault evidence.
 *
 * Strategy:
 *   * Reject non-image files (caller already validated mime).
 *   * Cap width at ``maxWidth`` (default 2048 px); preserve aspect ratio.
 *   * Re-encode to JPEG at ``quality`` (default 0.8).
 *   * Skip compression when the image is already smaller than the cap
 *     AND under ``minBytes`` — saves CPU on already-tiny shots.
 *
 * Falls back to the original blob on any error so a buggy decoder
 * never blocks the upload.
 */
const DEFAULTS = {
  maxWidth: 2048,
  quality: 0.8,
  minBytes: 400 * 1024, // 400 KB — don't bother compressing tiny shots
};

export async function compressImage(file, options = {}) {
  const opts = { ...DEFAULTS, ...options };
  if (!file || !file.type || !file.type.startsWith('image/')) return file;
  // GIF + SVG would lose animation / vector — pass through.
  if (file.type === 'image/gif' || file.type === 'image/svg+xml') return file;
  if (file.size < opts.minBytes) return file;

  try {
    const bitmap = await loadBitmap(file);
    const ratio = Math.min(1, opts.maxWidth / bitmap.width);
    const targetW = Math.round(bitmap.width * ratio);
    const targetH = Math.round(bitmap.height * ratio);
    const canvas = document.createElement('canvas');
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0, targetW, targetH);
    const blob = await new Promise((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', opts.quality);
    });
    if (!blob || blob.size >= file.size) return file;
    const baseName = (file.name || 'photo').replace(/\.[^.]+$/, '');
    return new File([blob], `${baseName}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now(),
    });
  } catch (_e) {
    return file;
  }
}

async function loadBitmap(file) {
  if (typeof createImageBitmap === 'function') {
    return createImageBitmap(file);
  }
  // Fallback for older browsers.
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = (e) => {
      URL.revokeObjectURL(url);
      reject(e);
    };
    img.src = url;
  });
}

export const __test__ = { DEFAULTS };
