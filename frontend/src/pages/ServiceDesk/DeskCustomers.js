import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Search, ChevronRight } from 'lucide-react';
import { authConfig } from './authConfig';

const ACCOUNT_TYPE_LABELS = {
  full: { label: 'GymAxis', className: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  pulse_pro: { label: 'Pulse Pro', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  lite: { label: 'Pulse Lite', className: 'bg-sky-50 text-sky-700 border-sky-200' },
  gymaxis: { label: 'GymAxis', className: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
};

function OrgRow({ org, onSelect }) {
  const acct = ACCOUNT_TYPE_LABELS[org.account_type] || { label: org.account_type || '—', className: 'bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:border-zinc-800' };
  return (
    <button
      onClick={() => onSelect(org.id)}
      data-testid={`desk-org-row-${org.id}`}
      className="w-full text-left p-4 bg-white border border-zinc-200 rounded-lg hover:border-orange-300 hover:shadow-sm transition flex items-center gap-4 dark:bg-zinc-900 dark:border-zinc-800"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="text-sm font-semibold text-zinc-900 truncate dark:text-zinc-100">{org.name}</div>
          <Badge variant="outline" className={`text-[10px] ${acct.className}`}>{acct.label}</Badge>
          {org.is_multi_site && (
            <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200">Multi-site</Badge>
          )}
          {org.status === 'archived' && (
            <Badge variant="outline" className="text-[10px] bg-zinc-100 text-zinc-600 dark:bg-zinc-800">Archived</Badge>
          )}
          {org.status === 'pending_invite' && (
            <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-700 border-amber-200">Pending Invite</Badge>
          )}
        </div>
        <div className="text-xs text-zinc-500 mt-1 flex items-center gap-3">
          {org.sicon_customer_ref && <span>Ref: {org.sicon_customer_ref}</span>}
          {org.head_office_ref && <span>HO: {org.head_office_ref}</span>}
          {org.primary_contact_email && <span className="truncate">{org.primary_contact_email}</span>}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-zinc-400" />
    </button>
  );
}

export default function DeskCustomers({ API, onSelect, initialStatus = '' }) {
  const [orgs, setOrgs] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [accountType, setAccountType] = useState('');
  const [status, setStatus] = useState(initialStatus);
  const [loading, setLoading] = useState(false);
  // Iter 268 — when navigated from a dashboard stat card, pre-apply that
  // card's status filter (and re-apply if the user clicks a different card).
  useEffect(() => { setStatus(initialStatus || ''); }, [initialStatus]);
  // Iter 245 — true when the backend restricted the list to Pulse customers
  // (pulse-brand desk agents + Pulse Master Admins).
  const [scopedToPulse, setScopedToPulse] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ q, account_type: accountType, status, limit: '50' });
      const r = await axios.get(`${API}/service-desk/customers?${params}`, authConfig());
      setOrgs(r.data.organizations || []);
      setTotal(r.data.total || 0);
      setScopedToPulse(!!r.data.scoped_to_pulse);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [API, q, accountType, status]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="desk-customers">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Customers</h1>
        <p className="text-sm text-zinc-500 mt-1">
          {total.toLocaleString()} organisations. Search by name, Sicon ref, or head-office ref.
          {scopedToPulse && (
            <Badge variant="outline" className="ml-2 text-[10px] bg-blue-50 text-blue-700 border-blue-200" data-testid="desk-scope-pulse-badge">
              Pulse customers only
            </Badge>
          )}
        </p>
      </div>

      <div className="flex gap-2 flex-wrap">
        <div className="flex-1 min-w-[220px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <Input
            placeholder="Search customers…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-9"
            data-testid="desk-customer-search"
          />
        </div>
        <select
          value={accountType}
          onChange={(e) => setAccountType(e.target.value)}
          data-testid="desk-filter-account-type"
          className="px-3 py-2 border border-zinc-200 rounded-md text-sm bg-white dark:bg-zinc-900 dark:border-zinc-800"
        >
          <option value="">All account types</option>
          <option value="full">GymAxis (full)</option>
          <option value="pulse_pro">Pulse Pro</option>
          <option value="lite">Pulse Lite</option>
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          data-testid="desk-filter-status"
          className="px-3 py-2 border border-zinc-200 rounded-md text-sm bg-white dark:bg-zinc-900 dark:border-zinc-800"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="pending_invite">Pending Invite</option>
          <option value="archived">Archived</option>
        </select>
      </div>

      {loading ? (
        <div className="text-zinc-500 py-8 text-center">Loading…</div>
      ) : orgs.length === 0 ? (
        <div className="text-zinc-500 py-8 text-center">No customers match these filters.</div>
      ) : (
        <div className="space-y-2">
          {orgs.map((o) => <OrgRow key={o.id} org={o} onSelect={onSelect} />)}
        </div>
      )}
    </div>
  );
}
