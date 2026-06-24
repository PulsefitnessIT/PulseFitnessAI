import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  BarChart3, Download, FileText, FileSpreadsheet, FileType2, Loader2,
  CheckCircle2, Rocket, Upload, Users2, Eye, EyeOff,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const STATUS_LABELS = {
  not_started: 'Not started', in_progress: 'In progress', waiting_customer: 'Waiting customer',
  waiting_admin: 'Waiting admin', blocked: 'Blocked', ready_for_review: 'Ready for review',
  complete: 'Complete', archived: 'Archived',
};

const StatCard = ({ icon: Icon, label, value, tone = 'text-zinc-900', testId }) => (
  <Card className="p-4 flex items-center gap-3" data-testid={testId}>
    <div className="h-9 w-9 rounded-lg bg-zinc-100 flex items-center justify-center shrink-0">
      <Icon size={16} className="text-zinc-500" />
    </div>
    <div className="min-w-0">
      <div className={`text-xl font-bold leading-tight ${tone}`}>{value}</div>
      <div className="text-[11px] text-zinc-500 truncate">{label}</div>
    </div>
  </Card>
);

const Breakdown = ({ title, data, labelMap }) => {
  const entries = Object.entries(data || {});
  if (!entries.length) return null;
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return (
    <Card className="p-4" data-testid={`onb-report-breakdown-${title.toLowerCase().replace(/\s/g, '-')}`}>
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-3">{title}</p>
      <div className="space-y-2">
        {entries.sort((a, b) => b[1] - a[1]).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="text-xs text-zinc-600 w-32 truncate">{labelMap ? (labelMap[k] || k) : k}</span>
            <div className="flex-1 h-2 rounded-full bg-zinc-100 overflow-hidden">
              <div className="h-full rounded-full bg-[var(--color-brand-blue,#2563EB)]" style={{ width: `${(v / max) * 100}%` }} />
            </div>
            <span className="text-xs text-zinc-500 tabular-nums w-6 text-right">{v}</span>
          </div>
        ))}
      </div>
    </Card>
  );
};

