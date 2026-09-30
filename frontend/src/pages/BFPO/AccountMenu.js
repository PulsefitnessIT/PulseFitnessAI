import React, { useState, useRef, useEffect } from 'react';
import { changePassword } from './bfpoApi';
import { Btn, inputCls, Field, ROLE_LABEL } from './ui';
import { Menu, X, LogOut, KeyRound, UserCog, Wifi, WifiOff, Loader2, CheckCircle2, ChevronDown } from 'lucide-react';

export default function AccountMenu({ user, role, online, onLogout }) {
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const name = user?.full_name || user?.email || 'Account';

  return (
    <div className="relative" ref={ref}>
      <div className="flex items-center gap-3">
        <span className={`hidden sm:flex items-center gap-1 text-xs ${online ? 'text-emerald-400' : 'text-amber-400'}`} data-testid="bfpo-online">
          {online ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}{online ? 'Synced' : 'Offline'}
        </span>
        <button onClick={() => setOpen((v) => !v)} data-testid="bfpo-menu-button"
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-white/20 hover:bg-white/10 transition-colors" aria-label="Open menu">
          <span className="w-7 h-7 rounded-full bg-cyan-600 flex items-center justify-center text-white text-xs font-bold">
            {(name || 'U').charAt(0).toUpperCase()}
          </span>
          <span className="hidden sm:inline text-sm text-white max-w-[140px] truncate">{name}</span>
          <ChevronDown className={`w-4 h-4 text-white/70 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-white rounded-2xl shadow-xl border border-slate-200 py-2 z-50" data-testid="bfpo-menu-dropdown">
          <div className="px-4 py-2 border-b border-slate-100">
            <p className="font-semibold text-slate-900 truncate">{name}</p>
            <p className="text-xs text-slate-500">{ROLE_LABEL[role] || 'MOD / BFPO'}</p>
            <p className={`text-xs mt-1 flex items-center gap-1 sm:hidden ${online ? 'text-emerald-600' : 'text-amber-600'}`}>
              {online ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}{online ? 'Synced' : 'Offline'}
            </p>
          </div>
          <button onClick={() => { setModal(true); setOpen(false); }} data-testid="bfpo-menu-account"
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
            <UserCog className="w-4 h-4 text-slate-400" /> Account settings
          </button>
          <button onClick={() => { setModal(true); setOpen(false); }} data-testid="bfpo-menu-password"
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50">
            <KeyRound className="w-4 h-4 text-slate-400" /> Change password
          </button>
          <div className="border-t border-slate-100 my-1" />
          <button onClick={() => { setOpen(false); onLogout(); }} data-testid="bfpo-menu-logout"
            className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50">
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      )}

      {modal && <AccountModal user={user} role={role} onClose={() => setModal(false)} />}
    </div>
  );
}

function AccountModal({ user, role, onClose }) {
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    if (next !== confirm) { setErr('New passwords do not match'); return; }
    setBusy(true);
    try { await changePassword(cur, next); setDone(true); setCur(''); setNext(''); setConfirm(''); }
    catch (e2) { setErr(e2?.response?.data?.detail || 'Could not change password'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4" data-testid="bfpo-account-modal" onMouseDown={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-md p-6" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">Account settings</h2>
          <button onClick={onClose} data-testid="bfpo-account-close" className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>

        <div className="space-y-1 mb-5 text-sm">
          <div className="flex justify-between"><span className="text-slate-400">Name</span><span className="font-medium text-slate-800">{user?.full_name || '—'}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Email</span><span className="font-medium text-slate-800 truncate ml-4">{user?.email}</span></div>
          <div className="flex justify-between"><span className="text-slate-400">Role</span><span className="font-medium text-slate-800">{ROLE_LABEL[role] || role}</span></div>
        </div>

        <form onSubmit={submit} className="space-y-3 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Change password</p>
          <Field label="Current password"><input type="password" className={inputCls} value={cur} onChange={(e) => setCur(e.target.value)} required data-testid="bfpo-pw-current" /></Field>
          <Field label="New password" hint="Use a strong, unique password."><input type="password" className={inputCls} value={next} onChange={(e) => setNext(e.target.value)} required data-testid="bfpo-pw-new" /></Field>
          <Field label="Confirm new password"><input type="password" className={inputCls} value={confirm} onChange={(e) => setConfirm(e.target.value)} required data-testid="bfpo-pw-confirm" /></Field>
          {err && <p className="text-sm text-red-600" data-testid="bfpo-pw-error">{err}</p>}
          {done && <p className="text-sm text-emerald-600 flex items-center gap-1" data-testid="bfpo-pw-success"><CheckCircle2 className="w-4 h-4" /> Password updated</p>}
          <Btn type="submit" full disabled={busy} data-testid="bfpo-pw-submit">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} Update password</Btn>
        </form>
      </div>
    </div>
  );
}
