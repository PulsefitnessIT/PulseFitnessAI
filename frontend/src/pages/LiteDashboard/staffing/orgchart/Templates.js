/** Org Chart — starter templates picker. */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { LayoutTemplate, Loader2, Plus } from 'lucide-react';
import { ocApi } from './api';

export default function Templates({ chartId, onApplied }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [applyingId, setApplyingId] = useState(null);

  useEffect(() => { ocApi.listTemplates().then((r) => setTemplates(r.templates || [])).finally(() => setLoading(false)); }, []);

  const apply = async (tid, name) => {
    setApplyingId(tid);
    try { const r = await ocApi.applyTemplate(chartId, tid); toast.success(`Added ${r.added} roles from "${name}"`); onApplied?.(); }
    catch { toast.error('Could not apply template'); } finally { setApplyingId(null); }
  };

  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} /></div>;

  return (
    <div data-testid="orgchart-templates">
      <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>Templates add example placeholder roles + reporting lines to the current chart. Edit or link them to real staff afterwards.</p>
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {templates.map((t) => (
          <div key={t.id} className="rounded-2xl border p-4 flex flex-col justify-between" style={{ borderColor: 'var(--theme-border)' }} data-testid={`orgchart-template-${t.id}`}>
            <div>
              <LayoutTemplate size={18} style={{ color: 'var(--color-brand-cyan)' }} className="mb-2" />
              <div className="text-sm font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t.name}</div>
              <div className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>{t.roles} starter roles</div>
            </div>
            <button onClick={() => apply(t.id, t.name)} disabled={applyingId === t.id} className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid={`orgchart-template-apply-${t.id}`}>
              {applyingId === t.id ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Use template
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