const OnboardingReports = ({ types = [] }) => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(null);
  const [portalEnabled, setPortalEnabled] = useState(false);
  const [savingPortal, setSavingPortal] = useState(false);

  const typeLabel = useCallback(
    (id) => (types.find((t) => t.id === id) || {}).label || id,
    [types],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([
        axios.get(`${API}/onboarding/reports`),
        axios.get(`${API}/onboarding/settings`),
      ]);
      setReport(r.data);
      setPortalEnabled(!!s.data?.customer_portal_enabled);
    } catch (e) {
      notifyApiError(notify, e, 'Could not load reports');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const exportReport = async (format) => {
    setExporting(format);
    try {
      const res = await axios.get(`${API}/onboarding/reports/export`, {
        params: { format }, responseType: 'blob',
      });
      // A 4xx/5xx can still arrive as a blob containing a JSON error —
      // detect it and surface the message instead of saving a broken file.
      const ctype = res.data?.type || res.headers?.['content-type'] || '';
      if (ctype.includes('application/json')) {
        const txt = await res.data.text();
        let msg = 'Export failed';
        try { msg = JSON.parse(txt).detail || msg; } catch { /* keep default */ }
        throw new Error(msg);
      }
      const ext = format === 'excel' ? 'xlsx' : format;
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `onboarding-report.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      notify.success('Export ready', `Onboarding report downloaded as ${ext.toUpperCase()}.`);
    } catch (e) {
      notifyApiError(notify, e, 'Export failed');
    } finally {
      setExporting(null);
    }
  };

  const togglePortal = async (val) => {
    setSavingPortal(true);
    try {
      await axios.patch(`${API}/onboarding/settings`, { customer_portal_enabled: val });
      setPortalEnabled(val);
      notify.success(
        val ? 'Customer portal enabled' : 'Customer portal disabled',
        val ? 'Customers can now track their onboarding from Account Settings → Onboarding.'
            : 'Customers can no longer see their onboarding portal.',
      );
    } catch (e) {
      notifyApiError(notify, e, 'Could not update setting');
    } finally {
      setSavingPortal(false);
    }
  };

  if (loading) {
    return <div className="py-12 flex justify-center text-zinc-400"><Loader2 className="animate-spin" /></div>;
  }

  const rows = report?.rows || [];

  return (
    <div className="space-y-6" data-testid="onboarding-reports">
      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard icon={Rocket} label="Total projects" value={report?.total_projects ?? 0} testId="onb-report-total" />
        <StatCard icon={CheckCircle2} label="Completed" value={report?.completed ?? 0} tone="text-emerald-600" testId="onb-report-completed" />
        <StatCard icon={BarChart3} label="Go-live success" value={`${report?.go_live_success_rate ?? 0}%`} testId="onb-report-success" />
        <StatCard icon={Upload} label="Imports run" value={report?.imports_run ?? 0} testId="onb-report-imports" />
        <StatCard icon={Users2} label="Owners" value={Object.keys(report?.by_owner || {}).length} testId="onb-report-owners" />
      </div>

      {/* Export bar */}
      <Card className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3" data-testid="onb-report-export-bar">
        <div>
          <p className="text-sm font-semibold text-zinc-900">Export onboarding report</p>
          <p className="text-xs text-zinc-500">Download progress across all {report?.total_projects ?? 0} projects.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={exporting} onClick={() => exportReport('csv')} data-testid="onb-export-csv">
            {exporting === 'csv' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <FileText size={14} className="mr-1.5" />} CSV
          </Button>
          <Button variant="outline" size="sm" disabled={exporting} onClick={() => exportReport('excel')} data-testid="onb-export-excel">
            {exporting === 'excel' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <FileSpreadsheet size={14} className="mr-1.5" />} Excel
          </Button>
          <Button variant="outline" size="sm" disabled={exporting} onClick={() => exportReport('pdf')} data-testid="onb-export-pdf">
            {exporting === 'pdf' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <FileType2 size={14} className="mr-1.5" />} PDF
          </Button>
        </div>
      </Card>

      {/* Customer portal toggle */}
      <Card className="p-4 flex items-center justify-between gap-3" data-testid="onb-portal-setting">
        <div className="flex items-start gap-3">
          <div className="h-9 w-9 rounded-lg bg-zinc-100 flex items-center justify-center shrink-0">
            {portalEnabled ? <Eye size={16} className="text-emerald-600" /> : <EyeOff size={16} className="text-zinc-400" />}
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-900">Customer-facing onboarding portal</p>
            <p className="text-xs text-zinc-500 max-w-md">
              When on, each linked customer can view their onboarding checklist and mark steps complete
              from <span className="font-medium">Account Settings → Onboarding</span>.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {savingPortal && <Loader2 size={14} className="animate-spin text-zinc-400" />}
          <Switch checked={portalEnabled} onCheckedChange={togglePortal} disabled={savingPortal} data-testid="onb-portal-toggle" />
        </div>
      </Card>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Breakdown title="By status" data={report?.by_status} labelMap={STATUS_LABELS} />
        <Breakdown title="By customer type" data={report?.by_type} labelMap={Object.fromEntries(types.map((t) => [t.id, t.label]))} />
        <Breakdown title="By owner" data={report?.by_owner} />
      </div>

      {/* Detailed table */}
      <div>
        <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold mb-2">All projects</p>
        {rows.length === 0 ? (
          <Card className="p-8 text-center text-sm text-zinc-500" data-testid="onb-report-empty">No onboarding projects yet.</Card>
        ) : (
          <Card className="overflow-x-auto" data-testid="onb-report-table">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-2.5 font-semibold">Customer</th>
                  <th className="px-4 py-2.5 font-semibold">Type</th>
                  <th className="px-4 py-2.5 font-semibold">Status</th>
                  <th className="px-4 py-2.5 font-semibold">Progress</th>
                  <th className="px-4 py-2.5 font-semibold">Owner</th>
                  <th className="px-4 py-2.5 font-semibold">Go-live</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-zinc-100 last:border-0" data-testid={`onb-report-row-${i}`}>
                    <td className="px-4 py-2.5 font-medium text-zinc-900">{r.customer_name}</td>
                    <td className="px-4 py-2.5 text-zinc-600">{typeLabel(r.customer_type)}</td>
                    <td className="px-4 py-2.5 text-zinc-600">{STATUS_LABELS[r.status] || r.status}</td>
                    <td className="px-4 py-2.5 text-zinc-600 tabular-nums">{r.progress}%{r.blocked ? <span className="ml-1.5 text-[10px] text-red-600">blocked</span> : null}</td>
                    <td className="px-4 py-2.5 text-zinc-600">{r.owner}</td>
                    <td className="px-4 py-2.5 text-zinc-600">{r.go_live_target || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
};

export default OnboardingReports;
