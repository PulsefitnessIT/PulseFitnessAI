import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Loader2, LogIn, ArrowLeft } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CORE = '#19CDFF';

const fmtErr = (d) => (typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e?.msg || '').join(' ') : d?.msg || 'Something went wrong.');

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-xl p-8 border border-slate-200">
        {children}
      </div>
    </div>
  );
}

export default function StaffLogin() {
  const nav = useNavigate();
  const [mode, setMode] = useState('login'); // login | forgot
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [info, setInfo] = useState('');

  const login = async () => {
    setBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/new-starter/staff-login`, { email, password });
      sessionStorage.setItem('staff_jwt', r.data.token);
      nav('/staff-portal');
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail) || 'Incorrect email or password.'); }
    finally { setBusy(false); }
  };

  const forgot = async () => {
    setBusy(true); setErr(''); setInfo('');
    try {
      const r = await axios.post(`${API}/new-starter/forgot-password`, { email });
      setInfo(r.data.message || 'If an account exists, a reset link has been sent.');
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail) || 'Could not send reset link.'); }
    finally { setBusy(false); }
  };

  return (
    <Shell>
      <h1 className="text-2xl font-bold text-slate-900">Pulse Fitness Staff Portal</h1>
      <p className="text-slate-500 mt-1 text-sm">
        {mode === 'login' ? 'Sign in with your email and password.' : 'Enter your email and we\u2019ll send you a reset link.'}
      </p>

      <label className="block mt-5 text-sm font-medium text-slate-700">Email</label>
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="staff-login-email"
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5" placeholder="you@company.com" />

      {mode === 'login' && (
        <>
          <label className="block mt-3 text-sm font-medium text-slate-700">Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="staff-login-password"
            onKeyDown={(e) => { if (e.key === 'Enter' && email && password) login(); }}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5" placeholder="Your password" />
        </>
      )}

      {err && <div className="text-red-500 text-sm mt-2" data-testid="staff-login-error">{err}</div>}
      {info && <div className="text-emerald-600 text-sm mt-2" data-testid="staff-login-info">{info}</div>}

      {mode === 'login' ? (
        <>
          <button onClick={login} disabled={busy || !email || !password} data-testid="staff-login-btn"
            className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-lg py-2.5 font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : <LogIn size={16} />} Log in
          </button>
          <button onClick={() => { setMode('forgot'); setErr(''); setInfo(''); }} data-testid="staff-forgot-link"
            className="mt-3 text-sm text-cyan-600 hover:underline w-full text-center">Forgot your password?</button>
        </>
      ) : (
        <>
          <button onClick={forgot} disabled={busy || !email} data-testid="staff-forgot-btn"
            className="mt-4 w-full rounded-lg py-2.5 font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            {busy ? 'Sending…' : 'Send reset link'}
          </button>
          <button onClick={() => { setMode('login'); setErr(''); setInfo(''); }} data-testid="staff-back-login"
            className="mt-3 text-sm text-slate-500 hover:underline w-full text-center inline-flex items-center justify-center gap-1"><ArrowLeft size={13} /> Back to sign in</button>
        </>
      )}
    </Shell>
  );
}
