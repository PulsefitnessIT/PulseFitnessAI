/**
 * AdminAuditLogs — iter 216h161.
 *
 * Master-admin surface for the platform-wide `audit_logs` collection.
 * Filterable by free text, action, resource type, email and date
 * window. CSV export. Drives the procurement / SOC2 / GDPR question
 * "show me every action timestamped".
 *
 * Mounted inside the Master Admin tabbed shell — no route file
 * changes required.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { RefreshCw, Search, Download, FileText, Filter,
  Calendar, User, FileBadge, ChevronLeft, ChevronRight, Loader2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PAGE_SIZE = 50;

// ── tiny utility for action colour-coding ─────────────────────
const actionColour = (action = '') => {
  if (action.includes('delete') || action.includes('disable')) return 'bg-red-50 text-red-700';
  if (action.includes('login') || action.includes('access'))   return 'bg-blue-50 text-blue-700';
  if (action.includes('refund') || action.includes('finalise'))return 'bg-violet-50 text-violet-700';
  if (action.includes('signature') || action.includes('approve')) return 'bg-emerald-50 text-emerald-700';
  if (action.includes('transition') || action.includes('dispatch')) return 'bg-amber-50 text-amber-700';
  return 'bg-zinc-100 text-zinc-600';
};

const AdminAuditLogs = () => {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(false);
  const [facets, setFacets] = useState({ actions: [], resource_types: [] });

  // Filters
  const [q, setQ] = useState('');
  const [action, setAction] = useState('');
  const [resourceType, setResourceType] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');

  const loadFacets = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/master-admin/audit-logs/facets`, auth());
      setFacets(r.data || { actions: [], resource_types: [] });
    } catch (_) { /* non-critical */ }
  }, []);

  const load = useCallback(async (nextSkip = 0) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/audit-logs`, {
        ...auth(),
        params: {
          q, action, resource_type: resourceType, user_email: userEmail,
          since, until, skip: nextSkip, limit: PAGE_SIZE,
        },
      });
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
      setSkip(nextSkip);
    } finally {
      setLoading(false);
    }
  }, [q, action, resourceType, userEmail, since, until]);

  useEffect(() => { loadFacets(); load(0); }, []); // eslint-disable-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — runs on the listed trigger deps; omitted refs are stable identities or read live state at call time.

  const onApply = () => load(0);
  const onReset = () => {
    setQ(''); setAction(''); setResourceType(''); setUserEmail('');
    setSince(''); setUntil('');
    setTimeout(() => load(0), 0);
  };

  const exportUrl = useMemo(() => {
    const p = new URLSearchParams();
    if (q) p.set('q', q);
    if (action) p.set('action', action);
    if (userEmail) p.set('user_email', userEmail);
    if (resourceType) p.set('resource_type', resourceType);
    if (since) p.set('since', since);
    if (until) p.set('until', until);
    return `${API}/master-admin/audit-logs/export.csv?${p.toString()}`;
  }, [q, action, resourceType, userEmail, since, until]);

  const downloadCsv = async () => {
    try {
      const r = await axios.get(exportUrl, { ...auth(), responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (_) { /* swallow — the admin can retry */ }
  };

  const pageStart = total ? skip + 1 : 0;
  const pageEnd = Math.min(skip + rows.length, total);

  return (
    <div className="space-y-4" data-testid="admin-audit-logs">
      {/* Filter bar */}
      <Card className="bg-white border-zinc-200 shadow-sm p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-zinc-400" />
          <p className="text-sm font-semibold text-zinc-900">Audit Trail</p>
          <Badge className="bg-zinc-100 text-zinc-500 text-[10px]">
            {total.toLocaleString()} records
          </Badge>
          <span className="flex-1" />
          <Button size="sm" variant="outline" className="h-8 border-zinc-200 text-zinc-600"
                  onClick={() => load(0)} data-testid="audit-refresh">
            {loading ? <Loader2 size={12} className="mr-1 animate-spin" /> : <RefreshCw size={12} className="mr-1" />}
            Refresh
          </Button>
          <Button size="sm" className="h-8 bg-violet-600 hover:bg-violet-700 text-white"
                  onClick={downloadCsv} data-testid="audit-export">
            <Download size={12} className="mr-1" /> CSV
          </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-2.5 text-zinc-400 pointer-events-none" />
            <Input
              className="pl-7 h-8 text-xs"
              placeholder="Search action, email, details, resource id"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onApply()}
              data-testid="audit-q"
            />
          </div>
          <select
            className="h-8 text-xs border border-zinc-200 rounded px-2 bg-white"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            data-testid="audit-action"
          >
            <option value="">All actions ({facets.actions.length})</option>
            {facets.actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select
            className="h-8 text-xs border border-zinc-200 rounded px-2 bg-white"
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value)}
            data-testid="audit-resource-type"
          >
            <option value="">All resource types</option>
            {facets.resource_types.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <div className="relative">
            <User size={12} className="absolute left-2.5 top-2.5 text-zinc-400 pointer-events-none" />
            <Input
              className="pl-7 h-8 text-xs"
              placeholder="User email contains…"
              value={userEmail}
              onChange={(e) => setUserEmail(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onApply()}
              data-testid="audit-email"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Calendar size={12} className="text-zinc-400" />
          <Input
            type="date" className="h-8 text-xs w-36"
            value={since.slice(0, 10)}
            onChange={(e) => setSince(e.target.value)}
            data-testid="audit-since"
          />
          <span className="text-xs text-zinc-400">→</span>
          <Input
            type="date" className="h-8 text-xs w-36"
            value={until.slice(0, 10)}
            onChange={(e) => setUntil(e.target.value)}
            data-testid="audit-until"
          />
          <Button size="sm" className="h-8 bg-blue-600 hover:bg-blue-700 text-white" onClick={onApply} data-testid="audit-apply">
            Apply
          </Button>
          <Button size="sm" variant="outline" className="h-8 border-zinc-200 text-zinc-600" onClick={onReset} data-testid="audit-reset">
            Reset
          </Button>
        </div>
      </Card>

      {/* Results table */}
      <Card className="bg-white border-zinc-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-zinc-50 border-b border-zinc-200 text-left">
              <tr className="text-zinc-500">
                <th className="px-3 py-2 font-semibold whitespace-nowrap">Timestamp</th>
                <th className="px-3 py-2 font-semibold">Action</th>
                <th className="px-3 py-2 font-semibold">User</th>
                <th className="px-3 py-2 font-semibold">Resource</th>
                <th className="px-3 py-2 font-semibold">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-zinc-50" data-testid={`audit-row-${i}`}>
                  <td className="px-3 py-2 whitespace-nowrap text-zinc-500 tabular-nums">
                    {r.timestamp ? new Date(r.timestamp).toLocaleString('en-GB', {
                      year: 'numeric', month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit', second: '2-digit',
                    }) : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${actionColour(r.action)}`}>
                      {r.action || '—'}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-zinc-700">
                    <p className="font-semibold truncate max-w-[200px]">{r.user_email || '(system)'}</p>
                    <p className="text-[10px] text-zinc-400 font-mono truncate max-w-[200px]">{r.user_id || ''}</p>
                  </td>
                  <td className="px-3 py-2">
                    {r.resource_type ? (
                      <p className="text-zinc-700 flex items-center gap-1">
                        <FileBadge size={10} /> {r.resource_type}
                      </p>
                    ) : null}
                    {r.resource_id ? (
                      <p className="text-[10px] font-mono text-zinc-400 truncate max-w-[160px]">{r.resource_id}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-zinc-600">
                    <p className="truncate max-w-[420px]" title={r.details}>{r.details || '—'}</p>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !loading ? (
                <tr><td colSpan={5} className="text-center text-zinc-400 py-12">
                  <FileText size={20} className="mx-auto mb-2 opacity-40" />
                  No audit records match these filters.
                </td></tr>
              ) : null}
              {loading && rows.length === 0 ? (
                <tr><td colSpan={5} className="text-center text-zinc-400 py-12">
                  <Loader2 size={20} className="mx-auto animate-spin opacity-40" />
                </td></tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="px-3 py-2 border-t border-zinc-100 flex items-center justify-between bg-zinc-50">
          <p className="text-xs text-zinc-500 tabular-nums">
            {pageStart}–{pageEnd} of {total.toLocaleString()}
          </p>
          <div className="flex items-center gap-1">
            <Button
              size="sm" variant="outline" className="h-7 border-zinc-200 text-zinc-600"
              disabled={skip === 0 || loading}
              onClick={() => load(Math.max(0, skip - PAGE_SIZE))}
              data-testid="audit-prev"
            >
              <ChevronLeft size={12} />
            </Button>
            <Button
              size="sm" variant="outline" className="h-7 border-zinc-200 text-zinc-600"
              disabled={skip + rows.length >= total || loading}
              onClick={() => load(skip + PAGE_SIZE)}
              data-testid="audit-next"
            >
              <ChevronRight size={12} />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default AdminAuditLogs;
