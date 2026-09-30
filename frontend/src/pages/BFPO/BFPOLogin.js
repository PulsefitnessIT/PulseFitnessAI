import React, { useState } from 'react';
import { bfpoLogin, bfpoToken } from './bfpoApi';
import { Btn, inputCls } from './ui';
import { ShieldCheck, Loader2, Globe2 } from 'lucide-react';

export default function BFPOLogin({ onLoggedIn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(''); setBusy(true);
    try {
      const data = await bfpoLogin(email.trim(), password);
      if (!data.token) throw new Error('No token');
      bfpoToken.set(data.token);
      onLoggedIn(data);
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Sign-in failed. Check your details and try again.');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4" data-testid="bfpo-login">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-cyan-600 mb-4">
            <Globe2 className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Pulse Fitness</h1>
          <p className="text-cyan-400 font-semibold text-sm mt-1">MOD / BFPO Service Portal</p>
        </div>
        <form onSubmit={submit} className="bg-white rounded-2xl p-6 shadow-xl space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-500 uppercase">Email</label>
            <input data-testid="bfpo-login-email" className={inputCls + ' mt-1'} value={email}
              onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-500 uppercase">Password</label>
            <input data-testid="bfpo-login-password" type="password" className={inputCls + ' mt-1'} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {err && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2" data-testid="bfpo-login-error">{err}</p>}
          <Btn type="submit" full disabled={busy} data-testid="bfpo-login-submit">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
            {busy ? 'Signing in…' : 'Sign in'}
          </Btn>
          <p className="text-xs text-slate-400 text-center flex items-center justify-center gap-1">
            <ShieldCheck className="w-3 h-3" /> Access is restricted to authorised MOD/BFPO personnel.
          </p>
        </form>
      </div>
    </div>
  );
}
