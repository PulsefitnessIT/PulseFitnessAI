import { useEffect, useState, useCallback } from 'react';
import { Radar, Play, AlertTriangle } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner } from './shared';

const STATUSES = ['new', 'under_review', 'investigating', 'action_required', 'resolved', 'dismissed'];
const SEV_TONE = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  monitor: 'bg-blue-50 text-blue-700 border-blue-200',
  info: 'bg-slate-100 text-slate-600 border-slate-200',
};
const TYPE_LABEL = {
  high_failure_rate: 'High failure rate',
  potential_quality_issue: 'Potential quality issue',
  repeated_failure_by_serial: 'Repeated failure (serial range)',
};

export default function AlertsTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listAlerts().then((d) => setRows(d.alerts || [])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setRunning(true);
    try {
      const r = await dpApi.runMonitoring();
      notify.success(`Monitoring run — ${r.alerts_created} new alert(s) from ${r.failures_scanned} failures`);
      load();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Monitoring failed'); }
    finally { setRunning(false); }
  };

  const setStatus = async (a, status) => {
    try { await dpApi.updateAlert(a.id, { status }); notify.success('Alert updated'); load(); }
    catch { notify.error('Update failed'); }
  };

  return (
    <div className="space-y-4" data-testid="dp-alerts-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500 flex items-center gap-2"><Radar size={15} /> Parts Failure Monitoring Agent</h3>
        <button data-testid="dp-run-monitoring-btn" onClick={run} disabled={running}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-50">
          <Play size={15} /> {running ? 'Scanning…' : 'Run monitoring agent'}
        </button>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No alerts. Run the monitoring agent to scan usage &amp; failures.</div>
      ) : (
        <div className="space-y-2">
          {rows.map((a) => (
            <div key={a.id} data-testid={`dp-alert-row-${a.id}`} className="rounded-xl border border-slate-200 bg-white p-4 flex items-start gap-3">
              <AlertTriangle size={18} className={a.severity === 'critical' ? 'text-red-500 mt-0.5' : 'text-amber-500 mt-0.5'} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-900">{TYPE_LABEL[a.alert_type] || a.alert_type}</span>
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${SEV_TONE[a.severity] || SEV_TONE.info}`}>{a.severity}</span>
                  {a.scope && a.scope !== 'global' && <span className="text-xs text-slate-400">{a.scope}</span>}
                </div>
                <p className="text-sm text-slate-600 mt-1">{a.evidence}</p>
                <p className="text-xs text-slate-400 mt-1">→ {a.suggested_action}</p>
              </div>
              <select data-testid={`dp-alert-status-${a.id}`} value={a.status} onChange={(e) => setStatus(a, e.target.value)}
                className="text-xs font-semibold px-2 py-1.5 rounded-lg border border-slate-200 capitalize">
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
