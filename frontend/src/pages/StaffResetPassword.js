import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CORE = '#19CDFF';

const fmtErr = (d) => (typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e?.msg || '').join(' ') : d?.msg || 'Something went wrong.');

export default function StaffResetPassword() {
  const { token } = useParams();
  const nav = useNavigate();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  const submit = async () => {
    if (password !== confirm) { setErr('Passwords do not match.'); return; }
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/reset-password`, { token, password });
      setDone(true);
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail) || 'Could not reset password.'); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl p-8 border border-slate-200">
        {done ? (
          <div className="text-center" data-testid="staff-reset-done">
            <CheckCircle2 className="mx-auto text-emerald-500" size={40} />
            <h1 className="text-xl font-bold text-slate-900 mt-3">Password reset</h1>
            <p className="text-slate-500 text-sm mt-1">Your password has been updated. You can now sign in.</p>
            <button onClick={() => nav('/staff-login')} data-testid="staff-reset-tologin"
              className="mt-4 w-full rounded-lg py-2.5 font-semibold text-slate-900" style={{ background: CORE }}>Go to sign in</button>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-slate-900">Choose a new password</h1>
            <p className="text-slate-500 mt-1 text-sm">Enter a new password for your Pulse Fitness portal.</p>
            <label className="block mt-5 text-sm font-medium text-slate-700">New password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="staff-reset-password"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5" placeholder="At least 8 characters" />
            <label className="block mt-3 text-sm font-medium text-slate-700">Confirm password</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="staff-reset-confirm"
              onKeyDown={(e) => { if (e.key === 'Enter' && password.length >= 8) submit(); }}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5" placeholder="Re-enter password" />
            {err && <div className="text-red-500 text-sm mt-2" data-testid="staff-reset-error">{err}</div>}
            <button onClick={submit} disabled={busy || password.length < 8} data-testid="staff-reset-btn"
              className="mt-4 w-full rounded-lg py-2.5 font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
              {busy ? 'Saving…' : 'Reset password'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
