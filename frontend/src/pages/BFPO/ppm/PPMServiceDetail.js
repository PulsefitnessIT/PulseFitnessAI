import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Badge, Spinner, Field, inputCls } from '../ui';
import SignOffFields, { signoffBody } from '../engineer/SignOffFields';
import { ChevronLeft, CheckCircle2, XCircle, MinusCircle, Wrench, AlertTriangle, FileText, Loader2, ClipboardCheck } from 'lucide-react';

const STATUS_CHIP = {
  pending: { label: 'To check', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  passed: { label: 'Passed', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  failed: { label: 'Fault raised', cls: 'bg-red-50 text-red-700 border-red-200' },
};

export default function PPMServiceDetail({ serviceId, onBack }) {
  const [svc, setSvc] = useState(null);
  const [active, setActive] = useState(null); // inspection being filled
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const [signoff, setSignoff] = useState({});

  const load = useCallback(async () => {
    const r = await bfpo.get(`/ppm/services/${serviceId}`);
    setSvc(r.data);
  }, [serviceId]);
  useEffect(() => { load(); }, [load]);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 2600); };
  if (!svc) return <Spinner />;
  const p = svc.progress || {};
  const completed = svc.status === 'completed';

  const complete = async () => {
    const so = signoffBody(signoff);
    if (so.error) { flash(so.error); return; }
    setBusy(true);
    try { const r = await bfpo.post(`/ppm/services/${serviceId}/complete`, { signoff: so.body }); await load(); flash(r.data.emailed_to ? `Certificate issued & emailed to ${r.data.emailed_to}` : 'Service certificate issued'); }
    catch (e) { flash(e?.response?.data?.detail || 'Could not complete'); }
    finally { setBusy(false); }
  };

  return (
    <div className="pb-28 max-w-2xl mx-auto lg:max-w-4xl" data-testid="ppm-service-detail">
      <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
        <button onClick={onBack} data-testid="ppm-back" className="p-1 -ml-1"><ChevronLeft className="w-6 h-6 text-slate-600" /></button>
        <div className="min-w-0 flex-1">
          <p className="font-bold text-slate-900 truncate">{svc.reference} · {svc.site_name}</p>
          <p className="text-xs text-slate-500">{svc.territory_name} · {svc.country}</p>
        </div>
        <Badge className={completed ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-cyan-50 text-cyan-700 border-cyan-200'}>{completed ? 'Completed' : (svc.status === 'due' ? 'Due' : 'In progress')}</Badge>
      </div>

      <div className="p-4 space-y-4">
        <Card className="p-4 flex items-center gap-4">
          <ClipboardCheck className="w-8 h-8 text-cyan-600" />
          <div className="flex-1">
            <p className="font-semibold text-slate-900" data-testid="ppm-progress">{p.done} of {p.total} checked</p>
            <div className="h-2 bg-slate-100 rounded-full mt-1.5 overflow-hidden">
              <div className="h-full bg-cyan-500" style={{ width: `${p.total ? (p.done / p.total) * 100 : 0}%` }} />
            </div>
            {p.failed > 0 && <p className="text-xs text-red-600 mt-1">{p.failed} fault(s) raised</p>}
          </div>
          {completed && (
            <a href={`${process.env.REACT_APP_BACKEND_URL}/api/bfpo/ppm/services/${serviceId}/certificate.pdf`} target="_blank" rel="noreferrer"
              className="text-cyan-600 font-semibold text-sm flex items-center gap-1" data-testid="ppm-cert-link"><FileText className="w-4 h-4" /> Certificate</a>
          )}
        </Card>

        <div className="space-y-2">
          {(svc.inspections || []).map((i) => (
            <button key={i.id} disabled={completed} onClick={() => setActive(i)} className="w-full text-left disabled:opacity-70" data-testid={`ppm-asset-${i.id}`}>
              <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                <Wrench className="w-5 h-5 text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{i.equipment_name}</p>
                  <p className="text-sm text-slate-500 truncate">{i.serial} · {i.results?.length || 0} checks</p>
                </div>
                <Badge className={(STATUS_CHIP[i.status] || STATUS_CHIP.pending).cls}>{(STATUS_CHIP[i.status] || STATUS_CHIP.pending).label}</Badge>
              </Card>
            </button>
          ))}
        </div>
      </div>

      {!completed && p.remaining === 0 && (
        <div className="px-4 pb-40"><Card className="p-4"><SignOffFields value={signoff} onChange={setSignoff} testid="ppm-signoff" /></Card></div>
      )}

      {active && <ChecklistPanel inspection={active} onClose={() => setActive(null)}
        onSaved={() => { setActive(null); load(); flash('Inspection saved'); }} onFlash={flash} />}

      {!completed && (
        <div className="fixed bottom-16 left-0 right-0 px-4 pb-3 pt-2 bg-gradient-to-t from-white via-white to-transparent max-w-2xl mx-auto">
          <Btn full variant="primary" disabled={busy || p.remaining > 0} onClick={complete} data-testid="ppm-complete" className="shadow-lg py-4 text-base">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle2 className="w-5 h-5" />}
            {p.remaining > 0 ? `${p.remaining} asset(s) left to check` : 'Complete & issue certificate'}
          </Btn>
        </div>
      )}
      {toast && <div className="fixed bottom-32 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2 rounded-full shadow-lg z-20" data-testid="ppm-toast">{toast}</div>}
    </div>
  );
}

