/**
 * SSOCompletePage — lands here after the IdP callback. The backend drops the
 * JWT in the URL fragment so it never hits server logs or the referrer.
 * We parse, persist, and redirect to the dashboard.
 */
import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/App';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SSOCompletePage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  useEffect(() => {
    const hash = window.location.hash || '';
    const params = new URLSearchParams(hash.replace(/^#/, ''));
    const token = params.get('token');
    if (!token) {
      notify.error('SSO login failed — no token returned.');
      navigate('/', { replace: true });
      return;
    }
    // Fetch the user record using the new token, then persist.
    axios
      .get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => {
        login(token, res.data);
        notify.success('Signed in via SSO.');
        // Clear the fragment so the token is not bookmarked.
        window.history.replaceState({}, document.title, '/dashboard');
        const dest = res.data?.account_type === 'lite' ? '/pulse' : '/dashboard';
        navigate(dest, { replace: true });
      })
      .catch(() => {
        notify.error('SSO token invalid.');
        navigate('/', { replace: true });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-ink-alt)] text-white flex items-center justify-center" data-testid="sso-complete-page">
      <div className="text-center">
        <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-white mx-auto mb-3" />
        <p className="text-sm text-white/70">Completing sign-in…</p>
      </div>
    </div>
  );
}
