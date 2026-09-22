/**
 * Platform Health / Self-Healing — Master Admin data-integrity monitor.
 *
 * Runs a registry of read-only "checks" that detect records which exist
 * in the DB but don't surface correctly in the product (e.g. a fault
 * logged against a site-less machine → invisible in per-site views). Each
 * finding is AI-diagnosed in plain English; the admin applies a reversible
 * one-click fix. Nothing auto-heals (Phase 1 policy).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Loader2, RefreshCw, Wrench, Undo2, XCircle,
  ShieldCheck, AlertTriangle, Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import SubTabBar from '../../components/shared/SubTabBar';

const API = process.env.REACT_APP_BACKEND_URL;

const RISK_STYLE = {
  high: 'bg-red-100 text-red-700 border-red-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  low: 'bg-emerald-100 text-emerald-700 border-emerald-200',
};
const SEV_DOT = { high: 'bg-red-500', medium: 'bg-amber-500', low: 'bg-emerald-500' };

export default function PlatformHealth() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const [findings, setFindings] = useState([]);
  const [lastScan, setLastScan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [tab, setTab] = useState('open');

  const load = useCallback(async (status = 'open') => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/master-admin/platform-health/findings?status=${status}`, auth);
      setFindings(r.data.findings || []);
      setLastScan(r.data.last_scan || null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to load findings');
    } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(tab); }, [load, tab]);

  const scan = async () => {
    setScanning(true);
    try {
      const r = await axios.post(`${API}/api/master-admin/platform-health/scan`, {}, auth);
      const n = r.data?.summary?.total ?? 0;
      toast.success(n === 0 ? 'Scan complete — no integrity issues found' : `Scan complete — ${n} finding(s)`);
      setTab('open');
      await load('open');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Scan failed');
    } finally { setScanning(false); }
  };

  const act = async (id, verb, okMsg) => {
    setBusyId(id);
    try {
      await axios.post(`${API}/api/master-admin/platform-health/findings/${id}/${verb}`, {}, auth);
      toast.success(okMsg);
      await load(tab);
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Could not ${verb} finding`);
    } finally { setBusyId(null); }
  };

  const TABS = [
    { id: 'open', label: 'Open' },
    { id: 'fixed', label: 'Fixed' },
    { id: 'dismissed', label: 'Dismissed' },
  ];

  return (
    <div className="space-y-6" data-testid="platform-health-panel">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          {lastScan ? (
            <p className="text-xs text-zinc-400" data-testid="platform-health-last-scan">
              Last scan: {new Date(lastScan.started_at).toLocaleString()} · {lastScan.findings_count} finding(s)
              {lastScan.by ? ` · ${lastScan.by}` : ''}
            </p>
          ) : (
            <p className="text-xs text-zinc-400">No scan yet — run one to check the platform.</p>
          )}
        </div>
        <button onClick={scan} disabled={scanning}
          data-testid="platform-health-scan-btn"
          className="px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium flex items-center gap-2 disabled:opacity-60">
          {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {scanning ? 'Scanning…' : 'Run integrity scan'}
        </button>
      </div>

      <SubTabBar
        tabs={TABS}
        active={tab}
        onChange={setTab}
        testId="platform-health-tab"
      />

      {loading ? (
        <div className="flex items-center justify-center py-16 text-zinc-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      ) : findings.length === 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-800 flex items-center gap-2"
          data-testid="platform-health-empty">
          <ShieldCheck className="w-5 h-5" />
          {tab === 'open' ? 'No open integrity issues. Run a scan to check again.' : `No ${tab} findings.`}
        </div>
      ) : (
        <div className="space-y-3">
          {findings.map((f) => (
            <div key={f.id} data-testid={`finding-${f.id}`}
              className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex items-start gap-2 min-w-0">
                  <span className={`mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 ${SEV_DOT[f.severity] || 'bg-zinc-400'}`} />
                  <div className="min-w-0">
                    <div className="font-semibold text-zinc-800">{f.title}</div>
                    <div className="text-xs text-zinc-400 mt-0.5">
                      {f.org_name} · {f.check_id}
                      {f.breakdown ? ` · ${f.breakdown.equipment || 0} equipment, ${f.breakdown.issues || 0} faults` : ''}
                    </div>
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${RISK_STYLE[f.ai_risk] || RISK_STYLE.low}`}>
                  {f.ai_risk || 'low'} risk
                </span>
              </div>

              <div className="mt-3 rounded-lg bg-sky-50 border border-sky-100 p-3">
                <div className="flex items-center gap-1.5 text-xs font-medium text-sky-700 mb-1">
                  <Sparkles className="w-3.5 h-3.5" /> AI diagnosis
                </div>
                <p className="text-sm text-zinc-700" data-testid={`finding-diagnosis-${f.id}`}>{f.ai_diagnosis}</p>
                {f.ai_recommendation && (
                  <p className="text-sm text-zinc-500 mt-1"><b>Fix:</b> {f.ai_recommendation}</p>
                )}
              </div>

              {f.status === 'fixed' && f.fix_result && (
                <p className="text-xs text-emerald-600 mt-2 flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" /> Fixed by {f.fixed_by} · {f.fix_result.equipment} equipment + {f.fix_result.issues} faults stamped
                </p>
              )}

              <div className="mt-3 flex items-center gap-2 flex-wrap">
                {f.status === 'open' && (
                  <>
                    <button onClick={() => act(f.id, 'fix', 'Fix applied')} disabled={busyId === f.id || !f.fix_kind}
                      data-testid={`finding-fix-${f.id}`}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm flex items-center gap-1.5 disabled:opacity-60">
                      {busyId === f.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wrench className="w-4 h-4" />}
                      Apply fix
                    </button>
                    <button onClick={() => act(f.id, 'dismiss', 'Finding dismissed')} disabled={busyId === f.id}
                      data-testid={`finding-dismiss-${f.id}`}
                      className="px-3 py-1.5 rounded-lg border border-zinc-300 text-zinc-600 text-sm flex items-center gap-1.5 hover:bg-zinc-50">
                      <XCircle className="w-4 h-4" /> Dismiss
                    </button>
                  </>
                )}
                {f.status === 'fixed' && (
                  <button onClick={() => act(f.id, 'undo', 'Fix undone')} disabled={busyId === f.id}
                    data-testid={`finding-undo-${f.id}`}
                    className="px-3 py-1.5 rounded-lg border border-amber-300 text-amber-700 text-sm flex items-center gap-1.5 hover:bg-amber-50">
                    {busyId === f.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Undo2 className="w-4 h-4" />}
                    Undo fix
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-500 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        Checks: missing-site & broken site references, orphaned users, faults on missing equipment, and
        duplicate data (org names, equipment serials, user emails). Runs on demand and automatically once a night.
      </div>
    </div>
  );
}
