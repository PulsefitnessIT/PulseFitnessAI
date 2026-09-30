import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { inviteStatus, acceptInvite } from './bfpoApi';
import { PULSE_LOGO, inputCls } from './ui';
import { Loader2, CheckCircle2, KeyRound } from 'lucide-react';

export default function BFPOInviteSetPassword() {
  const { token } = useParams();
  const [state, setState] = useState({ loading: true });
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    let alive = true;
    inviteStatus(token)
      .then((d) => { if (alive) setState({ loading: false, ...d }); })
      .catch(() => { if (alive) setState({ loading: false, valid: false, reason: 'error' }); });
    return () => { alive = false; };
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    if (pw.length < 8) { setErr('Password must be at least 8 characters'); return; }
    if (pw !== confirm) { setErr('Passwords do not match'); return; }
    setBusy(true);
    try { await acceptInvite(token, pw); setDone(true); }
    catch (e2) { setErr(e2?.response?.data?.detail || 'Could not set your password'); }
    finally { setBusy(false); }
  };

  const Shell = ({ children }) => (
    <div className="min-h-screen bg-[#F8F9FA] flex flex-col" style={{ fontFamily: "'Proxima Nova', 'Inter', system-ui, sans-serif" }}>
      <div className="on-dark text-white" style={{ backgroundColor: '#000000' }}>
        <div className="max-w-6xl mx-auto px-4 h-20 flex items-center">
          <img src={PULSE_LOGO} alt="Pulse Fitness" className="h-10 rounded-md object-cover" style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }} />
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center p-4">{children}</div>
    </div>
  );

  if (state.loading) return <Shell><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></Shell>;

  if (!state.valid) {
    const msg = state.reason === 'used' ? 'This invite has already been used. Please sign in instead.'
      : state.reason === 'expired' ? 'This invite link has expired. Ask your MOD Operations contact to resend it.'
      : 'This invite link is invalid.';
    return (
      <Shell>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md text-center" data-testid="invite-invalid">
          <p className="text-lg font-bold text-slate-900 mb-1">Invite unavailable</p>
          <p className="text-sm text-slate-500 mb-5">{msg}</p>
          <a href="/MODService"><button className="bg-cyan-600 hover:bg-cyan-700 text-white font-semibold rounded-xl px-5 py-3 text-sm">Go to sign in</button></a>
        </div>
      </Shell>
    );
  }

  if (done) {
    return (
      <Shell>
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md text-center" data-testid="invite-done">
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
          <p className="text-lg font-bold text-slate-900 mb-1">You're all set</p>
          <p className="text-sm text-slate-500 mb-5">Your password has been created. Sign in to open the MOD / BFPO Engineer Portal.</p>
          <a href="/MODService"><button className="bg-cyan-600 hover:bg-cyan-700 text-white font-semibold rounded-xl px-5 py-3 text-sm" data-testid="invite-done-signin">Sign in</button></a>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <form onSubmit={submit} className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 max-w-md w-full" data-testid="invite-form">
        <p className="text-xs font-semibold text-cyan-700 uppercase tracking-wide mb-1">MOD / BFPO Engineer Portal</p>
        <h1 className="text-2xl font-bold text-slate-900 mb-1">Set your password</h1>
        <p className="text-sm text-slate-500 mb-5">Welcome{state.full_name ? `, ${state.full_name}` : ''}. Choose a password for <span className="font-medium">{state.email}</span>.</p>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">New password</span>
            <input type="password" className={`${inputCls} mt-1`} value={pw} onChange={(e) => setPw(e.target.value)} required data-testid="invite-pw" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Confirm password</span>
            <input type="password" className={`${inputCls} mt-1`} value={confirm} onChange={(e) => setConfirm(e.target.value)} required data-testid="invite-pw-confirm" />
          </label>
          {err && <p className="text-sm text-red-600" data-testid="invite-error">{err}</p>}
          <button type="submit" disabled={busy} className="w-full inline-flex items-center justify-center gap-2 bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white font-semibold rounded-xl px-5 py-3 text-sm" data-testid="invite-submit">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} Set password &amp; activate
          </button>
        </div>
      </form>
    </Shell>
  );
}
