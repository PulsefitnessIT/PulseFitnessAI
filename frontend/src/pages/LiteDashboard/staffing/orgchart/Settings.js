/** Org Chart — chart settings (display toggles, layout, rename, delete). */
import { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';

const FIELD_TOGGLES = [
  ['photo', 'Avatars'], ['department', 'Department'], ['site', 'Site'],
  ['email', 'Email'], ['phone', 'Phone'], ['employment_type', 'Employment type'],
  ['reports_count', 'Direct reports count'], ['status', 'Status'],
];

function Toggle({ on, onClick, label, testId }) {
  return (
    <button onClick={onClick} data-testid={testId}
      className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border text-sm w-full"
      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
      <span>{label}</span>
      <span className="relative inline-block w-9 h-5 rounded-full transition-colors" style={{ background: on ? 'var(--color-brand-cyan)' : 'var(--theme-border)' }}>
        <span className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: on ? 18 : 2 }} />
      </span>
    </button>
  );
}

export default function Settings({ chart, onSave, onRename, onDelete }) {
  const s = chart.settings || {};
  const [name, setName] = useState(chart.name);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const toggles = s.field_toggles || {};
  const setToggle = (k) => onSave({ ...s, field_toggles: { ...toggles, [k]: !toggles[k] } });
  const setKey = (k, v) => onSave({ ...s, [k]: v });

  return (
    <div className="space-y-5 max-w-2xl" data-testid="orgchart-settings">
      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>Chart name</h4>
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} className="flex-1 px-3 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-name" />
          <button onClick={() => onRename(name)} className="px-4 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-settings-rename">Save</button>
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>Card fields</h4>
        <div className="grid sm:grid-cols-2 gap-2">
          {FIELD_TOGGLES.map(([k, lbl]) => (
            <Toggle key={k} on={!!toggles[k]} label={lbl} onClick={() => setToggle(k)} testId={`orgchart-toggle-${k}`} />
          ))}
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>Layout & grouping</h4>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Direction</span>
            <select value={s.layout || 'vertical'} onChange={(e) => setKey('layout', e.target.value)} className="mt-1 w-full px-2 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-layout">
              <option value="vertical">Vertical (stacked)</option>
              <option value="top-down">Top-down</option>
              <option value="left-right">Left-to-right</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Group by</span>
            <select value={s.group_by || 'none'} onChange={(e) => setKey('group_by', e.target.value)} className="mt-1 w-full px-2 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-groupby">
              <option value="none">None</option>
              <option value="department">Department</option>
              <option value="site">Site</option>
            </select>
          </label>
          <div className="flex items-end">
            <Toggle on={!!s.show_grid} label="Show grid" onClick={() => setKey('show_grid', !s.show_grid)} testId="orgchart-toggle-grid" />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: '#fca5a5' }}>
        <h4 className="text-sm font-bold mb-1" style={{ color: '#dc2626' }}>Danger zone</h4>
        <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>Deleting this chart removes its cards. Linked staff records are not affected.</p>
        {!confirming ? (
          <button onClick={() => setConfirming(true)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: '#fca5a5', color: '#dc2626' }} data-testid="orgchart-delete-chart"><Trash2 size={13} /> Delete chart</button>
        ) : (
          <div className="flex gap-2">
            <button onClick={async () => { setDeleting(true); await onDelete(); }} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold" style={{ background: '#dc2626', color: '#fff' }} data-testid="orgchart-delete-confirm">
              {deleting ? <Loader2 size={13} className="animate-spin" /> : null} Yes, delete
            </button>
            <button onClick={() => setConfirming(false)} className="px-3 py-2 rounded-lg text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  );
}
