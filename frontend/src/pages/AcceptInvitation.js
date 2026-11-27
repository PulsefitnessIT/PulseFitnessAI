import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { ShieldCheck, Loader2, KeyRound, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const STATE_TEXT = {
  invalid: 'This invitation link is not valid. Check you opened the whole link from the email.',
  expired: 'This invitation has expired. Ask whoever invited you to send a new one.',
  used: 'This invitation has already been used. Sign in instead.',
  revoked: 'This invitation was cancelled. Ask for a new one if you still need access.',
};

// Token lives in the URL fragment, which browsers never send to the server, so link scanners can't use it.
const readToken = () => new URLSearchParams((window.location.hash || '').replace(/^#/, '')).get('token') || '';

const Shell = ({ children }) => (
  <div className="min-h-screen bg-[#f4f6f8] flex items-center justify-center px-4 py-12" data-testid="accept-invite-page">
    <div className="w-full max-w-md bg-white rounded-2xl border border-zinc-200 shadow-sm p-8">
      <p className="text-xs font-semibold tracking-[0.2em] text-[#0073A4] uppercase">Pulse Fitness</p>
      {children}
    </div>
  </div>
);

const Done = ({ res }) => (
  <div className="mt-4 space-y-4" data-testid="accept-invite-done">
    <CheckCircle2 className="text-emerald-600" size={36} />
    <h1 className="text-2xl font-bold text-zinc-900">Your account is ready</h1>
    <p className="text-sm text-zinc-600">
      {res.requires_mfa_setup
        ? 'Sign in with your email and new password. You will then set up two-step verification with an authenticator app (Google Authenticator, Microsoft Authenticator or similar).'
        : 'Sign in with your email and new password.'}
    </p>
    <Button asChild className="w-full rounded-full" data-testid="accept-invite-signin"><Link to="/login">Sign in</Link></Button>
  </div>
);

export default function AcceptInvitation() {
  const token = useRef(readToken()).current;
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ email: '', full_name: '', password: '', confirm: '' });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    if (!token) { setInfo({ state: 'invalid' }); return; }
    window.history.replaceState(null, '', window.location.pathname);  // keep the token out of history/screenshots
    axios.post(`${API}/invitations/inspect`, { token })
      .then((r) => { setInfo(r.data); setForm((f) => ({ ...f, full_name: r.data.full_name || '' })); })
      .catch(() => setInfo({ state: 'invalid' }));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    if (form.password !== form.confirm) { setErr('The two passwords do not match.'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/invitations/accept`, { token, email: form.email, full_name: form.full_name, password: form.password });
      setDone(r.data);
    } catch (ex) { setErr(formatApiError(ex, 'Could not accept the invitation')); }
    setBusy(false);
  };

  if (!info) return <Shell><p className="mt-6 text-sm text-zinc-500 flex items-center gap-2"><Loader2 className="animate-spin" size={14} />Checking your invitation…</p></Shell>;
  if (done) return <Shell><Done res={done} /></Shell>;
  if (info.state !== 'valid') {
    return (
      <Shell>
        <XCircle className="text-red-500 mt-4" size={32} />
        <p className="mt-3 text-base text-zinc-800" data-testid="accept-invite-state">{STATE_TEXT[info.state] || STATE_TEXT.invalid}</p>
        <Button asChild variant="outline" className="mt-5 rounded-full"><Link to="/login">Go to sign in</Link></Button>
      </Shell>
    );
  }
  const owner = info.kind === 'owner_activation';
  return (
    <Shell>
      <h1 className="text-2xl sm:text-3xl font-bold text-zinc-900 mt-2" data-testid="accept-invite-title">
        {owner ? `Activate ${info.organization_name}` : `Join ${info.organization_name}`}
      </h1>
      <p className="text-sm text-zinc-600 mt-2">
        {owner ? 'Pulse Fitness has verified you as the owner. Your equipment, sites and service history are already set up.'
          : `You have been invited as ${info.role}.`} This invitation was sent to <b data-testid="accept-invite-email-hint">{info.email_hint}</b>.
      </p>
      <form onSubmit={submit} className="mt-6 space-y-3">
        <div><Label htmlFor="ai-email">Confirm your email address</Label>
          <Input id="ai-email" type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="accept-invite-email" /></div>
        <div><Label htmlFor="ai-name">Your name</Label>
          <Input id="ai-name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} data-testid="accept-invite-name" /></div>
        <div><Label htmlFor="ai-pw">Choose a password</Label>
          <Input id="ai-pw" type="password" required autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="accept-invite-password" />
          <p className="text-[11px] text-zinc-500 mt-1">At least 12 characters, with upper and lower case, a number and a symbol.</p></div>
        <div><Label htmlFor="ai-pw2">Confirm password</Label>
          <Input id="ai-pw2" type="password" required autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} data-testid="accept-invite-password-confirm" /></div>
        {info.require_mfa && <p className="text-xs text-[#0073A4] flex items-start gap-1.5" data-testid="accept-invite-mfa-note"><ShieldCheck size={14} className="shrink-0 mt-0.5" />You will set up two-step verification the first time you sign in.</p>}
        {err && <p className="text-sm text-red-600" data-testid="accept-invite-error">{err}</p>}
        <Button type="submit" disabled={busy} className="w-full rounded-full" data-testid="accept-invite-submit">
          {busy ? <Loader2 className="animate-spin mr-2" size={14} /> : <KeyRound size={14} className="mr-2" />}{owner ? 'Activate account' : 'Accept invitation'}
        </Button>
      </form>
    </Shell>
  );
}
