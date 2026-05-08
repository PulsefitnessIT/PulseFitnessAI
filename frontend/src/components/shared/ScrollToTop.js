/**
 * ScrollToTop — resets window scroll to (0,0) on every route change.
 *
 * Fixes the UX issue where clicking a link (especially in the footer)
 * left the user at the previous page's scroll position instead of the
 * top of the new page. Mount once inside <BrowserRouter>.
 */
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

export default function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    // If the URL has a hash (#section), let the browser jump to it.
    if (hash) return;
    // Use 'instant' so the page jumps immediately, not animated — the
    // user expects a fresh page to start at the top, not scroll to it.
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [pathname, hash]);
  return null;
}
