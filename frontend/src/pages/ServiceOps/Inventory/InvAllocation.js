import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { UserPlus, MapPin, Wrench, CheckCircle2, ScanLine, ShieldCheck, Building2, CalendarDays, CalendarPlus, ChevronLeft, ChevronRight, Clock, List, ClipboardList, FileText, Layers, AlertTriangle, Download, HardHat, RefreshCw, ExternalLink } from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, fmtDate, statusLabel } from './api';
import { Card, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';

// ───────────── Customer picker with duplicate prevention ─────────────
function CustomerPicker({ value, onPick }) {
  const [q, setQ] = useState('');
  const [matches, setMatches] = useState([]);
  const [dupes, setDupes] = useState(null);

  useEffect(() => { if (q.length < 2) { setMatches([]); return; } const t = setTimeout(() => invApi.custSearch(q).then((d) => setMatches(d.matches || [])).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);

  const createNew = async (force = false) => {
    try {
      const r = await invApi.createCustomer({ name: q.trim(), force });
      if (!r.created && r.duplicates) { setDupes(r.duplicates); return; }
      notify.success('Customer created (pending validation)');
      setDupes(null); onPick(r.company);
    } catch (e) { notify.error('Failed'); }
  };

  if (value) return (
    <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm" data-testid="inv-alloc-customer-selected">
      <Building2 size={15} className="text-emerald-600" /> <span className="font-semibold">{value.name}</span>
      <button className="ml-auto text-xs text-slate-500 underline" data-testid="inv-alloc-customer-change" onClick={() => onPick(null)}>change</button>
    </div>
  );

  return (
    <div>
      <input className={inputCls} placeholder="Search existing customer or type a new name…" value={q} data-testid="inv-alloc-customer-search" onChange={(e) => { setQ(e.target.value); setDupes(null); }} />
      {matches.length > 0 && (
        <div className="mt-1 rounded-lg border border-slate-200 bg-white shadow-sm">
          {matches.map((m) => <button key={m.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" data-testid={`inv-alloc-cust-opt-${m.id}`} onClick={() => onPick(m)}>{m.name} <span className="text-slate-400">· {m.country || '—'}</span></button>)}
        </div>
      )}
      {q.length >= 2 && (
        <div className="mt-2">
          {dupes ? (
            <div className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800" data-testid="inv-alloc-dupes">
              Possible existing customer(s): {dupes.map((d) => d.name).join(', ')}. Use the match above, or
              <button className="ml-1 font-semibold underline" data-testid="inv-alloc-create-force" onClick={() => createNew(true)}>create anyway</button>.
            </div>
          ) : (
            <Btn variant="secondary" onClick={() => createNew(false)} data-testid="inv-alloc-create-customer"><UserPlus size={14} /> Create "{q.trim()}"</Btn>
          )}
        </div>
      )}
    </div>
  );
}

// ───────────── Install modal ─────────────
function InstallModal({ alloc, onClose, onDone }) {
  const [form, setForm] = useState({ engineer_name: '', software_version: '', condition: 'Good', customer_acceptance: false, checklist: {} });
  const [busy, setBusy] = useState(false);
  const CHECKS = [['positioned', 'Positioned & levelled'], ['power', 'Power / network connected'], ['safety', 'Safety checks'], ['test_run', 'Test run passed'], ['customer_walkthrough', 'Customer walkthrough']];
  const submit = async () => {
    setBusy(true);
    try { const r = await invApi.install(alloc.id, form); notify.success(`Asset active — warranty to ${r.warranty_end?.slice(0, 10)}`); onDone(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-install-modal">
      <div className="my-8 w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">Install checks — {alloc.serial_number}</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        <div className="space-y-3 px-5 py-4">
          <p className="text-xs text-slate-400">Completed via the Engineer App workflow. Activates the customer asset &amp; starts warranty.</p>
          <Field label="Engineer" required><input className={inputCls} value={form.engineer_name} data-testid="inv-install-engineer" onChange={(e) => setForm((f) => ({ ...f, engineer_name: e.target.value }))} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Software / console version"><input className={inputCls} value={form.software_version} data-testid="inv-install-software" onChange={(e) => setForm((f) => ({ ...f, software_version: e.target.value }))} /></Field>
            <Field label="Condition"><input className={inputCls} value={form.condition} data-testid="inv-install-condition" onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))} /></Field>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-600">Install checks</p>
            {CHECKS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 py-1 text-sm"><input type="checkbox" checked={!!form.checklist[k]} data-testid={`inv-install-check-${k}`} onChange={(e) => setForm((f) => ({ ...f, checklist: { ...f.checklist, [k]: e.target.checked } }))} /> {label}</label>
            ))}
          </div>
          <label className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-800"><input type="checkbox" checked={form.customer_acceptance} data-testid="inv-install-acceptance" onChange={(e) => setForm((f) => ({ ...f, customer_acceptance: e.target.checked }))} /> Customer acceptance obtained</label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn onClick={submit} disabled={busy || !form.engineer_name.trim() || !form.customer_acceptance} data-testid="inv-install-submit"><Wrench size={15} /> {busy ? 'Saving…' : 'Complete install checks'}</Btn>
        </div>
      </div>
    </div>
  );
}

// ───────────── Customer Allocations ─────────────
export function CustomerAllocations() {
  const [available, setAvailable] = useState(null);
  const [allocations, setAllocations] = useState([]);
  const [sel, setSel] = useState({});
  const [customer, setCustomer] = useState(null);
  const [site, setSite] = useState('');
  const [installDate, setInstallDate] = useState('');
  const [service, setService] = useState('dealer');
  const [installing, setInstalling] = useState(null);
  const [portal, setPortal] = useState(null);

  const load = useCallback(() => {
    invApi.allocAvailable().then((d) => setAvailable(d.available || [])).catch(() => setAvailable([]));
    invApi.allocations().then((d) => setAllocations(d.allocations || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const selectedUnits = Object.keys(sel).filter((k) => sel[k]);
  const allocate = async () => {
    if (!customer || selectedUnits.length === 0) { notify.error('Pick a customer and at least one machine'); return; }
    try {
      const r = await invApi.allocate({ unit_ids: selectedUnits, customer_company_id: customer.id, customer_site: site, planned_install_date: installDate, service_responsibility: service });
      notify.success(`${r.allocated} machine(s) allocated to ${r.customer}`);
      setSel({}); setCustomer(null); setSite(''); load();
      invApi.customerPortal(customer.id).then(setPortal).catch(() => {});
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); }
  };

  return (
    <div className="space-y-5" data-testid="inv-allocations">
      <h2 className="text-xl font-bold text-slate-900">Customer Allocations</h2>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4" testId="inv-alloc-available">
          <h3 className="mb-2 text-sm font-bold text-slate-900">Dealer stock available to allocate</h3>
          {available === null ? <Spinner /> : available.length === 0 ? <p className="text-sm text-slate-400">No dealer-held stock available.</p> : available.map((a) => (
            <label key={a.unit_id} className="flex items-center gap-3 border-b border-slate-100 py-2 text-sm last:border-0" data-testid={`inv-alloc-stock-${a.serial_number}`}>
              <input type="checkbox" checked={!!sel[a.unit_id]} data-testid={`inv-alloc-pick-${a.serial_number}`} onChange={(e) => setSel((s) => ({ ...s, [a.unit_id]: e.target.checked }))} />
              <ScanLine size={13} className="text-[#0B3D91]" /> <span className="font-mono text-xs font-semibold">{a.serial_number}</span>
              <span className="text-slate-500">{a.model || a.product_code}</span>
              <span className="ml-auto text-xs text-slate-400">{a.dealer_name}</span>
            </label>
          ))}
        </Card>

        <Card className="p-4" testId="inv-alloc-form">
          <h3 className="mb-2 text-sm font-bold text-slate-900">Allocate to customer</h3>
          <div className="space-y-3">
            <Field label="Customer (duplicate-checked)"><CustomerPicker value={customer} onPick={setCustomer} /></Field>
            <Field label="Installation site"><input className={inputCls} value={site} data-testid="inv-alloc-site" onChange={(e) => setSite(e.target.value)} placeholder="e.g. Main Club, 5th Ave" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Planned install date"><input type="date" className={inputCls} value={installDate} data-testid="inv-alloc-install-date" onChange={(e) => setInstallDate(e.target.value)} /></Field>
              <Field label="Service responsibility"><select className={inputCls} value={service} data-testid="inv-alloc-service" onChange={(e) => setService(e.target.value)}>{['dealer', 'pulse', 'third_party'].map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></Field>
            </div>
            <Btn onClick={allocate} disabled={!customer || selectedUnits.length === 0} data-testid="inv-alloc-submit"><MapPin size={15} /> Allocate {selectedUnits.length || ''} machine(s)</Btn>
          </div>
        </Card>
      </div>

      {portal && (
        <Card className="p-4" testId="inv-alloc-portal-preview">
          <h3 className="mb-2 text-sm font-bold text-slate-900">Customer Operations Portal — {portal.company?.name}</h3>
          <p className="mb-2 text-[11px] text-slate-400">Machines auto-populated into the customer's portal (single asset register — no duplicate).</p>
          {portal.equipment.map((e) => (
            <div key={e.id} className="flex items-center gap-3 border-b border-slate-100 py-1.5 text-sm last:border-0"><span className="font-mono text-xs">{e.serial_number}</span><span>{e.model}</span><StatusBadge status={e.status} className="ml-auto" /></div>
          ))}
        </Card>
      )}

      <Card testId="inv-alloc-list">
        <div className="border-b border-slate-200 px-4 py-3"><h3 className="text-sm font-bold text-slate-900">Allocations</h3></div>
        {allocations.length === 0 ? <p className="px-4 py-8 text-center text-sm text-slate-400">No allocations yet.</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-400"><th className="px-4 py-2">Ref</th><th>Serial</th><th>Customer</th><th>Site</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {allocations.map((a) => (
                <tr key={a.id} className="border-t border-slate-100" data-testid={`inv-alloc-row-${a.reference}`}>
                  <td className="px-4 py-2.5 font-semibold text-[#0B3D91]">{a.reference}</td>
                  <td className="font-mono text-xs">{a.serial_number}</td>
                  <td>{a.customer_company_name}</td>
                  <td className="text-slate-500">{a.customer_site || '—'}</td>
                  <td><StatusBadge status={a.status} /></td>
                  <td className="pr-4 text-right">{a.status === 'awaiting_installation' ? <Btn variant="secondary" onClick={() => setInstalling(a)} data-testid={`inv-alloc-install-${a.reference}`}><Wrench size={13} /> Install</Btn> : a.status === 'active' ? <span className="text-emerald-600" title="Active asset"><CheckCircle2 size={16} className="inline" /></span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {installing && <InstallModal alloc={installing} onClose={() => setInstalling(null)} onDone={() => { setInstalling(null); load(); }} />}
    </div>
  );
}

// ───────────── Schedule (reschedule) modal ─────────────
function ScheduleModal({ alloc, onClose, onDone }) {
  const [date, setDate] = useState(alloc.planned_install_date ? alloc.planned_install_date.slice(0, 10) : '');
  const [win, setWin] = useState(alloc.install_window || 'all_day');
  const [note, setNote] = useState(alloc.logistics_note || '');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!date) return;
    setBusy(true);
    try { await invApi.scheduleInstall(alloc.id, { planned_install_date: date, install_window: win, logistics_note: note }); notify.success('Installation scheduled'); onDone(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-schedule-modal">
      <div className="my-16 w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">Schedule installation — {alloc.serial_number}</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        <div className="space-y-3 px-5 py-4">
          <p className="text-xs text-slate-400">{alloc.customer_company_name}{alloc.customer_site ? ` · ${alloc.customer_site}` : ''}</p>
          <Field label="Planned install date" required><input type="date" className={inputCls} value={date} data-testid="inv-schedule-date" onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Window"><select className={inputCls} value={win} data-testid="inv-schedule-window" onChange={(e) => setWin(e.target.value)}>{[['all_day', 'All day'], ['am', 'Morning (AM)'], ['pm', 'Afternoon (PM)']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
          <Field label="Logistics note"><textarea className={inputCls} rows={2} value={note} data-testid="inv-schedule-note" onChange={(e) => setNote(e.target.value)} placeholder="Access, crew, lift required…" /></Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn onClick={submit} disabled={busy || !date} data-testid="inv-schedule-submit"><CalendarPlus size={15} /> {busy ? 'Saving…' : 'Save schedule'}</Btn>
        </div>
      </div>
    </div>
  );
}

// ───────────── Install pack (collated logistics info) ─────────────
const RISK_COLOR = { Low: 'bg-emerald-50 text-emerald-700 ring-emerald-200', Medium: 'bg-amber-50 text-amber-700 ring-amber-200', High: 'bg-orange-50 text-orange-700 ring-orange-200', Critical: 'bg-red-50 text-red-700 ring-red-200' };
const YN = (v) => (v === true ? 'Yes' : v === false ? 'No' : '—');

function InstallPackModal({ alloc, onClose, onChanged }) {
  const [pack, setPack] = useState(null);
  const [loading, setLoading] = useState(true);
  const [relinking, setRelinking] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const load = useCallback(() => {
    setLoading(true);
    invApi.installPack(alloc.id).then(setPack).catch(() => notify.error('Could not load install pack')).finally(() => setLoading(false));
  }, [alloc.id]);
  useEffect(() => { load(); }, [load]);

  const openAuthed = async (relUrl) => {
    try {
      const r = await axios.get(`${process.env.REACT_APP_BACKEND_URL}${relUrl}`, { responseType: 'blob', headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
      window.open(URL.createObjectURL(r.data), '_blank');
    } catch { notify.error('Could not open file'); }
  };
  const openRelink = () => { setRelinking(true); invApi.surveyCandidates(alloc.id).then((d) => setCandidates(d.candidates || [])).catch(() => setCandidates([])); };
  const doLink = async (surveyId) => {
    try { await invApi.linkSurvey(alloc.id, surveyId); notify.success(surveyId ? 'Survey linked' : 'Survey unlinked'); setRelinking(false); load(); onChanged && onChanged(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); }
  };

  const s = pack?.survey;
  const hs = s?.hs;
  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-install-pack-modal" onClick={onClose}>
      <div className="my-10 w-full max-w-2xl rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div className="flex items-center gap-2"><ClipboardList size={18} className="text-slate-500" /><div><h3 className="font-bold text-slate-900">Install pack</h3><p className="text-xs text-slate-400">{pack?.visit?.customer_company_name}{pack?.visit?.customer_site ? ` · ${pack.visit.customer_site}` : ''}</p></div></div>
          <button onClick={onClose} className="text-slate-400" data-testid="inv-install-pack-close">✕</button>
        </div>
        <div className="max-h-[75vh] space-y-4 overflow-y-auto px-5 py-4">
          {loading && <div className="py-10"><Spinner /></div>}
          {!loading && pack && (<>
            {/* Visit header */}
            <div className="grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-sm sm:grid-cols-4">
              <div><p className="text-[11px] uppercase text-slate-400">Planned</p><p className="font-semibold text-slate-800">{pack.visit.planned_install_date ? fmtDate(pack.visit.planned_install_date) : 'Unscheduled'}</p></div>
              <div><p className="text-[11px] uppercase text-slate-400">Window</p><p className="font-semibold text-slate-800">{statusLabel(pack.visit.install_window) || '—'}</p></div>
              <div><p className="text-[11px] uppercase text-slate-400">Machines</p><p className="font-semibold text-slate-800">{pack.visit.machine_count}</p></div>
              <div><p className="text-[11px] uppercase text-slate-400">Note</p><p className="font-semibold text-slate-800">{pack.visit.logistics_note || '—'}</p></div>
            </div>

            {/* Site survey + H&S */}
            <div className="rounded-xl border border-slate-200">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
                <div className="flex items-center gap-2"><FileText size={15} className="text-slate-500" /><span className="text-sm font-bold text-slate-800">Pre-install site survey</span></div>
                <button onClick={openRelink} className="flex items-center gap-1 text-xs font-semibold text-cyan-700 hover:underline" data-testid="inv-install-pack-relink"><RefreshCw size={12} /> {s ? 'Change' : 'Link survey'}</button>
              </div>
              {!s ? (
                <div className="px-4 py-4 text-sm text-slate-400" data-testid="inv-install-pack-no-survey">No site survey linked. The customer's survey (with the Health &amp; Safety questionnaire) should be completed before the install team arrives.</div>
              ) : (
                <div className="space-y-3 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="font-semibold text-slate-800">{s.reference}</span>
                    <StatusBadge status={s.status} />
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">Readiness: {statusLabel(s.readiness_status)}</span>
                    {s.auto_linked && <span className="rounded bg-cyan-50 px-1.5 py-0.5 text-[11px] font-semibold text-cyan-700">Auto-linked</span>}
                  </div>
                  {/* H&S risks */}
                  <div>
                    <p className="mb-1 flex items-center gap-1 text-xs font-bold uppercase text-slate-500"><AlertTriangle size={12} /> Health &amp; Safety risks</p>
                    {(!hs?.risks || hs.risks.length === 0) ? <p className="text-xs text-slate-400">No risks recorded on the survey.</p> : (
                      <div className="space-y-1.5" data-testid="inv-install-pack-risks">
                        {hs.risks.map((r, i) => (
                          <div key={i} className={`rounded-lg px-2.5 py-1.5 text-xs ring-1 ${RISK_COLOR[r.risk_level] || 'bg-slate-50 text-slate-600 ring-slate-200'}`}>
                            <div className="flex items-center justify-between"><span className="font-semibold">{r.category || 'Risk'}</span><span className="font-bold">{r.risk_level || r.severity || '—'}</span></div>
                            {r.description && <p className="mt-0.5 opacity-90">{r.description}</p>}
                            {r.mitigation && <p className="mt-0.5 opacity-80"><span className="font-semibold">Mitigation:</span> {r.mitigation}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Access + site rules */}
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div className="rounded-lg bg-slate-50 p-2.5 text-xs">
                      <p className="mb-1 font-bold uppercase text-slate-500">Access</p>
                      <p>Risk level: <span className="font-semibold">{hs?.access_risk_level || '—'}</span></p>
                      {hs?.access_risk_notes && <p className="mt-0.5 text-slate-500">{hs.access_risk_notes}</p>}
                    </div>
                    <div className="rounded-lg bg-slate-50 p-2.5 text-xs" data-testid="inv-install-pack-siterules">
                      <p className="mb-1 flex items-center gap-1 font-bold uppercase text-slate-500"><HardHat size={11} /> Site rules</p>
                      <p>Induction: <span className="font-semibold">{YN(hs?.site_rules?.site_induction_required)}</span> · RAMS: <span className="font-semibold">{YN(hs?.site_rules?.rams_required)}</span> · Permit: <span className="font-semibold">{YN(hs?.site_rules?.permit_to_work_required)}</span></p>
                      {hs?.site_rules?.ppe_required && <p className="mt-0.5">PPE: <span className="font-semibold">{hs.site_rules.ppe_required}</span></p>}
                      {hs?.site_rules?.emergency_contact && <p className="mt-0.5">Emergency: <span className="font-semibold">{hs.site_rules.emergency_contact}</span></p>}
                    </div>
                  </div>
                  {/* Attachments */}
                  {pack.survey_attachments.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-bold uppercase text-slate-500">Documents &amp; photos</p>
                      <div className="flex flex-wrap gap-2" data-testid="inv-install-pack-attachments">
                        {pack.survey_attachments.map((att) => (
                          <button key={att.id} onClick={() => openAuthed(att.download_url)} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50" data-testid={`inv-install-pack-att-${att.id}`}>
                            <Download size={12} /> {att.filename || 'file'} <span className="text-slate-400">({statusLabel(att.category)})</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Machines + drawings */}
            <div className="rounded-xl border border-slate-200">
              <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-2.5"><Layers size={15} className="text-slate-500" /><span className="text-sm font-bold text-slate-800">Machines &amp; assembly drawings</span></div>
              <div className="divide-y divide-slate-100" data-testid="inv-install-pack-machines">
                {pack.machines.map((m) => (
                  <div key={m.allocation_id} className="px-4 py-2.5">
                    <div className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-800">{m.model || m.product_code}</span><span className="text-xs text-slate-400">{m.serial_number || m.reference}</span></div>
                    {m.drawings.length > 0 ? (
                      <div className="mt-1.5 flex flex-wrap gap-2">
                        {m.drawings.map((d) => (
                          <button key={d.drawing_id} onClick={() => openAuthed(d.file_url)} className="flex items-center gap-1.5 rounded-lg bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800 hover:bg-cyan-100" data-testid={`inv-install-pack-drawing-${d.drawing_id}`}>
                            <ExternalLink size={12} /> {d.title || 'Drawing'}
                          </button>
                        ))}
                      </div>
                    ) : <p className="mt-1 text-xs text-slate-400">No assembly drawing on file for this model.</p>}
                  </div>
                ))}
              </div>
            </div>
          </>)}
        </div>
        <div className="flex justify-end border-t border-slate-200 px-5 py-3"><Btn variant="secondary" onClick={onClose}>Close</Btn></div>
      </div>

      {/* Relink survey picker */}
      {relinking && (
        <div className="fixed inset-0 z-[210] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-relink-survey-modal" onClick={() => setRelinking(false)}>
          <div className="my-24 w-full max-w-md rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">Link a site survey</h3><p className="text-xs text-slate-400">Surveys for {pack?.visit?.customer_company_name}</p></div>
            <div className="max-h-[50vh] space-y-2 overflow-y-auto px-5 py-4">
              {candidates.length === 0 && <p className="text-sm text-slate-400">No surveys found for this customer.</p>}
              {candidates.map((cnd) => (
                <button key={cnd.id} onClick={() => doLink(cnd.id)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-left hover:bg-slate-50" data-testid={`inv-relink-candidate-${cnd.id}`}>
                  <div><p className="text-sm font-semibold text-slate-800">{cnd.reference}</p><p className="text-xs text-slate-400">{statusLabel(cnd.status)} · {cnd.attachment_count} file(s)</p></div>
                  <StatusBadge status={cnd.status} />
                </button>
              ))}
            </div>
            <div className="flex justify-between border-t border-slate-200 px-5 py-3">
              {s && <Btn variant="secondary" onClick={() => doLink(null)} data-testid="inv-relink-unlink">Unlink current</Btn>}
              <Btn variant="secondary" onClick={() => setRelinking(false)}>Cancel</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────── Install action chooser ─────────────
function InstallActions({ alloc, onClose, onSchedule, onInstall, onPack }) {
  return (
    <div className="fixed inset-0 z-[190] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-install-actions" onClick={onClose}>
      <div className="my-24 w-full max-w-sm rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">{alloc.serial_number}</h3><p className="text-xs text-slate-400">{alloc.customer_company_name}{alloc.customer_site ? ` · ${alloc.customer_site}` : ''}</p></div>
        <div className="px-5 py-4 text-sm space-y-1">
          <div className="flex justify-between"><span className="text-slate-500">Reference</span><span className="font-semibold">{alloc.reference}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Planned</span><span className="font-semibold">{alloc.planned_install_date ? fmtDate(alloc.planned_install_date) : 'Unscheduled'}</span></div>
        </div>
        <div className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Btn variant="secondary" onClick={onPack} data-testid="inv-install-actions-pack"><ClipboardList size={14} /> Install pack</Btn>
          <Btn variant="secondary" onClick={onSchedule} data-testid="inv-install-actions-schedule"><CalendarDays size={14} /> {alloc.planned_install_date ? 'Reschedule' : 'Schedule'}</Btn>
          <Btn onClick={onInstall} data-testid="inv-install-actions-install"><Wrench size={14} /> Install checks</Btn>
        </div>
      </div>
    </div>
  );
}

// ───────────── Installations — logistics calendar ─────────────
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const localKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function Installations() {
  const [rows, setRows] = useState(null);
  const [view, setView] = useState('calendar');
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [acting, setActing] = useState(null);
  const [scheduling, setScheduling] = useState(null);
  const [installing, setInstalling] = useState(null);
  const [packing, setPacking] = useState(null);
  const load = useCallback(() => invApi.allocations('awaiting_installation').then((d) => setRows(d.allocations || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);

  const byDay = {};
  const unscheduled = [];
  (rows || []).forEach((a) => {
    if (a.planned_install_date) { const k = a.planned_install_date.slice(0, 10); (byDay[k] = byDay[k] || []).push(a); }
    else unscheduled.push(a);
  });

  // Build month grid (Mon-first)
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const lead = (first.getDay() + 6) % 7; // days before the 1st (Mon-first)
  const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(cursor.getFullYear(), cursor.getMonth(), d));
  const todayKey = localKey(new Date());
  const monthLabel = cursor.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });

  const doneAll = () => { setActing(null); setScheduling(null); setInstalling(null); setPacking(null); load(); };

  return (
    <div className="space-y-4" data-testid="inv-installations">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Installations</h2>
          <p className="text-sm text-slate-500">Logistics calendar for machines allocated from CRM orders. Schedule installs, then engineers complete <span className="font-semibold text-slate-600">install checks</span> via the Engineer App to activate the asset &amp; warranty.</p>
        </div>
        <div className="ml-auto flex rounded-lg border border-slate-200 bg-white p-0.5" data-testid="inv-install-viewtoggle">
          {[['calendar', 'Calendar', CalendarDays], ['list', 'List', List]].map(([v, l, Ic]) => (
            <button key={v} onClick={() => setView(v)} data-testid={`inv-install-view-${v}`} className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${view === v ? 'inv-active text-white' : 'text-slate-600 hover:bg-slate-50'}`}><Ic size={14} /> {l}</button>
          ))}
        </div>
      </div>

      {rows === null ? <Spinner /> : view === 'list' ? (
        rows.length === 0 ? <Card className="p-10 text-center text-slate-400" testId="inv-install-empty">Nothing awaiting installation.</Card> : (
          <Card testId="inv-install-table">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Ref</th><th>Serial</th><th>Customer</th><th>Site</th><th>Planned</th><th></th></tr></thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} className="border-b border-slate-100" data-testid={`inv-install-row-${a.reference}`}>
                    <td className="px-4 py-3 font-semibold text-[#0B3D91]">{a.reference}</td>
                    <td className="font-mono text-xs">{a.serial_number}</td>
                    <td>{a.customer_company_name}</td><td className="text-slate-500">{a.customer_site || '—'}</td>
                    <td className={a.planned_install_date ? 'text-slate-600' : 'text-amber-600 font-semibold'}>{a.planned_install_date ? fmtDate(a.planned_install_date) : 'Unscheduled'}</td>
                    <td className="pr-4 text-right"><div className="flex justify-end gap-2"><Btn variant="secondary" onClick={() => setPacking(a)} data-testid={`inv-install-pack-${a.reference}`}><ClipboardList size={13} /> Install pack</Btn><Btn variant="secondary" onClick={() => setScheduling(a)} data-testid={`inv-install-schedule-${a.reference}`}><CalendarDays size={13} /> {a.planned_install_date ? 'Reschedule' : 'Schedule'}</Btn><Btn onClick={() => setInstalling(a)} data-testid={`inv-install-open-${a.reference}`}><Wrench size={13} /> Install checks</Btn></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
          <Card className="p-4" testId="inv-install-calendar">
            <div className="mb-3 flex items-center gap-2">
              <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))} className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50" data-testid="inv-cal-prev"><ChevronLeft size={16} /></button>
              <button onClick={() => { const d = new Date(); setCursor(new Date(d.getFullYear(), d.getMonth(), 1)); }} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50" data-testid="inv-cal-today">Today</button>
              <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))} className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50" data-testid="inv-cal-next"><ChevronRight size={16} /></button>
              <span className="ml-2 text-sm font-bold text-slate-900" data-testid="inv-cal-month">{monthLabel}</span>
            </div>
            <div className="grid grid-cols-7 gap-1">
              {WEEKDAYS.map((w) => <div key={w} className="pb-1 text-center text-[10px] font-bold uppercase tracking-wide text-slate-400">{w}</div>)}
              {cells.map((d, i) => {
                if (!d) return <div key={`b${i}`} />;
                const k = localKey(d);
                const items = byDay[k] || [];
                const isToday = k === todayKey;
                return (
                  <div key={k} className={`min-h-[84px] rounded-lg border p-1 ${isToday ? 'border-[#19CDFF] bg-cyan-50/40' : 'border-slate-100'}`} data-testid={`inv-cal-day-${k}`}>
                    <div className={`px-1 text-[11px] font-semibold ${isToday ? 'text-[#0BB0DD]' : 'text-slate-400'}`}>{d.getDate()}</div>
                    <div className="space-y-1">
                      {items.slice(0, 3).map((a) => (
                        <button key={a.id} onClick={() => setActing(a)} title={`${a.customer_company_name} · ${a.serial_number}`} data-testid={`inv-cal-chip-${a.reference}`}
                          className="block w-full truncate rounded bg-cyan-100 px-1.5 py-1 text-left text-[11px] font-medium text-cyan-900 hover:bg-cyan-200">
                          {a.customer_company_name || a.serial_number}
                        </button>
                      ))}
                      {items.length > 3 && <div className="px-1 text-[10px] text-slate-400">+{items.length - 3} more</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card className="p-4" testId="inv-install-unscheduled">
            <h3 className="mb-1 flex items-center gap-1.5 text-sm font-bold text-slate-900"><Clock size={14} className="text-amber-500" /> To schedule</h3>
            <p className="mb-3 text-xs text-slate-400">Allocated from CRM orders, awaiting an install date.</p>
            {unscheduled.length === 0 ? <p className="py-6 text-center text-xs text-slate-400">All installs are scheduled.</p> : (
              <div className="space-y-2">
                {unscheduled.map((a) => (
                  <div key={a.id} className="rounded-lg border border-slate-200 p-2.5" data-testid={`inv-unscheduled-${a.reference}`}>
                    <p className="text-sm font-semibold text-slate-800 truncate">{a.customer_company_name}</p>
                    <p className="text-[11px] text-slate-400 truncate">{a.serial_number}{a.customer_site ? ` · ${a.customer_site}` : ''}</p>
                    <Btn variant="secondary" className="mt-2 w-full" onClick={() => setScheduling(a)} data-testid={`inv-unscheduled-schedule-${a.reference}`}><CalendarPlus size={13} /> Schedule</Btn>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {acting && <InstallActions alloc={acting} onClose={() => setActing(null)} onSchedule={() => { setScheduling(acting); setActing(null); }} onInstall={() => { setInstalling(acting); setActing(null); }} onPack={() => { setPacking(acting); setActing(null); }} />}
      {scheduling && <ScheduleModal alloc={scheduling} onClose={() => setScheduling(null)} onDone={doneAll} />}
      {installing && <InstallModal alloc={installing} onClose={() => setInstalling(null)} onDone={doneAll} />}
      {packing && <InstallPackModal alloc={packing} onClose={() => setPacking(null)} onChanged={load} />}
    </div>
  );
}
