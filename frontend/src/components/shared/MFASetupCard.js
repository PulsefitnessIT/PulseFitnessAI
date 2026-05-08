/**
 * MFASetupCard — renders inside Account panel. Fetches /auth/mfa/status,
 * walks the user through: setup → scan QR → enter first code → show backup
 * codes (once) → disable with code.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Shield, ShieldCheck, ShieldAlert, Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MFASetupCard() {
  const [status, setStatus] = useState(null);
  const [stage, setStage] = useState('idle'); // idle | enrolling | backup | disabling
  const [secret, setSecret] = useState('');
  const [qrUri, setQrUri] = useState('');
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const headers = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('token')}`,
  }), []);

  const loadStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/auth/mfa/status`, { headers: headers() });
      setStatus(res.data);
    } catch {
      setStatus(null);
    }
  }, [headers]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const startEnrol = async () => {
    setBusy(true);
    try {
      const res = await axios.post(`${API}/auth/mfa/setup`, {}, { headers: headers() });
      setQrUri(res.data.provisioning_uri);
      setQrDataUrl(res.data.qrcode_data_url || '');
      setSecret(res.data.secret);
      setStage('enrolling');
    } catch (e) {
      notifyApiError(notify, e, 'Failed to start MFA setup');
    }
    setBusy(false);
  };

  const confirmEnrol = async () => {
    setBusy(true);
    try {
      const res = await axios.post(`${API}/auth/mfa/enable`, { code }, { headers: headers() });
      setBackupCodes(res.data.backup_codes || []);
      setStage('backup');
      notify.success('MFA enabled. Save your backup codes!');
      await loadStatus();
    } catch (e) {
      notifyApiError(notify, e, 'Invalid code');
    }
    setBusy(false);
  };

  const disable = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/auth/mfa/disable`, { code }, { headers: headers() });
      notify.success('MFA disabled');
      setStage('idle');
      setCode('');
      await loadStatus();
    } catch (e) {
      notifyApiError(notify, e, 'Invalid code');
    }
    setBusy(false);
  };

  const copyBackup = () => {
    navigator.clipboard.writeText(backupCodes.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (!status) return null;
  const enabled = status.enabled;

  return (
    <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/5 p-5" data-testid="mfa-card">
      <div className="flex items-center gap-3 mb-3">
        {enabled ? <ShieldCheck className="text-emerald-400" size={22} /> : <Shield className="text-white/60" size={22} />}
        <div>
          <h3 className="text-base font-semibold text-white">Two-factor authentication</h3>
          <p className="text-xs text-white/60">
            {enabled ? `Enabled · ${status.backup_codes_remaining} backup codes remaining` :
             status.required ? 'Required for your account — please enable it now.' : 'Optional but strongly recommended.'}
          </p>
        </div>
      </div>

      {stage === 'idle' && !enabled && (
        <Button onClick={startEnrol} disabled={busy} data-testid="mfa-start-btn">
          {busy ? 'Preparing…' : 'Enable MFA'}
        </Button>
      )}

      {stage === 'idle' && enabled && (
        <>
          <Button variant="outline" onClick={() => setStage('disabling')} data-testid="mfa-disable-prompt-btn">
            Disable MFA
          </Button>
          {status.required && (
            <p className="mt-2 text-xs text-amber-300 flex items-center gap-1">
              <ShieldAlert size={14} /> MFA is required for your role and cannot be disabled.
            </p>
          )}
        </>
      )}

      {stage === 'enrolling' && (
        <div className="space-y-3">
          <p className="text-sm text-white/80">
            Scan the QR code with Google Authenticator, Authy, or 1Password.
            Can't scan? Enter the secret manually: <code className="text-sky-300">{secret}</code>
          </p>
          <img
            src={qrDataUrl || `${API}/auth/mfa/qrcode?uri=${encodeURIComponent(qrUri)}`}
            alt="MFA QR"
            className="w-48 h-48 bg-white dark:bg-zinc-900 rounded p-2"
            data-testid="mfa-qr-img"
          />
          <Input
            placeholder="6-digit code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            maxLength={6}
            className="w-40"
            data-testid="mfa-code-input"
          />
          <div className="flex gap-2">
            <Button onClick={confirmEnrol} disabled={busy || code.length !== 6} data-testid="mfa-confirm-btn">
              {busy ? 'Verifying…' : 'Verify & enable'}
            </Button>
            <Button variant="ghost" onClick={() => setStage('idle')}>Cancel</Button>
          </div>
        </div>
      )}

      {stage === 'backup' && (
        <div className="space-y-3">
          <p className="text-sm text-white/80">
            Save these backup codes somewhere safe. Each can be used once if you lose your device.
          </p>
          <pre className="rounded bg-black/40 p-3 text-xs font-mono grid grid-cols-2 gap-1 text-emerald-300" data-testid="mfa-backup-codes">
            {backupCodes.join('\n')}
          </pre>
          <div className="flex gap-2">
            <Button onClick={copyBackup} size="sm" variant="outline" data-testid="mfa-copy-backup-btn">
              {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy'}
            </Button>
            <Button onClick={() => { setStage('idle'); setBackupCodes([]); setCode(''); }}>
              I've saved them
            </Button>
          </div>
        </div>
      )}

      {stage === 'disabling' && (
        <div className="space-y-3">
          <p className="text-sm text-white/80">Enter a TOTP or backup code to confirm disable:</p>
          <Input
            placeholder="Code"
            value={code}
            onChange={(e) => setCode(e.target.value.trim())}
            className="w-40"
            data-testid="mfa-disable-code-input"
          />
          <div className="flex gap-2">
            <Button onClick={disable} disabled={busy || !code} variant="destructive" data-testid="mfa-disable-confirm-btn">
              {busy ? 'Working…' : 'Disable'}
            </Button>
            <Button variant="ghost" onClick={() => { setStage('idle'); setCode(''); }}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
