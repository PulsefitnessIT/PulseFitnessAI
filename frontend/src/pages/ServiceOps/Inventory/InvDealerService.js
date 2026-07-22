import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Plus, Headphones, Building2, Wrench, AlertTriangle, ArrowUpRight, Route } from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, fmtDate, statusLabel } from './api';
import { Card, StatCard, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';

// ───────────── Create desk wizard (condensed single card, dealer picker) ─────────────
function CreateDeskModal({ onClose, onCreated }) {
  const [dealer, setDealer] = useState(null);
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [form, setForm] = useState({ country: 'GB', territories: '', languages: 'en', sla: '48h', warranty_routing: 'dealer', portal_fault_logging: true, branding: 'pulse' });
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (q.length < 2) { setResults([]); return; } const t = setTimeout(() => invApi.dealers(q).then((d) => setResults(d.dealers || [])).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);

  const submit = async () => {
    if (!dealer) { notify.error('Select a dealer'); return; }
    setBusy(true);
    try {
      const d = await invApi.createDesk({
        dealer_id: dealer.id, dealer_name: dealer.name, country: form.country,
        territories: form.territories.split(',').map((s) => s.trim()).filter(Boolean),
        coverage: { languages: form.languages.split(',').map((s) => s.trim()) },
        service_rules: { sla: form.sla, warranty_routing: form.warranty_routing },
        customer_portal: { fault_logging: form.portal_fault_logging, language: form.languages.split(',')[0] },
        branding: { mode: form.branding },
      });
      notify.success(`Service desk ${d.reference} created`);
      onCreated(d.id);
    } catch (e) { notify.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Failed'); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-desk-modal">
      <div className="my-8 w-full max-w-xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">New Dealer Service Desk</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        <div className="space-y-4 px-5 py-4">
          <Field label="Dealer (existing CRM company)" required>
            {dealer ? (
              <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm"><Building2 size={15} className="text-emerald-600" /><span className="font-semibold">{dealer.name}</span><button className="ml-auto text-xs underline" data-testid="inv-desk-dealer-change" onClick={() => setDealer(null)}>change</button></div>
            ) : (
              <>
                <input className={inputCls} placeholder="Search dealer…" value={q} data-testid="inv-desk-dealer-search" onChange={(e) => setQ(e.target.value)} />
                {results.length > 0 && <div className="mt-1 rounded-lg border border-slate-200 bg-white shadow-sm">{results.map((r) => <button key={r.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" data-testid={`inv-desk-dealer-opt-${r.id}`} onClick={() => { setDealer(r); setResults([]); }}>{r.name} <span className="text-slate-400">· {r.country || '—'}</span></button>)}</div>}
              </>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Country"><select className={inputCls} value={form.country} data-testid="inv-desk-country" onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}>{['GB', 'FR', 'US'].map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
            <Field label="Languages (csv)"><input className={inputCls} value={form.languages} data-testid="inv-desk-languages" onChange={(e) => setForm((f) => ({ ...f, languages: e.target.value }))} /></Field>
            <Field label="Territories (csv)"><input className={inputCls} value={form.territories} data-testid="inv-desk-territories" onChange={(e) => setForm((f) => ({ ...f, territories: e.target.value }))} /></Field>
            <Field label="SLA"><input className={inputCls} value={form.sla} data-testid="inv-desk-sla" onChange={(e) => setForm((f) => ({ ...f, sla: e.target.value }))} /></Field>
            <Field label="Warranty routing"><select className={inputCls} value={form.warranty_routing} data-testid="inv-desk-warranty-routing" onChange={(e) => setForm((f) => ({ ...f, warranty_routing: e.target.value }))}>{['dealer', 'pulse', 'dealer_then_pulse'].map((c) => <option key={c} value={c}>{statusLabel(c)}</option>)}</select></Field>
            <Field label="Branding"><select className={inputCls} value={form.branding} data-testid="inv-desk-branding" onChange={(e) => setForm((f) => ({ ...f, branding: e.target.value }))}>{['pulse', 'co_branded'].map((c) => <option key={c} value={c}>{statusLabel(c)}</option>)}</select></Field>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.portal_fault_logging} data-testid="inv-desk-portal-fault" onChange={(e) => setForm((f) => ({ ...f, portal_fault_logging: e.target.checked }))} /> Allow customer fault logging in portal</label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3"><Btn variant="secondary" onClick={onClose}>Cancel</Btn><Btn onClick={submit} disabled={busy || !dealer} data-testid="inv-desk-submit"><Plus size={15} /> Create desk</Btn></div>
      </div>
    </div>
  );
}

// ───────────── Desk detail (overview + log fault + escalate) ─────────────
function LogFaultModal({ desk, assets, onClose, onDone }) {
  const [serial, setSerial] = useState(assets[0]?.serial_number || '');
  const [title, setTitle] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [routing, setRouting] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (serial) invApi.routeFault(serial).then(setRouting).catch(() => setRouting(null)); }, [serial]);
  const submit = async () => {
    if (!serial || !title.trim()) { notify.error('Pick a machine and enter a fault title'); return; }
    setBusy(true);
    try { const r = await invApi.logFault({ serial_number: serial, title, severity }); notify.success(`Fault logged — routed to ${r.routing.responsible === 'dealer' ? 'dealer desk' : 'Pulse'}`); onDone(); }
    catch (e) { notify.error('Failed'); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-fault-modal">
      <div className="my-8 w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3"><h3 className="font-bold text-slate-900">Log fault</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        <div className="space-y-3 px-5 py-4">
          <Field label="Machine (serial)"><select className={inputCls} value={serial} data-testid="inv-fault-serial" onChange={(e) => setSerial(e.target.value)}>{assets.map((a) => <option key={a.id} value={a.serial_number}>{a.serial_number} — {a.model}</option>)}</select></Field>
          <Field label="Fault title" required><input className={inputCls} value={title} data-testid="inv-fault-title" onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Severity"><select className={inputCls} value={severity} data-testid="inv-fault-severity" onChange={(e) => setSeverity(e.target.value)}>{['low', 'medium', 'high', 'critical'].map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}</select></Field>
          {routing && <div className="flex items-start gap-2 rounded-lg bg-blue-50 p-3 text-xs text-blue-800" data-testid="inv-fault-routing"><Route size={14} className="mt-0.5" /><span><strong>{routing.responsible === 'dealer' ? 'Dealer service desk' : 'Pulse Service Desk'}</strong> — {routing.reason}</span></div>}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3"><Btn variant="secondary" onClick={onClose}>Cancel</Btn><Btn onClick={submit} disabled={busy} data-testid="inv-fault-submit"><Wrench size={15} /> Log fault</Btn></div>
      </div>
    </div>
  );
}

function DeskDetail({ deskId, onBack }) {
  const [data, setData] = useState(null);
  const [logging, setLogging] = useState(false);
  const load = useCallback(() => invApi.desk(deskId).then(setData).catch(() => notify.error('Load failed')), [deskId]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <Spinner />;
  const { desk, customers, assets, faults, stats } = data;
  const activeAssets = assets.filter((a) => a.status === 'active');
  const escalate = async (id) => { try { await invApi.escalateFault(id); notify.success('Escalated to Pulse'); load(); } catch (e) { notify.error('Failed'); } };
  return (
    <div className="space-y-5" data-testid="inv-desk-detail">
      <div className="flex items-center gap-3">
        <Btn variant="ghost" onClick={onBack} data-testid="inv-desk-back"><ArrowLeft size={16} /> Service desks</Btn>
        <div><h2 className="text-xl font-bold text-slate-900">{desk.dealer_name}</h2><p className="text-sm text-slate-500">{desk.reference} · {desk.country}</p></div>
        <StatusBadge status={desk.status} className="ml-2" />
        {desk.status !== 'active' && <Btn className="ml-auto" onClick={async () => { await invApi.activateDesk(deskId); load(); }} data-testid="inv-desk-activate">Activate desk</Btn>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Customers" value={stats.customers} testId="inv-desk-stat-customers" />
        <StatCard label="Assets" value={stats.assets} testId="inv-desk-stat-assets" />
        <StatCard label="Active assets" value={stats.active_assets} tone="green" />
        <StatCard label="Open faults" value={stats.open_faults} tone={stats.open_faults ? 'amber' : 'green'} testId="inv-desk-stat-faults" />
      </div>
      <div className="flex justify-end"><Btn onClick={() => setLogging(true)} disabled={activeAssets.length === 0} data-testid="inv-desk-log-fault"><Wrench size={15} /> Log fault</Btn></div>
      <Card testId="inv-desk-faults">
        <div className="border-b border-slate-200 px-4 py-3"><h3 className="text-sm font-bold text-slate-900">Faults (shared Service Desk records)</h3></div>
        {faults.length === 0 ? <p className="px-4 py-6 text-center text-sm text-slate-400">No faults logged.</p> : (
          <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase text-slate-400"><th className="px-4 py-2">Serial</th><th>Title</th><th>Severity</th><th>Responsible</th><th></th></tr></thead>
            <tbody>{faults.map((f) => (
              <tr key={f.id} className="border-t border-slate-100" data-testid={`inv-desk-fault-${f.serial_number}`}>
                <td className="px-4 py-2.5 font-mono text-xs">{f.serial_number}</td><td>{f.title}</td>
                <td><StatusBadge status={f.severity} /></td>
                <td>{f.responsible === 'dealer' ? 'Dealer' : 'Pulse'}{f.escalated ? ' (escalated)' : ''}</td>
                <td className="pr-4 text-right">{f.responsible === 'dealer' && !f.escalated && <Btn variant="secondary" onClick={() => escalate(f.id)} data-testid={`inv-desk-escalate-${f.serial_number}`}><ArrowUpRight size={13} /> Escalate</Btn>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Card>
      <Card className="p-4" testId="inv-desk-customers"><h3 className="mb-2 text-sm font-bold text-slate-900">Dealer customers</h3>{customers.length === 0 ? <p className="text-sm text-slate-400">No customers yet.</p> : customers.map((c) => <div key={c.id} className="flex items-center gap-2 border-b border-slate-100 py-1.5 text-sm last:border-0"><Building2 size={13} className="text-slate-400" />{c.name}<StatusBadge status={c.status || 'active'} className="ml-auto" /></div>)}</Card>
      {logging && <LogFaultModal desk={desk} assets={activeAssets} onClose={() => setLogging(false)} onDone={() => { setLogging(false); load(); }} />}
    </div>
  );
}

// ───────────── Dealer service desks list ─────────────
export function DealerServiceDesks() {
  const [rows, setRows] = useState(null);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState(null);
  const load = useCallback(() => invApi.desks().then((d) => setRows(d.desks || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  if (selected) return <DeskDetail deskId={selected} onBack={() => { setSelected(null); load(); }} />;
  return (
    <div className="space-y-4" data-testid="inv-service-desks">
      <div className="flex items-center gap-3"><h2 className="text-xl font-bold text-slate-900">Dealer Service Desks</h2><Btn className="ml-auto" onClick={() => setCreating(true)} data-testid="inv-new-desk-btn"><Plus size={16} /> New service desk</Btn></div>
      <p className="text-sm text-slate-500">Scoped service-desk workspaces over the shared platform — faults, customers, assets and engineers stay single shared records.</p>
      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-10 text-center" testId="inv-desks-empty"><Headphones size={34} className="mx-auto mb-2 text-slate-300" /><p className="text-slate-500">No dealer service desks yet.</p><Btn className="mx-auto mt-3" onClick={() => setCreating(true)}><Plus size={16} /> Create one</Btn></Card> : (
        <Card testId="inv-desks-table"><table className="w-full text-sm"><thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Reference</th><th>Dealer</th><th>Country</th><th>Status</th></tr></thead>
          <tbody>{rows.map((d) => (
            <tr key={d.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" data-testid={`inv-desk-row-${d.reference}`} onClick={() => setSelected(d.id)}>
              <td className="px-4 py-3 font-semibold text-[#0B3D91]">{d.reference}</td><td>{d.dealer_name}</td><td>{d.country}</td><td><StatusBadge status={d.status} /></td>
            </tr>
          ))}</tbody>
        </table></Card>
      )}
      {creating && <CreateDeskModal onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setSelected(id); }} />}
    </div>
  );
}
