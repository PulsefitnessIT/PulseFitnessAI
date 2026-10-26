import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Loader2, ClipboardList, Search } from 'lucide-react';
import { Card } from '@/components/ui/card';
import EquipmentGapsPanel from './EquipmentGapsPanel';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const ScopeItem = ({ s, active, onPick }) => (
  <button onClick={() => onPick(s.organization_id)} data-testid={`gaps-scope-${s.organization_id}`}
    className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors duration-150 ${active ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.06)]' : 'border-transparent hover:bg-zinc-50'}`}>
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm font-medium text-zinc-900 truncate">{s.name}</span>
      {s.is_mod && <span className="text-[9px] font-bold uppercase tracking-wider text-cyan-700 bg-cyan-50 border border-cyan-100 rounded px-1.5">MOD</span>}
    </div>
    <span className="text-[11px] text-red-600">{s.incomplete} of {s.total} need info</span>
  </button>
);

export default function EquipmentGapsSection() {
  const [scopes, setScopes] = useState(null);
  const [failed, setFailed] = useState(false);
  const [orgId, setOrgId] = useState(() => new URLSearchParams(window.location.search).get('org') || '');
  const [q, setQ] = useState('');

  const loadScopes = useCallback(() => {
    axios.get(`${API}/equipment-gaps/scopes`).then(({ data }) => {
      setFailed(false);
      setScopes(data.scopes || []);
      setOrgId((cur) => cur || data.scopes?.[0]?.organization_id || '');
    }).catch(() => { setFailed(true); setScopes([]); });
  }, []);
  useEffect(() => { loadScopes(); }, [loadScopes]);

  const pick = (id) => {
    setOrgId(id);
    const u = new URL(window.location.href);
    u.searchParams.set('org', id);
    window.history.replaceState(null, '', u.toString());
  };

  const list = (scopes || []).filter((s) => s.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_1fr]" data-testid="equipment-gaps-section">
      <Card className="p-3 rounded-xl border-zinc-200 h-fit lg:sticky lg:top-4">
        <div className="flex items-center gap-2 px-1 pb-2">
          <ClipboardList size={15} className="text-[var(--color-brand-blue)]" />
          <h2 className="text-sm font-bold text-zinc-900">Missing information</h2>
        </div>
        <p className="px-1 pb-3 text-[11px] text-zinc-500 leading-relaxed">Customers whose equipment is missing a Sicon essential (Customer Ref, Location, Description, Make, Model or Serial Number).</p>
        <div className="relative mb-2">
          <Search size={13} className="absolute left-2.5 top-2.5 text-zinc-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customers" data-testid="gaps-scope-search"
            className="w-full h-8 rounded-md border border-zinc-200 pl-8 pr-2 text-xs focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-blue)]" />
        </div>
        <div className="space-y-1 max-h-[65vh] overflow-auto" data-testid="gaps-scope-list">
          {scopes === null && <Loader2 className="mx-auto my-6 animate-spin text-zinc-400" />}
          {failed && <p className="text-xs text-red-600 p-3" data-testid="gaps-scope-error">Could not load customers — refresh to try again.</p>}
          {!failed && scopes?.length === 0 && <p className="text-xs text-emerald-700 p-3" data-testid="gaps-scope-empty">All equipment is complete.</p>}
          {list.map((s) => <ScopeItem key={s.organization_id} s={s} active={s.organization_id === orgId} onPick={pick} />)}
        </div>
      </Card>
      <Card className="p-5 rounded-xl border-zinc-200 min-w-0">
        {orgId ? <EquipmentGapsPanel key={orgId} organizationId={orgId} onChanged={loadScopes} /> : <p className="text-sm text-zinc-500">Pick a customer.</p>}
      </Card>
    </div>
  );
}
