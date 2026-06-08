/**
 * Master Admin → Support → Documents library.
 *
 * Unified store for everything we generate (invoice PDFs, audit exports,
 * onboarding packets) plus everything master admin manually uploads
 * (DPAs, signed contracts, NDAs, supplier certs).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
  FileText, Upload, Download, Trash2, Search, Loader2, Sparkles,
  Receipt, FileSignature, Shield, Briefcase, FolderArchive, FileBox,
  RefreshCw, X, Zap, Send,
} from 'lucide-react';

const CATEGORY_META = {
  invoice:    { label: 'Invoice',    icon: Receipt,        tone: 'emerald' },
  contract:   { label: 'Contract',   icon: FileSignature,  tone: 'sky' },
  dpa:        { label: 'DPA / GDPR', icon: Shield,         tone: 'violet' },
  audit:      { label: 'Audit',      icon: Sparkles,       tone: 'amber' },
  onboarding: { label: 'Onboarding', icon: Briefcase,      tone: 'rose' },
  compliance: { label: 'Compliance', icon: Shield,         tone: 'indigo' },
  other:      { label: 'Other',      icon: FileBox,        tone: 'zinc' },
};

const TONE_BG = {
  emerald: 'bg-emerald-100 text-emerald-700',
  sky:     'bg-sky-100 text-sky-700',
  violet:  'bg-violet-100 text-violet-700',
  amber:   'bg-amber-100 text-amber-700',
  rose:    'bg-rose-100 text-rose-700',
  indigo:  'bg-indigo-100 text-indigo-700',
  zinc:    'bg-zinc-100 text-zinc-700',
};

/**
 * Props:
 *   • `orgId` — when provided, the panel is rendered inside an org detail
 *     view and is scoped to that org's documents only.
 */
