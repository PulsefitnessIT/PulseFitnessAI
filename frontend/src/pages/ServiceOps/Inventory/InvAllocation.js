import { useCallback, useEffect, useState } from 'react';
import { UserPlus, MapPin, Wrench, CheckCircle2, ScanLine, ShieldCheck, Building2 } from 'lucide-react';
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
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">Install & commission — {alloc.serial_number}</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        <div className="space-y-3 px-5 py-4">
          <p className="text-xs text-slate-400">Via the Engineer App workflow. Activates the customer asset & starts warranty.</p>
          <Field label="Engineer" required><input className={inputCls} value={form.engineer_name} data-testid="inv-install-engineer" onChange={(e) => setForm((f) => ({ ...f, engineer_name: e.target.value }))} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Software / console version"><input className={inputCls} value={form.software_version} data-testid="inv-install-software" onChange={(e) => setForm((f) => ({ ...f, software_version: e.target.value }))} /></Field>
            <Field label="Condition"><input className={inputCls} value={form.condition} data-testid="inv-install-condition" onChange={(e) => setForm((f) => ({ ...f, condition: e.target.value }))} /></Field>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="mb-2 text-xs font-semibold text-slate-600">Commissioning checklist</p>
            {CHECKS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 py-1 text-sm"><input type="checkbox" checked={!!form.checklist[k]} data-testid={`inv-install-check-${k}`} onChange={(e) => setForm((f) => ({ ...f, checklist: { ...f.checklist, [k]: e.target.checked } }))} /> {label}</label>
            ))}
          </div>
          <label className="flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm font-semibold text-blue-800"><input type="checkbox" checked={form.customer_acceptance} data-testid="inv-install-acceptance" onChange={(e) => setForm((f) => ({ ...f, customer_acceptance: e.target.checked }))} /> Customer acceptance obtained</label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn onClick={submit} disabled={busy || !form.engineer_name.trim() || !form.customer_acceptance} data-testid="inv-install-submit"><Wrench size={15} /> {busy ? 'Commissioning…' : 'Commission & activate'}</Btn>
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

// ───────────── Installations queue ─────────────
export function Installations() {
  const [rows, setRows] = useState(null);
  const [installing, setInstalling] = useState(null);
  const load = useCallback(() => invApi.allocations('awaiting_installation').then((d) => setRows(d.allocations || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  return (
    <div className="space-y-4" data-testid="inv-installations">
      <h2 className="text-xl font-bold text-slate-900">Installations & Commissioning</h2>
      <p className="text-sm text-slate-500">Machines awaiting installation. Engineers commission via the Engineer App — activating the asset and warranty.</p>
      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-10 text-center text-slate-400" testId="inv-install-empty">Nothing awaiting installation.</Card> : (
        <Card testId="inv-install-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Ref</th><th>Serial</th><th>Customer</th><th>Site</th><th>Planned</th><th></th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className="border-b border-slate-100" data-testid={`inv-install-row-${a.reference}`}>
                  <td className="px-4 py-3 font-semibold text-[#0B3D91]">{a.reference}</td>
                  <td className="font-mono text-xs">{a.serial_number}</td>
                  <td>{a.customer_company_name}</td><td className="text-slate-500">{a.customer_site || '—'}</td>
                  <td className="text-slate-400">{fmtDate(a.planned_install_date)}</td>
                  <td className="pr-4 text-right"><Btn variant="secondary" onClick={() => setInstalling(a)} data-testid={`inv-install-open-${a.reference}`}><Wrench size={13} /> Install</Btn></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {installing && <InstallModal alloc={installing} onClose={() => setInstalling(null)} onDone={() => { setInstalling(null); load(); }} />}
    </div>
  );
}
