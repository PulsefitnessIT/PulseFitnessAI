import { useEffect, useState, useCallback } from 'react';
import { Plus, Trash2, Layers, ChevronRight, ArrowLeft } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, inputTight, money, StatusBadge } from './shared';

const FLAGS = [
  { key: 'warranty_relevance', label: 'Warranty' },
  { key: 'recommended_spare', label: 'Rec. spare' },
  { key: 'service_part', label: 'Service' },
  { key: 'wear_item', label: 'Wear' },
  { key: 'consumable', label: 'Consumable' },
];

function newItem() {
  return { part_number: '', part_description: '', quantity_per_machine: 1, criticality: 'medium', cost: '', warranty_relevance: false, recommended_spare: false, service_part: false, wear_item: false, consumable: false };
}

function BomDetail({ bom, onBack }) {
  return (
    <div className="space-y-4" data-testid="dp-bom-detail">
      <button onClick={onBack} className="text-sm text-slate-500 hover:text-slate-800 inline-flex items-center gap-1"><ArrowLeft size={14} /> Back to BOMs</button>
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-bold text-slate-900">{bom.machine_model}</h2>
        <StatusBadge status={bom.status} />
        <span className="text-xs text-slate-400">v{bom.version} · {bom.machine_category || 'Uncategorised'}</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
            <th className="py-2.5 px-4">Part</th><th>Criticality</th><th>Flags</th><th className="text-right">Cost</th>
          </tr></thead>
          <tbody>
            {bom.items.map((it) => (
              <tr key={it.id} className="border-b border-slate-50">
                <td className="py-2.5 px-4"><span className="font-mono text-xs text-slate-500">{it.part_number}</span> {it.part_description}</td>
                <td className="capitalize">{it.criticality}</td>
                <td className="text-xs text-slate-500">{FLAGS.filter((f) => it[f.key]).map((f) => f.label).join(', ') || '—'}</td>
                <td className="text-right tabular-nums">{money(it.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function BomTab() {
  const [boms, setBoms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [modal, setModal] = useState(false);
  const [model, setModel] = useState('');
  const [category, setCategory] = useState('');
  const [items, setItems] = useState([newItem()]);

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listBoms({ include_superseded: true }).then((d) => setBoms(d.boms || [])).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!model.trim()) { notify.error('Machine model required'); return; }
    const clean = items.filter((i) => i.part_number).map((i) => ({ ...i, quantity_per_machine: Number(i.quantity_per_machine) || 1, cost: Number(i.cost) || 0 }));
    if (clean.length === 0) { notify.error('Add at least one part'); return; }
    try {
      await dpApi.createBom({ machine_model: model, machine_category: category, items: clean, status: 'active' });
      notify.success('BOM saved (new version activated)');
      setModal(false); setModel(''); setCategory(''); setItems([newItem()]); load();
    } catch { notify.error('Failed to save BOM'); }
  };

  if (selected) return <BomDetail bom={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="space-y-4" data-testid="dp-bom-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500">Bills of Materials (versioned per model)</h3>
        <button data-testid="dp-add-bom-btn" onClick={() => setModal(true)} className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90">
          <Plus size={15} /> New BOM
        </button>
      </div>

      {loading ? <Spinner /> : boms.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No BOMs yet. Add a machine model's parts list to power recommendations.</div>
      ) : (
        <div className="space-y-2">
          {boms.map((b) => (
            <button key={b.id} data-testid={`dp-bom-row-${b.id}`} onClick={() => setSelected(b)} className="w-full text-left rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-3 hover:shadow-md hover:border-[var(--gx-brand-from)]/40 transition-all">
              <Layers size={16} className="text-[var(--gx-brand-from)]" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-900">{b.machine_model}</span>
                  <StatusBadge status={b.status} />
                  <span className="text-xs text-slate-400">v{b.version}</span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">{b.items.length} parts · {b.machine_category || 'Uncategorised'}</div>
              </div>
              <ChevronRight size={16} className="text-slate-300" />
            </button>
          ))}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="New BOM" testid="dp-bom-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-bom-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Save BOM</button>
        </>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Machine model *"><input data-testid="dp-bom-model" className={input} value={model} onChange={(e) => setModel(e.target.value)} placeholder="260G Treadmill" /></Field>
          <Field label="Category"><input className={input} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Cardio" /></Field>
        </div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500">Parts</span>
          <button onClick={() => setItems([...items, newItem()])} className="text-xs text-[var(--gx-brand-from)] font-semibold">+ Add part</button>
        </div>
        {items.map((it, i) => (
          <div key={i} className="border border-slate-100 rounded-lg p-2.5 mb-2 space-y-2">
            <div className="flex gap-2">
              <input placeholder="Part number" className={`${inputTight} w-32 font-mono`} value={it.part_number} onChange={(e) => { const n = [...items]; n[i].part_number = e.target.value.toUpperCase(); setItems(n); }} />
              <input placeholder="Description" className={`${inputTight} flex-1`} value={it.part_description} onChange={(e) => { const n = [...items]; n[i].part_description = e.target.value; setItems(n); }} />
              <input type="number" placeholder="£" className={`${inputTight} w-20`} value={it.cost} onChange={(e) => { const n = [...items]; n[i].cost = e.target.value; setItems(n); }} />
              {items.length > 1 && <button onClick={() => setItems(items.filter((_, x) => x !== i))} className="text-slate-300 hover:text-red-500"><Trash2 size={15} /></button>}
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <select className={`${inputTight} w-28`} value={it.criticality} onChange={(e) => { const n = [...items]; n[i].criticality = e.target.value; setItems(n); }}>
                {['critical', 'high', 'medium', 'low', 'optional'].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              {FLAGS.map((f) => (
                <label key={f.key} className="text-xs text-slate-600 flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={it[f.key]} onChange={(e) => { const n = [...items]; n[i][f.key] = e.target.checked; setItems(n); }} /> {f.label}
                </label>
              ))}
            </div>
          </div>
        ))}
      </Modal>
    </div>
  );
}
