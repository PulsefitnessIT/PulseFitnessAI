import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/App';
import { API, useAuthHeaders, FieldRow } from './shared';
import MFASetupCard from '../MFASetupCard';

export default function SecuritySection() {
  const headers = useAuthHeaders();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (next !== confirm) {
      toast.error('New passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/account/change-password`,
        { current_password: current, new_password: next },
        { headers: headers() });
      toast.success('Password updated');
      setCurrent(''); setNext(''); setConfirm('');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not change password');
    }
    setBusy(false);
  };

  return (
    <div className="space-y-8" data-testid="account-section-security">
      <div>
        <h3 className="account-section-title">Two-factor authentication</h3>
        <p className="account-section-sub">Protect your account with a 6-digit code on every sign-in.</p>
        <div className="mt-3">
          <MFASetupCard />
        </div>
      </div>

      <div>
        <h3 className="account-section-title">Reset password</h3>
        <p className="account-section-sub">Change your password without leaving the app.</p>
        <div className="mt-3 space-y-3">
          <FieldRow label="Current password">
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="account-input"
              data-testid="account-current-password-input"
            />
          </FieldRow>
          <FieldRow label="New password">
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="account-input"
              data-testid="account-new-password-input"
            />
            <p className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              At least 8 characters. Use a mix of letters, numbers, and symbols.
            </p>
          </FieldRow>
          <FieldRow label="Confirm new password">
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="account-input"
              data-testid="account-confirm-password-input"
            />
          </FieldRow>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={submit}
              disabled={busy || !current || next.length < 8}
              className="account-btn-primary"
              data-testid="account-password-save-btn"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              Update password
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

