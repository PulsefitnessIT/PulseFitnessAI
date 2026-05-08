import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollText, RefreshCw } from 'lucide-react';
import { authConfig } from './authConfig';

const ACTION_COLOURS = {
  'org.update': 'bg-blue-50 text-blue-700 border-blue-200',
  'org.impersonate': 'bg-red-50 text-red-700 border-red-200',
  'site.update': 'bg-teal-50 text-teal-700 border-teal-200',
  'desk.grant': 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'desk.revoke': 'bg-amber-50 text-amber-700 border-amber-200',
};

function formatTimestamp(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function DeskAuditLog({ API }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (filter) params.set('action', filter);
      const r = await axios.get(`${API}/service-desk/audit-log?${params}`, authConfig());
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [API, filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="desk-audit-log">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Audit Log</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Immutable record of every Service Desk action. {total.toLocaleString()} rows.
        </p>
      </div>

      <div className="flex gap-2">
        <Input
          placeholder="Filter by action (e.g. org.update)"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
          data-testid="desk-audit-filter"
        />
        <button
          onClick={load}
          className="px-3 py-2 border border-zinc-200 rounded-md text-sm hover:bg-zinc-50 flex items-center gap-1 dark:bg-zinc-900 dark:border-zinc-800"
          data-testid="desk-audit-refresh"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-zinc-500 py-8 text-center">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-zinc-500 py-8 text-center">No audit entries yet.</div>
      ) : (
        <Card className="divide-y divide-zinc-100">
          {rows.map((r) => (
            <div key={r.id} className="p-4" data-testid={`desk-audit-row-${r.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className={`text-[10px] ${ACTION_COLOURS[r.action] || 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800'}`}>
                      {r.action}
                    </Badge>
                    {r.actor_role === 'master_admin' && (
                      <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200">Master Admin</Badge>
                    )}
                  </div>
                  <div className="text-sm text-zinc-900 mt-1 dark:text-zinc-100">{r.summary}</div>
                  <div className="text-xs text-zinc-500 mt-1">
                    {r.actor_email} · {r.target_type} · {r.target_id?.slice(0, 8)}…
                  </div>
                </div>
                <div className="text-xs text-zinc-400 flex-shrink-0">{formatTimestamp(r.timestamp)}</div>
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
