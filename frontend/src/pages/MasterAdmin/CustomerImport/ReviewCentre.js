import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;
const PRIO = { high: 'bg-red-100 text-red-800', medium: 'bg-amber-100 text-amber-800', low: 'bg-zinc-100 text-zinc-700' };
const PAGE = 50;

export default function ReviewCentre({ onOpenJob }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [type, setType] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [d, setD] = useState({ total: 0, types: {}, items: [] });
  const [err, setErr] = useState('');
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/review`, { headers, params: { type: type || undefined, search: q || undefined, skip: page * PAGE, limit: PAGE } });
    setD(data);
  }, [headers, type, q, page]);
  useEffect(() => { load().then(() => setErr('')).catch((e) => setErr(e.response?.data?.detail || 'Could not load the review list')); }, [load]);
  const site = async (id, decision) => { await axios.post(`${API}/proposed-sites/${id}/${decision}`, {}, { headers }); load(); };
  return (
    <div className="space-y-3" data-testid="review-centre">
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => { setType(''); setPage(0); }} className={`text-xs px-3 py-1 rounded-full ${!type ? 'seg-active' : 'bg-zinc-100'}`} data-testid="rc-type-all">All ({Object.values(d.types).reduce((a, b) => a + b, 0)})</button>
        {Object.entries(d.types).map(([k, v]) => (
          <button key={k} type="button" onClick={() => { setType(k); setPage(0); }} className={`text-xs px-3 py-1 rounded-full ${type === k ? 'seg-active' : 'bg-zinc-100'}`} data-testid={`rc-type-${k.replace(/\W+/g, '-').toLowerCase()}`}>{k} ({v})</button>
        ))}
      </div>
      {err && <p className="text-sm text-red-600" data-testid="rc-error">{err}</p>}
      <Input className="h-8 w-72" placeholder="Search customer or account number" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} data-testid="rc-search" />
      <Card className="rounded-xl border-zinc-200 overflow-auto">
        <table className="w-full text-xs">
          <thead className="bg-zinc-50 text-left text-zinc-500"><tr><th className="p-2">Priority</th><th className="p-2">Issue</th><th className="p-2">Account</th><th className="p-2">Customer / contact</th><th className="p-2">Details</th><th className="p-2">What to do</th><th className="p-2" /></tr></thead>
          <tbody>
            {d.items.length === 0 && <tr><td colSpan={7} className="p-4 text-zinc-500" data-testid="rc-empty">Nothing needs review.</td></tr>}
            {d.items.map((it, i) => (
              <tr key={`${it.type}-${it.ref}-${i}`} className="border-t align-top" data-testid={`rc-item-${i}`}>
                <td className="p-2"><span className={`px-2 py-0.5 rounded-full ${PRIO[it.priority]}`}>{it.priority}</span></td>
                <td className="p-2 font-medium">{it.type}</td>
                <td className="p-2 font-mono">{it.ref}</td>
                <td className="p-2">{it.name}</td>
                <td className="p-2 text-zinc-600">{it.detail}<span className="block text-zinc-400">{it.source}{it.owner ? ` · ${it.owner}` : ''}</span></td>
                <td className="p-2 text-zinc-600">{it.resolve}</td>
                <td className="p-2 whitespace-nowrap">
                  {it.site_id && <><Button size="sm" variant="outline" className="h-6 text-[11px]" onClick={() => site(it.site_id, 'confirm')} data-testid={`rc-site-confirm-${i}`}>Confirm site</Button>
                    <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => site(it.site_id, 'reject')} data-testid={`rc-site-reject-${i}`}>Not a site</Button></>}
                  {it.job_id && <Button size="sm" variant="outline" className="h-6 text-[11px]" onClick={() => onOpenJob?.(it.job_id)} data-testid={`rc-open-job-${i}`}>Open import</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="flex items-center gap-2 text-xs">
        <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)} data-testid="rc-prev">Previous</Button>
        <span>Page {page + 1} of {Math.max(1, Math.ceil(d.total / PAGE))} · {d.total} items</span>
        <Button size="sm" variant="outline" disabled={(page + 1) * PAGE >= d.total} onClick={() => setPage(page + 1)} data-testid="rc-next">Next</Button>
      </div>
    </div>
  );
}
