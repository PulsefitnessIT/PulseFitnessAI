/**
 * Master Admin — MOD Sites console.
 *
 * List of all MOD sites, per-site counts (equipment / staff / open faults),
 * and per-site audit log viewer. Consumes:
 * GET /api/master-admin/mod/sites
 * GET /api/master-admin/mod/audit-log/{site_id}
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Shield, Building2, Wrench, ChevronRight, ClipboardList, KeyRound, AlertTriangle, Target, Play, CheckCircle2, Clock, ShieldAlert, Save, Loader2, FileSignature, CalendarCheck, RefreshCw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

export default function AdminMODConsole({ API }) {
 const token = localStorage.getItem('token');
 const headers = { Authorization: `Bearer ${token}` };
 const [sites, setSites] = useState([]);
 const [loading, setLoading] = useState(true);
 const [selected, setSelected] = useState(null);
 const [log, setLog] = useState([]);
 const [logLoading, setLogLoading] = useState(false);

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const { data } = await axios.get(`${API}/master-admin/mod/sites`, { headers });
 setSites(data.sites || []);
 } catch {
 notify.error('Failed to load MOD sites');
 } finally {
 setLoading(false);
 }
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
 }, [API]);

 useEffect(() => { load(); }, [load]);

 const openSite = async (site) => {
 setSelected(site);
 setLogLoading(true);
 setLog([]);
 try {
 const { data } = await axios.get(`${API}/master-admin/mod/audit-log/${site.id}`, { headers });
 setLog(data.log || []);
 } catch {
 notify.error('Failed to load audit log');
 } finally {
 setLogLoading(false);
 }
 };

 const [rotating, setRotating] = useState(null);
 const [rotatedCode, setRotatedCode] = useState(null); // {site_name, username, new_password}

 // Drill mode state
 const [drills, setDrills] = useState([]);
 const [drillSiteTarget, setDrillSiteTarget] = useState(null); // site obj while opening launcher
 const [drillScenario, setDrillScenario] = useState('Unplanned power loss on cardio bank');
 const [drillStarting, setDrillStarting] = useState(false);
 const [drillCompleting, setDrillCompleting] = useState(null);
 const [drillReport, setDrillReport] = useState(null); // after complete, show metrics

 const loadDrills = useCallback(async () => {
 try {
 const { data } = await axios.get(`${API}/master-admin/mod/drills`, { headers });
 setDrills(data.drills || []);
 } catch { /* ignore */ }
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
 }, [API]);

 useEffect(() => { loadDrills(); }, [loadDrills]);

 const startDrill = async () => {
 if (!drillSiteTarget || !drillScenario.trim()) return;
 setDrillStarting(true);
 try {
 await axios.post(
 `${API}/master-admin/mod/sites/${drillSiteTarget.id}/drill/start`,
 { scenario: drillScenario, fault_type: 'electrical' },
 { headers },
 );
 notify.success(`Drill started on ${drillSiteTarget.name}`);
 setDrillSiteTarget(null);
 setDrillScenario('Unplanned power loss on cardio bank');
 loadDrills();
 } catch (e) {
 notifyApiError(notify, e, 'Drill start failed');
 } finally {
 setDrillStarting(false);
 }
 };

 const completeDrill = async (drill) => {
 if (!window.confirm(`Complete drill "${drill.drill_scenario}"? This closes the ticket and compiles the response report.`)) return;
 setDrillCompleting(drill.drill_id);
 try {
 const { data } = await axios.post(
 `${API}/master-admin/mod/drills/${drill.drill_id}/complete`,
 {},
 { headers },
 );
 setDrillReport(data.report);
 notify.success('Drill completed — report ready');
 loadDrills();
 } catch (e) {
 notifyApiError(notify, e, 'Complete failed');
 } finally {
 setDrillCompleting(null);
 }
 };

 const rotate = async (site) => {
 const days = site.password_days_until_expiry;
 const urgency = days === null ? 'never rotated' :
 days < 0 ? `expired ${-days} day(s) ago` :
 days === 0 ? 'expiring today' :
 `expiring in ${days} day(s)`;
 if (!window.confirm(`Rotate password for ${site.name}? (${urgency})\n\nThe existing code will be invalidated immediately.`)) return;
 setRotating(site.id);
 try {
 const { data } = await axios.post(`${API}/master-admin/mod/sites/${site.id}/rotate-password`, {}, { headers });
 setRotatedCode(data);
 notify.success('Password rotated — new code emailed');
 load();
 } catch (e) {
 notifyApiError(notify, e, 'Rotation failed');
 } finally {
 setRotating(null);
 }
 };

 const branchTally = sites.reduce((acc, s) => {
 const k = s.mod_branch || 'Other';
 acc[k] = (acc[k] || 0) + 1;
 return acc;
 }, {});

 return (
 <div className="space-y-6" data-testid="admin-mod-console">
 {/* ASER settings */}
 <AserSettingsPanel API={API} headers={headers} />

 {/* Contract Activation Board — Type A MOD service contracts */}
 <ContractActivationBoard API={API} headers={headers} />

 {/* Header tiles */}
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
 <KpiTile icon={Building2} label="MOD sites" value={sites.length} color="indigo" />
 <KpiTile icon={Shield} label="RAF" value={branchTally.RAF || 0} color="sky" />
 <KpiTile icon={Shield} label="Army" value={branchTally.Army || 0} color="emerald" />
 <KpiTile icon={Shield} label="Navy" value={branchTally.Navy || 0} color="blue" />
 </div>

 {/* List */}
 {loading ? (
 <div className="text-center text-zinc-500 py-10 text-sm">Loading MOD sites…</div>
 ) : sites.length === 0 ? (
 <div className="text-center text-zinc-500 py-10 text-sm">No MOD sites seeded yet.</div>
 ) : (
 <div className="bg-white rounded-xl border border-zinc-200 overflow-x-auto">
 <table className="w-full text-sm">
 <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500">
 <tr>
 <th className="px-4 py-3 text-left font-bold">Site</th>
 <th className="px-4 py-3 text-left font-bold">Branch</th>
 <th className="px-4 py-3 text-right font-bold">Equipment</th>
 <th className="px-4 py-3 text-right font-bold">Staff</th>
 <th className="px-4 py-3 text-right font-bold">Open faults</th>
 <th className="px-4 py-3 text-center font-bold">Password</th>
 <th className="px-4 py-3 text-center font-bold">Drill</th>
 <th className="px-4 py-3"></th>
 </tr>
 </thead>
 <tbody>
 {sites.map((s) => {
 const siteActiveDrill = drills.find((d) => d.organization_id === s.id && d.status !== 'resolved');
 return (
 <tr key={s.id} className="border-t border-zinc-100 hover:bg-zinc-50" data-testid={`admin-mod-site-${s.id}`}>
 <td className="px-4 py-3 font-bold text-zinc-800">
 {s.name}
 {s.username && <div className="text-[10px] text-zinc-500 font-mono font-normal">{s.username}</div>}
 </td>
 <td className="px-4 py-3 text-zinc-600">{s.mod_branch || '—'}</td>
 <td className="px-4 py-3 text-right text-zinc-700 font-medium">{s.equipment_count}</td>
 <td className="px-4 py-3 text-right text-zinc-700 font-medium">{s.staff_count}</td>
 <td className={`px-4 py-3 text-right font-bold ${s.open_faults > 0 ? 'text-amber-600' : 'text-emerald-600'}`}>{s.open_faults}</td>
 <td className="px-4 py-3 text-center">
 <PasswordChip s={s} onRotate={rotate} rotating={rotating === s.id} />
 </td>
 <td className="px-4 py-3 text-center">
 {siteActiveDrill ? (
 <button
 onClick={() => completeDrill(siteActiveDrill)}
 disabled={drillCompleting === siteActiveDrill.drill_id}
 className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100 disabled:opacity-50"
 data-testid={`admin-mod-drill-complete-${s.id}`}
 title="Complete drill & compile report"
 >
 <CheckCircle2 size={10} /> {drillCompleting === siteActiveDrill.drill_id ? 'Completing…' : 'Complete'}
 </button>
 ) : (
 <button
 onClick={() => setDrillSiteTarget(s)}
 className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border bg-zinc-50 text-zinc-600 border-zinc-200 hover:bg-violet-50 hover:text-violet-700 hover:border-violet-200"
 data-testid={`admin-mod-drill-start-${s.id}`}
 title="Start a red-team drill (doesn't affect KPIs)"
 >
 <Target size={10} /> Start
 </button>
 )}
 </td>
 <td className="px-4 py-3 text-right">
 <button
 onClick={() => openSite(s)}
 className="text-xs font-bold text-[var(--color-brand-blue)] hover:underline flex items-center gap-1 ml-auto"
 data-testid={`admin-mod-audit-${s.id}`}
 >
 <ClipboardList size={12} /> Audit log <ChevronRight size={12} />
 </button>
 </td>
 </tr>
 );
 })}
 </tbody>
 </table>
 </div>
 )}

 {/* Audit log drawer */}
 {selected && (
 <div className="fixed inset-0 z-[60] bg-black/50 flex justify-end" onClick={() => setSelected(null)}>
 <div className="w-full max-w-xl h-full bg-white shadow-2xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
 <div className="px-5 py-4 border-b border-zinc-200 sticky top-0 bg-white z-10 flex items-start justify-between gap-3">
 <div>
 <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-blue)]">MOD audit log</div>
 <h3 className="text-lg font-extrabold text-zinc-800">{selected.name}</h3>
 </div>
 <button onClick={() => setSelected(null)} className="px-2 py-1 text-sm text-zinc-600 hover:bg-zinc-100 rounded">Close</button>
 </div>
 <div className="px-5 py-4 space-y-2">
 {logLoading && <div className="text-center text-zinc-500 text-sm py-6">Loading…</div>}
 {!logLoading && log.length === 0 && <div className="text-center text-zinc-500 text-sm py-6">No audit entries yet.</div>}
 {log.map((row) => (
 <div key={row.id} className="rounded-lg border border-zinc-200 p-3" data-testid={`admin-mod-audit-row-${row.id}`}>
 <div className="flex items-center gap-2 mb-1">
 <span className="text-[10px] font-extrabold uppercase tracking-wider bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)] px-1.5 py-0.5 rounded">{row.action}</span>
 <span className="text-[10px] text-zinc-400">{new Date(row.created_at).toLocaleString()}</span>
 </div>
 {row.payload && Object.keys(row.payload).length > 0 && (
 <pre className="text-[11px] text-zinc-600 whitespace-pre-wrap break-all bg-zinc-50 rounded p-2 mt-1">{JSON.stringify(row.payload, null, 2)}</pre>
 )}
 </div>
 ))}
 </div>
 </div>
 </div>
 )}
 {/* Drill launcher modal */}
 {drillSiteTarget && (
 <div className="fixed inset-0 z-[70] bg-black/60 grid place-items-center p-4" data-testid="admin-mod-drill-launcher" onClick={() => setDrillSiteTarget(null)}>
 <div className="w-full max-w-md bg-white rounded-xl overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
 <div className="bg-violet-600 px-5 py-4 border-b-4 border-violet-300">
 <div className="text-[10px] font-extrabold tracking-[0.25em] uppercase text-violet-100 flex items-center gap-1.5"><Target size={11} /> MOD · Red Team Drill</div>
 <h3 className="text-white font-extrabold text-lg mt-1">Start drill — {drillSiteTarget.name}</h3>
 </div>
 <div className="p-5 space-y-3">
 <p className="text-sm text-zinc-700">
 A simulated URGENT fault will be logged. The PTI sees a purple <strong>DRILL</strong> banner and acknowledges / responds as if real. KPIs are unaffected; real on-call engineers are <strong>not</strong> paged.
 </p>
 <label className="block">
 <span className="text-[10px] font-extrabold uppercase tracking-wider text-zinc-500">Scenario</span>
 <input
 value={drillScenario}
 onChange={(e) => setDrillScenario(e.target.value)}
 className="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none"
 placeholder="e.g. Power loss on cardio bank"
 data-testid="admin-mod-drill-scenario-input"
 />
 </label>
 <div className="flex gap-2 pt-2">
 <button
 onClick={startDrill}
 disabled={drillStarting || !drillScenario.trim()}
 className="flex-1 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-extrabold py-2.5 text-sm flex items-center justify-center gap-1.5 disabled:opacity-50"
 data-testid="admin-mod-drill-start-confirm"
 >
 <Play size={13} /> {drillStarting ? 'Starting…' : 'Start drill'}
 </button>
 <button
 onClick={() => setDrillSiteTarget(null)}
 className="rounded-lg px-4 py-2.5 text-sm font-bold border border-zinc-300 text-zinc-700 hover:bg-zinc-50"
 >Cancel</button>
 </div>
 </div>
 </div>
 </div>
 )}

 {/* Drill report modal */}
 {drillReport && (
 <div className="fixed inset-0 z-[70] bg-black/60 grid place-items-center p-4" data-testid="admin-mod-drill-report" onClick={() => setDrillReport(null)}>
 <div className="w-full max-w-md bg-white rounded-xl overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
 <div className="bg-[var(--color-ink-2)] px-5 py-4 border-b-2 border-violet-400">
 <div className="text-[10px] font-extrabold tracking-[0.25em] uppercase text-violet-300 flex items-center gap-1.5"><CheckCircle2 size={11} /> Drill complete</div>
 <h3 className="text-white font-extrabold text-lg mt-1">{drillReport.scenario}</h3>
 <div className="text-[11px] text-white/60 font-mono mt-1">{drillReport.ticket_ref}</div>
 </div>
 <div className="p-5 space-y-3">
 <DrillMetric icon={Clock} label="Time to acknowledge"
 value={formatDuration(drillReport.time_to_acknowledge_s)}
 subtitle={drillReport.acknowledged_at ? `at ${new Date(drillReport.acknowledged_at).toLocaleString()}` : 'Never acknowledged'} />
 <DrillMetric icon={CheckCircle2} label="Time to resolution"
 value={formatDuration(drillReport.time_to_resolve_s)}
 subtitle={`Completed ${new Date(drillReport.completed_at).toLocaleString()}`} />
 <DrillMetric icon={Wrench} label="Attachments captured" value={drillReport.attachments_captured} />
 <button
 onClick={() => setDrillReport(null)}
 className="w-full mt-2 rounded-lg bg-[var(--color-brand-blue)] text-white font-bold py-2.5 text-sm hover:bg-[var(--color-brand-blue-hover)]"
 data-testid="admin-mod-drill-report-done"
 >Done</button>
 </div>
 </div>
 </div>
 )}

 {/* Rotation result modal — shows the new code once */}
 {rotatedCode && (
 <div className="fixed inset-0 z-[70] bg-black/60 grid place-items-center p-4" data-testid="admin-mod-rotation-result" onClick={() => setRotatedCode(null)}>
 <div className="w-full max-w-md bg-white rounded-xl overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
 <div className="bg-[var(--color-ink-2)] px-5 py-4 border-b-2 border-[var(--color-brand-cyan)]">
 <div className="text-[10px] font-extrabold tracking-[0.25em] uppercase text-[var(--color-brand-cyan)]">Pulse · MOD · New Site Code</div>
 <h3 className="text-white font-extrabold text-lg mt-1">{rotatedCode.site_name}</h3>
 </div>
 <div className="p-5 space-y-3">
 <p className="text-sm text-zinc-700">Share this with the on-site PTI via a secure channel. The previous code has been invalidated.</p>
 <div className="rounded-lg border border-zinc-200 overflow-hidden">
 <div className="flex items-center justify-between px-3 py-2 bg-zinc-50 text-[10px] font-extrabold uppercase tracking-wider text-zinc-500">
 Username
 </div>
 <div className="px-3 py-2.5 font-mono font-bold text-zinc-800">{rotatedCode.username}</div>
 <div className="flex items-center justify-between px-3 py-2 bg-[var(--color-ink-2)] text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)]">
 New code
 <button
 onClick={() => { navigator.clipboard.writeText(rotatedCode.new_password); notify.success('Copied to clipboard'); }}
 className="text-[10px] text-white/80 hover:text-white"
 data-testid="admin-mod-rotation-copy"
 >COPY</button>
 </div>
 <div className="px-3 py-3 font-mono font-bold text-[15px] bg-[var(--color-ink-2)] text-white break-all" data-testid="admin-mod-rotation-new-code">{rotatedCode.new_password}</div>
 </div>
 <p className="text-xs text-zinc-500">This code has also been emailed to the MOD rotation notify address.</p>
 <button
 onClick={() => setRotatedCode(null)}
 className="w-full rounded-lg bg-[var(--color-brand-blue)] text-white font-bold py-2.5 text-sm hover:bg-[var(--color-brand-blue-hover)]"
 data-testid="admin-mod-rotation-done"
 >Done</button>
 </div>
 </div>
 </div>
 )}
 </div>
 );
}


