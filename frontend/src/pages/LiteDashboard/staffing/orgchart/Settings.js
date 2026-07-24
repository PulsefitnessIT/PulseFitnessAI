/** Org Chart — chart settings (display toggles, layout, rename, delete). */
import { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
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
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>{t('orgchart.set_chart_name', 'Chart name')}</h4>
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} className="flex-1 px-3 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-name" />
          <button onClick={() => onRename(name)} className="px-4 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-settings-rename">{t('orgchart.set_save', 'Save')}</button>
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>{t('orgchart.set_card_fields', 'Card fields')}</h4>
        <div className="grid sm:grid-cols-2 gap-2">
          {FIELD_TOGGLES.map(([k, lbl]) => (
            <Toggle key={k} on={!!toggles[k]} label={t(`orgchart.field_${k}`, lbl)} onClick={() => setToggle(k)} testId={`orgchart-toggle-${k}`} />
          ))}
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold mb-3" style={{ color: 'var(--theme-text)' }}>{t('orgchart.set_layout_grouping', 'Layout & grouping')}</h4>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.set_direction', 'Direction')}</span>
            <select value={s.layout || 'vertical'} onChange={(e) => setKey('layout', e.target.value)} className="mt-1 w-full px-2 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-layout">
              <option value="vertical">{t('orgchart.set_dir_vertical', 'Vertical (stacked)')}</option>
              <option value="top-down">{t('orgchart.set_dir_topdown', 'Top-down')}</option>
              <option value="left-right">{t('orgchart.set_dir_leftright', 'Left-to-right')}</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.set_group_by', 'Group by')}</span>
            <select value={s.group_by || 'none'} onChange={(e) => setKey('group_by', e.target.value)} className="mt-1 w-full px-2 py-2 rounded-lg text-sm border outline-none" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg,#fff)', color: 'var(--theme-text)' }} data-testid="orgchart-settings-groupby">
              <option value="none">{t('orgchart.set_group_none', 'None')}</option>
              <option value="department">{t('orgchart.field_department', 'Department')}</option>
              <option value="site">{t('orgchart.field_site', 'Site')}</option>
            </select>
          </label>
          <div className="flex items-end">
            <Toggle on={!!s.show_grid} label={t('orgchart.set_show_grid', 'Show grid')} onClick={() => setKey('show_grid', !s.show_grid)} testId="orgchart-toggle-grid" />
          </div>
        </div>
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: '#fca5a5' }}>
        <h4 className="text-sm font-bold mb-1" style={{ color: '#dc2626' }}>{t('orgchart.set_danger_zone', 'Danger zone')}</h4>
        <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.set_danger_desc', 'Deleting this chart removes its cards. Linked staff records are not affected.')}</p>
        {!confirming ? (
          <button onClick={() => setConfirming(true)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border" style={{ borderColor: '#fca5a5', color: '#dc2626' }} data-testid="orgchart-delete-chart"><Trash2 size={13} /> {t('orgchart.set_delete_chart', 'Delete chart')}</button>
        ) : (
          <div className="flex gap-2">
            <button onClick={async () => { setDeleting(true); await onDelete(); }} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold" style={{ background: '#dc2626', color: '#fff' }} data-testid="orgchart-delete-confirm">
              {deleting ? <Loader2 size={13} className="animate-spin" /> : null} {t('orgchart.set_yes_delete', 'Yes, delete')}
            </button>
            <button onClick={() => setConfirming(false)} className="px-3 py-2 rounded-lg text-xs font-semibold" style={{ color: 'var(--theme-text-muted)' }}>{t('orgchart.set_cancel', 'Cancel')}</button>
          </div>
        )}
      </div>
    </div>
  );
}
