import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Download, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ImportHistory({ onOpenJob }) {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);
  const [rows, setRows] = useState([]);
  const [msg, setMsg] = useState('');
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/master-admin/customer-import/history`, { headers });
    setRows(data.imports || []);
  }, [headers]);
  useEffect(() => { load().catch(() => {}); }, [load]);
  const report = async (id) => {
    const r = await axios.get(`${API}/master-admin/customer-import/jobs/${id}/report.csv`, { headers, responseType: 'blob' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(r.data); a.download = `import-reconciliation-${id.slice(0, 8)}.csv`; a.click();
  };
  const undo = async (r) => {
    if (!window.confirm('Undo this import? Records it created that nobody has started using are removed, and values it changed are restored.')) return;
    try {
      const url = r.engine === 'customer_import' ? `/master-admin/customer-import/jobs/${r.id}/rollback` : `/master-admin/bulk-import/undo/${r.id}`;
      await axios.post(`${API}${url}`, {}, { headers }); setMsg('Import undone'); load();
    } catch (e) { setMsg(e.response?.data?.detail || e.message); }
  };
  return (
    <Card className="rounded-xl border-zinc-200 overflow-auto" data-testid="import-history">
      {msg && <p className="p-2 text-xs text-sky-700" data-testid="ih-msg">{msg}</p>}
      <table className="w-full text-xs">
        <thead className="bg-zinc-50 text-left text-zinc-500"><tr>
          <th className="p-2">Date</th><th className="p-2">Type</th><th className="p-2">File</th><th className="p-2">By</th><th className="p-2">Status</th>
          <th className="p-2 text-right">Processed</th><th className="p-2 text-right">Created</th><th className="p-2 text-right">Updated</th>
          <th className="p-2 text-right">Skipped</th><th className="p-2 text-right">Failed</th><th className="p-2" /></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={11} className="p-4 text-zinc-500">No imports yet.</td></tr>}
          {rows.map((r) => (
            <tr key={`${r.engine}-${r.id}`} className="border-t" data-testid={`ih-row-${r.id}`}>
              <td className="p-2 whitespace-nowrap">{String(r.at || '').slice(0, 16).replace('T', ' ')}</td>
              <td className="p-2">{r.type}</td><td className="p-2 truncate max-w-[200px]">{r.filename || '—'}</td><td className="p-2">{r.by || '—'}</td>
              <td className="p-2">{r.status}</td>
              {['processed', 'created', 'updated', 'skipped', 'failed'].map((k) => <td key={k} className="p-2 text-right tabular-nums">{r[k]}</td>)}
              <td className="p-2 whitespace-nowrap">
                {r.engine === 'customer_import' && <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => onOpenJob?.(r.id)} data-testid={`ih-open-${r.id}`}>Open</Button>}
                {r.report && <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => report(r.id)} data-testid={`ih-report-${r.id}`}><Download size={12} /></Button>}
                {r.undo && <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => undo(r)} data-testid={`ih-undo-${r.id}`}><RotateCcw size={12} /></Button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
