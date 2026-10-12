// Cross-department visibility grant (Owners / Master Admins / HR only).
// Lets a manager or team lead see staff in extra departments without HR status.
// Site limits still apply to granted departments.
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Check, Eye, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function DeptVisibilityPanel({ staffId, headers, departments = [], ownDepartment, grant, onSaved }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(!!grant?.all);
  const [picked, setPicked] = useState(grant?.departments || []);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setAll(!!grant?.all);
    setPicked(grant?.departments || []);
    setSaved(false);
  }, [staffId, grant]);

  const toggle = (d) => setPicked((p) => (p.includes(d) ? p.filter((x) => x !== d) : [...p, d]));

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/staffing/staff/${staffId}/dept-visibility`,
        { all_departments: all, departments: all ? [] : picked }, { headers });
      setSaved(true);
      onSaved && onSaved();
    } catch (e) {
      window.alert(e?.response?.data?.detail || t('staffing.hr_dept_vis_failed', 'Could not save department visibility'));
    }
    setSaving(false);
  };

  const options = departments.filter((d) => d !== ownDepartment);

  return (
    <div className="md:col-span-2 mt-3 pt-3 border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid="dept-visibility-panel">
      <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-1 inline-flex items-center gap-1.5" style={{ color: 'var(--color-brand-cyan)' }}>
        <Eye size={11} /> {t('staffing.hr_dept_vis', 'Department visibility')}
      </p>
      <p className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>
        {t('staffing.hr_dept_vis_hint', 'Let this person see staff in other departments without HR status. Their own site limits still apply.')}
        {ownDepartment && <> {t('staffing.hr_dept_vis_own', 'Own department:')} <b data-testid="dept-visibility-own">{ownDepartment}</b>.</>}
      </p>
      <label className="flex items-center gap-2 mb-3 text-sm cursor-pointer" style={{ color: 'var(--theme-text)' }}>
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} data-testid="dept-visibility-all-toggle" />
        {t('staffing.hr_dept_vis_all', 'All departments')}
      </label>
      <div className={`flex flex-wrap gap-1.5 ${all ? 'opacity-40 pointer-events-none' : ''}`} data-testid="dept-visibility-options">
        {options.map((d) => {
          const on = picked.includes(d);
          return (
            <button key={d} type="button" onClick={() => toggle(d)}
              className="h-7 rounded-full px-3 text-[11px] font-bold border transition-colors"
              style={on
                ? { borderColor: 'var(--color-brand-cyan)', background: 'rgba(25,205,255,0.15)', color: 'var(--color-brand-cyan)' }
                : { borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
              data-testid={`dept-visibility-opt-${d.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
              {d}
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button type="button" onClick={save} disabled={saving}
          className="h-8 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="dept-visibility-save">
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          {t('staffing.hr_dept_vis_save', 'Save visibility')}
        </button>
        {saved && <span className="text-[11px]" style={{ color: '#059669' }} data-testid="dept-visibility-saved">{t('staffing.hr_saved', 'Saved')}</span>}
      </div>
    </div>
  );
}
