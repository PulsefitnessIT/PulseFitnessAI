import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { notify } from '@/components/notifications';

/**
 * useSignedOutNotice (iter 274)
 *
 * Shared sign-out confirmation across portals. When a user arrives with
 * `?signedout=1` (set by the auth-context logout redirect), shows a one-time
 * "Signed out successfully" toast and strips the flag so a refresh won't
 * re-toast. Returns `prefillEmail` from `?email=` to pre-fill the login form.
 */
export function useSignedOutNotice() {
  const [searchParams] = useSearchParams();
  const prefillEmail = searchParams.get('email') || '';
  const signedOut = searchParams.get('signedout') === '1';

  useEffect(() => {
    if (signedOut) {
      notify.success('Signed out successfully');
      const url = new URL(window.location.href);
      url.searchParams.delete('signedout');
      window.history.replaceState({}, '', url.pathname + url.search);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { prefillEmail, signedOut };
}
