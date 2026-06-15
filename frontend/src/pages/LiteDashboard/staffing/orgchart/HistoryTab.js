/** Org Chart — version history + audit trail. */
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { History, Save, RotateCcw, Clock, Loader2, ShieldCheck } from 'lucide-react';
import { ocApi } from './api';

const ACTION_LABEL = {
  card_added: 'Card added', card_edited: 'Card edited', card_removed: 'Card removed',
  reporting_changed: 'Reporting line changed', import: 'Import', template_applied: 'Template applied',
  version_saved: 'Version saved', version_restored: 'Version restored', edge_added: 'Secondary line added',
};

function ago(iso) {
  try {
    const d = new Date(iso); const s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return d.toLocaleDateString();
  } catch { return ''; }
}

export default function HistoryTab({ chartId, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [restoringId, setRestoringId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [v, a] = await Promise.all([ocApi.listVersions(chartId), ocApi.audit(chartId)]);
      setVersions(v.versions || []); setAudit(a.audit || []);
    } finally { setLoading(false); }
  }, [chartId]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try { await ocApi.saveVersion(chartId, null); toast.success('Snapshot saved'); await load(); }
    catch { toast.error('Save failed'); } finally { setSaving(false); }
  };
  const restore = async (vid) => {
    setRestoringId(vid);
    try { await ocApi.restoreVersion(chartId, vid); toast.success('Version restored'); await load(); onRestored?.(); }
    catch { toast.error('Restore failed'); } finally { setRestoringId(null); }
  };

  if (loading) return <div className="py-10 flex justify-center"><Loader2 className="animate-spin" style={{ color: 'var(--theme-text-muted)' }} /></div>;

  return (
    <div className="grid md:grid-cols-2 gap-4" data-testid="orgchart-history">
      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-bold inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><History size={15} /> Versions</h4>
          <button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-version-save">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save snapshot
          </button>
        </div>
        {!versions.length ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--theme-text-muted)' }}>No saved versions yet. Save a snapshot before big restructures.</p>
        ) : (
          <div className="space-y-2">
            {versions.map((v) => (
              <div key={v.id} className="flex items-center justify-between gap-2 rounded-xl border p-2.5" style={{ borderColor: 'var(--theme-border)' }} data-testid={`orgchart-version-${v.id}`}>
                <div className="min-w-0">
                  <div className="text-xs font-semibold truncate" style={{ color: 'var(--theme-text)' }}>v{v.version} · {v.label}</div>
                  <div className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{v.node_count} cards · {ago(v.created_at)} · {v.actor}</div>
                </div>
                <button onClick={() => restore(v.id)} disabled={restoringId === v.id} className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold border flex-shrink-0" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`orgchart-version-restore-${v.id}`}>
                  {restoringId === v.id ? <Loader2 size={11} className="animate-spin" /> : <RotateCcw size={11} />} Restore
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
        <h4 className="text-sm font-bold inline-flex items-center gap-2 mb-3" style={{ color: 'var(--theme-text)' }}><ShieldCheck size={15} /> Audit trail</h4>
        {!audit.length ? (
          <p className="text-xs py-4 text-center" style={{ color: 'var(--theme-text-muted)' }}>No activity recorded yet.</p>
        ) : (
          <div className="space-y-1.5 max-h-[60vh] overflow-y-auto" data-testid="orgchart-audit-list">
            {audit.map((e) => (
              <div key={e.id} className="flex items-start gap-2 text-xs">
                <Clock size={12} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--theme-text-muted)' }} />
                <div className="min-w-0">
                  <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{ACTION_LABEL[e.action] || e.action}</span>
                  {e.detail ? <span style={{ color: 'var(--theme-text-muted)' }}> — {e.detail}</span> : null}
                  <div className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{e.actor} · {ago(e.at)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
