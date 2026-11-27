import { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Copy, ShieldCheck } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const H = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });
const contactName = (c) => c.full_name || [c.first_name, c.last_name].filter(Boolean).join(' ') || c.email;

const InviteHistory = ({ invites, onChanged }) => {
  const [link, setLink] = useState('');
  const [err, setErr] = useState('');
  const act = async (id, what) => {
    setErr(''); setLink('');
    try {
      const r = await axios.post(`${API}/master-admin/customer-activation/invitations/${id}/${what}`, {}, { headers: H() });
      if (r.data?.link) setLink(r.data.link);
    } catch (e) { const f = formatApiError(e); setErr(f.detail || f.title); }
    onChanged();
  };
  if (!invites.length) return null;
  return (
    <div className="border-t pt-3 mt-3 space-y-1.5" data-testid="oi-history">
      <p className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">Invitations</p>
      {invites.map((i) => (
        <div key={i.id} className="flex flex-wrap items-center justify-between text-xs gap-2" data-testid={`oi-inv-${i.id}`}>
          <span className="truncate min-w-0 flex-1">{i.email} · <b>{i.status}</b> · {(i.verification || {}).method || ''}</span>
          {i.status === 'pending' && (
            <span className="flex gap-1">
              <Button size="sm" variant="outline" className="h-6 text-[11px]" onClick={() => act(i.id, 'reissue')} data-testid={`oi-reissue-${i.id}`}>Send new link</Button>
              <Button size="sm" variant="outline" className="h-6 text-[11px]" onClick={() => act(i.id, 'revoke')} data-testid={`oi-revoke-${i.id}`}>Cancel</Button>
            </span>
          )}
        </div>
      ))}
      {link && <p className="text-[11px] font-mono break-all bg-amber-50 border border-amber-200 rounded p-2" data-testid="oi-reissue-link">New one-time link (emails off): {link}</p>}
      {err && <p className="text-xs text-red-600" data-testid="oi-history-error">{err}</p>}
    </div>
  );
};

export default function OwnerInviteDialog({ org, onClose }) {
  const [d, setD] = useState(null);
  const [f, setF] = useState({ contact_id: '', email: '', full_name: '', verification_method: '', verification_note: '', accounts_confirmed: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [res, setRes] = useState(null);
  const load = () => axios.get(`${API}/master-admin/customer-activation/${org.id}`, { headers: H() }).then((r) => setD(r.data)).catch((e) => { const f = formatApiError(e); setErr(f.detail || f.title); });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [org.id]);
  const pick = (id) => {
    const c = (d.contacts || []).find((x) => x.id === id);
    setF({ ...f, contact_id: id, email: c ? c.email : f.email, full_name: c ? contactName(c) : f.full_name });
  };
  const submit = async (e) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const r = await axios.post(`${API}/master-admin/customer-activation/${org.id}/owner-invite`, { ...f, contact_id: f.contact_id || null }, { headers: H() });
      setRes(r.data); load();
    } catch (ex) { { const f = formatApiError(ex, 'Could not create the invitation'); setErr(f.detail || f.title); }; }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(!!res)}>
      <DialogContent className="max-w-lg w-[95vw] overflow-x-hidden" data-testid="owner-invite-dialog">
        <DialogHeader><DialogTitle>Verify and invite the owner of {org.name}</DialogTitle></DialogHeader>
        {!d ? <p className="text-sm text-zinc-500 flex gap-2"><Loader2 className="animate-spin" size={14} />Loading…</p> : res ? (
          <div className="space-y-3" data-testid="oi-result">
            <p className="text-sm">{res.delivery.mode === 'sent' ? `Invitation emailed to ${res.invitation.email}.` : res.delivery.mode === 'failed' ? 'The email could not be sent. Send a new link or try later.' : 'Invitation created. Invitation emails are switched off, so nothing was sent.'}</p>
            {res.link && (
              <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900" data-testid="oi-held-link">
                <p className="font-semibold mb-1">One-time link (shown once, for testing)</p>
                <p className="font-mono break-all">{res.link}</p>
                <Button size="sm" variant="outline" className="mt-2 h-7 text-xs" onClick={() => navigator.clipboard?.writeText(res.link)} data-testid="oi-copy-link"><Copy size={12} className="mr-1" />Copy</Button>
              </div>
            )}
            <Button className="w-full rounded-full" onClick={() => onClose(true)} data-testid="oi-done">Done</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            {d.contacts.length > 0 && (
              <div><Label>Contact on the account</Label>
                <select className="w-full h-9 border rounded-md px-2 text-sm" value={f.contact_id} onChange={(e) => pick(e.target.value)} data-testid="oi-contact">
                  <option value="">Someone else (type below)</option>
                  {d.contacts.map((c) => <option key={c.id} value={c.id}>{contactName(c)} · {c.email}{c.job_title ? ` · ${c.job_title}` : ''}</option>)}
                </select></div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 min-w-0">
              <div><Label>Owner name</Label><Input required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} data-testid="oi-name" /></div>
              <div><Label>Owner email</Label><Input required type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="oi-email" /></div>
            </div>
            <div><Label>How did you verify they are the owner?</Label>
              <select required className="w-full h-9 border rounded-md px-2 text-sm" value={f.verification_method} onChange={(e) => setF({ ...f, verification_method: e.target.value })} data-testid="oi-method">
                <option value="">Choose…</option>
                {Object.entries(d.verification_methods).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></div>
            <div><Label>Verification notes</Label><Textarea required minLength={5} rows={2} value={f.verification_note} onChange={(e) => setF({ ...f, verification_note: e.target.value })} placeholder="e.g. Called the number on the Sage account, spoke to Jane, confirmed as director" data-testid="oi-note" /></div>
            {d.sage_hold && (
              <label className="flex items-start gap-2 text-xs text-amber-800" data-testid="oi-hold">
                <input type="checkbox" checked={f.accounts_confirmed} onChange={(e) => setF({ ...f, accounts_confirmed: e.target.checked })} data-testid="oi-accounts-confirmed" />
                This Sage account is on hold or hidden. I have confirmed with Accounts that we can activate it.
              </label>
            )}
            <p className="text-[11px] text-zinc-500 flex gap-1.5"><ShieldCheck size={13} className="shrink-0" />The link works once, expires in 72 hours and asks the owner to set up two-step verification. The customer stays on LITE; no paid products are switched on. {d.emails_live ? 'An email will be sent.' : 'Emails are switched off: nothing will be sent.'}</p>
            {err && <p className="text-sm text-red-600" data-testid="oi-error">{err}</p>}
            <Button type="submit" disabled={busy} className="w-full rounded-full" data-testid="oi-submit">{busy && <Loader2 className="animate-spin mr-2" size={14} />}Create invitation</Button>
          </form>
        )}
        {d && <InviteHistory invites={d.invitations} onChanged={load} />}
      </DialogContent>
    </Dialog>
  );
}
