import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
  Activity, CheckCircle, XCircle, AlertTriangle, Loader2,
  Wifi, WifiOff, RefreshCw, Plug, Clock, Building2,
  ArrowDownToLine, FileWarning
} from 'lucide-react';

const STATUS_STYLES = {
  connected: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', icon: Wifi, label: 'Connected' },
  unreachable: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', icon: WifiOff, label: 'Unreachable' },
  error: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', icon: XCircle, label: 'Error' },
  unknown: { bg: 'bg-zinc-50', border: 'border-zinc-200', text: 'text-zinc-600', icon: AlertTriangle, label: 'Not tested' },
};

const fmtTime = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return d.toLocaleDateString();
  } catch {
    return iso;
  }
};

function SummaryTile({ label, value, icon: Icon, tone = 'zinc', testid }) {
  const tones = {
    zinc: 'text-zinc-900 bg-zinc-50 border-zinc-200',
    emerald: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    amber: 'text-amber-700 bg-amber-50 border-amber-200',
    red: 'text-red-700 bg-red-50 border-red-200',
    blue: 'text-blue-700 bg-blue-50 border-blue-200',
  };
  return (
    <div className={`border rounded-xl p-4 ${tones[tone]}`} data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest opacity-70 font-semibold">{label}</span>
        <Icon size={14} className="opacity-60" />
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

function OrgRow({ row, onTest, testing }) {
  const style = STATUS_STYLES[row.connection_status] || STATUS_STYLES.unknown;
  const Icon = style.icon;
  return (
    <tr className="border-b border-zinc-100 hover:bg-zinc-50 transition-colors" data-testid={`sicon-health-row-${row.organization_id}`}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Building2 size={14} className="text-zinc-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-zinc-900">{row.organization_name}</p>
            {row.base_url && <p className="text-[10px] text-zinc-400 font-mono truncate max-w-[240px]">{row.base_url}</p>}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        {!row.configured ? (
          <Badge className="bg-zinc-100 text-zinc-500">Not configured</Badge>
        ) : !row.enabled ? (
          <Badge className="bg-zinc-100 text-zinc-500">Disabled</Badge>
        ) : (
          <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium ${style.bg} ${style.text} border ${style.border}`}>
            <Icon size={11} /> {style.label}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-zinc-700 tabular-nums">
        <div className="flex items-center gap-1">
          <CheckCircle size={12} className="text-emerald-500" />
          {row.synced_issues}
        </div>
      </td>
      <td className="px-4 py-3 text-sm tabular-nums">
        {row.pending_queue > 0 ? (
          <span className="inline-flex items-center gap-1 text-amber-700 font-semibold">
            <Clock size={12} /> {row.pending_queue}
          </span>
        ) : (
          <span className="text-zinc-400">0</span>
        )}
      </td>
      <td className="px-4 py-3 text-sm tabular-nums">
        {row.failed_queue > 0 ? (
          <span className="inline-flex items-center gap-1 text-red-700 font-semibold">
            <FileWarning size={12} /> {row.failed_queue}
          </span>
        ) : (
          <span className="text-zinc-400">0</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-zinc-500">{fmtTime(row.last_tested_at)}</td>
      <td className="px-4 py-3 text-xs text-zinc-500">{fmtTime(row.last_poll_at)}</td>
      <td className="px-4 py-3">
        {row.enabled && (
          <Button size="sm" variant="outline" disabled={testing}
            onClick={() => onTest(row.organization_id)}
            data-testid={`sicon-test-${row.organization_id}`}
            className="h-7 text-[11px] border-zinc-300">
            {testing ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />}
            <span className="ml-1">Test</span>
          </Button>
        )}
      </td>
    </tr>
  );
}

export default function SiconHealthPanel({ view = 'all' }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ organizations: [], totals: {} });
  const [testingAll, setTestingAll] = useState(false);
  const [pollingAll, setPollingAll] = useState(false);
  const [testingOne, setTestingOne] = useState(null);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/master-admin/sicon/health`, { headers });
      setData(res.data || { organizations: [], totals: {} });
    } catch (err) {
      notify.error('Failed to load Sicon health');
      console.error(err);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { loadHealth(); }, [loadHealth]);

  const handleTestAll = async () => {
    setTestingAll(true);
    try {
      const res = await axios.post(`${API}/master-admin/sicon/test-all`, {}, { headers });
      notify.success(`Tested ${res.data?.tested || 0} organisation${res.data?.tested === 1 ? '' : 's'}`);
      await loadHealth();
    } catch (err) {
      notify.error('Bulk test failed');
    } finally {
      setTestingAll(false);
    }
  };

  const handlePollAll = async () => {
    setPollingAll(true);
    try {
      const res = await axios.post(`${API}/master-admin/sicon/poll-all`, {}, { headers });
      notify.success(`Polled ${res.data?.polled || 0} organisation${res.data?.polled === 1 ? '' : 's'}`);
      await loadHealth();
    } catch (err) {
      notify.error('Bulk poll failed');
    } finally {
      setPollingAll(false);
    }
  };

  const handleTestOne = async (orgId) => {
    setTestingOne(orgId);
    // The per-org test-connection endpoint is scoped to the current user's org,
    // so we use the bulk endpoint here and re-fetch — still gives fast feedback.
    try {
      await axios.post(`${API}/master-admin/sicon/test-all`, {}, { headers });
      await loadHealth();
    } catch (err) {
      notify.error('Test failed');
    } finally {
      setTestingOne(null);
    }
  };

  const { organizations = [], totals = {} } = data;
  const connectedCount = totals.connected || 0;
  const enabledCount = totals.enabled || 0;
  const healthPct = enabledCount > 0 ? Math.round((connectedCount / enabledCount) * 100) : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="animate-spin text-zinc-400" size={20} />
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="sicon-health-panel">
      {view !== 'organisations' && (
        <>
          {/* Header */}
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-lg font-semibold text-zinc-900 flex items-center gap-2">
                <Activity size={18} className="text-violet-600" />
                Integration Health
              </h3>
              <p className="text-sm text-zinc-500 mt-0.5">Live Sicon connection status across every organisation.</p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={loadHealth} data-testid="sicon-health-refresh">
                <RefreshCw size={12} className="mr-1" /> Refresh
              </Button>
              <Button size="sm" variant="outline" disabled={pollingAll} onClick={handlePollAll} data-testid="sicon-poll-all">
                {pollingAll ? <Loader2 size={12} className="animate-spin mr-1" /> : <ArrowDownToLine size={12} className="mr-1" />}
                Poll All
              </Button>
              <Button size="sm" disabled={testingAll} onClick={handleTestAll} data-testid="sicon-test-all"
                className="bg-violet-600 hover:bg-violet-700 text-white">
                {testingAll ? <Loader2 size={12} className="animate-spin mr-1" /> : <Plug size={12} className="mr-1" />}
                Test All Connections
              </Button>
            </div>
          </div>

          {/* Summary tiles */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <SummaryTile label="Orgs" value={totals.total_orgs || 0} icon={Building2} tone="zinc" testid="tile-total-orgs" />
            <SummaryTile label="Enabled" value={totals.enabled || 0} icon={CheckCircle} tone="blue" testid="tile-enabled" />
            <SummaryTile label="Connected" value={`${totals.connected || 0}/${totals.enabled || 0}`} icon={Wifi} tone="emerald" testid="tile-connected" />
            <SummaryTile label="Synced Cases" value={totals.total_synced_issues || 0} icon={CheckCircle} tone="emerald" testid="tile-synced-cases" />
            <SummaryTile label="Queued" value={totals.total_pending_queue || 0} icon={Clock} tone={totals.total_pending_queue ? 'amber' : 'zinc'} testid="tile-queued" />
            <SummaryTile label="Failed" value={totals.total_failed_queue || 0} icon={XCircle} tone={totals.total_failed_queue ? 'red' : 'zinc'} testid="tile-failed" />
          </div>

          {/* Health percentage bar */}
          {enabledCount > 0 && (
            <Card className="p-5 border-zinc-200">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-zinc-700">Platform-wide connection health</span>
                <span className={`text-sm font-bold ${healthPct >= 90 ? 'text-emerald-600' : healthPct >= 60 ? 'text-amber-600' : 'text-red-600'}`}>
                  {healthPct}%
                </span>
              </div>
              <div className="w-full h-2 bg-zinc-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${healthPct >= 90 ? 'bg-emerald-500' : healthPct >= 60 ? 'bg-amber-500' : 'bg-red-500'}`}
                  style={{ width: `${healthPct}%` }} />
              </div>
            </Card>
          )}
        </>
      )}

      {view !== 'overview' && (
        <>
          {/* Org table */}
          <Card className="border-zinc-200 overflow-hidden">
            {organizations.length === 0 ? (
              <div className="p-10 text-center">
                <Activity size={28} className="text-zinc-300 mx-auto mb-2" />
                <p className="text-sm text-zinc-500">No organisations found.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-zinc-50 border-b border-zinc-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500">
                      <th className="px-4 py-2.5 font-semibold">Organisation</th>
                      <th className="px-4 py-2.5 font-semibold">Status</th>
                      <th className="px-4 py-2.5 font-semibold">Synced</th>
                      <th className="px-4 py-2.5 font-semibold">Queued</th>
                      <th className="px-4 py-2.5 font-semibold">Failed</th>
                      <th className="px-4 py-2.5 font-semibold">Last Test</th>
                      <th className="px-4 py-2.5 font-semibold">Last Poll</th>
                      <th className="px-4 py-2.5 font-semibold w-[90px]"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {organizations.map(row => (
                      <OrgRow key={row.organization_id} row={row} onTest={handleTestOne} testing={testingOne === row.organization_id} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Footer note */}
          <p className="text-[11px] text-zinc-400">
            Background poller runs every 5 minutes. Queued items retry automatically with exponential backoff.
            Click <strong>Test All</strong> to ping every configured instance now.
          </p>
        </>
      )}
    </div>
  );
}
