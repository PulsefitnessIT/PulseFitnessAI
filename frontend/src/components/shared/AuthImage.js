/**
 * AuthImage
 * ---------
 * An <img> replacement that fetches authenticated image endpoints with the
 * Bearer token, because HTML <img src> cannot set request headers.
 *
 * Usage:
 *   <AuthImage src={`${API}/equipment/${id}/qr-code?size=120`} alt="QR" />
 *
 * - Reads the JWT from localStorage('token') at load time.
 * - Converts the response into a blob URL and feeds it to a real <img>.
 * - Revokes the blob URL on unmount / src change to avoid memory leaks.
 * - Falls back to a `fallbackSrc` or a plain `<img>` on error.
 *
 * If `src` is already a direct blob or data URL, or a public URL (spec-sheet
 * image), render the <img> directly without fetching.
 */
import React, { useEffect, useState } from 'react';

const isAlreadyRenderable = (src) => {
  if (!src) return false;
  return src.startsWith('blob:') || src.startsWith('data:') || /\/spec-sheets\/image\//.test(src) || /^https?:\/\/(?!.*\/api\/)/.test(src);
};

export default function AuthImage({ src, alt = '', className = '', onError, fallbackSrc, ...rest }) {
  const [objectUrl, setObjectUrl] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!src) return undefined;
    // Public URL → skip the fetch round-trip, render directly.
    if (isAlreadyRenderable(src)) {
      setObjectUrl(src);
      return undefined;
    }
    let aborted = false;
    let localUrl = null;
    (async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('token') : '';
        const res = await fetch(src, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        localUrl = URL.createObjectURL(blob);
        if (!aborted) setObjectUrl(localUrl);
      } catch {
        if (!aborted) setFailed(true);
      }
    })();
    return () => {
      aborted = true;
      if (localUrl) URL.revokeObjectURL(localUrl);
    };
  }, [src]);

  if (failed) {
    if (fallbackSrc) return <img src={fallbackSrc} alt={alt} className={className} {...rest} />;
    return null;
  }

  if (!objectUrl) {
    return <div className={`${className} animate-pulse bg-white dark:bg-zinc-900/5`} aria-hidden data-testid="auth-image-loading" />;
  }

  return <img src={objectUrl} alt={alt} className={className} onError={onError} {...rest} />;
}
