import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Badge, Spinner, Empty, Field, inputCls } from '../ui';
import { ClipboardCheck, Plus, FileText, Settings2, Trash2, Loader2, ChevronRight, X } from 'lucide-react';

export default function PPMStaff({ onOpen }) {
  const [tab, setTab] = useState('services');
  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="ppm-staff">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-slate-900">Planned Servicing</h1>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          <button onClick={() => setTab('services')} data-testid="ppm-tab-services" className={`px-3 py-1.5 rounded-md text-sm font-semibold ${tab === 'services' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}>Services</button>
          <button onClick={() => setTab('templates')} data-testid="ppm-tab-templates" className={`px-3 py-1.5 rounded-md text-sm font-semibold ${tab === 'templates' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500'}`}>Checklists</button>
        </div>
      </div>
      {tab === 'services' ? <Services onOpen={onOpen} /> : <Templates />}
    </div>
  );
}

function Services({ onOpen }) {
  const [rows, setRows] = useState(null);
  const [meta, setMeta] = useState({ sites: [], engineers: [] });
  const [form, setForm] = useState({ site_id: '', due_date: '', engineer_id: '' });
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(() => { bfpo.get('/ppm/services').then((r) => setRows(r.data.services)); }, []);
  useEffect(() => { load(); Promise.all([bfpo.get('/sites'), bfpo.get('/staff/engineers')]).then(([s, e]) => setMeta({ sites: s.data.sites, engineers: e.data.engineers })); }, [load]);

  const create = async () => {
    setBusy(true); setErr('');
    try { await bfpo.post('/ppm/services', form); setForm({ site_id: '', due_date: '', engineer_id: '' }); setCreating(false); load(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not create'); }
    finally { setBusy(false); }
  };
  if (!rows) return <Spinner />;

  return (
    <>
      {creating ? (
        <Card className="p-4 mb-4" data-testid="ppm-create-form">
          <p className="font-semibold text-slate-900 mb-3">New service</p>
          <div className="grid md:grid-cols-3 gap-3">
            <Field label="Site"><select className={inputCls} value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })} data-testid="ppm-create-site"><option value="">— choose —</option>{meta.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
            <Field label="Due date"><input type="date" className={inputCls} value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="ppm-create-due" /></Field>
            <Field label="Assign engineer (optional)"><select className={inputCls} value={form.engineer_id} onChange={(e) => setForm({ ...form, engineer_id: e.target.value })} data-testid="ppm-create-engineer"><option value="">Unallocated</option>{meta.engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</select></Field>
          </div>
          {err && <p className="text-sm text-red-600 mt-2">{err}</p>}
          <div className="flex gap-2 mt-3">
            <Btn variant="primary" disabled={busy || !form.site_id} onClick={create} data-testid="ppm-create-submit">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Create service</Btn>
            <Btn variant="ghost" onClick={() => setCreating(false)}>Cancel</Btn>
          </div>
        </Card>
      ) : (
        <div className="mb-4"><Btn variant="primary" onClick={() => setCreating(true)} data-testid="ppm-new-service"><Plus className="w-4 h-4" /> New service</Btn></div>
      )}

      {rows.length === 0 ? <Empty icon={ClipboardCheck} title="No services yet" testid="ppm-staff-empty" /> : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr><th className="text-left p-3">Ref</th><th className="text-left p-3">Site</th><th className="text-left p-3 hidden md:table-cell">Engineer</th><th className="text-left p-3">Progress</th><th className="text-left p-3">Status</th><th className="p-3" /></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-t border-slate-100 hover:bg-slate-50" data-testid={`ppm-staff-row-${s.id}`}>
                  <td className="p-3 font-mono text-xs text-slate-500">{s.reference}</td>
                  <td className="p-3 font-medium text-slate-800">{s.site_name}</td>
                  <td className="p-3 hidden md:table-cell text-slate-500">{s.assigned_engineer_name || <span className="text-amber-600">Unallocated</span>}</td>
                  <td className="p-3 text-slate-600">{s.progress?.done}/{s.progress?.total}{s.progress?.failed ? ` · ${s.progress.failed} fault` : ''}</td>
                  <td className="p-3"><Badge className={s.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : s.status === 'due' ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-cyan-50 text-cyan-700 border-cyan-200'}>{s.status === 'in_progress' ? 'In progress' : s.status === 'due' ? 'Due' : 'Completed'}</Badge></td>
                  <td className="p-3 flex items-center gap-3">
                    {s.status === 'completed' && <a href={`${process.env.REACT_APP_BACKEND_URL}/api/bfpo/ppm/services/${s.id}/certificate.pdf`} target="_blank" rel="noreferrer" className="text-cyan-600" title="Certificate" data-testid={`ppm-cert-${s.id}`}><FileText className="w-4 h-4" /></a>}
                    <button onClick={() => onOpen(s.id)} className="text-slate-400 hover:text-slate-600" data-testid={`ppm-open-${s.id}`}><ChevronRight className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

function Templates() {
  const [rows, setRows] = useState(null);
  const [edit, setEdit] = useState(null);

  const load = useCallback(() => { bfpo.get('/ppm/templates').then((r) => setRows(r.data.templates)); }, []);
  useEffect(() => { load(); }, [load]);
  if (!rows) return <Spinner />;

  return (
    <div className="space-y-3" data-testid="ppm-templates">
      <p className="text-sm text-slate-500">Checklists applied to each asset by equipment category. Edit to add, rename or remove checks.</p>
      {rows.map((t) => (
        <Card key={t.id} className="p-4">
          <div className="flex items-center justify-between">
            <div><p className="font-semibold text-slate-900">{t.name}</p><p className="text-xs text-slate-500">{t.category} · {t.items.length} checks</p></div>
            <Btn variant="outline" onClick={() => setEdit({ ...t, items: t.items.map((i) => ({ ...i })) })} data-testid={`ppm-tpl-edit-${t.category}`}><Settings2 className="w-4 h-4" /> Edit</Btn>
          </div>
        </Card>
      ))}
      {edit && <TemplateEditor tpl={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function TemplateEditor({ tpl, onClose, onSaved }) {
  const [items, setItems] = useState(tpl.items.map((i) => i.label));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await bfpo.post('/ppm/templates', { category: tpl.category, name: tpl.name, items: items.filter((x) => x.trim()).map((label) => ({ label })) }); onSaved(); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onMouseDown={onClose} data-testid="ppm-tpl-editor">
      <div className="bg-white rounded-2xl w-full max-w-lg max-h-[88vh] overflow-y-auto p-5" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3"><h2 className="text-lg font-bold text-slate-900">{tpl.name}</h2><button onClick={onClose} className="p-1 text-slate-400"><X className="w-5 h-5" /></button></div>
        <div className="space-y-2">
          {items.map((it, idx) => (
            <div key={idx} className="flex gap-2">
              <input className={inputCls} value={it} onChange={(e) => setItems((a) => a.map((x, i) => i === idx ? e.target.value : x))} data-testid={`ppm-tpl-item-${idx}`} />
              <button onClick={() => setItems((a) => a.filter((_, i) => i !== idx))} className="text-red-500 p-2 shrink-0" data-testid={`ppm-tpl-del-${idx}`}><Trash2 className="w-4 h-4" /></button>
            </div>
          ))}
        </div>
        <Btn variant="ghost" className="mt-2" onClick={() => setItems((a) => [...a, ''])} data-testid="ppm-tpl-add"><Plus className="w-4 h-4" /> Add check</Btn>
        <div className="grid grid-cols-1 gap-2 mt-4">
          <Btn variant="primary" disabled={busy} onClick={save} data-testid="ppm-tpl-save">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Save checklist</Btn>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        </div>
      </div>
    </div>
  );
}
