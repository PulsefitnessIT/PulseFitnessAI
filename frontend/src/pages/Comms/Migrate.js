/**
 * Migrate — ESP migration / CSV import for the Comms Centre.
 * Upload any ESP export (Mailchimp/Klaviyo/generic), auto-map columns,
 * import contacts and carry over unsubscribe status to the suppression list.
 */
import React, { useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Upload, FileSpreadsheet, ArrowRight, CheckCircle2, Loader2, ShieldOff, UserPlus, RefreshCw, SkipForward } from 'lucide-react';

const FIELDS = [
  { key: 'email', label: 'Email address', required: true },
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'company', label: 'Company' },
  { key: 'status', label: 'Subscription status' },
];

export function MigrateView({ API, headers }) {
  const apiRoot = (API || process.env.REACT_APP_BACKEND_URL || '').replace(/\/api\/?$/, '');
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);

  const onPick = async (f) => {
    if (!f) return;
    setFile(f); setSummary(null); setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const r = await axios.post(`${apiRoot}/api/comms/import/preview`, fd, { headers });
      setPreview(r.data);
      setMapping(r.data.suggested_mapping || {});
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not read that file');
      setPreview(null);
    } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!mapping.email) { toast.error('Map the email column first'); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('mapping', JSON.stringify(mapping));
      const r = await axios.post(`${apiRoot}/api/comms/import/commit`, fd, { headers });
      setSummary(r.data);
      toast.success('Import complete');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Import failed');
    } finally { setBusy(false); }
  };

  const reset = () => { setFile(null); setPreview(null); setMapping({}); setSummary(null); if (fileRef.current) fileRef.current.value = ''; };

  const card = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' };
  const input = { background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

  if (summary) {
    const stats = [
      { label: 'Created', value: summary.created, icon: UserPlus, color: '#10b981' },
      { label: 'Updated', value: summary.updated, icon: RefreshCw, color: '#06b6d4' },
      { label: 'Suppressed', value: summary.suppressed, icon: ShieldOff, color: '#f59e0b' },
      { label: 'Skipped', value: summary.skipped, icon: SkipForward, color: '#94a3b8' },
    ];
    return (
      <div data-testid="migrate-summary">
        <div className="rounded-2xl border p-8 text-center" style={card}>
          <CheckCircle2 size={40} className="mx-auto mb-3 text-emerald-500" />
          <h3 className="text-lg font-bold" style={{ color: 'var(--theme-text)' }}>Import complete</h3>
          <p className="text-sm mb-6" style={{ color: 'var(--theme-text-muted)' }}>{summary.total} rows processed from your export.</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl mx-auto">
            {stats.map((s) => (
              <div key={s.label} className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)' }}>
                <s.icon size={18} style={{ color: s.color }} className="mx-auto mb-1" />
                <div className="text-2xl font-bold" style={{ color: 'var(--theme-text)' }} data-testid={`migrate-stat-${s.label.toLowerCase()}`}>{s.value}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.label}</div>
              </div>
            ))}
          </div>
          <button onClick={reset} className="mt-6 px-4 py-2 rounded-full text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="migrate-again">Import another file</button>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="comms-migrate">
      <div className="rounded-2xl border p-5 mb-4" style={card}>
        <p className="text-sm mb-3" style={{ color: 'var(--theme-text-muted)' }}>
          Moving from Mailchimp, Klaviyo or another tool? Export your audience as CSV and drop it here — we'll map the columns, import your contacts and honour anyone who'd already unsubscribed.
        </p>
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => onPick(e.target.files?.[0])} data-testid="migrate-file-input" />
        <button onClick={() => fileRef.current?.click()} disabled={busy} className="w-full rounded-xl border-2 border-dashed py-10 flex flex-col items-center gap-2 hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors disabled:opacity-50" style={{ borderColor: 'var(--theme-border)' }} data-testid="migrate-upload-btn">
          {busy && !preview ? <Loader2 size={26} className="animate-spin text-cyan-500" /> : <Upload size={26} style={{ color: 'var(--theme-text-muted)' }} />}
          <span className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{file ? file.name : 'Choose a CSV file'}</span>
          <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{file ? 'Click to replace' : 'Up to ~50k rows'}</span>
        </button>
      </div>

      {preview && (
        <div className="rounded-2xl border p-5" style={card} data-testid="migrate-mapping">
          <div className="flex items-center gap-2 mb-1"><FileSpreadsheet size={16} style={{ color: 'var(--theme-text)' }} /><h3 className="font-bold" style={{ color: 'var(--theme-text)' }}>Map your columns</h3></div>
          <p className="text-xs mb-4" style={{ color: 'var(--theme-text-muted)' }}>{preview.total_rows} rows · {preview.columns.length} columns detected. We auto-matched what we could.</p>
          <div className="grid sm:grid-cols-2 gap-3 mb-5">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label className="block text-[11px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{f.label}{f.required && <span className="text-rose-500"> *</span>}</label>
                <select value={mapping[f.key] || ''} onChange={(e) => setMapping((m) => ({ ...m, [f.key]: e.target.value || null }))} className="w-full px-3 py-2 rounded-lg border text-sm" style={input} data-testid={`migrate-map-${f.key}`}>
                  <option value="">— Not mapped —</option>
                  {preview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            ))}
          </div>
          <p className="text-xs mb-4 rounded-lg p-2.5" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text-muted)' }}>
            Tip: map <strong>Subscription status</strong> so unsubscribed/cleaned contacts are added to your suppression list automatically.
          </p>
          <button onClick={commit} disabled={busy || !mapping.email} className="flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-bold disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink, #03212b)' }} data-testid="migrate-commit">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}Import {preview.total_rows} contacts
          </button>
        </div>
      )}
    </div>
  );
}
