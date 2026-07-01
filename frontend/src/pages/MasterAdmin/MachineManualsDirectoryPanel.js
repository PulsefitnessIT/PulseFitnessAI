/**
 * Master Admin → Governance → Machine Manuals directory (Iter 376).
 * Cross-org view of the shared machine-manual library. Manuals are uploaded
 * once by operators, auto-linked to every machine of the same make/model,
 * and de-duplicated by file hash.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { FileText, Download, Trash2, Search, Loader2, Layers, Globe, UploadCloud } from 'lucide-react';

export default function MachineManualsDirectoryPanel() {
  const [manuals, setManuals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [gForm, setGForm] = useState({ manufacturer: '', model: '', title: '' });
  const [uploadingGlobal, setUploadingGlobal] = useState(false);
  const gFileRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/master-admin/machine-manuals/directory');
      setManuals(r.data?.manuals || []);
    } catch { notify.error('Failed to load manual directory'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return manuals;
    return manuals.filter((m) =>
      [m.title, m.manufacturer, m.model, m.organization_name].some((v) => (v || '').toLowerCase().includes(t)));
  }, [manuals, q]);

  const download = async (m) => {
    try {
      const r = await api.get(`/machine-manuals/${m.id}/download`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: m.content_type || 'application/pdf' }));
      window.open(url, '_blank');
      setTimeout(() => window.URL.revokeObjectURL(url), 30000);
    } catch { notify.error('Failed to open manual'); }
  };

  const remove = async (m) => {
    if (!window.confirm(`Delete "${m.title}"? It will be unlinked from ${m.linked_count} machine(s).`)) return;
    try {
      await api.delete(`/machine-manuals/${m.id}`);
      setManuals((prev) => prev.filter((x) => x.id !== m.id));
      notify.success('Manual deleted');
    } catch { notify.error('Failed to delete'); }
  };

  const promote = async (m) => {
    setBusyId(m.id);
    try {
      const r = await api.post(`/master-admin/machine-manuals/${m.id}/promote-global`);
      notify.success(r.data?.already_global ? 'Already in the global library' : `"${m.title}" promoted to the platform-global library`);
      await load();
    } catch { notify.error('Failed to promote manual'); } finally { setBusyId(null); }
  };

  const uploadGlobal = async (file) => {
    if (!file) return;
    if (!gForm.manufacturer.trim() || !gForm.model.trim()) { notify.error('Enter a manufacturer and model first'); return; }
    setUploadingGlobal(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('manufacturer', gForm.manufacturer.trim());
      fd.append('model', gForm.model.trim());
      fd.append('title', gForm.title.trim() || file.name);
      const r = await api.post('/master-admin/machine-manuals/global/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      notify.success(r.data?.reused ? 'That global manual already exists' : 'Global manual added');
      setGForm({ manufacturer: '', model: '', title: '' });
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Failed to upload global manual');
    } finally { setUploadingGlobal(false); }
  };

  return (
    <div className="space-y-4" data-testid="machine-manuals-directory">
      {/* Upload a platform-curated global manual */}
      <div className="rounded-lg border border-[var(--theme-border)] p-3 bg-[var(--theme-surface)]" data-testid="global-manual-upload">
        <div className="flex items-center gap-1.5 mb-2 text-sm font-semibold text-[var(--theme-text)]">
          <Globe size={14} className="text-[var(--color-brand-blue)]" /> Add a platform-global manual
        </div>
        <p className="text-xs text-[var(--color-text-muted)] mb-2">Curated manuals are offered to every organisation that owns a machine of this make &amp; model.</p>
        <div className="flex flex-wrap items-center gap-2">
          <input value={gForm.manufacturer} onChange={(e) => setGForm((f) => ({ ...f, manufacturer: e.target.value }))} placeholder="Manufacturer" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] w-40" data-testid="global-manufacturer" />
          <input value={gForm.model} onChange={(e) => setGForm((f) => ({ ...f, model: e.target.value }))} placeholder="Model" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] w-40" data-testid="global-model" />
          <input value={gForm.title} onChange={(e) => setGForm((f) => ({ ...f, title: e.target.value }))} placeholder="Title (optional)" className="px-2.5 py-1.5 rounded-md border text-sm bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] flex-1 min-w-[160px]" data-testid="global-title" />
          <input ref={gFileRef} type="file" accept=".pdf,.doc,.docx,image/*" className="hidden" onChange={(e) => { uploadGlobal(e.target.files?.[0]); e.target.value = ''; }} data-testid="global-file-input" />
          <button onClick={() => gFileRef.current?.click()} disabled={uploadingGlobal} className="px-3 py-1.5 rounded-md text-sm font-medium bg-[var(--color-brand-blue)] text-white inline-flex items-center gap-1.5 disabled:opacity-60" data-testid="global-upload-btn">
            {uploadingGlobal ? <Loader2 size={13} className="animate-spin" /> : <UploadCloud size={13} />} Upload
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search manufacturer, model, org…"
            className="w-full pl-8 pr-3 py-2 rounded-md border text-sm bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)]"
            data-testid="manual-directory-search"
          />
        </div>
        <span className="text-xs text-[var(--color-text-muted)]">{filtered.length} manual{filtered.length === 1 ? '' : 's'}</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-[var(--color-text-muted)]"><Loader2 className="animate-spin" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-sm text-[var(--color-text-muted)]">
          <Layers className="mx-auto mb-2 opacity-40" size={28} />
          No machine manuals uploaded yet.
        </div>
      ) : (
        <div className="rounded-lg border border-[var(--theme-border)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--theme-surface-2)] text-left text-xs text-[var(--color-text-muted)]">
                <th className="px-3 py-2 font-semibold">Manual</th>
                <th className="px-3 py-2 font-semibold">Make / Model</th>
                <th className="px-3 py-2 font-semibold">Organisation</th>
                <th className="px-3 py-2 font-semibold text-center">Linked</th>
                <th className="px-3 py-2 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => (
                <tr key={m.id} className="border-t border-[var(--theme-border)]" data-testid={`directory-manual-${m.id}`}>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText size={13} className="text-[var(--color-brand-blue)] shrink-0" />
                      <span className="text-[var(--theme-text)] truncate">{m.title}</span>
                      {m.is_global && (
                        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-[var(--color-brand-blue)]/10 text-[var(--color-brand-blue)] shrink-0" data-testid={`directory-global-badge-${m.id}`}>
                          <Globe size={9} /> Global
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-[var(--color-text-muted)]">{m.manufacturer} · {m.model}</td>
                  <td className="px-3 py-2 text-[var(--color-text-muted)]">{m.organization_name}</td>
                  <td className="px-3 py-2 text-center">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-[var(--color-brand-blue)]/10 text-[var(--color-brand-blue)]">{m.linked_count}</span>
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {!m.is_global && (
                      <button onClick={() => promote(m)} disabled={busyId === m.id} className="h-7 px-2 rounded text-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue)]/10 inline-flex items-center gap-1 text-[11px] font-medium disabled:opacity-50" title="Promote to platform-global library" data-testid={`directory-promote-${m.id}`}>
                        {busyId === m.id ? <Loader2 size={12} className="animate-spin" /> : <Globe size={12} />} Make global
                      </button>
                    )}
                    <button onClick={() => download(m)} className="h-7 w-7 rounded text-[var(--color-text-muted)] hover:text-[var(--theme-text)] inline-flex items-center justify-center" title="Open" data-testid={`directory-download-${m.id}`}><Download size={13} /></button>
                    <button onClick={() => remove(m)} className="h-7 w-7 rounded text-[var(--color-text-muted)] hover:text-red-500 inline-flex items-center justify-center" title="Delete" data-testid={`directory-delete-${m.id}`}><Trash2 size={13} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
