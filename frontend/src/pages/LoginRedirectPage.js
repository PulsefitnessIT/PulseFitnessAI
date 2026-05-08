import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/App';
import LoginPage from './LoginPage';

/**
 * /login route guard — sends authenticated users to their home portal,
 * otherwise renders the dedicated GymAxis sign-in page.
 */
const LoginRedirectPage = () => {
  const { user } = useAuth();

  if (user) {
    const dest = (user.is_master_admin || user.is_pulse_admin)
      ? '/master-admin'
      : (user.account_type === 'lite' || user.account_type === 'pulse_pro')
        ? '/pulse'
        : '/dashboard';
    return <Navigate to={dest} replace />;
  }
  return <LoginPage />;
};

export default LoginRedirectPage;
