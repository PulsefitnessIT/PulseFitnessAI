import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { notify } from '@/components/notifications';
import { isModServiceMode } from '@/utils/portalMode';

/**
 * useSignedOutNotice (iter 274)
 *
 * Shared sign-out confirmation across portals. When a user arrives with
 * `?signedout=1` (set by the auth-context logout redirect), shows a one-time
 * "Signed out successfully" toast and strips the flag so a refresh won't
 * re-toast. Returns `prefillEmail` from `?email=` to pre-fill the login form.
 *
 * MODService mode: never pre-fill from — or leave — an email in the URL (a
 * service email must not sit in the address bar / browser history), so the
 * `email` param is ignored and actively stripped there.
 */
export function useSignedOutNotice() {
  const [searchParams] = useSearchParams();
  const modMode = isModServiceMode();
  const prefillEmail = modMode ? '' : (searchParams.get('email') || '');
  const signedOut = searchParams.get('signedout') === '1';

  useEffect(() => {
    const url = new URL(window.location.href);
    let changed = false;
    if (signedOut) {
      notify.success('Signed out successfully');
      url.searchParams.delete('signedout');
      changed = true;
    }
    // Privacy — never leave a service email in the MOD portal URL/history.
    if (modMode && url.searchParams.has('email')) {
      url.searchParams.delete('email');
      changed = true;
    }
    if (changed) {
      window.history.replaceState({}, '', url.pathname + url.search);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { prefillEmail, signedOut };
}
