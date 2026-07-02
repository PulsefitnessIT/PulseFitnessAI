/**
 * Operations · Request a Part
 *
 * Operator-facing parts request workflow (Lite + Pro + Full). Mirrors
 * Log-a-Fault: pick machine(s) → see cover (warranty/contract/chargeable)
 * → list parts (helped by exploded drawings + AI photo ID) → attach
 * photos → submit → a branded Supplier Parts Card is emailed. The
 * request detail page shows the full supplier lifecycle timeline.
 *
 * Views: list | edit (draft) | detail
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  ArrowLeft, Package, Plus, Trash2, Search, Upload, Loader2, Send,
  ShieldCheck, ShieldAlert, ShieldQuestion, X, Image as ImageIcon,
  Sparkles, FileText, CheckCircle2, Truck, ClipboardList, ExternalLink,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700',
  submitted: 'bg-blue-100 text-blue-700',
  acknowledged: 'bg-indigo-100 text-indigo-700',
  quoted: 'bg-amber-100 text-amber-800',
  invoiced: 'bg-purple-100 text-purple-700',
  allocated: 'bg-cyan-100 text-cyan-800',
  despatched: 'bg-teal-100 text-teal-800',
  completed: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-rose-100 text-rose-700',
};
const STATUS_LABEL = {
  draft: 'Draft', submitted: 'Sent to Supplier', acknowledged: 'Acknowledged',
  quoted: 'Quote Provided', invoiced: 'Invoiced', allocated: 'Parts Allocated',
  despatched: 'Despatched', completed: 'Completed', cancelled: 'Cancelled',
};

function CoverBadge({ machine }) {
  const cs = machine.coverage_status;
  if (cs === 'covered_contract') {
    return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700" data-testid="cover-badge-contract"><ShieldCheck size={12} /> Contract{machine.contract_tier ? ` · ${machine.contract_tier}` : ''}</span>;
  }
  if (cs === 'covered_warranty') {
    return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700" data-testid="cover-badge-warranty"><ShieldCheck size={12} /> Under warranty</span>;
  }
  return <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800" data-testid="cover-badge-chargeable"><ShieldAlert size={12} /> Chargeable</span>;
}

function StatusBadge({ status }) {
  return <span className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full ${STATUS_STYLES[status] || 'bg-slate-100 text-slate-700'}`} data-testid={`status-badge-${status}`}>{STATUS_LABEL[status] || status}</span>;
}

// ── Exploded drawings modal ─────────────────────────────────────────
function DrawingsModal({ machine, onClose, onAddPart }) {
  const [drawings, setDrawings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [viewingUrl, setViewingUrl] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams();
        if (machine.manufacturer) params.set('manufacturer', machine.manufacturer);
        if (machine.model) params.set('model', machine.model);
        const { data } = await axios.get(`${API}/exploded-drawings?${params.toString()}`, auth());
        setDrawings(data.drawings || []);
      } catch { setDrawings([]); }
      setLoading(false);
    })();
  }, [machine]);

  const open = async (d) => {
    setSelected(d);
    try {
      const res = await axios.get(`${API}/exploded-drawings/${d.id}/file`, { ...auth(), responseType: 'blob' });
      setViewingUrl(URL.createObjectURL(res.data));
    } catch { toast.error('Could not open drawing'); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose} data-testid="drawings-modal">
      <div className="bg-white rounded-xl max-w-3xl w-full max-h-[85vh] overflow-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-slate-900">Exploded drawings — {machine.manufacturer} {machine.model}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="drawings-close"><X size={20} /></button>
        </div>
        {loading ? <div className="py-10 text-center text-slate-400"><Loader2 className="animate-spin inline" /></div>
          : selected ? (
            <div>
              <button onClick={() => { setSelected(null); setViewingUrl(null); }} className="text-sm text-blue-600 mb-2">← Back to list</button>
              {viewingUrl && <img src={viewingUrl} alt="Exploded drawing" className="w-full rounded-lg border mb-3" />}
              <p className="text-sm font-semibold text-slate-700 mb-2">Parts in this drawing</p>
              {(selected.parts || []).length === 0 ? (
                <p className="text-sm text-slate-400">No parts list attached to this drawing — read the part number off the diagram and add it manually.</p>
              ) : (
                <div className="space-y-1.5">
                  {selected.parts.map((p, i) => (
                    <div key={i} className="flex items-center justify-between border rounded-lg px-3 py-2" data-testid={`drawing-part-${i}`}>
                      <div className="min-w-0">
                        <p className="text-sm text-slate-800 truncate">{p.description || p.part_number}</p>
                        {p.part_number && <p className="text-xs text-slate-500 font-mono">{p.part_number}</p>}
                      </div>
                      <button onClick={() => { onAddPart({ part_name: p.description || '', part_number: p.part_number || '', qty: 1, notes: p.notes || '' }); toast.success('Added to request'); }}
                        className="text-sm font-medium text-blue-600 inline-flex items-center gap-1 shrink-0" data-testid={`drawing-add-part-${i}`}><Plus size={14} /> Add</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : drawings.length === 0 ? (
            <p className="text-sm text-slate-500 py-8 text-center">No exploded drawings found for this make/model yet. Ask your admin to upload one, or type the part details manually.</p>
          ) : (
            <div className="space-y-2">
              {drawings.map((d) => (
                <div key={d.id} className="flex items-center justify-between border rounded-lg px-3 py-2" data-testid={`drawing-row-${d.id}`}>
                  <div>
                    <p className="text-sm font-medium text-slate-900">{d.title}</p>
                    <p className="text-xs text-slate-500">{d.manufacturer} {d.model} {d.equipment_type ? `· ${d.equipment_type}` : ''}{(d.parts || []).length ? ` · ${d.parts.length} part(s)` : ''}</p>
                  </div>
                  <button onClick={() => open(d)} className="text-sm font-medium text-blue-600 inline-flex items-center gap-1" data-testid={`drawing-view-${d.id}`}><ImageIcon size={14} /> Open</button>
                </div>
              ))}
            </div>
          )}
      </div>
    </div>
  );
}

// ── Editor (draft request) ──────────────────────────────────────────
function Editor({ requestId, onDone, onCancel }) {
  const [req, setReq] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [supplierEmail, setSupplierEmail] = useState('');
  const [notes, setNotes] = useState('');
  const [toSD, setToSD] = useState(false);
  const [machines, setMachines] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [searchQ, setSearchQ] = useState('');
  const [results, setResults] = useState([]);
  const [drawingFor, setDrawingFor] = useState(null);
  const [aiBusy, setAiBusy] = useState(null);
  const fileRefs = useRef({});

  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/parts-requests/${requestId}`, auth());
    setReq(data);
    setMachines(data.machines || []);
    setSupplierEmail(data.supplier_email || '');
    setNotes(data.notes || '');
    setAttachments(data.attachments || []);
    setLoading(false);
  }, [requestId]);

  useEffect(() => { load(); }, [load]);

  const doSearch = async () => {
    const { data } = await axios.get(`${API}/parts-requests/equipment-search?q=${encodeURIComponent(searchQ)}`, auth());
    setResults(data.equipment || []);
  };

  const addMachine = async (eq) => {
    if (machines.some((m) => m.serial_number && m.serial_number === eq.serial_number)) {
      toast('Machine already added'); return;
    }
    // Persist first so cover is computed server-side.
    const next = [...machines, {
      equipment_id: eq.id, machine_name: eq.name, serial_number: eq.serial_number,
      manufacturer: eq.manufacturer, model: eq.model, equipment_type: eq.equipment_type, parts: [],
    }];
    await persist(next);
    setResults([]); setSearchQ('');
  };

  const persist = async (nextMachines, extra = {}) => {
    setSaving(true);
    try {
      const { data } = await axios.put(`${API}/parts-requests/${requestId}`, {
        machines: (nextMachines || machines), supplier_email: supplierEmail, notes, ...extra,
      }, auth());
      setMachines(data.machines || []);
      return data;
    } catch (e) { toast.error(e?.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  const removeMachine = (idx) => persist(machines.filter((_, i) => i !== idx));

  const addPart = (idx) => {
    const next = machines.map((m, i) => i === idx ? { ...m, parts: [...(m.parts || []), { part_name: '', part_number: '', qty: 1, notes: '' }] } : m);
    setMachines(next);
  };
  const addFilledPart = (idx, part) => {
    setMachines((prev) => prev.map((m, i) => i === idx ? { ...m, parts: [...(m.parts || []), part] } : m));
  };
  const updatePart = (mi, pi, field, value) => {
    setMachines(machines.map((m, i) => i === mi ? { ...m, parts: m.parts.map((p, j) => j === pi ? { ...p, [field]: value } : p) } : m));
  };
  const removePart = (mi, pi) => setMachines(machines.map((m, i) => i === mi ? { ...m, parts: m.parts.filter((_, j) => j !== pi) } : m));

  const uploadPhoto = async (mi, file) => {
    if (!file) return;
    // Save parts edits before uploading so nothing is lost.
    await persist(machines);
    const fd = new FormData(); fd.append('file', file);
    try {
      await axios.post(`${API}/parts-requests/${requestId}/attachments?machine_index=${mi}`, fd, auth());
      toast.success('Photo uploaded');
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Upload failed'); }
  };

  const aiIdentify = async (att, mi) => {
    setAiBusy(att.id);
    try {
      const m = machines[mi] || {};
      const { data } = await axios.post(`${API}/parts-requests/${requestId}/ai-identify`, {
        attachment_id: att.id, machine_type: m.equipment_type, manufacturer: m.manufacturer,
        model: m.model, notes: m.notes,
      }, auth());
      if (!data.available) { toast.error(data.error || 'AI unavailable'); return; }
      const s = (data.suggestions || [])[0];
      if (s) {
        const next = machines.map((mm, i) => i === mi ? { ...mm, parts: [...(mm.parts || []), { part_name: s.part_name || '', part_number: s.part_number || '', qty: 1, notes: `AI (${s.confidence}): ${s.reasoning || ''}` }] } : mm);
        setMachines(next);
        toast.success(`AI added: ${s.part_name || s.part_number || 'part'}`);
      } else { toast('AI could not identify a part'); }
    } catch { toast.error('AI request failed'); }
    finally { setAiBusy(null); }
  };

  const submit = async () => {
    if (machines.length === 0) { toast.error('Add at least one machine'); return; }
    setSubmitting(true);
    try {
      await persist(machines);
      const { data } = await axios.post(`${API}/parts-requests/${requestId}/submit`, {
        supplier_email: supplierEmail, send_to_service_desk: toSD,
      }, auth());
      toast.success(data.email_sent ? 'Sent to supplier' : 'Submitted (email not dispatched)');
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Submit failed'); }
    finally { setSubmitting(false); }
  };

  if (loading) return <div className="py-16 text-center text-slate-400"><Loader2 className="animate-spin inline" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-5" data-testid="parts-request-editor">
      <div className="flex items-center gap-3">
        <button onClick={onCancel} className="text-slate-500 hover:text-slate-800" data-testid="editor-back"><ArrowLeft size={20} /></button>
        <div>
          <h2 className="text-xl font-bold text-slate-900">New Parts Request <span className="text-slate-400 font-mono text-sm">{req?.reference}</span></h2>
          <p className="text-sm text-slate-500">Add the machines and the parts each one needs.</p>
        </div>
        {saving && <Loader2 className="animate-spin text-slate-400 ml-auto" size={16} />}
      </div>

      {/* Machine picker */}
      <div className="rounded-xl border border-slate-200 p-4 bg-white">
        <label className="text-sm font-semibold text-slate-700">Add a machine</label>
        <div className="flex gap-2 mt-2">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={searchQ} onChange={(e) => setSearchQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doSearch()}
              placeholder="Search by name, serial, manufacturer…" className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="machine-search-input" />
          </div>
          <button onClick={doSearch} className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm font-medium" data-testid="machine-search-btn">Search</button>
        </div>
        {results.length > 0 && (
          <div className="mt-2 border rounded-lg divide-y max-h-52 overflow-auto">
            {results.map((eq) => (
              <button key={eq.id} onClick={() => addMachine(eq)} className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-center justify-between" data-testid={`machine-result-${eq.id}`}>
                <span className="text-sm text-slate-800">{eq.name} <span className="text-slate-400">· {eq.serial_number || 'no serial'}</span></span>
                <Plus size={15} className="text-blue-600" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Machines + parts */}
      {machines.map((m, mi) => {
        const machineAtts = attachments.filter((a) => a.machine_index === mi);
        return (
          <div key={mi} className="rounded-xl border border-slate-200 p-4 bg-white" data-testid={`machine-block-${mi}`}>
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold text-slate-900">{m.machine_name || m.equipment_type || 'Machine'}</p>
                <p className="text-xs text-slate-500">{m.manufacturer} {m.model} · Serial: {m.serial_number || '—'}</p>
                <div className="mt-1"><CoverBadge machine={m} /></div>
              </div>
              <button onClick={() => removeMachine(mi)} className="text-slate-400 hover:text-rose-600" data-testid={`remove-machine-${mi}`}><Trash2 size={16} /></button>
            </div>

            {/* Parts */}
            <div className="mt-3 space-y-2">
              {(m.parts || []).map((p, pi) => (
                <div key={pi} className="grid grid-cols-12 gap-2 items-center" data-testid={`part-row-${mi}-${pi}`}>
                  <input value={p.part_name} onChange={(e) => updatePart(mi, pi, 'part_name', e.target.value)} placeholder="Part name" className="col-span-4 px-2 py-1.5 border border-slate-300 rounded text-sm" data-testid={`part-name-${mi}-${pi}`} />
                  <input value={p.part_number} onChange={(e) => updatePart(mi, pi, 'part_number', e.target.value)} placeholder="Part no." className="col-span-3 px-2 py-1.5 border border-slate-300 rounded text-sm" data-testid={`part-number-${mi}-${pi}`} />
                  <input type="number" min="1" value={p.qty} onChange={(e) => updatePart(mi, pi, 'qty', e.target.value)} className="col-span-1 px-2 py-1.5 border border-slate-300 rounded text-sm" data-testid={`part-qty-${mi}-${pi}`} />
                  <input value={p.notes} onChange={(e) => updatePart(mi, pi, 'notes', e.target.value)} placeholder="Notes" className="col-span-3 px-2 py-1.5 border border-slate-300 rounded text-sm" />
                  <button onClick={() => removePart(mi, pi)} className="col-span-1 text-slate-400 hover:text-rose-600"><X size={15} /></button>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-2 mt-3">
              <button onClick={() => addPart(mi)} className="text-sm font-medium text-blue-600 inline-flex items-center gap-1" data-testid={`add-part-${mi}`}><Plus size={14} /> Add part</button>
              <button onClick={() => setDrawingFor({ machine: m, index: mi })} className="text-sm font-medium text-slate-600 inline-flex items-center gap-1" data-testid={`find-drawing-${mi}`}><ImageIcon size={14} /> Find in exploded drawing</button>
              <label className="text-sm font-medium text-slate-600 inline-flex items-center gap-1 cursor-pointer" data-testid={`upload-photo-${mi}`}>
                <Upload size={14} /> Add photo
                <input ref={(el) => (fileRefs.current[mi] = el)} type="file" accept="image/*" className="hidden" onChange={(e) => uploadPhoto(mi, e.target.files?.[0])} />
              </label>
            </div>

            {machineAtts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {machineAtts.map((a) => (
                  <div key={a.id} className="flex items-center gap-2 bg-slate-50 border rounded-lg px-2 py-1.5" data-testid={`att-chip-${a.id}`}>
                    <ImageIcon size={13} className="text-slate-400" />
                    <span className="text-xs text-slate-700 max-w-[120px] truncate">{a.original_filename}</span>
                    <button onClick={() => aiIdentify(a, mi)} disabled={aiBusy === a.id} className="text-xs font-medium text-purple-600 inline-flex items-center gap-1" data-testid={`ai-identify-${a.id}`}>
                      {aiBusy === a.id ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} AI ID
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {/* Supplier + submit */}
      <div className="rounded-xl border border-slate-200 p-4 bg-white space-y-3">
        <div>
          <label className="text-sm font-semibold text-slate-700">Supplier email</label>
          <input value={supplierEmail} onChange={(e) => setSupplierEmail(e.target.value)} className="w-full mt-1 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="supplier-email-input" />
          <p className="text-xs text-slate-400 mt-1">Defaults to parts@pulsefitness.com — change it to route to a specific supplier.</p>
        </div>
        <div>
          <label className="text-sm font-semibold text-slate-700">Notes for supplier</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="w-full mt-1 px-3 py-2 border border-slate-300 rounded-lg text-sm" data-testid="request-notes-input" />
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={toSD} onChange={(e) => setToSD(e.target.checked)} data-testid="send-to-sd-checkbox" />
          Also send this request to the Service Desk
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={() => persist(machines).then(() => toast.success('Draft saved'))} className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-medium text-slate-700" data-testid="save-draft-btn">Save draft</button>
          <button onClick={submit} disabled={submitting} className="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60" data-testid="submit-request-btn">
            {submitting ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} Submit to supplier
          </button>
        </div>
      </div>

      {drawingFor && <DrawingsModal machine={drawingFor.machine} onClose={() => setDrawingFor(null)} onAddPart={(part) => addFilledPart(drawingFor.index, part)} />}
    </div>
  );
}

// ── Detail (lifecycle timeline) ─────────────────────────────────────
const EVENT_ICON = {
  created: ClipboardList, submitted: Send, acknowledge: CheckCircle2, quote: FileText,
  invoice: FileText, allocate: Package, despatch: Truck, complete: CheckCircle2,
  service_desk: ExternalLink, cancelled: X, received: CheckCircle2, ai_identify: Sparkles,
};
function Detail({ requestId, onBack }) {
  const [req, setReq] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/parts-requests/${requestId}`, auth());
    setReq(data);
  }, [requestId]);
  useEffect(() => { load(); }, [load]);

  const act = async (path, label) => {
    setBusy(true);
    try { await axios.post(`${API}/parts-requests/${requestId}/${path}`, {}, auth()); toast.success(label); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || 'Action failed'); }
    finally { setBusy(false); }
  };

  if (!req) return <div className="py-16 text-center text-slate-400"><Loader2 className="animate-spin inline" /></div>;
  const cardUrl = req.supplier_card_token ? `${window.location.origin}/parts-card/${req.supplier_card_token}` : null;

  return (
    <div className="max-w-4xl mx-auto space-y-5" data-testid="parts-request-detail">
      <div className="flex items-center gap-3">
        <button onClick={onBack} className="text-slate-500 hover:text-slate-800" data-testid="detail-back"><ArrowLeft size={20} /></button>
        <div className="flex-1">
          <h2 className="text-xl font-bold text-slate-900">{req.reference}</h2>
          <p className="text-sm text-slate-500">To {req.supplier_email} · {req.machines?.length || 0} machine(s)</p>
        </div>
        <StatusBadge status={req.status} />
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {cardUrl && <a href={cardUrl} target="_blank" rel="noreferrer" className="px-3 py-1.5 rounded-lg border text-sm font-medium text-blue-600 inline-flex items-center gap-1" data-testid="view-supplier-card"><ExternalLink size={14} /> View supplier card</a>}
        {!req.service_desk_case_id && req.status !== 'cancelled' && <button onClick={() => act('service-desk', 'Pushed to Service Desk')} disabled={busy} className="px-3 py-1.5 rounded-lg border text-sm font-medium text-slate-700" data-testid="push-sd-btn">Send to Service Desk</button>}
        {['despatched', 'invoiced', 'allocated'].includes(req.status) && <button onClick={() => act('mark-received', 'Marked received')} disabled={busy} className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-sm font-medium" data-testid="mark-received-btn">Mark received</button>}
        {!['completed', 'cancelled'].includes(req.status) && <button onClick={() => act('cancel', 'Request cancelled')} disabled={busy} className="px-3 py-1.5 rounded-lg border border-rose-200 text-sm font-medium text-rose-600" data-testid="cancel-request-btn">Cancel</button>}
      </div>

      {/* Machines */}
      <div className="space-y-3">
        {(req.machines || []).map((m, mi) => (
          <div key={mi} className="rounded-xl border border-slate-200 p-4 bg-white" data-testid={`detail-machine-${mi}`}>
            <div className="flex items-center justify-between">
              <p className="font-semibold text-slate-900">{m.machine_name || m.equipment_type} <span className="text-slate-400 font-normal text-sm">· {m.serial_number || '—'}</span></p>
              <CoverBadge machine={m} />
            </div>
            <ul className="mt-2 text-sm text-slate-700 list-disc pl-5">
              {(m.parts || []).map((p, pi) => <li key={pi}>{p.qty}× {p.part_name || '—'}{p.part_number ? ` (${p.part_number})` : ''}{p.notes ? ` — ${p.notes}` : ''}</li>)}
              {(m.parts || []).length === 0 && <li className="text-slate-400 list-none">No specific parts listed</li>}
            </ul>
          </div>
        ))}
      </div>

      {/* Quote / invoice / despatch */}
      {(req.quote || req.invoice || req.despatch) && (
        <div className="grid sm:grid-cols-3 gap-3">
          {req.quote && <div className="rounded-xl border p-3 bg-amber-50" data-testid="detail-quote"><p className="text-xs font-semibold text-amber-800 uppercase">Quote</p><p className="text-lg font-bold text-slate-900">{req.quote.currency} {req.quote.amount}</p><p className="text-xs text-slate-600">{req.quote.notes}</p></div>}
          {req.invoice && <div className="rounded-xl border p-3 bg-purple-50" data-testid="detail-invoice"><p className="text-xs font-semibold text-purple-800 uppercase">Invoice</p><p className="text-lg font-bold text-slate-900">{req.invoice.currency} {req.invoice.amount}</p><p className="text-xs text-slate-600">{req.invoice.invoice_number}</p></div>}
          {req.despatch && <div className="rounded-xl border p-3 bg-teal-50" data-testid="detail-despatch"><p className="text-xs font-semibold text-teal-800 uppercase">Despatch</p><p className="text-sm font-bold text-slate-900">{req.despatch.carrier}</p><p className="text-xs text-slate-600">{req.despatch.tracking}</p></div>}
        </div>
      )}

      {/* Timeline */}
      <div className="rounded-xl border border-slate-200 p-4 bg-white">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Activity</h3>
        <div className="space-y-3">
          {(req.events || []).map((e) => {
            const Icon = EVENT_ICON[e.action] || ClipboardList;
            return (
              <div key={e.id} className="flex gap-3" data-testid={`timeline-event-${e.action}`}>
                <div className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 ${e.actor_role === 'supplier' ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600'}`}><Icon size={14} /></div>
                <div className="flex-1">
                  <p className="text-sm text-slate-800"><span className="font-medium">{e.actor}</span> <span className="text-slate-500">({e.actor_role})</span> — {e.note || e.action}</p>
                  <p className="text-xs text-slate-400">{new Date(e.at).toLocaleString('en-GB')}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── List + page shell ───────────────────────────────────────────────
export default function PartsRequestsPage() {
  const navigate = useNavigate();
  const [view, setView] = useState('list');
  const [activeId, setActiveId] = useState(null);
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadList = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/parts-requests`, auth()); setRequests(data.requests || []); }
    catch { setRequests([]); }
    setLoading(false);
  }, []);
  useEffect(() => { if (view === 'list') loadList(); }, [view, loadList]);

  const newRequest = async () => {
    try {
      const { data } = await axios.post(`${API}/parts-requests`, { machines: [] }, auth());
      setActiveId(data.id); setView('edit');
    } catch (e) { toast.error(e?.response?.data?.detail || 'Could not start request'); }
  };

  return (
    <div className="min-h-screen bg-slate-50 pulse-font" data-testid="parts-page">
      <div className="max-w-5xl mx-auto px-4 py-6">
        {view === 'list' && (
          <>
            <div className="flex items-center gap-3 mb-5">
              <button onClick={() => navigate(-1)} className="text-slate-500 hover:text-slate-800" data-testid="parts-page-back"><ArrowLeft size={20} /></button>
              <div className="flex items-center gap-2">
                <Package className="text-blue-600" size={22} />
                <div>
                  <h1 className="text-2xl font-bold text-slate-900">Parts Requests</h1>
                  <p className="text-sm text-slate-500">Request spare parts from your suppliers and track them to delivery.</p>
                </div>
              </div>
              <button onClick={newRequest} className="ml-auto px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold inline-flex items-center gap-2" data-testid="new-request-btn"><Plus size={16} /> New Request</button>
            </div>

            {loading ? <div className="py-16 text-center text-slate-400"><Loader2 className="animate-spin inline" /></div>
              : requests.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 py-16 text-center" data-testid="parts-empty-state">
                  <Package className="mx-auto text-slate-300 mb-3" size={40} />
                  <p className="text-slate-600 font-medium">No parts requests yet</p>
                  <p className="text-sm text-slate-400 mb-4">Raise your first request — pick a machine and list the parts it needs.</p>
                  <button onClick={newRequest} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold" data-testid="empty-new-request-btn">New Request</button>
                </div>
              ) : (
                <div className="space-y-2">
                  {requests.map((r) => (
                    <button key={r.id} onClick={() => { setActiveId(r.id); setView(r.status === 'draft' ? 'edit' : 'detail'); }}
                      className="w-full text-left rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-300 transition-colors flex items-center justify-between" data-testid={`request-row-${r.id}`}>
                      <div>
                        <p className="font-semibold text-slate-900 font-mono">{r.reference}</p>
                        <p className="text-sm text-slate-500">{r.machine_count} machine(s) · {r.part_count} part(s) · {r.supplier_email}</p>
                      </div>
                      <StatusBadge status={r.status} />
                    </button>
                  ))}
                </div>
              )}
          </>
        )}
        {view === 'edit' && <Editor requestId={activeId} onDone={() => setView('list')} onCancel={() => setView('list')} />}
        {view === 'detail' && <Detail requestId={activeId} onBack={() => setView('list')} />}
      </div>
    </div>
  );
}
