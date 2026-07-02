/**
 * EquipmentMultiSelect — iter 215dq.
 *
 * Type-ahead picker pulling from the existing /api/equipment list.
 * Returns { ids[], serials[] } via onChange so parent can store both
 * for Sicon EquipmentIDs[] mapping.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Search, X, Plus } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export default function EquipmentMultiSelect({ value = [], onChange }) {
  const [all, setAll] = useState([]);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [manualSerial, setManualSerial] = useState('');

  useEffect(() => {
    axios.get(`${API}/equipment`, auth())
      .then((r) => setAll(r.data?.equipment || []))
      .catch(() => setAll([]));
  }, []);

  const selected = useMemo(() => value || [], [value]);
  const selectedIds = useMemo(() => new Set(selected.map((v) => v.id).filter(Boolean)), [selected]);

  const filtered = useMemo(() => {
    if (!search.trim()) return all.slice(0, 8);
    const s = search.toLowerCase();
    return all.filter((e) =>
      (e.name || '').toLowerCase().includes(s)
      || (e.serial_number || '').toLowerCase().includes(s)
      || (e.equipment_type || '').toLowerCase().includes(s),
    ).slice(0, 12);
  }, [all, search]);

  const addEquipment = (e) => {
    if (selectedIds.has(e.id)) return;
    onChange?.([
      ...selected,
      { id: e.id, name: e.name, serial: e.serial_number || '' },
    ]);
    setSearch('');
  };

  const addManualSerial = () => {
    const s = manualSerial.trim();
    if (!s) return;
    onChange?.([...selected, { id: '', name: `Serial ${s}`, serial: s }]);
    setManualSerial('');
  };

  const remove = (idx) => {
    const next = [...selected];
    next.splice(idx, 1);
    onChange?.(next);
  };

  return (
    <div className="space-y-2" data-testid="equipment-multiselect">
      <div className="flex flex-wrap gap-1.5 min-h-[1.75rem]" data-testid="equipment-selected">
        {selected.length === 0 ? (
          <span className="text-[11px] opacity-50 italic">No equipment attached yet.</span>
        ) : selected.map((e, i) => (
          <span
            key={`${e.id || 'manual'}-${i}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold"
            style={{ background: '#cffafe', color: '#0891b2' }}
            data-testid={`equipment-chip-${i}`}
          >
            {e.name || 'Equipment'}{e.serial ? ` · ${e.serial}` : ''}
            <button type="button" aria-label="Remove" onClick={() => remove(i)} className="hover:opacity-80" data-testid={`equipment-chip-remove-${i}`}>
              <X size={11} />
            </button>
          </span>
        ))}
      </div>

      <div className="relative">
        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Search by name, serial, or type…"
          className="w-full pl-7 pr-3 py-2 rounded-md border bg-transparent text-sm"
          style={{ borderColor: 'var(--theme-border)' }}
          data-testid="equipment-search"
        />
        {open && filtered.length > 0 ? (
          <ul
            className="absolute z-20 left-0 right-0 mt-1 rounded-md border max-h-48 overflow-y-auto shadow-lg"
            style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface, #fff)' }}
            data-testid="equipment-dropdown"
          >
            {filtered.map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  onMouseDown={(ev) => { ev.preventDefault(); addEquipment(e); }}
                  className="w-full text-left px-3 py-1.5 text-sm hover:bg-black/5"
                  data-testid={`equipment-option-${e.id}`}
                >
                  <span className="font-bold">{e.name}</span>
                  {e.serial_number ? <span className="opacity-60 text-xs"> · {e.serial_number}</span> : null}
                  {e.equipment_type ? <span className="opacity-60 text-xs"> · {e.equipment_type}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={manualSerial}
          onChange={(e) => setManualSerial(e.target.value)}
          placeholder="Add serial manually (no record yet)"
          className="flex-1 px-3 py-1.5 rounded-md border bg-transparent text-xs"
          style={{ borderColor: 'var(--theme-border)' }}
          data-testid="equipment-manual-serial"
        />
        <button
          type="button"
          onClick={addManualSerial}
          disabled={!manualSerial.trim()}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-bold border disabled:opacity-50"
          style={{ borderColor: 'var(--theme-border)' }}
          data-testid="equipment-add-manual"
        >
          <Plus size={11} /> Add
        </button>
      </div>
    </div>
  );
}
