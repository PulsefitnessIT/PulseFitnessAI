import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;

// Give Pulse Service Administration / Aftersales staff only the onboarding steps they need — no Master Admin access.
export default function OnboardingDelegates() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [data, setData] = useState({ permissions: {}, delegates: [] });
  const [email, setEmail] = useState('');
  const [perms, setPerms] = useState([]);
  const [msg, setMsg] = useState('');
  const load = () => axios.get(`${API}/delegates`, { headers }).then((r) => setData(r.data)).catch((e) => setMsg(e?.response?.data?.detail || 'Could not load'));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    setMsg('');
    try {
      await axios.post(`${API}/delegates`, { email, permissions: perms }, { headers });
      setMsg(`Saved for ${email}`); setEmail(''); setPerms([]); load();
    } catch (e) { setMsg(String(e?.response?.data?.detail || 'Could not save')); }
  };
  const toggle = (p) => setPerms((x) => (x.includes(p) ? x.filter((y) => y !== p) : [...x, p]));
  return (
    <div className="space-y-4" data-testid="onb-delegates">
      <Card className="p-4 space-y-3">
        <p className="text-sm font-semibold">Give a Pulse staff member onboarding permissions</p>
        <input className="border rounded px-2 py-1 text-sm w-80" placeholder="staff email" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="onb-delegate-email" />
        <div className="grid sm:grid-cols-2 gap-1">
          {Object.entries(data.permissions).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={perms.includes(k)} onChange={() => toggle(k)} data-testid={`onb-delegate-perm-${k}`} />{label}</label>
          ))}
        </div>
        <Button size="sm" onClick={save} disabled={!email} data-testid="onb-delegate-save">Save permissions</Button>
        {msg && <p className="text-xs text-zinc-600" data-testid="onb-delegate-msg">{msg}</p>}
      </Card>
      <Card className="p-4">
        <p className="text-sm font-semibold mb-2">Staff with onboarding permissions</p>
        {data.delegates.length === 0 ? <p className="text-xs text-zinc-500">Nobody yet.</p> : (
          <ul className="text-sm divide-y" data-testid="onb-delegate-list">
            {data.delegates.map((d) => (
              <li key={d.id} className="py-1.5 flex justify-between gap-4">
                <span>{d.full_name || d.email} <span className="text-zinc-400">{d.email}</span></span>
                <span className="text-xs text-zinc-500">{(d.onboarding_permissions || []).map((p) => data.permissions[p] || p).join(' · ')}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
