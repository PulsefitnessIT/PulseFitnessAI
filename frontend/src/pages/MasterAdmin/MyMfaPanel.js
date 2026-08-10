/**
 * Master Admin — My two-factor (MFA) enrolment.
 *
 * Light-themed panel (matches the admin console) that walks the master admin
 * through TOTP enrolment: setup → scan QR → verify first code → save backup
 * codes → done. Once enabled, step-up and forced re-auth use the authenticator
 * code instead of a password (see utils/step_up.py verify_step_up_challenge).
 *
 * Consumes the existing, already-built endpoints:
 *   GET  /auth/mfa/status, POST /auth/mfa/setup, /auth/mfa/enable, /auth/mfa/disable
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { ShieldCheck, Shield, ShieldAlert, Copy, Check, Smartphone, KeyRound, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MyMfaPanel() {
  const [status, setStatus] = useState(null);
  const [stage, setStage] = useState('idle'); // idle | enrolling | backup
  const [secret, setSecret] = useState('');
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState([]);
  const [savedAck, setSavedAck] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const headers = useCallback(() => ({
    Authorization: `Bearer ${localStorage.getItem('token')}`,
  }), []);

  const loadStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/auth/mfa/status`, { headers: headers() });
      setStatus(res.data);
    } catch { setStatus(null); }
  }, [headers]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const startEnrol = async () => {
    setBusy(true);
    try {
      const res = await axios.post(`${API}/auth/mfa/setup`, {}, { headers: headers() });
      setQrDataUrl(res.data.qrcode_data_url || '');
      setSecret(res.data.secret || '');
      setCode('');
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
      if (!res.data?.success || !Array.isArray(res.data.backup_codes) || res.data.backup_codes.length === 0) {
        throw new Error('MFA was not completed: backup codes were not issued.');
      }
      setBackupCodes(res.data.backup_codes);
      setSavedAck(false);
      setStage('backup');
      notify.success('MFA enabled', 'Save your backup codes before leaving this screen.');
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

  const downloadBackup = () => {
    const blob = new Blob(
      [`Pulse Fitness — Master Admin MFA backup codes\nGenerated: ${new Date().toISOString()}\n\n${backupCodes.join('\n')}\n\nEach code can be used once. Store securely.`],
      { type: 'text/plain' },
    );
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'pulse-mfa-backup-codes.txt';
    document.body.appendChild(a); a.click(); a.remove();
    window.URL.revokeObjectURL(url);
  };

  if (!status) {
    return (
      <div className="flex items-center justify-center h-40 text-zinc-400" data-testid="my-mfa-panel">
        <Loader2 className="animate-spin" size={20} />
      </div>
    );
  }

  const enabled = status.enabled;

  return (
    <div className="max-w-2xl space-y-5" data-testid="my-mfa-panel">
      {/* Status header */}
      <div className="rounded-xl border border-zinc-200 bg-white p-5">
        <div className="flex items-start gap-3">
          <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${enabled ? 'bg-emerald-100' : 'bg-zinc-100'}`}>
            {enabled ? <ShieldCheck className="text-emerald-600" size={22} /> : <Shield className="text-zinc-500" size={22} />}
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-zinc-900">Two-factor authentication (TOTP)</h3>
            <p className="text-sm text-zinc-500 mt-0.5">
              {enabled
                ? `Enabled · ${status.backup_codes_remaining} backup codes remaining. Step-up and forced re-auth now use your authenticator code.`
                : 'Add an authenticator app (Google Authenticator, Authy, 1Password) so sensitive actions ask for a 6-digit code instead of your password.'}
            </p>
            {enabled && (
              <span className="inline-flex items-center gap-1.5 mt-3 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-xs font-semibold text-emerald-700" data-testid="my-mfa-enabled-badge">
                <ShieldCheck size={13} /> Active
              </span>
            )}
          </div>
        </div>

        {stage === 'idle' && !enabled && (
          <button
            onClick={startEnrol}
            disabled={busy}
            className="mt-4 inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50" style={{background:"#18181b",color:"#fff"}}
            data-testid="my-mfa-start-btn"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Smartphone size={15} />}
            {busy ? 'Preparing…' : 'Set up authenticator'}
          </button>
        )}

        {stage === 'idle' && enabled && (
          <p className="mt-4 flex items-center gap-1.5 text-xs text-amber-600" data-testid="my-mfa-locked-note">
            <ShieldAlert size={14} /> MFA is mandatory for the master admin and cannot be self-disabled.
          </p>
        )}
      </div>

      {/* Enrolment */}
      {stage === 'enrolling' && (
        <div className="rounded-xl border border-zinc-200 bg-white p-5 space-y-4" data-testid="my-mfa-enrolling">
          <div className="flex flex-col sm:flex-row gap-5">
            <div className="flex-shrink-0">
              {qrDataUrl
                ? <img src={qrDataUrl} alt="Scan this QR in your authenticator app" className="w-44 h-44 rounded-lg border border-zinc-200 p-2 bg-white" data-testid="my-mfa-qr" />
                : <div className="w-44 h-44 rounded-lg border border-zinc-200 flex items-center justify-center text-zinc-300"><Loader2 className="animate-spin" /></div>}
            </div>
            <div className="flex-1 space-y-3">
              <p className="text-sm text-zinc-700">
                1. Scan the QR code with your authenticator app.<br />
                Can't scan? Enter this key manually:
              </p>
              <code className="block break-all rounded-lg bg-zinc-100 px-3 py-2 text-sm text-zinc-800 font-mono" data-testid="my-mfa-secret">{secret}</code>
              <div>
                <label className="text-xs font-semibold text-zinc-600 mb-1 block">2. Enter the 6-digit code it shows</label>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  maxLength={6}
                  inputMode="numeric"
                  placeholder="123456"
                  className="w-40 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-center text-lg tracking-[0.3em] text-zinc-900 focus:outline-none focus:border-zinc-900"
                  data-testid="my-mfa-code-input"
                />
              </div>
            </div>
          </div>
          <div className="flex gap-2 pt-2">
            <button
              onClick={confirmEnrol}
              disabled={busy || code.length !== 6}
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50" style={{background:"#18181b",color:"#fff"}}
              data-testid="my-mfa-confirm-btn"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />}
              {busy ? 'Verifying…' : 'Verify & enable'}
            </button>
            <button
              onClick={() => { setStage('idle'); setCode(''); }}
              className="rounded-lg px-4 py-2 text-sm font-medium text-zinc-500 hover:text-zinc-900"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Backup codes */}
      {stage === 'backup' && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-5 space-y-3" data-testid="my-mfa-backup">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-amber-600" />
            <h4 className="text-sm font-semibold text-amber-900">Save your backup codes</h4>
          </div>
          <p className="text-sm text-amber-800">
            Each code works once if you lose your authenticator. Store them somewhere safe — they won't be shown again.
          </p>
          <pre className="rounded-lg bg-white border border-amber-200 p-3 text-sm font-mono grid grid-cols-2 gap-1 text-zinc-800" data-testid="my-mfa-backup-codes">
            {backupCodes.join('\n')}
          </pre>
          <div className="flex flex-wrap gap-2">
            <button onClick={copyBackup} className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100" data-testid="my-mfa-copy-btn">
              {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy'}
            </button>
            <button onClick={downloadBackup} className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-100" data-testid="my-mfa-download-btn">
              Download .txt
            </button>
          </div>
          <label className="flex items-center gap-2 pt-1 text-sm text-amber-900">
            <input type="checkbox" checked={savedAck} onChange={(e) => setSavedAck(e.target.checked)} data-testid="my-mfa-saved-check" />
            I have stored these codes securely
          </label>
          <button
            onClick={() => { setStage('idle'); setBackupCodes([]); setCode(''); }}
            disabled={!savedAck}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 disabled:opacity-50" style={{background:"#18181b",color:"#fff"}}
            data-testid="my-mfa-done-btn"
          >
            Done
          </button>
        </div>
      )}
    </div>
  );
}
