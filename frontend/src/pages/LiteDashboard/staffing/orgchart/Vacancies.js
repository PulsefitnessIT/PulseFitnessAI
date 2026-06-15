/** Org Chart — vacancies / open roles manager. */
import { UserPlus, Plus } from 'lucide-react';
import { VACANCY_STAGES, humanize } from './api';

const STAGE_COLOR = {
  Planned: '#64748b', Approved: '#2563eb', Recruiting: '#0891b2', Interviewing: '#7c3aed',
  'Offer Made': '#ca8a04', Filled: '#16a34a', 'On Hold': '#ea580c', Cancelled: '#dc2626',
};

export default function Vacancies({ nodes, byId, onOpen, onAdd, onUpdate }) {
  const vacancies = nodes.filter((n) => n.type === 'vacancy');
  return (
    <div data-testid="orgchart-vacancies">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{vacancies.length} open role{vacancies.length === 1 ? '' : 's'}</p>
        <button onClick={onAdd} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-vacancy-add">
          <Plus size={14} /> New vacancy
        </button>
      </div>
      {!vacancies.length ? (
        <div className="rounded-2xl p-10 border text-center" style={{ borderColor: 'var(--theme-border)' }}>
          <UserPlus size={22} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>No open roles</p>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Add a vacancy to plan ahead and spot staffing gaps.</p>
        </div>
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {vacancies.map((v) => (
            <div key={v.id} className="rounded-2xl border p-3.5" style={{ borderColor: 'var(--theme-border)', borderLeft: '4px solid #ea580c' }} data-testid={`orgchart-vacancy-${v.id}`}>
              <button onClick={() => onOpen(v)} className="text-left w-full">
                <div className="text-sm font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{v.full_name}</div>
                <div className="text-[11px] mb-2" style={{ color: 'var(--theme-text-muted)' }}>
                  {humanize(v.job_title) || 'Open role'}{v.department ? ` · ${v.department}` : ''}{v.site_name ? ` · ${v.site_name}` : ''}
                </div>
              </button>
              <div className="flex items-center justify-between gap-2">
                <select
                  value={v.recruitment_stage || 'Planned'}
                  onChange={(e) => onUpdate(v.id, { recruitment_stage: e.target.value })}
                  className="text-[11px] font-semibold px-2 py-1 rounded-md border outline-none"
                  style={{ color: STAGE_COLOR[v.recruitment_stage] || '#64748b', borderColor: 'var(--theme-border)', background: 'var(--theme-bg, #fff)' }}
                  data-testid={`orgchart-vacancy-stage-${v.id}`}
                >
                  {VACANCY_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                {byId[v.manager_node_id] && (
                  <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>↳ {byId[v.manager_node_id].full_name}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