function ChecklistPanel({ inspection, onClose, onSaved, onFlash }) {
  const [results, setResults] = useState(inspection.results.map((r) => ({ ...r })));
  const [busy, setBusy] = useState(false);
  const [faultOpen, setFaultOpen] = useState(false);
  const [faultTitle, setFaultTitle] = useState(`PPM fault: ${inspection.equipment_name}`);
  const [faultPriority, setFaultPriority] = useState('p3');
  const [faultSafety, setFaultSafety] = useState(false);
  const [raised, setRaised] = useState(inspection.fault_reference || '');

  const setResult = (idx, val) => setResults((rs) => rs.map((r, i) => i === idx ? { ...r, result: val } : r));
  const setNote = (idx, val) => setResults((rs) => rs.map((r, i) => i === idx ? { ...r, note: val } : r));
  const anyFail = results.some((r) => r.result === 'fail');

  const save = async () => {
    setBusy(true);
    try { await bfpo.post(`/ppm/inspections/${inspection.id}`, { results }); if (!anyFail) onSaved(); else onFlash('Saved — raise a fault for the failed item(s)'); }
    catch (e) { onFlash(e?.response?.data?.detail || 'Could not save'); }
    finally { setBusy(false); }
  };
  const raiseFault = async () => {
    setBusy(true);
    try {
      await bfpo.post(`/ppm/inspections/${inspection.id}`, { results });
      const r = await bfpo.post(`/ppm/inspections/${inspection.id}/raise-fault`, { title: faultTitle, priority: faultPriority, safety_critical: faultSafety });
      setRaised(r.data.reference); setFaultOpen(false); onFlash(`Fault ${r.data.reference} created`); setTimeout(onSaved, 800);
    } catch (e) { onFlash(e?.response?.data?.detail || 'Could not raise fault'); }
    finally { setBusy(false); }
  };

  const OPTS = [
    { v: 'pass', label: 'Pass', icon: CheckCircle2, on: 'bg-emerald-600 text-white', off: 'text-emerald-700' },
    { v: 'fail', label: 'Fail', icon: XCircle, on: 'bg-red-600 text-white', off: 'text-red-700' },
    { v: 'na', label: 'N/A', icon: MinusCircle, on: 'bg-slate-600 text-white', off: 'text-slate-600' },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center" onMouseDown={onClose} data-testid="ppm-checklist">
      <div className="bg-white w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl max-h-[88vh] overflow-y-auto p-5" onMouseDown={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-slate-900">{inspection.equipment_name}</h2>
        <p className="text-sm text-slate-500 mb-4">{inspection.serial} · {inspection.template_name || 'Inspection'}</p>
        <div className="space-y-3">
          {results.map((r, idx) => (
            <div key={r.item_id} className="border-b border-slate-100 pb-3" data-testid={`ppm-item-${idx}`}>
              <p className="text-sm font-medium text-slate-800 mb-2">{r.label}</p>
              <div className="flex gap-2">
                {OPTS.map((o) => (
                  <button key={o.v} onClick={() => setResult(idx, o.v)} data-testid={`ppm-item-${idx}-${o.v}`}
                    className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-sm font-semibold border transition-colors ${r.result === o.v ? o.on + ' border-transparent' : 'bg-white border-slate-200 ' + o.off}`}>
                    <o.icon className="w-4 h-4" /> {o.label}
                  </button>
                ))}
              </div>
              {r.result === 'fail' && <input className={inputCls + ' mt-2'} placeholder="What's wrong?" value={r.note} onChange={(e) => setNote(idx, e.target.value)} data-testid={`ppm-item-${idx}-note`} />}
            </div>
          ))}
        </div>

        {raised ? (
          <p className="mt-4 text-sm text-red-700 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> Fault {raised} raised for this asset</p>
        ) : faultOpen ? (
          <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
            <Field label="Fault title"><input className={inputCls} value={faultTitle} onChange={(e) => setFaultTitle(e.target.value)} data-testid="ppm-fault-title" /></Field>
            <Field label="Priority">
              <select className={inputCls} value={faultPriority} onChange={(e) => setFaultPriority(e.target.value)} data-testid="ppm-fault-priority">
                <option value="p1">P1 · Critical</option><option value="p2">P2 · High</option><option value="p3">P3 · Medium</option><option value="p4">P4 · Low</option>
              </select>
            </Field>
            <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={faultSafety} onChange={(e) => setFaultSafety(e.target.checked)} data-testid="ppm-fault-safety" /> Safety critical</label>
            <Btn full variant="danger" disabled={busy} onClick={raiseFault} data-testid="ppm-fault-submit">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />} Create fault & save</Btn>
          </div>
        ) : null}

        <div className="mt-5 grid grid-cols-1 gap-2">
          {anyFail && !faultOpen && !raised && <Btn full variant="outline" onClick={() => setFaultOpen(true)} data-testid="ppm-raise-fault"><AlertTriangle className="w-4 h-4" /> Raise a fault</Btn>}
          <Btn full variant="primary" disabled={busy} onClick={save} data-testid="ppm-save">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Save inspection</Btn>
          <Btn full variant="ghost" onClick={onClose}>Close</Btn>
        </div>
      </div>
    </div>
  );
}
