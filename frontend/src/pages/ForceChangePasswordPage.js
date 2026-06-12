/**
 * Force-Change-Password Page
 *
 * Shown to users with `must_change_password === true` on their session.
 * They land here right after first login with a temporary password and
 * cannot navigate elsewhere until the password is rotated. On success
 * we replace their JWT with the freshly-issued one and route them to
 * the appropriate dashboard for their role.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Lock, ShieldCheck, ArrowRight, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { useInlineBanner } from '@/components/notifications';
import { useAuth } from '@/App';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ForceChangePasswordPage() {
  const navigate = useNavigate();
  const { user, login } = useAuth();
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const { banner, show, clear } = useInlineBanner();

  // If the user lands here without the flag (e.g. refreshed after a real
  // change) just bounce them to their proper console.
  if (user && !user.must_change_password) {
    navigate(
      user.is_master_admin || user.is_pulse_admin ? '/master-admin'
        : user.is_service_desk ? '/service-desk'
          : '/dashboard',
      { replace: true },
    );
    return null;
  }
  if (!user) {
    navigate('/login', { replace: true });
    return null;
  }

  const passwordRules = [
    { label: 'At least 8 characters', ok: newPwd.length >= 8 },
    { label: 'Contains an uppercase letter', ok: /[A-Z]/.test(newPwd) },
    { label: 'Contains a lowercase letter', ok: /[a-z]/.test(newPwd) },
    { label: 'Contains a number', ok: /\d/.test(newPwd) },
    { label: 'Contains a symbol', ok: /[^A-Za-z0-9]/.test(newPwd) },
    { label: 'Different from temporary password', ok: newPwd && newPwd !== currentPwd },
  ];
  const allValid = passwordRules.every((r) => r.ok) && newPwd === confirmPwd;

  const submit = async (e) => {
    e.preventDefault();
    clear();
    if (newPwd !== confirmPwd) {
      show({ tone: 'error', title: 'Passwords don\'t match', detail: 'Re-type the new password to confirm.' });
      return;
    }
    if (!allValid) {
      show({ tone: 'error', title: 'Password too weak', detail: 'Tick every rule below before continuing.' });
      return;
    }
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/auth/force-change-password`,
        { current_password: currentPwd, new_password: newPwd },
        { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } },
      );
      // Re-issue session with the new token from the server.
      login(data.token, { ...user, must_change_password: false });
      show({ tone: 'success', title: 'Password updated', detail: 'Redirecting you in…' });
      setTimeout(() => {
        // Iter 250 — Service-Desk-nominated users go straight to the desk
        // after setting their first password.
        navigate(
          user.is_master_admin || user.is_pulse_admin ? '/master-admin'
            : user.is_service_desk ? '/service-desk'
              : '/dashboard',
          { replace: true },
        );
      }, 800);
    } catch (err) {
      show({
        tone: 'error',
        title: 'Couldn\'t update password',
        detail: err.response?.data?.detail || 'Please try again.',
      });
    }
    setBusy(false);
  };

  return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center p-4" data-testid="force-change-password-page">
      <Card className="max-w-md w-full p-7 rounded-2xl shadow-xl border border-zinc-200">
        <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)] mx-auto mb-5">
          <ShieldCheck size={26} />
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 text-center mb-1">Set your password</h1>
        <p className="text-sm text-zinc-500 text-center mb-6">
          You signed in with a temporary password. Choose a permanent one to continue.
        </p>

        {banner}

        <form onSubmit={submit} className="space-y-4 mt-2" data-testid="force-change-form">
          <div>
            <Label className="text-xs">Current (temporary) password</Label>
            <div className="relative">
              <Input
                type={showCurrent ? 'text' : 'password'}
                value={currentPwd}
                onChange={(e) => setCurrentPwd(e.target.value)}
                className="mt-1 pr-9"
                autoComplete="current-password"
                data-testid="force-change-current"
                required
              />
              <button type="button" onClick={() => setShowCurrent((v) => !v)} className="absolute right-2 top-2.5 text-zinc-400 hover:text-zinc-600" tabIndex={-1}>
                {showCurrent ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div>
            <Label className="text-xs">New password</Label>
            <div className="relative">
              <Input
                type={showNew ? 'text' : 'password'}
                value={newPwd}
                onChange={(e) => setNewPwd(e.target.value)}
                className="mt-1 pr-9"
                autoComplete="new-password"
                data-testid="force-change-new"
                required
              />
              <button type="button" onClick={() => setShowNew((v) => !v)} className="absolute right-2 top-2.5 text-zinc-400 hover:text-zinc-600" tabIndex={-1}>
                {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div>
            <Label className="text-xs">Confirm new password</Label>
            <Input
              type={showNew ? 'text' : 'password'}
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
              className="mt-1"
              autoComplete="new-password"
              data-testid="force-change-confirm"
              required
            />
          </div>

          <ul className="text-[11px] space-y-1 mt-3">
            {passwordRules.map((r, i) => (
              <li key={i} className={r.ok ? 'text-emerald-600' : 'text-zinc-400'} data-testid={`pw-rule-${i}`}>
                <span className="inline-block w-3 mr-1.5">{r.ok ? '✓' : '○'}</span>{r.label}
              </li>
            ))}
          </ul>

          <Button
            type="submit"
            disabled={busy || !allValid}
            className="w-full mt-2 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white rounded-full"
            data-testid="force-change-submit"
          >
            {busy ? 'Saving…' : <><Lock size={14} className="mr-1.5" /> Update password</>}
            {!busy && <ArrowRight size={14} className="ml-1.5" />}
          </Button>
        </form>
      </Card>
    </div>
  );
}
