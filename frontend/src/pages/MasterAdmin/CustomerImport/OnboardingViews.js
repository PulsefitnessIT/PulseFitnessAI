import { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import OwnerInviteDialog from './OwnerInviteDialog';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const H = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const Tile = ({ label, value, onClick, testId }) => (
  <button type="button" onClick={onClick} className="text-left rounded-xl border border-zinc-200 bg-white px-4 py-3 hover:bg-zinc-50" data-testid={testId}>
    <p className="text-[11px] text-zinc-500">{label}</p><p className="text-2xl font-bold tabular-nums">{value ?? '—'}</p>
  </button>
);

export function OnboardingDashboard({ go }) {
  const [o, setO] = useState({});
  const [rv, setRv] = useState(0);
  useEffect(() => {
    axios.get(`${API}/master-admin/customer-import/overview`, { headers: H() }).then((r) => setO(r.data)).catch(() => {});
    axios.get(`${API}/master-admin/customer-import/review`, { headers: H(), params: { limit: 1 } }).then((r) => setRv(r.data.total)).catch(() => {});
  }, []);
  return (
    <div className="space-y-4" data-testid="onboarding-dashboard">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Tile label="Customers from Sage" value={o.customer_organisations} onClick={() => go('activation')} testId="od-customers" />
        <Tile label="Awaiting activation" value={o.awaiting_activation} onClick={() => go('activation')} testId="od-awaiting" />
        <Tile label="Needs review" value={rv} onClick={() => go('review')} testId="od-review" />
        <Tile label="Business contacts" value={o.imported_contacts} onClick={() => go('import-centre')} testId="od-contacts" />
        <Tile label="Unmatched contacts" value={o.unmatched_contacts} onClick={() => go('review')} testId="od-unmatched" />
        <Tile label="Proposed sites" value={o.proposed_sites} onClick={() => go('review')} testId="od-sites" />
        <Tile label="Hidden in Sage" value={o.hidden_sage_accounts} onClick={() => go('review')} testId="od-hidden" />
        <Tile label="On hold in Sage" value={o.accounts_on_hold} onClick={() => go('review')} testId="od-hold" />
        <Tile label="LITE only" value={o.lite_only} onClick={() => go('activation')} testId="od-lite" />
        <Tile label="Account numbers" value={o.sage_account_references} onClick={() => go('history')} testId="od-refs" />
      </div>
      <Card className="p-4 rounded-xl border-zinc-200 text-sm">
        <p className="font-semibold mb-1">How onboarding works</p>
        <ol className="list-decimal ml-5 text-zinc-600 space-y-0.5">
          <li><b>Import Centre:</b> import Sage customer accounts, then Sicon contacts, then sites, equipment and contracts.</li>
          <li><b>Review Centre:</b> resolve anything held: possible duplicates, unmatched contacts, proposed sites.</li>
          <li><b>Onboarding Projects:</b> track each customer’s readiness.</li>
          <li><b>Customer Activation:</b> verify the owner, then send a secure single-use invitation. Activation keeps them on LITE.</li>
        </ol>
        <Button className="mt-3" size="sm" onClick={() => go('import-centre')} data-testid="od-start-import">Open Import Centre</Button>
      </Card>
    </div>
  );
}

export function CustomerActivation() {
  const [q, setQ] = useState('');
  const [d, setD] = useState({ total: 0, customers: [] });
  const [open, setOpen] = useState(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    axios.get(`${API}/master-admin/customer-import/activation`, { headers: H(), params: { search: q || undefined } }).then((r) => setD(r.data)).catch(() => {});
  }, [q, tick]);
  return (
    <div className="space-y-3" data-testid="customer-activation">
      <Card className="p-4 rounded-xl border-sky-200 bg-sky-50 text-sm text-sky-900" data-testid="ca-notice">
        Imported customers can’t sign in until you verify the owner and send a secure, single-use invitation. Nobody is invited automatically, and activating never switches on paid products.
      </Card>
      <Input className="h-8 w-72" placeholder="Search customer or account number" value={q} onChange={(e) => setQ(e.target.value)} data-testid="ca-search" />
      <Card className="rounded-xl border-zinc-200 overflow-auto">
        <table className="w-full text-xs">
          <thead className="bg-zinc-50 text-left text-zinc-500"><tr><th className="p-2">Customer</th><th className="p-2">Account</th><th className="p-2">Town</th><th className="p-2 text-right">Contacts</th><th className="p-2 text-right">With email</th><th className="p-2 text-right">Sites</th><th className="p-2">Sage</th><th className="p-2">Ready to invite?</th><th className="p-2">Invitation</th><th className="p-2" /></tr></thead>
          <tbody>
            {d.customers.map((c) => (
              <tr key={c.id} className="border-t" data-testid={`ca-row-${c.id}`}>
                <td className="p-2 font-medium">{c.name}</td><td className="p-2 font-mono">{c.customer_account_number || '—'}</td><td className="p-2">{c.city}</td>
                <td className="p-2 text-right">{c.contacts}</td><td className="p-2 text-right">{c.contacts_with_email}</td><td className="p-2 text-right">{c.sites}</td>
                <td className="p-2">{c.hidden ? 'Hidden' : c.on_hold ? 'On hold' : 'Active'}</td>
                <td className="p-2">{c.activation_review_required ? 'Activation review: owner already has a login elsewhere' : c.hidden || c.on_hold ? 'Check with Accounts first' : c.contacts_with_email ? 'Owner to verify' : 'Needs a contact email'}</td>
                <td className="p-2" data-testid={`ca-inv-status-${c.id}`}>{c.invitation ? `${c.invitation.status} · ${c.invitation.email}` : '—'}</td>
                <td className="p-2"><Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setOpen(c)} data-testid={`ca-invite-${c.id}`}>{c.invitation?.status === 'pending' ? 'Manage' : 'Verify & invite owner'}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="p-2 text-[11px] text-zinc-500">{d.total} customer(s) awaiting activation</p>
      </Card>
      {open && <OwnerInviteDialog org={open} onClose={() => { setOpen(null); setTick((t) => t + 1); }} />}
    </div>
  );
}

export function TemplatesGuidance() {
  const dl = async (path, name) => {
    const r = await axios.get(`${API}${path}`, { headers: H(), responseType: 'blob' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(r.data); a.download = name; a.click();
  };
  const T = [
    ['Sage Customer Accounts (115 columns)', '/master-admin/customer-import/templates/sage_accounts.csv', 'sage-customer-accounts-template.csv'],
    ['Sicon Customer Contacts (25 columns)', '/master-admin/customer-import/templates/sicon_contacts.csv', 'sicon-customer-contacts-template.csv'],
    ['Customer Sites', '/master-admin/bulk-import/templates/sites', 'sites-template.csv'],
    ['Equipment (Sicon template)', '/master-admin/bulk-import/templates/equipment?format=xlsx', 'Equipment Import.xlsx'],
    ['Maintenance Contracts', '/master-admin/bulk-import/templates/contracts', 'contracts-template.csv'],
  ];
  return (
    <div className="grid md:grid-cols-2 gap-4" data-testid="templates-guidance">
      <Card className="p-4 rounded-xl border-zinc-200 space-y-2">
        <p className="text-sm font-semibold">Templates</p>
        {T.map(([l, p, n]) => <Button key={p} variant="outline" size="sm" className="w-full justify-start" onClick={() => dl(p, n)} data-testid={`tg-${n.split('.')[0].replace(/\W+/g, '-').toLowerCase()}`}>{l}</Button>)}
        <p className="text-[11px] text-zinc-500">Sage and Sicon exports can be uploaded exactly as they come out of Sage/Sicon, including their own template rows — those are recognised and skipped.</p>
      </Card>
      <Card className="p-4 rounded-xl border-zinc-200 text-sm text-zinc-700 space-y-2">
        <p className="font-semibold">Guidance</p>
        <p><b>Order:</b> customer accounts → contacts → sites → equipment → contracts.</p>
        <p><b>Matching:</b> customers are matched only by Sage account number. Customers without one are checked against similar names and you confirm.</p>
        <p><b>Safe by design:</b> imports never create logins, send emails or turn on paid products. New customers get Pulse Fitness LITE.</p>
        <p><b>Mistakes:</b> use Import History → Undo. Customers someone has started using are never removed.</p>
        <p><b>Confidential Sage fields</b> (balances, credit, memo) are kept in a staff-only record and never shown to customers.</p>
        <p><b>Source company:</b> always enter the Sage company on upload (live Sicon is linked to <b>Pulse Fitness</b>). The same account number in two Sage companies is two different customers.</p>
        <p><b>Manual customers:</b> if a customer was added by hand, the next Sage import offers to link the account to it, keeping its ID, sites, users and subscriptions.</p>
        <p><b>Direct from Sage/Sicon:</b> a Sage pull creates an Import Centre job for review. A Sicon sync matches customers by account number under the configured Sage company. Equipment goes to that customer; unknown customers are held in the Review Centre. A sync is shown as <i>partial</i> when something could not be retrieved. For example, Sicon has no confirmed contract read API, so use the Maintenance Contracts template instead.</p>
        <p><b>Staff access:</b> Onboarding → Staff Permissions lets Service Administration and Aftersales staff prepare, review, approve or undo imports without Master Admin access.</p>
      </Card>
    </div>
  );
}