function PasswordChip({ s, onRotate, rotating }) {
 const days = s.password_days_until_expiry;
 const tone = days === null ? 'bg-zinc-100 text-zinc-500 border-zinc-200' :
 days < 0 ? 'bg-red-100 text-red-700 border-red-200' :
 days <= 7 ? 'bg-red-50 text-red-600 border-red-200' :
 days <= 30 ? 'bg-amber-50 text-amber-700 border-amber-200' :
 'bg-emerald-50 text-emerald-700 border-emerald-200';
 const label = days === null ? 'never set' :
 days < 0 ? `expired ${-days}d ago` :
 days === 0 ? 'expires today' :
 `${days}d`;
 const Icon = (days !== null && days <= 7) ? AlertTriangle : KeyRound;
 return (
 <div className="inline-flex items-center gap-2">
 <span className={`inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded border ${tone}`} data-testid={`admin-mod-password-chip-${s.id}`}>
 <Icon size={10} /> {label}
 </span>
 <button
 onClick={() => onRotate(s)}
 disabled={rotating}
 className="text-[10px] font-bold text-[var(--color-brand-blue)] hover:underline disabled:opacity-40"
 data-testid={`admin-mod-rotate-${s.id}`}
 >{rotating ? '…' : 'Rotate'}</button>
 </div>
 );
}



