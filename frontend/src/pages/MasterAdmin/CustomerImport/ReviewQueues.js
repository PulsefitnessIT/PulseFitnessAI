import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;

export default function ReviewQueues({ headers, onChange }) {
  const [sites, setSites] = useState([]);
  const [staged, setStaged] = useState([]);
  const load = useCallback(async () => {
    const [a, b] = await Promise.all([axios.get(`${API}/proposed-sites`, { headers }), axios.get(`${API}/staged-contacts`, { headers })]);
    setSites(a.data.sites || []); setStaged(b.data.groups || []);
  }, [headers]);
  useEffect(() => { load().catch(() => {}); }, [load]);
  const decide = async (id, d) => { await axios.post(`${API}/proposed-sites/${id}/${d}`, {}, { headers }); load(); onChange?.(); };
  if (!sites.length && !staged.length) return null;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card className="p-4 rounded-xl border-zinc-200" data-testid="ci-proposed-sites">
        <p className="text-xs font-semibold text-zinc-700">Proposed sites from Sage addresses ({sites.length})</p>
        <p className="text-[11px] text-zinc-500 mb-2">A Sage address may be a billing or head office address. Confirm only real gym locations — confirming does not create gym-floor access.</p>
        <div className="max-h-72 overflow-auto">
          {sites.slice(0, 200).map((s) => (
            <div key={s.id} className="flex items-center gap-2 py-1.5 border-t border-zinc-100 text-xs">
              <span className="flex-1"><b>{s.name}</b> · {[s.address_line1, s.city, s.postcode].filter(Boolean).join(', ')} <span className="text-zinc-400">({s.account_ref})</span></span>
              <Button size="sm" variant="outline" className="h-6 text-[11px]" onClick={() => decide(s.id, 'confirm')} data-testid={`ci-site-confirm-${s.id}`}>Confirm site</Button>
              <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => decide(s.id, 'reject')} data-testid={`ci-site-reject-${s.id}`}>Not a site</Button>
            </div>
          ))}
        </div>
      </Card>
      <Card className="p-4 rounded-xl border-zinc-200" data-testid="ci-staged-contacts">
        <p className="text-xs font-semibold text-zinc-700">Contacts awaiting a Sage account ({staged.reduce((a, g) => a + g.contacts.length, 0)})</p>
        <p className="text-[11px] text-zinc-500 mb-2">Linked automatically when the matching Sage account is imported.</p>
        <div className="max-h-72 overflow-auto">
          {staged.slice(0, 200).map((g) => (
            <div key={g.account_ref} className="py-1.5 border-t border-zinc-100 text-xs" data-testid={`ci-staged-${g.account_ref}`}>
              <b className="font-mono">{g.account_ref}</b> — {g.contacts.map((c) => [c.contact.first_name, c.contact.last_name].filter(Boolean).join(' ') || c.contact.email || 'unnamed').join(', ')}
              {g.contacts.some((c) => c.status === 'needs_review') && <span className="text-amber-700"> · needs review</span>}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
