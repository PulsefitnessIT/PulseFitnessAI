import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Upload, FolderOpen, Search, Trash2, Download, FileText, File, Image, X, Filter, Eye
} from 'lucide-react';
import axios from 'axios';

const CATEGORIES = ['spec_sheets', 'pre_install', 'maintenance', 'manuals', 'general', 'contract', 'proposal', 'invoice', 'other'];
const CAT_COLORS = { general: 'var(--color-info-ios)', contract: 'var(--color-accent-magenta)', proposal: 'var(--color-warning)', invoice: 'var(--color-success-alt)', manual: 'var(--color-cyan-500)', other: 'var(--color-text-faint-alt)', spec_sheets: 'var(--color-info)', pre_install: 'var(--color-accent-amber)', maintenance: 'var(--color-success)', manuals: 'var(--color-accent-indigo)' };

const DOC_TABS = [
  { id: '', label: 'All' },
  { id: 'spec_sheets', label: 'Spec Sheets' },
  { id: 'pre_install', label: 'Pre-Install' },
  { id: 'maintenance', label: 'Maintenance' },
  { id: 'manuals', label: 'Manuals' },
  { id: 'contract', label: 'Contracts' },
  { id: 'general', label: 'General' },
];

function formatSize(bytes) {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function fileIcon(ct) {
  if (ct?.startsWith('image/')) return Image;
  if (ct?.includes('pdf')) return FileText;
  return File;
}

export default function CRMDocuments() {
  const { API, headers, c, isDark, user } = useCRM();
  const [docs, setDocs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [catFilter, setCatFilter] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadCat, setUploadCat] = useState('general');
  const [uploadNotes, setUploadNotes] = useState('');
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const params = { limit: 100 };
      if (search) params.search = search;
      if (catFilter) params.category = catFilter;
      const res = await axios.get(`${API}/crm/v2/documents`, { headers: headers(), params });
      setDocs(res.data.documents || []);
      setTotal(res.data.total || 0);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers, search, catFilter]);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(
        `${API}/crm/v2/documents?category=${uploadCat}&notes=${encodeURIComponent(uploadNotes)}`,
        formData, { headers: { ...headers(), 'Content-Type': 'multipart/form-data' } }
      );
      setShowUpload(false);
      setUploadNotes('');
      setUploadCat('general');
      load();
    } catch (e) { console.error(e); }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API}/crm/v2/documents/${id}`, { headers: headers() });
      load();
    } catch (e) { console.error(e); }
  };

  return (
    <div data-testid="crm-documents">
      {/* Toolbar — search + count + upload */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search documents..."
            className="w-full pl-9 pr-3 py-2 text-sm rounded-md"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }}
            data-testid="doc-search" />
        </div>
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-md hidden"
          style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }}
          data-testid="doc-filter">
          <option value="">All categories</option>
          {CATEGORIES.map(cat => <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1).replace('_', ' ')}</option>)}
        </select>
        <p className="text-xs ml-auto" style={{ color: c.textDim }}>{total} file{total !== 1 ? 's' : ''}</p>
        <button type="button" onClick={() => setShowUpload(true)} className="btn-primary" data-testid="upload-doc-btn">
          <Upload size={14} /> Upload
        </button>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {DOC_TABS.map(tab => (
          <button key={tab.id} onClick={() => setCatFilter(tab.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-all ${catFilter === tab.id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
            style={catFilter !== tab.id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
            data-testid={`doc-tab-${tab.id || 'all'}`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Document list */}
      {loading ? (
        <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>
      ) : docs.length === 0 ? (
        <div className="text-center py-16 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <FolderOpen size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
          <p className="text-sm font-medium" style={{ color: c.textMuted }}>No documents yet</p>
          <button onClick={() => setShowUpload(true)} className="text-sm text-[var(--color-info-ios)] mt-2 hover:underline">Upload your first document</button>
        </div>
      ) : (
        <div className="space-y-2">
          {docs.map(doc => {
            const Icon = fileIcon(doc.content_type);
            const color = CAT_COLORS[doc.category] || 'var(--color-text-faint-alt)';
            return (
              <div key={doc.id} className="flex items-center gap-4 p-4 rounded-lg border transition-all"
                style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                data-testid={`doc-row-${doc.id}`}>
                <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${color}15` }}>
                  <Icon size={18} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{doc.original_filename}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${color}20`, color }}>{doc.category}</span>
                    <span className="text-[11px]" style={{ color: c.textDim }}>{formatSize(doc.size)}</span>
                    <span className="text-[11px]" style={{ color: c.textDim }}>{doc.uploaded_by_name}</span>
                    <span className="text-[11px]" style={{ color: c.textDim }}>{new Date(doc.created_at).toLocaleDateString('en-GB')}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <a href={`${API}/crm/v2/documents/${doc.id}/view`} target="_blank" rel="noreferrer" className="p-2 rounded-md hover:bg-[rgb(var(--rgb-info-ios)/0.1)]" style={{ color: 'var(--color-info-ios)' }} data-testid={`doc-view-${doc.id}`}>
                    <Eye size={14} />
                  </a>
                  <a href={`${API}/crm/v2/documents/${doc.id}/view`} download={doc.original_filename} className="p-2 rounded-md hover:bg-[rgb(var(--rgb-success-alt)/0.1)]" style={{ color: 'var(--color-success-alt)' }} data-testid={`doc-download-${doc.id}`}>
                    <Download size={14} />
                  </a>
                  {(doc.uploaded_by === user?.id || user?.role === 'admin' || user?.role === 'owner') && (
                    <button onClick={() => handleDelete(doc.id)} className="p-2 rounded-md hover:bg-[rgb(var(--rgb-danger-alt)/0.1)]" style={{ color: c.textDim }} data-testid={`doc-delete-${doc.id}`}>
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Upload Dialog */}
      {showUpload && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowUpload(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl"
            style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="upload-doc-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>Upload Document</h2>
            <div className="space-y-3 mb-4">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Category</label>
                <select value={uploadCat} onChange={e => setUploadCat(e.target.value)}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  {CATEGORIES.map(cat => <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Notes</label>
                <input value={uploadNotes} onChange={e => setUploadNotes(e.target.value)}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>
            <div className="border-2 border-dashed rounded-lg p-8 text-center" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <Upload size={28} className="mx-auto mb-3" style={{ color: c.textDim }} />
              <p className="text-sm mb-3" style={{ color: c.textMuted }}>Click to upload a file</p>
              <input type="file" onChange={handleUpload} ref={fileRef} className="hidden" id="crm-doc-upload" data-testid="doc-file-input" />
              <label htmlFor="crm-doc-upload" className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md cursor-pointer hover:bg-[var(--color-brand-blue-deep)]">
                <Upload size={14} /> {uploading ? 'Uploading...' : 'Choose File'}
              </label>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={() => setShowUpload(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
