/**
 * TeamAccessTab — Line Manager grants their direct reports access to the
 * organisation's modules (System Access Provisioning, step 2).
 * HR assigns the line manager in Staff Onboarding; the assigned manager
 * approves module access here. Backed by /api/staffing/access/*.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, ShieldCheck, CheckCircle2, Users } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TeamAccessTab({ headers }) {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState('');

  const load = useCallback(() => {
    axios.get(`${API}/staffing/access/my-reports`, { headers })
      .then((r) => setData(r.data)).catch(() => setData({ reports: [], available_modules: [] }));
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const toggle = async (report, key) => {
    const current = new Set(report.granted_modules || []);
    if (current.has(key)) current.delete(key); else current.add(key);
    const modules = Array.from(current);
    setSaving(report.staff_id);
    try {
      await axios.post(`${API}/staffing/access/reports/${report.staff_id}/modules`, { modules }, { headers });
      setData((d) => ({ ...d, reports: d.reports.map((r) => r.staff_id === report.staff_id ? { ...r, granted_modules: modules, status: 'granted' } : r) }));
    } finally { setSaving(''); }
  };

  if (!data) return <div className="p-6"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text)' }} /></div>;
  const mods = data.available_modules || [];

  return (
    <div className="space-y-4" data-testid="team-access-tab">
      <div className="rounded-2xl p-4 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center gap-2 mb-1"><ShieldCheck size={16} style={{ color: 'var(--theme-accent, #19CDFF)' }} /><h3 className="font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>Team system access</h3></div>
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Grant your direct reports access to the modules your organisation uses. HR assigns you as the line manager during onboarding.</p>
      </div>

      {(data.reports || []).length === 0 ? (
        <div className="rounded-2xl p-10 border text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="team-access-empty">
          <Users size={22} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
          <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>No direct reports yet</div>
          <div className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>HR assigns team members to you in Staff Onboarding → Activate.</div>
        </div>
      ) : (
        <div className="space-y-3">
          {data.reports.map((r) => (
            <div key={r.staff_id} className="rounded-2xl p-4 border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`team-access-report-${r.staff_id}`}>
              <div className="flex items-center justify-between gap-3 mb-3">
                <div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{r.full_name}</div>
                  <div className="text-xs capitalize" style={{ color: 'var(--theme-text-muted)' }}>{(r.role || 'staff')}{r.department ? ` · ${r.department}` : ''}</div>
                </div>
                {saving === r.staff_id && <Loader2 size={16} className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} />}
                {r.status === 'granted' && saving !== r.staff_id && <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-500"><CheckCircle2 size={13} /> Provisioned</span>}
              </div>
              <div className="flex flex-wrap gap-2">
                {mods.length === 0 && <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No modules available on your plan.</span>}
                {mods.map((m) => {
                  const on = (r.granted_modules || []).includes(m.key);
                  return (
                    <button key={m.key} onClick={() => toggle(r, m.key)} data-testid={`team-access-toggle-${r.staff_id}-${m.key}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors"
                      style={on
                        ? { background: '#19CDFF', color: '#0B1220', borderColor: '#19CDFF' }
                        : { background: 'transparent', color: 'var(--theme-text-muted)', borderColor: 'var(--theme-border)' }}>
                      {on && <CheckCircle2 size={12} />} {m.label}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
