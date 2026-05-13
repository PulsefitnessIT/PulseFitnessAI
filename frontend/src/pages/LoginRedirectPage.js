import React from 'react';
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
    const safeNext = (raw && raw.startsWith('/') && !raw.startsWith('//')) ? raw : null;
    const fallback = (user.is_master_admin || user.is_pulse_admin)
      ? '/master-admin'
      : (user.account_type === 'lite' || user.account_type === 'pulse_pro')
        ? '/pulse'
        : '/dashboard';
    return <Navigate to={safeNext || fallback} replace />;
  }
  return <LoginPage />;
};

export default LoginRedirectPage;