function ContractActivationBoard({ API, headers }) {
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState({ pending_confirmation: 0, active_count: 0 });
  const [busyId, setBusyId] = useState('');
  const [form, setForm] = useState({}); // per-contract { scheduled_date, engineer, notes }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/master-admin/mod-estate/contracts`, { headers });
      setContracts(data.contracts || []);
      setMeta({ pending_confirmation: data.pending_confirmation || 0, active_count: data.active_count || 0 });
    } catch { /* ignore */ }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);
  useEffect(() => { load(); }, [load]);

  const money = (n, c = 'GBP') => new Intl.NumberFormat('en-GB', { style: 'currency', currency: c }).format(Number(n) || 0);
  const setF = (id, k, v) => setForm((f) => ({ ...f, [id]: { ...(f[id] || {}), [k]: v } }));

  const confirm = async (c) => {
    setBusyId(c.id);
    try {
      const body = form[c.id] || {};
      await axios.post(`${API}/master-admin/mod-estate/contracts/${c.id}/confirm-visit`, {
        scheduled_date: body.scheduled_date || c.proposed_date,
        engineer: body.engineer || '',
        notes: body.notes || '',
      }, { headers });
      notify.success('Annual visit confirmed with the MOD Service team');
      await load();
    } catch (e) { notifyApiError(e, 'Could not confirm visit'); }
    setBusyId('');
  };

  return (
    <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden" data-testid="mod-contract-board">
      <div className="px-5 py-4 border-b border-zinc-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileSignature size={16} className="text-[var(--color-brand-blue)]" />
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-blue)]">Contract Activation Board</div>
            <h3 className="text-base font-extrabold text-zinc-800">Type A service contracts</h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {meta.pending_confirmation > 0 && (
            <span className="text-[11px] font-bold px-2 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-200" data-testid="mod-contract-pending-badge">
              {meta.pending_confirmation} awaiting confirmation
            </span>
          )}
          <span className="text-[11px] font-semibold px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">{meta.active_count} active</span>
          <button onClick={load} disabled={loading} className="p-1.5 rounded-md border border-zinc-200 text-zinc-500 hover:bg-zinc-50 disabled:opacity-50" title="Refresh" data-testid="mod-contract-refresh">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-zinc-500 py-8 text-sm">Loading contracts…</div>
      ) : contracts.length === 0 ? (
        <div className="text-center text-zinc-500 py-8 text-sm" data-testid="mod-contract-empty">No Type A contracts activated yet. When a site e-signs a Type A quote it will appear here to confirm the annual service.</div>
      ) : (
        <div className="divide-y divide-zinc-100">
          {contracts.map((c) => {
            const confirmed = c.visit_status === 'confirmed';
            const f = form[c.id] || {};
            return (
              <div key={c.id} className="px-5 py-4" data-testid={`mod-contract-row-${c.id}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold text-zinc-800">{c.mod_site_name}</span>
                      <span className="text-[10px] font-mono text-zinc-500">{c.quote_number}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full border ${confirmed ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                        {confirmed ? 'Visit confirmed' : 'Awaiting confirmation'}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      {money(c.annual_value, c.currency)}/yr · {c.equipment_count || 0} machines · term {c.term_months || 12} mo
                      {c.start_date ? ` · starts ${c.start_date}` : ''}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-wider text-zinc-400">{confirmed ? 'Scheduled' : 'Proposed'}</div>
                    <div className="font-bold text-zinc-800">{confirmed ? c.scheduled_date : c.proposed_date}</div>
                    {confirmed && c.engineer && <div className="text-[11px] text-zinc-500">Eng: {c.engineer}</div>}
                  </div>
                </div>

                {confirmed ? (
                  <div className="mt-2 text-[11px] text-emerald-700 flex items-center gap-1">
                    <CheckCircle2 size={12} /> Confirmed by {c.confirmed_by}{c.visit_notes ? ` — ${c.visit_notes}` : ''}
                  </div>
                ) : (
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-0.5">Service date</label>
                      <input type="date" value={f.scheduled_date || c.proposed_date || ''} onChange={(e) => setF(c.id, 'scheduled_date', e.target.value)}
                        className="w-full px-2 py-1.5 text-sm rounded-md border border-zinc-300" data-testid={`mod-contract-date-${c.id}`} />
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-0.5">Engineer</label>
                      <input type="text" value={f.engineer || ''} onChange={(e) => setF(c.id, 'engineer', e.target.value)} placeholder="Assign engineer"
                        className="w-full px-2 py-1.5 text-sm rounded-md border border-zinc-300" data-testid={`mod-contract-eng-${c.id}`} />
                    </div>
                    <div>
                      <label className="block text-[10px] font-semibold uppercase tracking-wider text-zinc-500 mb-0.5">Notes</label>
                      <input type="text" value={f.notes || ''} onChange={(e) => setF(c.id, 'notes', e.target.value)} placeholder="Confirmed with site POC"
                        className="w-full px-2 py-1.5 text-sm rounded-md border border-zinc-300" data-testid={`mod-contract-notes-${c.id}`} />
                    </div>
                    <button onClick={() => confirm(c)} disabled={busyId === c.id}
                      className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-bold rounded-md text-white disabled:opacity-50"
                      style={{ background: 'var(--color-brand-blue, #0055FF)' }} data-testid={`mod-contract-confirm-${c.id}`}>
                      {busyId === c.id ? <Loader2 size={13} className="animate-spin" /> : <CalendarCheck size={13} />} Confirm service
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function KpiTile({ icon: Icon, label, value, color = 'indigo' }) {
 const colors = {
 indigo: 'border-indigo-200 bg-indigo-50 text-indigo-600',
 sky: 'border-sky-200 bg-sky-50 text-sky-600',
 emerald: 'border-emerald-200 bg-emerald-50 text-emerald-600',
 blue: 'border-blue-200 bg-blue-50 text-blue-600',
 }[color];
 return (
 <div className={`rounded-xl border p-4 ${colors}`}>
 <div className="flex items-center gap-2 mb-1">
 <Icon size={13} />
 <span className="text-[10px] uppercase tracking-wider font-bold opacity-75">{label}</span>
 </div>
 <div className="text-2xl font-extrabold tracking-tight text-zinc-800">{value}</div>
 </div>
 );
}


function DrillMetric({ icon: Icon, label, value, subtitle }) {
 return (
 <div className="rounded-lg border border-zinc-200 p-3 flex items-start gap-3">
 <div className="w-9 h-9 rounded-lg bg-violet-50 text-violet-600 grid place-items-center shrink-0">
 <Icon size={15} />
 </div>
 <div className="flex-1 min-w-0">
 <div className="text-[10px] font-extrabold uppercase tracking-wider text-zinc-500">{label}</div>
 <div className="text-xl font-extrabold text-zinc-900 tracking-tight">{value ?? '—'}</div>
 {subtitle && <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{subtitle}</div>}
 </div>
 </div>
 );
}


function formatDuration(seconds) {
 if (seconds === null || seconds === undefined) return '—';
 if (seconds < 60) return `${seconds}s`;
 if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
 const h = Math.floor(seconds / 3600);
 const m = Math.round((seconds % 3600) / 60);
 return `${h}h ${m}m`;
}


function AserSettingsPanel({ API, headers }) {
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try { const { data } = await axios.get(`${API}/master-admin/aser/settings`, { headers }); setS(data); }
      catch { /* ignore */ } finally { setLoading(false); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await axios.put(`${API}/master-admin/aser/settings`, s, { headers });
      setS(data.settings); notify.success('ASER settings saved');
    } catch { notify.error('Save failed'); } finally { setSaving(false); }
  };

  const set = (k, v) => setS({ ...s, [k]: v });
  const setN = (grp, k, v) => setS({ ...s, notifications: { ...s.notifications, [grp]: { ...s.notifications[grp], [k]: v } } });

  if (loading) return <div className="rounded-xl border border-zinc-200 bg-white p-4 text-sm text-zinc-500">Loading ASER settings…</div>;
  if (!s) return null;

  const Toggle = ({ label, val, onChange, testid }) => (
    <label className="flex items-center justify-between gap-3 py-1.5 cursor-pointer">
      <span className="text-sm text-zinc-700">{label}</span>
      <input type="checkbox" checked={!!val} onChange={(e) => onChange(e.target.checked)} className="accent-red-600 w-4 h-4" data-testid={testid} />
    </label>
  );

  return (
    <div className="rounded-xl border border-red-200 bg-white overflow-hidden" data-testid="aser-settings-panel">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-red-50 hover:bg-red-100 transition-colors" data-testid="aser-settings-toggle">
        <div className="flex items-center gap-2">
          <ShieldAlert size={16} className="text-red-600" />
          <span className="font-extrabold text-sm text-zinc-800">ASER — Activity Safety Events Register · Settings</span>
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${s.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-200 text-zinc-500'}`}>{s.enabled ? 'ENABLED' : 'DISABLED'}</span>
        </div>
        <ChevronRight size={16} className={`text-zinc-400 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>

      {open && (
        <div className="p-4 grid md:grid-cols-2 gap-6">
          <div>
            <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-zinc-500 mb-2">General</h4>
            <Toggle label="ASER enabled for MOD" val={s.enabled} onChange={(v) => set('enabled', v)} testid="aser-set-enabled" />
            <Toggle label="Require equipment selection" val={s.require_equipment_selection} onChange={(v) => set('require_equipment_selection', v)} testid="aser-set-require-equip" />
            <Toggle label="Enable CAPEX linking" val={s.enable_capex_linking} onChange={(v) => set('enable_capex_linking', v)} testid="aser-set-capex" />
            <Toggle label="Enable fault linking" val={s.enable_fault_linking} onChange={(v) => set('enable_fault_linking', v)} testid="aser-set-fault" />
            <Toggle label="Require manager review for high/critical" val={s.require_manager_review_high_critical} onChange={(v) => set('require_manager_review_high_critical', v)} testid="aser-set-review" />
            <Toggle label="Patient-identifiable info warning" val={s.patient_pii_warning} onChange={(v) => set('patient_pii_warning', v)} testid="aser-set-pii" />
            <Toggle label="AI summaries" val={s.ai_summaries} onChange={(v) => set('ai_summaries', v)} testid="aser-set-ai" />
            <label className="flex items-center justify-between gap-3 py-1.5">
              <span className="text-sm text-zinc-700">Repeated-issue threshold (ASER / 90 days)</span>
              <input type="number" min="1" max="20" value={s.repeated_issue_threshold} onChange={(e) => set('repeated_issue_threshold', parseInt(e.target.value || '2', 10))} className="w-16 rounded border border-zinc-300 px-2 py-1 text-sm text-right" data-testid="aser-set-threshold" />
            </label>
          </div>

          <div>
            <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-zinc-500 mb-2">Notifications — Site manager</h4>
            <Toggle label="On new entry" val={s.notifications.site_manager.on_new} onChange={(v) => setN('site_manager', 'on_new', v)} testid="aser-set-sm-new" />
            <Toggle label="On high/critical risk" val={s.notifications.site_manager.on_high_critical} onChange={(v) => setN('site_manager', 'on_high_critical', v)} testid="aser-set-sm-high" />
            <Toggle label="On removed from use" val={s.notifications.site_manager.on_removed} onChange={(v) => setN('site_manager', 'on_removed', v)} testid="aser-set-sm-removed" />
            <Toggle label="On repeated issue" val={s.notifications.site_manager.on_repeated} onChange={(v) => setN('site_manager', 'on_repeated', v)} testid="aser-set-sm-repeated" />

            <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-zinc-500 mt-4 mb-2">Notifications — Service desk</h4>
            <Toggle label="Enable service desk alerts" val={s.notifications.service_desk.enabled} onChange={(v) => setN('service_desk', 'enabled', v)} testid="aser-set-sd-enabled" />
            <input type="email" placeholder="service-desk@example.mod.uk" value={s.notifications.service_desk.email || ''} onChange={(e) => setN('service_desk', 'email', e.target.value)} className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm mb-1" data-testid="aser-set-sd-email" />

            <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-zinc-500 mt-4 mb-2">Notifications — Account manager</h4>
            <Toggle label="Enable account manager alerts" val={s.notifications.account_manager.enabled} onChange={(v) => setN('account_manager', 'enabled', v)} testid="aser-set-am-enabled" />
            <input type="email" placeholder="account-manager@pulsefitness.com" value={s.notifications.account_manager.email || ''} onChange={(e) => setN('account_manager', 'email', e.target.value)} className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm" data-testid="aser-set-am-email" />
          </div>

          <div className="md:col-span-2 flex justify-end border-t border-zinc-100 pt-3">
            <button onClick={save} disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-bold hover:bg-red-700 disabled:opacity-60" data-testid="aser-settings-save">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save ASER settings
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