export default function DocumentsPanel({ orgId } = {}) {
  const { API } = useAuth();
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [scopeFilter, setScopeFilter] = useState(orgId ? 'org' : 'all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [showUpload, setShowUpload] = useState(false);
  const [showSendPager, setShowSendPager] = useState(null); // 'sales' | 'trust' | null

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (orgId) {
        params.set('organization_id', orgId);
      } else if (scopeFilter !== 'all') {
        params.set('scope', scopeFilter);
      }
      if (categoryFilter !== 'all') params.set('category', categoryFilter);
      if (search.trim()) params.set('q', search.trim());
      const r = await axios.get(`${API}/master-admin/document-library?${params}`, { headers });
      setDocs(r.data?.documents || []);
    } catch (e) {
      notify.error('Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, [API, headers, orgId, scopeFilter, categoryFilter, search]);

  useEffect(() => { load(); }, [load]);

  const downloadDoc = async (doc) => {
    try {
      const r = await axios.get(
        `${API}/master-admin/document-library/${doc.id}/download`,
        { headers, responseType: 'blob' },
      );
      const blob = new Blob([r.data], { type: doc.content_type || 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename || `${doc.title}.bin`;
      // Anchor MUST be in the DOM for the click to trigger a download
      // in Firefox / Safari. Revoke the object URL on the next tick so
      // the browser has time to start the transfer.
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      notify.error('Download failed');
    }
  };

  const deleteDoc = async (doc) => {
    if (!window.confirm(`Delete "${doc.title}"? This cannot be undone.`)) return;
    try {
      await axios.delete(`${API}/master-admin/document-library/${doc.id}`, { headers });
      notify.success('Document deleted');
      load();
    } catch (e) {
      notify.error('Delete failed');
    }
  };

  const downloadPulsePager = async (kind) => {
    try {
      const r = await axios.get(
        `${API}/master-admin/sales-pack/${kind}`,
        { headers, responseType: 'blob' },
      );
      const blob = new Blob([r.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pulse-fitness-${kind}-1-pager.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify.success(`Pulse ${kind === 'sales' ? 'sales' : 'trust'} 1-pager downloaded`);
      load();
    } catch (e) {
      notify.error(`${kind === 'sales' ? 'Sales' : 'Trust'} 1-pager download failed`);
    }
  };

  const generatePulsePack = async () => {
    try {
      await axios.post(`${API}/master-admin/sales-pack/generate-all`, {}, { headers });
      notify.success('Pulse Fitness 1-pagers regenerated');
      load();
    } catch (e) {
      notify.error('Pulse pack generation failed');
    }
  };

  return (
    <div data-testid="documents-panel" className="space-y-5">
      {/* ── Pulse Fitness quick-pack banner (platform scope only) ── */}
      {!orgId && (
        <div
          className="p-4 rounded-xl border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
          data-testid="documents-pulse-pack-banner"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-50 flex items-center justify-center text-cyan-600 flex-shrink-0">
              <Zap size={18} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">Pulse Fitness — meeting handouts</div>
              <div className="text-xs text-slate-500 mt-0.5">
                Brand-headed A4 PDFs. Print &amp; hand out, send by email with a tracked link, or auto-save to this library.
              </div>
            </div>
            <button
              onClick={generatePulsePack}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50"
              title="Re-generate both PDFs and refresh the library"
              data-testid="documents-pulse-regen-btn"
            >
              <RefreshCw size={13} /> Regenerate
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <PulsePagerCard
              kind="sales"
              title="Sales 1-pager"
              tagline="Operations · Memberships · CRM in one read."
              onDownload={() => downloadPulsePager('sales')}
              onSend={() => setShowSendPager('sales')}
            />
            <PulsePagerCard
              kind="trust"
              title="Trust 1-pager"
              tagline="Procurement · IT · DPO sign-off in one read."
              onDownload={() => downloadPulsePager('trust')}
              onSend={() => setShowSendPager('trust')}
            />
          </div>
        </div>
      )}

      {/* ── Toolbar ── */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded border border-zinc-200 bg-white"
            data-testid="documents-search"
          />
        </div>
        {!orgId && (
          <select
            value={scopeFilter}
            onChange={(e) => setScopeFilter(e.target.value)}
            className="px-3 py-2 text-sm rounded border border-zinc-200 bg-white"
            data-testid="documents-scope-filter"
          >
            <option value="all">All scopes</option>
            <option value="platform">Platform-level</option>
            <option value="org">Per-org</option>
          </select>
        )}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded border border-zinc-200 bg-white"
          data-testid="documents-category-filter"
        >
          <option value="all">All categories</option>
          {Object.entries(CATEGORY_META).map(([k, m]) => (
            <option key={k} value={k}>{m.label}</option>
          ))}
        </select>
        <button
          onClick={load}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md border border-zinc-200 bg-white"
          data-testid="documents-refresh"
        >
          <RefreshCw size={13} /> Refresh
        </button>
        <button
          onClick={() => setShowUpload(true)}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900"
          data-testid="documents-upload-btn"
        >
          <Upload size={13} /> Upload
        </button>
      </div>

      {/* ── List ── */}
      {loading && !docs.length ? (
        <div className="flex items-center justify-center h-64"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>
      ) : docs.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-12 text-center" data-testid="documents-empty">
          <FolderArchive size={32} className="mx-auto text-zinc-300" />
          <h3 className="mt-3 text-base font-semibold text-zinc-900">No documents yet</h3>
          <p className="text-sm text-zinc-500 mt-1 max-w-sm mx-auto">
            Invoices and audit exports auto-capture themselves here. You can also upload contracts, DPAs, and supplier certs manually.
          </p>
          <button
            onClick={() => setShowUpload(true)}
            className="mt-5 inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-md bg-zinc-900 text-white"
          >
            <Upload size={14} /> Upload your first document
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
          {docs.map((d, idx) => {
            const meta = CATEGORY_META[d.category] || CATEGORY_META.other;
            const Icon = meta.icon;
            return (
              <div
                key={d.id}
                className={`flex items-center gap-3 p-3 sm:p-4 ${idx > 0 ? 'border-t border-zinc-100' : ''}`}
                data-testid={`document-row-${d.id}`}
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${TONE_BG[meta.tone] || TONE_BG.zinc}`}>
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-zinc-900 truncate">{d.title}</div>
                  <div className="text-xs text-zinc-500 truncate">
                    {meta.label} · {d.scope === 'platform' ? 'Platform' : 'Org'} ·
                    {' '}{d.source === 'auto' ? 'Auto-captured' : 'Uploaded'} ·
                    {' '}{(d.size_bytes / 1024).toFixed(1)} KB
                  </div>
                  <div className="text-[10px] text-zinc-400 mt-0.5">
                    {(d.uploaded_at || '').slice(0, 19).replace('T', ' ')}
                    {d.tags?.length > 0 && (
                      <span className="ml-2">
                        {d.tags.map((t) => (
                          <span key={t} className="ml-1 px-1.5 py-0.5 bg-zinc-100 rounded text-[10px] text-zinc-600 font-medium">
                            {t}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => downloadDoc(d)}
                  className="p-2 rounded-md hover:bg-zinc-100"
                  title="Download"
                  data-testid={`document-download-${d.id}`}
                >
                  <Download size={14} />
                </button>
                <button
                  onClick={() => deleteDoc(d)}
                  className="p-2 rounded-md hover:bg-rose-50 text-zinc-400 hover:text-rose-600"
                  title="Delete"
                  data-testid={`document-delete-${d.id}`}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {showUpload && (
        <UploadDialog
          orgId={orgId}
          API={API}
          headers={headers}
          onClose={() => setShowUpload(false)}
          onDone={() => { setShowUpload(false); load(); }}
        />
      )}
      {showSendPager && (
        <SendPulsePagerDialog
          variant={showSendPager}
          API={API}
          headers={headers}
          onClose={() => setShowSendPager(null)}
          onDone={() => { setShowSendPager(null); load(); }}
        />
      )}
    </div>
  );
}


/* ─────────────────── Pulse pager card ─────────────────── */

function PulsePagerCard({ kind, title, tagline, onDownload, onSend }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid={`documents-pulse-card-${kind}`}>
      <div className="text-[10px] uppercase tracking-wider font-bold text-cyan-600">{kind}</div>
      <div className="text-sm font-bold text-slate-900 mt-1">{title}</div>
      <div className="text-xs text-slate-500 mt-0.5">{tagline}</div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={onDownload}
          className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md bg-[var(--color-brand-cyan)] text-zinc-900 hover:brightness-95"
          data-testid={`documents-pulse-${kind}-btn`}
        >
          <Download size={13} /> Download
        </button>
        <button
          onClick={onSend}
          className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md border border-slate-200 bg-white text-slate-900 hover:bg-slate-50"
          data-testid={`documents-pulse-${kind}-send-btn`}
        >
          <Send size={13} /> Send…
        </button>
      </div>
    </div>
  );
}


/* ─────────────────── Send Pulse pager dialog ─────────────────── */

function SendPulsePagerDialog({ variant, API, headers, onClose, onDone }) {
  const [toEmail, setToEmail] = useState('');
  const [message, setMessage] = useState('');
  const [ttlDays, setTtlDays] = useState(30);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const variantLabel = variant === 'sales' ? 'sales 1-pager' : 'trust & security 1-pager';

  const submit = async () => {
    if (!toEmail || toEmail.indexOf('@') < 0) {
      notify.error('A recipient email is required');
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/master-admin/sales-pack/send`,
        { variant, to_email: toEmail, message, ttl_days: Number(ttlDays) || 30 },
        { headers },
      );
      setResult(r.data);
      if (r.data?.delivered_via_email) {
        notify.success(`${variantLabel} sent to ${toEmail}`);
      } else {
        notify.info('Share link created — email delivery is currently disabled, copy the link below.');
      }
    } catch (e) {
      notifyApiError(notify, e, 'Send failed');
    } finally {
      setSaving(false);
    }
  };

  const copyLink = async () => {
    if (!result?.share_url) return;
    try {
      await navigator.clipboard.writeText(result.share_url);
      notify.success('Link copied');
    } catch (e) {
      notify.error('Copy failed');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" data-testid="send-pulse-pager-dialog">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <h3 className="text-base font-semibold text-zinc-900">Send Pulse {variantLabel}</h3>
          <button onClick={onClose} className="p-1 hover:bg-zinc-100 rounded"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          {result ? (
            <>
              <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-emerald-800">
                {result.delivered_via_email
                  ? `Email delivered to ${result.recipient}.`
                  : `Share link created for ${result.recipient}. Email delivery was unavailable — copy the link below.`}
              </div>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Public download link</span>
                <div className="mt-1 flex gap-2">
                  <input
                    type="text"
                    readOnly
                    value={result.share_url || ''}
                    className="flex-1 px-2 py-1.5 rounded border border-zinc-200 bg-zinc-50 text-xs font-mono"
                    data-testid="send-pulse-pager-share-url"
                  />
                  <button
                    onClick={copyLink}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-900 text-white"
                    data-testid="send-pulse-pager-copy-link"
                  >
                    Copy
                  </button>
                </div>
              </label>
              <div className="text-xs text-zinc-500">
                Link expires {result.expires_at ? result.expires_at.slice(0, 10) : '—'}.
              </div>
              <div className="flex justify-end pt-3 border-t border-zinc-100">
                <button
                  onClick={onDone}
                  className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900"
                  data-testid="send-pulse-pager-done"
                >
                  Done
                </button>
              </div>
            </>
          ) : (
            <>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Recipient email</span>
                <input
                  type="email"
                  value={toEmail}
                  onChange={(e) => setToEmail(e.target.value)}
                  placeholder="prospect@example.com"
                  className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
                  data-testid="send-pulse-pager-email"
                />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Message (optional)</span>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={3}
                  placeholder="Hi Sarah, attaching the Pulse Fitness 1-pager from today's call. Happy to dig into any of it next week."
                  className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
                  data-testid="send-pulse-pager-message"
                />
              </label>
              <label className="block">
                <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Link valid for (days)</span>
                <input
                  type="number"
                  min={1}
                  max={180}
                  value={ttlDays}
                  onChange={(e) => setTtlDays(e.target.value)}
                  className="w-full mt-1 px-2 py-1.5 rounded border border-zinc-200"
                  data-testid="send-pulse-pager-ttl"
                />
              </label>
              <div className="text-xs text-zinc-500 leading-relaxed">
                We'll attach the PDF and include a tracked share link the recipient can re-fetch later.
              </div>
              <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
                <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
                <button
                  onClick={submit}
                  disabled={saving}
                  className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50"
                  data-testid="send-pulse-pager-confirm"
                >
                  {saving ? 'Sending…' : 'Send'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}


/* ─────────────────── Upload dialog ─────────────────── */

function UploadDialog({ orgId, API, headers, onClose, onDone }) {
  const fileRef = useRef(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('other');
  const [scope, setScope] = useState(orgId ? 'org' : 'platform');
  const [tags, setTags] = useState('');
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!file) { notify.error('Pick a file first'); return; }
    if (!title.trim()) { notify.error('Title required'); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', title.trim());
      fd.append('category', category);
      fd.append('scope', scope);
      if (orgId) fd.append('organization_id', orgId);
      fd.append('tags', tags);
      await axios.post(`${API}/master-admin/document-library`, fd, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      notify.success('Document uploaded');
      onDone();
    } catch (e) {
      notifyApiError(notify, e, 'Upload failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" data-testid="documents-upload-dialog">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-zinc-100">
          <h3 className="text-base font-semibold text-zinc-900">Upload document</h3>
          <button onClick={onClose} className="p-1 hover:bg-zinc-100 rounded"><X size={16} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className={`w-full px-4 py-6 rounded-lg border-2 border-dashed text-center ${file ? 'border-emerald-400 bg-emerald-50' : 'border-zinc-300 hover:border-[var(--color-brand-cyan)]'}`}
            data-testid="documents-upload-filebtn"
          >
            <FileText size={24} className={`mx-auto ${file ? 'text-emerald-500' : 'text-zinc-400'}`} />
            <div className="mt-2 text-sm font-medium text-zinc-700">
              {file ? file.name : 'Click to choose a file'}
            </div>
            {file && <div className="text-xs text-zinc-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB</div>}
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              data-testid="documents-upload-fileinput"
            />
          </button>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Title</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Pulse Fitness MSA — signed Apr 2026"
              className="w-full mt-1 px-3 py-1.5 rounded border border-zinc-200"
              data-testid="documents-upload-title"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Category</span>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full mt-1 px-3 py-1.5 rounded border border-zinc-200 bg-white"
                data-testid="documents-upload-category"
              >
                {Object.entries(CATEGORY_META).map(([k, m]) => (
                  <option key={k} value={k}>{m.label}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Scope</span>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                disabled={!!orgId}
                className="w-full mt-1 px-3 py-1.5 rounded border border-zinc-200 bg-white disabled:opacity-60"
                data-testid="documents-upload-scope"
              >
                <option value="platform">Platform-level</option>
                <option value="org">Per-org</option>
              </select>
            </label>
          </div>
          <label className="block">
            <span className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">Tags (comma-separated)</span>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="signed, msa, 2026"
              className="w-full mt-1 px-3 py-1.5 rounded border border-zinc-200"
              data-testid="documents-upload-tags"
            />
          </label>
          <div className="flex justify-end gap-2 pt-3 border-t border-zinc-100">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900">Cancel</button>
            <button
              onClick={submit}
              disabled={saving}
              className="px-4 py-1.5 text-sm font-semibold rounded bg-[var(--color-brand-cyan)] text-zinc-900 disabled:opacity-50"
              data-testid="documents-upload-confirm"
            >
              {saving ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
