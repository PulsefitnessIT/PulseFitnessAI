import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/App';
import LoginPage from './LoginPage';

/**
 * /login route guard — sends authenticated users to their home portal,
 * otherwise renders the dedicated GymAxis sign-in page.
 *
 * Iter 216h68 — also honour `?next=/path` so the SessionResumedBanner
 * (and any other deep-link sender) can bounce an *already* logged-in
 * user back to where they were instead of dumping them on /dashboard.
 * Only relative paths are accepted to avoid open-redirect abuse.
 */
const LoginRedirectPage = () => {
  const { user } = useAuth();
  const location = useLocation();

  if (user) {
    const sp = new URLSearchParams(location.search);
    const raw = sp.get('next');
    // Iter 220av · F-05 — tightened open-redirect guard. Reject any
    // backslash / CR / LF / NUL / tab, protocol-relative `//host`,
    // and embedded URI schemes (`javascript:`, `data:` etc).
    const safeNext = (() => {
      if (!raw || raw.length > 512) return null;
      if (/[\\\r\n\t\0]/.test(raw)) return null;
      if (!raw.startsWith('/') || raw.startsWith('//')) return null;
      if (/^[A-Za-z][A-Za-z0-9+\-.]*:/.test(raw)) return null;
      return raw;
    })();
    const fallback = (user.is_master_admin || user.is_pulse_admin)
      ? '/master-admin'
      : (user.is_partner_engineer || user.account_type === 'partner_engineer' || user.role === 'engineer_partner')
        ? '/partner-engineer'
        : (user.account_type === 'lite' || user.account_type === 'pulse_pro')
          ? '/pulse'
          : '/dashboard';
    return <Navigate to={safeNext || fallback} replace />;
  }
  return <LoginPage />;
};

export default LoginRedirectPage;
