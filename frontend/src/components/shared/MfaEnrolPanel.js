/**
 * MfaEnrolPanel — mandatory MFA enrolment during login (used inside the Navbar
 * auth dialog). Given a short-lived { temp_token, email } it walks the user
 * through: fetch QR (/auth/mfa/enrol/setup) → scan + enter first code
 * (/auth/mfa/enrol/complete) → save backup codes → onComplete(loginResponse).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, ArrowRight, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MfaEnrolPanel({
  enrol, setEnrol, code, setCode, backupCodes, setBackupCodes, onComplete,
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState(false);

  // Fetch the QR/secret once for this temp_token.
  useEffect(() => {
    let alive = true;
    if (!enrol?.temp_token || enrol.secret) return () => {};
    (async () => {
      try {
        const { data } = await axios.post(`${API}/auth/mfa/enrol/setup`, { temp_token: enrol.temp_token });
        if (!alive) return;
        setEnrol((prev) => ({ ...prev, secret: data.secret, qrDataUrl: data.qrcode_data_url || '', provisioning_uri: data.provisioning_uri }));
      } catch {
        if (alive) setErr('Could not start MFA enrolment. Please try signing in again.');
      }
    })();
    return () => { alive = false; };
  }, [enrol, setEnrol]);

  const verify = async (e) => {
    e?.preventDefault?.();
    const c = (code || '').replace(/\D/g, '');
    if (busy || c.length !== 6) { setErr('Enter the 6-digit code from your authenticator app.'); return; }
    setBusy(true); setErr('');
    try {
      const { data } = await axios.post(`${API}/auth/mfa/enrol/complete`, { temp_token: enrol.temp_token, code: c });
      setBackupCodes({ codes: data.backup_codes || [], data });
    } catch (e2) {
      const s = e2?.response?.status;
      setErr((s === 400 || s === 401) ? 'That code did not match. Try the current code from your app.' : 'Could not complete enrolment.');
    } finally { setBusy(false); }
  };

  // Backup-codes acknowledgement step.
  if (backupCodes) {
    return (
      <div className="space-y-4" data-testid="nav-mfa-enrol-backup">
        <div className="flex items-start gap-2">
          <ShieldCheck className="text-emerald-400 mt-0.5" size={20} />
          <div>
            <p className="text-sm font-semibold text-white">Two-factor is now on</p>
            <p className="text-xs text-white/60 mt-0.5">Save these backup codes — each works once if you lose your authenticator. They won't be shown again.</p>
          </div>
        </div>
        <pre className="rounded-xl bg-black/40 border border-white/10 p-3 text-sm font-mono grid grid-cols-2 gap-1 text-emerald-300" data-testid="nav-mfa-enrol-codes">
          {(backupCodes.codes || []).join('\n')}
        </pre>
        <label className="flex items-center gap-2 text-sm text-white/80">
          <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} data-testid="nav-mfa-enrol-saved" />
          I've saved my backup codes
        </label>
        <Button
          onClick={() => onComplete?.(backupCodes.data)}
          disabled={!saved}
          className="w-full"
          data-testid="nav-mfa-enrol-continue"
        >Continue <ArrowRight size={14} /></Button>
      </div>
    );
  }

  return (
    <form onSubmit={verify} className="space-y-4" data-testid="nav-mfa-enrol-form">
      <p className="text-sm text-white/80">
        Two-factor authentication is required for <span className="text-white">{enrol?.email}</span>.
        Scan the QR code in Google Authenticator, Authy or 1Password, then enter the 6-digit code.
      </p>
      {enrol?.qrDataUrl ? (
        <img src={enrol.qrDataUrl} alt="Scan in your authenticator app" className="w-40 h-40 mx-auto rounded-lg border border-white/10 p-2 bg-white" data-testid="nav-mfa-enrol-qr" />
      ) : (
        <div className="w-40 h-40 mx-auto flex items-center justify-center"><Loader2 className="animate-spin text-white/60" /></div>
      )}
      {enrol?.secret && (
        <div>
          <p className="text-xs text-white/60 mb-1">Can't scan? Enter this key:</p>
          <code className="block break-all rounded-lg bg-white/10 px-3 py-2 text-xs font-mono text-sky-300" data-testid="nav-mfa-enrol-secret">{enrol.secret}</code>
        </div>
      )}
      <Input
        placeholder="123456"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
        maxLength={6}
        className="text-center tracking-[0.3em]"
        data-testid="nav-mfa-enrol-code"
      />
      {err && <div className="rounded-xl bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-300" data-testid="nav-mfa-enrol-error">{err}</div>}
      <Button type="submit" disabled={busy || (code || '').length !== 6} className="w-full" data-testid="nav-mfa-enrol-submit">
        {busy ? <><Loader2 size={14} className="animate-spin" /> Verifying…</> : <>Verify &amp; enable <ArrowRight size={14} /></>}
      </Button>
    </form>
  );
}
