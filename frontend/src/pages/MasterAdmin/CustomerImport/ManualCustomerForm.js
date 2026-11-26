import { useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;
const FIELDS = [
  ['name', 'Customer name *'], ['account_ref', 'Sage account number (if known)'], ['address_line1', 'Address line 1'],
  ['address_line2', 'Address line 2'], ['city', 'Town / city'], ['county', 'County'], ['postcode', 'Postcode'],
  ['address_country_code', 'Country code (e.g. GB)'], ['website', 'Website'], ['phone', 'Main phone'],
  ['primary_contact_name', 'Main contact name'], ['primary_contact_email', 'Main contact email'],
];

export default function ManualCustomerForm() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [f, setF] = useState({});
  const [sugg, setSugg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(null);
  const save = async (confirm_new = false) => {
    setBusy(true); setErr('');
    try {
      const { data } = await axios.post(`${API}/manual`, { ...f, confirm_new }, { headers });
      setDone(data); setSugg(null); setF({});
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.suggestions) setSugg(d.suggestions);
      else setErr(typeof d === 'string' ? d : d?.message || e.message);
    } finally { setBusy(false); }
  };
  return (
    <Card className="p-5 rounded-xl border-zinc-200 space-y-3" data-testid="ic-manual-form">
      <p className="text-sm text-zinc-600">For a customer with no Sage export yet. We check for existing customers first; the new customer gets LITE only, with no logins.</p>
      <div className="grid md:grid-cols-3 gap-2">
        {FIELDS.map(([k, l]) => (
          <label key={k} className="text-xs text-zinc-600">{l}
            <Input className="mt-1 h-8" value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`ic-manual-${k}`} />
          </label>
        ))}
      </div>
      {sugg && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs" data-testid="ic-manual-suggestions">
          <p className="font-semibold text-amber-900 mb-1">These existing customers look similar. Is it one of them?</p>
          {sugg.map((s) => <p key={s.id}>• {s.name}{s.postcode ? ` · ${s.postcode}` : ''}{s.customer_account_number ? ` · account ${s.customer_account_number}` : ''} <span className="text-amber-700">({s.reason})</span></p>)}
          <div className="flex gap-2 mt-2">
            <Button size="sm" variant="outline" onClick={() => setSugg(null)} data-testid="ic-manual-cancel">It’s one of these — don’t create</Button>
            <Button size="sm" onClick={() => save(true)} disabled={busy} data-testid="ic-manual-confirm-new">It’s a different customer — create it</Button>
          </div>
        </div>
      )}
      {err && <p className="text-sm text-red-600" data-testid="ic-manual-error">{err}</p>}
      {done && <p className="text-sm text-emerald-700 flex items-center gap-1.5" data-testid="ic-manual-done"><CheckCircle2 size={14} />{done.name} created on LITE, awaiting activation.</p>}
      <Button onClick={() => save(false)} disabled={busy || !f.name} data-testid="ic-manual-save">
        {busy && <Loader2 size={14} className="animate-spin mr-1" />}Check and create customer
      </Button>
    </Card>
  );
}
