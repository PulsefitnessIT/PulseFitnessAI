/* SiconDashboard.js — read-side (Sicon → Pulse) admin dashboard (spec §16/§17/§27).
   Connection health, equipment & case stats, import preview, sync runs,
   conflict review and API health. Consumes /api/sicon/read/* endpoints. */
import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  CheckCircle, XCircle, Loader2, RefreshCw, Activity, Boxes,
  ClipboardList, AlertTriangle, PlugZap, Gauge,
} from 'lucide-react';

const Stat = ({ label, value, tone = 'default', testid }) => (
  <div className="rounded-lg border border-white/10 bg-[var(--theme-surface)] px-4 py-3" data-testid={testid}>
    <div className="text-2xl font-extrabold text-[var(--theme-text)]">{value ?? 0}</div>
    <div className={`text-xs mt-0.5 ${tone === 'warn' ? 'text-amber-500' : tone === 'bad' ? 'text-rose-500' : 'text-[var(--theme-text-muted)]'}`}>{label}</div>
  </div>
);

const SiconDashboard = () => {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [dash, setDash] = useState(null);
  const [health, setHealth] = useState(null);
  const [conflicts, setConflicts] = useState([]);
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, c] = await Promise.all([
        axios.get(`${API}/sicon/read/dashboard`, { headers }),
        axios.get(`${API}/sicon/read/conflicts`, { headers }),
      ]);
      setDash(d.data);
      setConflicts(c.data.conflicts || []);
    } catch (e) { notifyApiError(e); }
    setLoading(false);
  }, [API]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const runHealth = async () => {
    setBusy('health');
    try { setHealth((await axios.get(`${API}/sicon/read/api-health`, { headers })).data); }
    catch (e) { notifyApiError(e); } finally { setBusy(''); }
  };

  const runPreview = async () => {
    setBusy('preview');
    try {
      const r = await axios.post(`${API}/sicon/read/equipment/preview`, { max_records: 500 }, { headers });
      setPreview(r.data);
      notify.success('Preview complete');
    } catch (e) { notifyApiError(e); } finally { setBusy(''); }
  };

  const runSync = async () => {
    setBusy('sync');
    try {
      const r = await axios.post(`${API}/sicon/read/equipment/sync`, { max_records: 0 }, { headers });
      notify.success(`Equipment sync started (run ${String(r.data.run_id).slice(0, 8)})`);
      setTimeout(load, 1500);
    } catch (e) { notifyApiError(e); } finally { setBusy(''); }
  };

  const resolve = async (extId, action, pulseAssetId) => {
    try {
      await axios.post(`${API}/sicon/read/conflicts/${extId}/resolve`,
        { entity: 'equipment', action, pulse_asset_id: pulseAssetId }, { headers });
      notify.success('Conflict resolved');
      load();
    } catch (e) { notifyApiError(e); }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-[var(--theme-text-muted)] py-8"><Loader2 className="animate-spin" size={16} /> Loading Sicon dashboard…</div>;

  const conn = dash?.connection || {};
  const eq = dash?.equipment || {};
  const cs = dash?.cases || {};
  const run = dash?.last_equipment_sync;

  return (
    <div className="space-y-6" data-testid="sicon-dashboard">
      {/* A. Connection */}
      <Card className="p-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <PlugZap size={20} className="text-[var(--theme-brand)]" />
            <div>
              <div className="flex items-center gap-2">
                {conn.connected
                  ? <Badge className="bg-emerald-500/15 text-emerald-500 border-emerald-500/30" data-testid="sicon-conn-status"><CheckCircle size={12} className="mr-1" /> Connected to Sicon</Badge>
                  : <Badge className="bg-zinc-500/15 text-zinc-400 border-zinc-500/30" data-testid="sicon-conn-status"><XCircle size={12} className="mr-1" /> {conn.status === 'not_configured' ? 'Not configured' : 'Disconnected'}</Badge>}
                {conn.writes_enabled
                  ? <Badge className="bg-rose-500/15 text-rose-500 border-rose-500/30">Writes ON</Badge>
                  : <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Read-only</Badge>}
              </div>
              <div className="text-xs text-[var(--theme-text-muted)] mt-1">
                Company ID {conn.company_id || '—'} · Last check {conn.last_authenticated_at ? new Date(conn.last_authenticated_at).toLocaleString() : 'never'}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={load} data-testid="sicon-refresh-btn"><RefreshCw size={14} className="mr-1.5" /> Refresh</Button>
            <Button variant="outline" size="sm" onClick={runHealth} disabled={busy === 'health'} data-testid="sicon-health-btn">
              {busy === 'health' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Gauge size={14} className="mr-1.5" />} API Health
            </Button>
          </div>
        </div>
      </Card>

      {/* B. Equipment */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><Boxes size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">Equipment estate</h3></div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Linked assets" value={eq.linked} testid="sicon-eq-linked" />
          <Stat label="Open conflicts" value={eq.open_conflicts} tone={eq.open_conflicts ? 'warn' : 'default'} testid="sicon-eq-conflicts" />
          <Stat label="Total tracked" value={eq.total_linked} testid="sicon-eq-total" />
          <Stat label="Last sync" value={run ? (run.counts?.created ?? 0) + (run.counts?.linked ?? 0) + (run.counts?.updated ?? 0) : 0} testid="sicon-eq-lastsync" />
        </div>
        <div className="flex flex-wrap gap-2 mt-4">
          <Button size="sm" variant="outline" onClick={runPreview} disabled={!conn.configured || busy === 'preview'} data-testid="sicon-preview-btn">
            {busy === 'preview' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <ClipboardList size={14} className="mr-1.5" />} Preview import
          </Button>
          <Button size="sm" onClick={runSync} disabled={!conn.configured || busy === 'sync'} data-testid="sicon-sync-btn">
            {busy === 'sync' ? <Loader2 size={14} className="mr-1.5 animate-spin" /> : <Activity size={14} className="mr-1.5" />} Run equipment sync
          </Button>
          {!conn.configured && <span className="text-xs text-[var(--theme-text-muted)] self-center">Configure the connection first (Connection tab).</span>}
        </div>

        {preview && (
          <div className="mt-4 rounded-lg border border-white/10 p-4" data-testid="sicon-preview-result">
            <div className="text-sm font-semibold text-[var(--theme-text)] mb-2">
              Preview — {preview.previewed} of {preview.total_in_sicon ?? '?'} records
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
              {['linked', 'match', 'new', 'conflict', 'failed'].map((k) => (
                <div key={k} className="rounded border border-white/10 py-2">
                  <div className="text-lg font-bold text-[var(--theme-text)]">{preview.counts?.[k] ?? 0}</div>
                  <div className="text-[10px] uppercase tracking-wide text-[var(--theme-text-muted)]">{k}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* C. Service cases */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><ClipboardList size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">Service cases</h3></div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Linked cases" value={cs.linked} testid="sicon-case-linked" />
          <Stat label="Total tracked" value={cs.total_linked} testid="sicon-case-total" />
        </div>
        <div className="text-xs text-[var(--theme-text-muted)] mt-3">Case import lands in the next increment (CaseSearch → Service Desk).</div>
      </Card>

      {/* D. Conflicts */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><AlertTriangle size={18} className="text-amber-500" /><h3 className="font-bold text-[var(--theme-text)]">Conflicts to review ({conflicts.length})</h3></div>
        {conflicts.length === 0 ? (
          <div className="text-sm text-[var(--theme-text-muted)]">No conflicts — every matched record was unambiguous.</div>
        ) : (
          <div className="space-y-2" data-testid="sicon-conflict-list">
            {conflicts.map((c) => (
              <div key={c.external_id} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 flex items-center justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-[var(--theme-text)]">Sicon equipment #{c.external_id} · serial {c.sicon_record?.serial_number || '—'}</div>
                  <div className="text-xs text-[var(--theme-text-muted)]">{(c.reasons || []).join('; ')} · {(c.candidates || []).length} candidate(s)</div>
                </div>
                <div className="flex gap-2">
                  {(c.candidates || []).slice(0, 3).map((cand) => (
                    <Button key={cand.id} size="sm" variant="outline" onClick={() => resolve(c.external_id, 'link', cand.id)} data-testid={`sicon-conflict-link-${c.external_id}`}>
                      Link to {String(cand.id).slice(0, 6)}…
                    </Button>
                  ))}
                  <Button size="sm" variant="outline" onClick={() => resolve(c.external_id, 'create_new')}>Create new</Button>
                  <Button size="sm" variant="ghost" onClick={() => resolve(c.external_id, 'ignore')}>Ignore</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* E. Sync log (latest run) */}
      {run && (
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3"><Activity size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">Latest equipment sync</h3></div>
          <div className="text-xs text-[var(--theme-text-muted)] mb-2">Run {String(run.id).slice(0, 8)} · {run.status} · {run.processed ?? 0} processed</div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center">
            {['created', 'linked', 'updated', 'conflict', 'failed'].map((k) => (
              <div key={k} className="rounded border border-white/10 py-2">
                <div className="text-lg font-bold text-[var(--theme-text)]">{run.counts?.[k] ?? 0}</div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--theme-text-muted)]">{k}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* F. API health */}
      {health && (
        <Card className="p-5" data-testid="sicon-api-health">
          <div className="flex items-center gap-2 mb-3"><Gauge size={18} className="text-[var(--theme-brand)]" /><h3 className="font-bold text-[var(--theme-text)]">API health</h3></div>
          {!health.configured ? (
            <div className="text-sm text-[var(--theme-text-muted)]">Not configured.</div>
          ) : (
            <div className="space-y-1.5">
              {health.endpoints.map((e) => (
                <div key={e.endpoint} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--theme-text)]">{e.ok ? <CheckCircle size={14} className="inline mr-1.5 text-emerald-500" /> : <XCircle size={14} className="inline mr-1.5 text-rose-500" />}{e.endpoint}</span>
                  <span className="text-xs text-[var(--theme-text-muted)]">{e.status || '—'} · {e.ms}ms{e.error ? ` · ${e.error}` : ''}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default SiconDashboard;
