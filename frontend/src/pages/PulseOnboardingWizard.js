import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import InvoiceParseProgress from '@/components/shared/InvoiceParseProgress';
import { useUploadQueue } from '@/components/shared/UploadQueue';
import {
  Building2, Users, Wrench, CheckCircle, ArrowRight, ArrowLeft,
  Loader2, Plus, Trash2, UserPlus, Download,
  Eye, EyeOff, Star, Sparkles, FileText, UserCheck
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

/* ─────── TIER OPTIONS ─────── */
const TIERS = [
  { id: 'lite', label: 'Pulse Lite', desc: 'Equipment tracking, fault reporting, documents', color: '#0891b2', brand: 'Pulse Fitness' },
  { id: 'pro', label: 'Pulse Pro', desc: 'Full platform with AI, reports, suppliers, check sheets', color: 'var(--color-blue-600)', brand: 'Pulse Fitness' },
  { id: 'gymaxis', label: 'Pulse Fitness AI', desc: 'Full Pulse Fitness AI service — maintenance, CRM, analytics', color: 'var(--color-brand-blue)', brand: 'Pulse Fitness AI' },
];

/* ─────── STEP 0: Choose Mode ─────── */
const ChooseModeStep = ({ mode, setMode, tier, setTier, orgs, selectedOrg, setSelectedOrg }) => {
  // Iter 216h51 — searchable + alphabetised picker. Lee reported that
  // scrolling through Pulse's full customer list takes ages; a search
  // box short-circuits that. We also sort by name (case-insensitive)
  // so the same customer is always in the same screen position.
  const [search, setSearch] = useState('');
  const sortedOrgs = React.useMemo(() => (
    [...(orgs || [])].sort((a, b) => (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }))
  ), [orgs]);
  const filteredOrgs = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sortedOrgs;
    return sortedOrgs.filter(o => (
      (o.name || '').toLowerCase().includes(q)
      || (o.company_code || '').toLowerCase().includes(q)
      || (o.account_type || '').toLowerCase().includes(q)
    ));
  }, [sortedOrgs, search]);

  return (
  <div className="space-y-8" data-testid="onboard-step-choose">
    <div className="text-center">
      <h2 className="text-2xl font-semibold text-zinc-900 tracking-tight" style={{ fontFamily: 'Outfit' }}>Onboard a Site</h2>
      <p className="text-zinc-500 text-sm mt-1">Create a new customer site or add to an existing one</p>
    </div>

    <div className="grid md:grid-cols-2 gap-4 max-w-2xl mx-auto">
      <button
        onClick={() => setMode('new')}
        className={`p-6 rounded-xl border-2 text-left transition-all ${mode === 'new' ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)] shadow-sm' : 'border-zinc-200 hover:border-zinc-300'}`}
        data-testid="onboard-mode-new"
      >
        <div className="w-12 h-12 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center mb-3">
          <Building2 size={22} className="text-[var(--color-brand-blue)]" />
        </div>
        <h3 className="text-zinc-900 font-semibold mb-1">New Site</h3>
        <p className="text-zinc-500 text-xs">Create a brand new customer site with users and equipment</p>
      </button>
      <button
        onClick={() => setMode('existing')}
        className={`p-6 rounded-xl border-2 text-left transition-all ${mode === 'existing' ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)] shadow-sm' : 'border-zinc-200 hover:border-zinc-300'}`}
        data-testid="onboard-mode-existing"
      >
        <div className="w-12 h-12 rounded-lg bg-green-500/10 flex items-center justify-center mb-3">
          <UserCheck size={22} className="text-green-600" />
        </div>
        <h3 className="text-zinc-900 font-semibold mb-1">Existing Customer</h3>
        <p className="text-zinc-500 text-xs">Add new equipment or update an existing customer site</p>
      </button>
    </div>

    {mode === 'new' && (
      <div className="max-w-2xl mx-auto">
        <Label className="text-zinc-500 text-xs mb-3 block">Service Tier</Label>
        <div className="grid grid-cols-3 gap-3">
          {TIERS.map(t => (
            <button
              key={t.id}
              onClick={() => setTier(t.id)}
              className={`p-4 rounded-xl border-2 text-left transition-all ${tier === t.id ? 'border-opacity-100 shadow-sm' : 'border-zinc-200 hover:border-zinc-300'}`}
              style={tier === t.id ? { borderColor: t.color, background: `${t.color}08` } : {}}
              data-testid={`onboard-tier-${t.id}`}
            >
              <div className="flex items-center gap-2 mb-1">
                {tier === t.id && <CheckCircle size={14} style={{ color: t.color }} />}
                <span className="font-semibold text-zinc-900 text-sm">{t.label}</span>
              </div>
              <p className="text-zinc-500 text-xs">{t.desc}</p>
            </button>
          ))}
        </div>
      </div>
    )}

    {mode === 'existing' && (
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-2">
          <Label className="text-zinc-500 text-xs">Select Existing Customer</Label>
          <span className="text-[10px] text-zinc-400">
            {filteredOrgs.length === sortedOrgs.length
              ? `${sortedOrgs.length} customer${sortedOrgs.length === 1 ? '' : 's'}`
              : `${filteredOrgs.length} of ${sortedOrgs.length}`}
          </span>
        </div>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, company code or type…"
          className="bg-white mb-2 h-9"
          data-testid="onboard-org-search"
        />
        {sortedOrgs.length === 0 ? (
          <p className="text-zinc-400 text-sm">No existing organizations found.</p>
        ) : filteredOrgs.length === 0 ? (
          <div className="text-center py-8 border border-dashed border-zinc-200 rounded-lg">
            <p className="text-zinc-400 text-sm">No customers match "{search}"</p>
            <button onClick={() => setSearch('')} className="text-xs text-[var(--color-brand-blue)] hover:underline mt-1">Clear search</button>
          </div>
        ) : (
          <div className="space-y-2 max-h-[28rem] overflow-y-auto border border-zinc-200 rounded-lg p-2" data-testid="onboard-org-list">
            {filteredOrgs.map(o => (
              <button
                key={o.id}
                onClick={() => setSelectedOrg(o)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors ${selectedOrg?.id === o.id ? 'bg-[rgb(var(--rgb-brand-blue)/0.05)] border border-[rgb(var(--rgb-brand-blue)/0.3)]' : 'hover:bg-zinc-50 border border-transparent'}`}
                data-testid={`onboard-org-${o.id}`}
              >
                <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center text-zinc-600 font-semibold text-xs">
                  {o.name?.charAt(0)?.toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-zinc-900 font-medium">{o.name}</span>
                  <p className="text-xs text-zinc-400 truncate">{o.company_code} · {o.account_type || o.tier || 'standard'}</p>
                </div>
                {selectedOrg?.id === o.id && <CheckCircle size={16} className="text-[var(--color-brand-blue)]" />}
              </button>
            ))}
          </div>
        )}
      </div>
    )}
  </div>
  );
};

/* ─────── STEP 1: Upload Invoice (AI) — Bulk Support ─────── */
const InvoiceUploadStep = ({ _aiData, setAiData, form, setForm, _mode, headers }) => {
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [processedInvoices, setProcessedInvoices] = useState([]);
  // Iter 216h35 — `processingQueue` (the local "N more in queue…" UI)
  // was replaced by the canonical bottom-right UploadQueueDrawer so
  // operators see per-file progress + retry even after closing the
  // wizard. The state stays as a slim derived list of currently-queued
  // file names for the lightweight inline indicator next to the
  // dropzone (drawer is the source of truth, this is just a hint).
  const [processingQueue, setProcessingQueue] = useState([]);
  const [currentFile, setCurrentFile] = useState('');
  // Iter 216m — phased AI parse progress so operators see motion
  // instead of a static spinner during the 30 s extraction.
  const [parseProgress, setParseProgress] = useState(null);
  const { enqueue } = useUploadQueue();

  // Iter 216h35 — shared "parse one invoice and merge into form" helper
  // used by both the inline single-file path (with phased parseProgress
  // UI) and the multi-file enqueue() path (drawer-based).
  const parseAndMerge = async (file, onProgress) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      throw new Error(`${file.name} — not a PDF`);
    }
    const formData = new FormData();
    formData.append('file', file);
    const res = await axios.post(`${API}/equipment-import/parse-invoice`, formData, {
      headers: { ...headers },
      timeout: 120000,
      onUploadProgress: (evt) => {
        if (evt.total && onProgress) onProgress((evt.loaded / evt.total) * 100);
      },
    });
    const invoiceResult = { ...res.data, filename: file.name };
    setProcessedInvoices(prev => [...prev, invoiceResult]);
    // Use functional updates so concurrent files don't clobber each other.
    if (res.data.site_name) setForm(f => ({ ...f, site_name: f.site_name || res.data.site_name }));
    if (res.data.account_ref) setForm(f => ({ ...f, account_ref: f.account_ref || res.data.account_ref }));
    if (res.data.install_date) setForm(f => ({ ...f, install_date: f.install_date || res.data.install_date }));
    if (res.data.supplier_name) setForm(f => ({ ...f, supplier_name: f.supplier_name || res.data.supplier_name }));
    if (res.data.equipment?.length > 0) {
      const supplierFallback = (res.data.supplier_name || '').trim();
      const goodSupplier = supplierFallback && supplierFallback.toLowerCase() !== 'unknown' ? supplierFallback : '';
      const mapped = res.data.equipment.map(eq => ({
        name: eq.model || '',
        equipment_type: classifyEquipment(eq.model || ''),
        equipment_category: eq.equipment_category || '',
        manufacturer: (eq.make && eq.make.trim()) || goodSupplier || 'Unknown',
        model: eq.model || '',
        serial_number: eq.serial_number || '',
        location: form.default_location || 'Main Floor',
        unit_price: eq.unit_price || 0,
        stock_item_code: eq.stock_item_code || '',
        warranty_code: eq.warranty_code || '',
        warranty_expiry: eq.warranty_expiry || '',
        sla_name: eq.sla_name || '',
        _invoice: res.data.invoice_number || file.name,
        _import_id: res.data.import_id,
      }));
      setForm(f => ({ ...f, equipment: [...f.equipment, ...mapped] }));
    }
    setAiData(prev => prev
      ? { ...prev, batch_import_ids: [...(prev.batch_import_ids || [prev.import_id]), res.data.import_id] }
      : { ...res.data, batch_import_ids: [res.data.import_id] }
    );
    return res.data;
  };

  const processFile = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) { notify.error(`${file.name} — not a PDF`); return; }
    setCurrentFile(file.name);
    setUploading(true);
    setParseProgress({ phase: 'upload', pct: 0 });
    // Estimate page count locally so the "Reading page X of Y…" copy
    // is honest. Cheap regex on the first 200 KB of the PDF.
    let pageCount = 20;
    try {
      const peek = await file.slice(0, Math.min(file.size, 200 * 1024)).text();
      const m = peek.match(/\/Type\s*\/Page[^s]/g);
      if (m && m.length) pageCount = m.length;
    } catch { /* best effort */ }
    try {
      const data = await parseAndMerge(file, (pct) => {
        setParseProgress({ phase: pct >= 100 ? 'parse' : 'upload', pct, pageCount });
      });
      notify.success(`${file.name}: extracted ${data.equipment?.length || 0} items`);
      setParseProgress({ phase: 'done', itemCount: data.equipment?.length || 0 });
      setTimeout(() => setParseProgress(null), 3500);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Failed';
      setParseProgress({ phase: 'error', message: `${file.name}: ${detail}` });
      setTimeout(() => setParseProgress(null), 6000);
      notify.error(`${file.name}: ${detail}`);
    }
    setUploading(false);
    setCurrentFile('');
  };

  const processMultipleFiles = (fileList) => {
    const pdfFiles = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) { notify.error('No PDF files found'); return; }
    // Iter 216h35 — route multi-file drops through the global
    // UploadQueueDrawer for per-file progress + retry. The wizard's
    // inline "phased parseProgress" UI continues to render for the
    // single-file path because that flow is interactive (the user
    // explicitly waits for ONE PDF to parse before moving on); for
    // multi-drop scenarios the drawer is the right UX.
    setProcessingQueue(pdfFiles.map(f => f.name));
    enqueue(pdfFiles, async (file, onProgress) => {
      try {
        await parseAndMerge(file, onProgress);
      } finally {
        setProcessingQueue(prev => prev.filter(n => n !== file.name));
      }
    }, {
      source: 'onboarding-invoices',
      onDone: (file) => {
        // Friendly toast per file so operators see successes even if
        // the drawer is collapsed.
        notify.success(`${file.name} extracted`);
      },
    });
  };

  const handleFileInput = (e) => {
    const files = e.target.files;
    if (files.length > 1) processMultipleFiles(files);
    else processFile(files?.[0]);
  };

  // Iter 216h33 — guard dragenter too so Safari doesn't lock the
  // cursor to "no-drop" before the dropzone registers dragover.
  const handleDragEnter = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
  const handleDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const files = e.dataTransfer?.files;
    if (files?.length > 1) processMultipleFiles(files);
    else processFile(files?.[0]);
  };

  const removeInvoice = (idx) => {
    const removed = processedInvoices[idx];
    setProcessedInvoices(prev => prev.filter((_, i) => i !== idx));
    if (removed?.import_id) {
      setForm(f => ({ ...f, equipment: f.equipment.filter(eq => eq._import_id !== removed.import_id) }));
      setAiData(prev => {
        if (!prev) return prev;
        const ids = (prev.batch_import_ids || []).filter(id => id !== removed.import_id);
        return ids.length === 0 ? null : { ...prev, batch_import_ids: ids };
      });
    }
  };

  const totalEquipment = processedInvoices.reduce((s, inv) => s + (inv.equipment_count || 0), 0);

  return (
    <div className="space-y-6" data-testid="onboard-step-invoice">
      <div>
        <h3 className="text-lg font-semibold text-zinc-900 mb-1">Upload Supplier Invoices</h3>
        <p className="text-zinc-500 text-sm">Drop one or multiple PDF invoices. AI will extract equipment details from each.</p>
      </div>

      <Card
        className={`p-8 border-2 border-dashed transition-colors text-center cursor-pointer ${dragOver ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)]' : 'border-zinc-200 hover:border-[rgb(var(--rgb-brand-blue)/0.3)]'}`}
        onClick={() => !uploading && fileRef.current?.click()}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        data-testid="onboard-invoice-dropzone"
      >
        <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple onChange={handleFileInput} ref={fileRef} className="hidden" data-testid="onboard-invoice-input" />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)]" />
            <p className="text-sm text-zinc-600 font-medium">Processing: {currentFile}</p>
            {processingQueue.length > 0 && (
              <p className="text-xs text-zinc-400">{processingQueue.length} more in queue...</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-16 h-16 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center">
              <Sparkles size={24} className="text-[var(--color-brand-blue)]" />
            </div>
            <p className="text-sm text-zinc-600 font-medium">
              {processedInvoices.length > 0 ? 'Drop more invoices or click to add' : 'Drop your invoice files here'}
            </p>
            <p className="text-xs text-zinc-400">PDFs, JPG, or PNG — AI will extract equipment from each (incl. scanned invoices)</p>
          </div>
        )}
      </Card>

      {/* Iter 216m — phased AI parse progress (replaces the old static
          spinner inside the dropzone with a live progress bar that
          shows real upload bytes + a simulated AI-parse phase). */}
      {parseProgress ? <InvoiceParseProgress state={parseProgress} /> : null}

      {/* Processed invoices list */}
      {processedInvoices.length > 0 && (
        <div className="space-y-2" data-testid="onboard-invoice-list">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-zinc-700">{processedInvoices.length} Invoice{processedInvoices.length > 1 ? 's' : ''} Processed</span>
            <Badge className="bg-green-50 text-green-700 border-green-200 text-xs">{totalEquipment} total items</Badge>
          </div>
          {processedInvoices.map((inv, idx) => (
            <Card key={inv.import_id || idx} className="p-5 border-zinc-200" data-testid={`onboard-invoice-${idx}`}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-green-50 flex items-center justify-center shrink-0">
                  <FileText size={16} className="text-green-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-zinc-900 truncate">{inv.site_name || inv.filename}</span>
                    <Badge className="bg-zinc-100 text-zinc-600 text-[10px] border-zinc-200 shrink-0">{inv.equipment_count} items</Badge>
                    {inv.sla_name && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${inv.sla_name === 'Platinum' ? 'bg-purple-100 text-purple-700' : inv.sla_name === 'Gold' ? 'bg-amber-100 text-amber-700' : inv.sla_name === 'Silver' ? 'bg-zinc-200 text-zinc-700' : 'text-zinc-400'}`}>
                        {inv.sla_name}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-zinc-400 truncate">
                    {inv.invoice_number && `#${inv.invoice_number}`}
                    {inv.supplier_name && ` · ${inv.supplier_name}`}
                    {inv.warranty_code && ` · ${inv.warranty_code}`}
                  </p>
                </div>
                <button onClick={(e) => { e.stopPropagation(); removeInvoice(idx); }} className="p-1 text-zinc-400 hover:text-red-500 shrink-0" data-testid={`onboard-remove-invoice-${idx}`}>
                  <Trash2 size={14} />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <p className="text-zinc-400 text-xs text-center">You can also skip this step and add equipment manually</p>
    </div>
  );
};

/* ─────── STEP 2: Site Details ─────── */
// Iter 215et — Pulse onboarding now hits postcodes.io on postcode-blur to
// auto-fill city/county/country. Killing manual entry of those fields is
// our biggest single UX win — users mistype counties constantly.
const SiteDetailsStep = ({ form, setForm, mode, _tier }) => {
  const lookupPostcode = async (pc) => {
    const trimmed = (pc || '').trim();
    if (!trimmed || trimmed.replace(/\s+/g, '').length < 5) return;
    try {
      const headers = { Authorization: `Bearer ${localStorage.getItem('token') || ''}` };
      const r = await axios.get(`${API}/integrations/postcode/lookup`, { headers, params: { postcode: trimmed } });
      if (r.data?.found) {
        setForm(f => ({
          ...f,
          postcode: r.data.postcode || f.postcode,
          city: f.city || r.data.city || '',
          county: f.county || r.data.county || '',
          country: r.data.country || f.country || 'United Kingdom',
        }));
      }
    } catch { /* silent */ }
  };
  return (
  <div className="space-y-6" data-testid="onboard-step-site">
    <div>
      <h3 className="text-lg font-semibold text-zinc-900 mb-1">Site Details</h3>
      <p className="text-zinc-500 text-sm">{mode === 'existing' ? 'Review and update site information.' : 'Enter the site information for this installation.'}</p>
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="text-zinc-500 text-xs">Site Name *</Label>
        <Input value={form.site_name} onChange={e => setForm(f => ({ ...f, site_name: e.target.value }))}
          placeholder="e.g. Tottenham Green Leisure Centre" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-site-name" />
      </div>
      <div>
        <Label className="text-zinc-500 text-xs">Account Ref</Label>
        <Input value={form.account_ref || ''} onChange={e => setForm(f => ({ ...f, account_ref: e.target.value }))}
          placeholder="e.g. 00002946" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-account-ref" />
      </div>
    </div>
    <div>
      <Label className="text-zinc-500 text-xs">Address</Label>
      <Input value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
        placeholder="123 High Street, London" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-address" />
    </div>
    <div className="grid md:grid-cols-3 gap-4">
      <div>
        <Label className="text-zinc-500 text-xs">Postcode</Label>
        <Input value={form.postcode}
          onChange={e => setForm(f => ({ ...f, postcode: e.target.value }))}
          onBlur={e => lookupPostcode(e.target.value)}
          placeholder="N15 4QT" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1 font-mono" data-testid="onboard-postcode" />
        <p className="text-[9px] text-zinc-400 mt-1">Auto-fills city + county on blur</p>
      </div>
      <div>
        <Label className="text-zinc-500 text-xs">City</Label>
        <Input value={form.city || ''} onChange={e => setForm(f => ({ ...f, city: e.target.value }))}
          placeholder="London" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-city" />
      </div>
      <div>
        <Label className="text-zinc-500 text-xs">County</Label>
        <Input value={form.county || ''} onChange={e => setForm(f => ({ ...f, county: e.target.value }))}
          placeholder="Greater London" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-county" />
      </div>
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="text-zinc-500 text-xs">Phone</Label>
        <Input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
          placeholder="020 7123 4567" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-phone" />
      </div>
      <div>
        <Label className="text-zinc-500 text-xs">Default Location</Label>
        <Input value={form.default_location} onChange={e => setForm(f => ({ ...f, default_location: e.target.value }))}
          placeholder="Main Floor" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" />
      </div>
    </div>
  </div>
);
};

/* ─────── STEP 3: Users (New sites only) ─────── */
const UsersStep = ({ form, setForm }) => {
  const addUser = () => setForm(f => ({ ...f, users: [...f.users, { name: '', email: '', password: '', role: 'staff', showPw: false }] }));
  const removeUser = (i) => setForm(f => ({ ...f, users: f.users.filter((_, idx) => idx !== i) }));
  const updateUser = (i, field, value) => setForm(f => ({ ...f, users: f.users.map((u, idx) => idx === i ? { ...u, [field]: value } : u) }));

  return (
    <div className="space-y-6" data-testid="onboard-step-users">
      <div>
        <h3 className="text-lg font-semibold text-zinc-900 mb-1">Users</h3>
        <p className="text-zinc-500 text-sm">Set up the site owner and any additional users.</p>
      </div>
      <Card className="bg-amber-50/50 border-amber-200 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Star size={16} className="text-amber-500" />
          <span className="text-zinc-900 font-semibold text-sm">Site Owner</span>
          <Badge className="bg-amber-100 text-amber-700 text-[10px] border-amber-200">Required</Badge>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <Label className="text-zinc-500 text-xs">Full Name *</Label>
            <Input value={form.owner_name} onChange={e => setForm(f => ({ ...f, owner_name: e.target.value }))}
              placeholder="John Smith" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-owner-name" />
          </div>
          <div>
            <Label className="text-zinc-500 text-xs">Email *</Label>
            <Input type="email" value={form.owner_email} onChange={e => setForm(f => ({ ...f, owner_email: e.target.value }))}
              placeholder="john@gym.com" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1" data-testid="onboard-owner-email" />
          </div>
          <div className="md:col-span-2">
            <Label className="text-zinc-500 text-xs">Password *</Label>
            <div className="relative">
              <Input type={form.ownerShowPw ? 'text' : 'password'} value={form.owner_password} onChange={e => setForm(f => ({ ...f, owner_password: e.target.value }))}
                placeholder="Min 8 characters" className="bg-white border-zinc-200 text-zinc-900 h-10 mt-1 pr-10" data-testid="onboard-owner-password" />
              <button type="button" onClick={() => setForm(f => ({ ...f, ownerShowPw: !f.ownerShowPw }))} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400">
                {form.ownerShowPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
        </div>
      </Card>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-zinc-700">Additional Staff</h4>
        <Button variant="outline" size="sm" onClick={addUser} className="border-zinc-200 text-zinc-600">
          <UserPlus size={14} className="mr-1" /> Add User
        </Button>
      </div>
      {form.users.map((u, i) => (
        <Card key={i} className="p-5 border-zinc-200">
          <div className="grid md:grid-cols-4 gap-3 items-end">
            <div>
              <Label className="text-zinc-500 text-xs">Name</Label>
              <Input value={u.name} onChange={e => updateUser(i, 'name', e.target.value)} className="bg-white border-zinc-200 text-zinc-900 h-9 mt-1" />
            </div>
            <div>
              <Label className="text-zinc-500 text-xs">Email</Label>
              <Input type="email" value={u.email} onChange={e => updateUser(i, 'email', e.target.value)} className="bg-white border-zinc-200 text-zinc-900 h-9 mt-1" />
            </div>
            <div>
              <Label className="text-zinc-500 text-xs">Password</Label>
              <Input type="text" value={u.password} onChange={e => updateUser(i, 'password', e.target.value)} className="bg-white border-zinc-200 text-zinc-900 h-9 mt-1" />
            </div>
            <div className="flex gap-2 items-end">
              <Select value={u.role} onValueChange={v => updateUser(i, 'role', v)}>
                <SelectTrigger className="h-9 bg-white border-zinc-200 text-zinc-900"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="manager">Manager</SelectItem><SelectItem value="staff">Staff</SelectItem></SelectContent>
              </Select>
              <Button variant="ghost" size="icon" onClick={() => removeUser(i)} className="h-9 w-9 text-zinc-400 hover:text-red-500"><Trash2 size={14} /></Button>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};

/* ─────── STEP 4: Equipment Review (grouped by invoice) ─────── */
const EquipmentReviewStep = ({ form, setForm }) => {
  const addEquipment = () => setForm(f => ({ ...f, equipment: [...f.equipment, { name: '', equipment_type: '', manufacturer: '', serial_number: '', location: form.default_location || 'Main Floor', unit_price: 0, _invoice: 'Manual' }] }));
  const removeEquipment = (i) => setForm(f => ({ ...f, equipment: f.equipment.filter((_, idx) => idx !== i) }));
  const updateEquipment = (i, field, value) => setForm(f => ({ ...f, equipment: f.equipment.map((eq, idx) => idx === i ? { ...eq, [field]: value } : eq) }));

  // Group equipment by invoice
  const groups = {};
  form.equipment.forEach((eq, i) => {
    const key = eq._invoice || 'Manual';
    if (!groups[key]) groups[key] = [];
    groups[key].push({ ...eq, _idx: i });
  });
  const groupKeys = Object.keys(groups);
  const hasMultipleGroups = groupKeys.length > 1;

  return (
    <div className="space-y-6" data-testid="onboard-step-equipment">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-zinc-900 mb-1">Equipment ({form.equipment.length})</h3>
          <p className="text-zinc-500 text-sm">
            {hasMultipleGroups
              ? `${groupKeys.length} invoices · ${form.equipment.length} items total — review or edit below.`
              : 'Review AI-extracted equipment or add manually.'}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={addEquipment} className="border-zinc-200 text-zinc-600">
          <Plus size={14} className="mr-1" /> Add Item
        </Button>
      </div>

      {form.equipment.length === 0 ? (
        <Card className="p-8 text-center border-zinc-200">
          <Wrench size={32} className="mx-auto text-zinc-300 mb-3" />
          <p className="text-zinc-500 text-sm">No equipment yet. Go back and upload an invoice, or add manually.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {groupKeys.map(groupKey => (
            <div key={groupKey}>
              {hasMultipleGroups && (
                <div className="flex items-center gap-2 mb-2">
                  <FileText size={14} className="text-[var(--color-brand-blue)]" />
                  <span className="text-sm font-semibold text-zinc-700">{groupKey}</span>
                  <Badge className="bg-zinc-100 text-zinc-600 text-[10px] border-zinc-200">{groups[groupKey].length} items</Badge>
                </div>
              )}
              <div className="border border-zinc-200 rounded-lg overflow-x-auto">
                <table className="w-full text-sm text-left min-w-[700px]" data-testid={`onboard-equipment-table-${groupKey}`}>
                  <thead>
                    <tr className="bg-zinc-50 border-b border-zinc-200">
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium">#</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium">Manufacturer</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium min-w-[200px]">Description</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium">Serial</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium">Price</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium">SLA</th>
                      <th className="px-3 py-2 text-xs text-zinc-500 uppercase font-medium w-10"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups[groupKey].map((eq) => (
                      <tr key={eq._idx} className="border-b border-zinc-100">
                        <td className="px-3 py-2 text-zinc-400">{eq._idx + 1}</td>
                        <td className="px-3 py-2">
                          <input value={eq.manufacturer || ''} onChange={e => updateEquipment(eq._idx, 'manufacturer', e.target.value)}
                            className="w-full px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
                        </td>
                        <td className="px-3 py-2">
                          <input value={eq.name || ''} onChange={e => updateEquipment(eq._idx, 'name', e.target.value)}
                            className="w-full px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
                        </td>
                        <td className="px-3 py-2">
                          <input value={eq.serial_number || ''} onChange={e => updateEquipment(eq._idx, 'serial_number', e.target.value)}
                            className="w-28 px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
                        </td>
                        <td className="px-3 py-2">
                          <input type="number" step="0.01" value={eq.unit_price || ''} onChange={e => updateEquipment(eq._idx, 'unit_price', parseFloat(e.target.value) || 0)}
                            className="w-24 px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
                        </td>
                        <td className="px-3 py-2">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${eq.sla_name === 'Platinum' ? 'bg-purple-100 text-purple-700' : eq.sla_name === 'Gold' ? 'bg-amber-100 text-amber-700' : eq.sla_name === 'Silver' ? 'bg-zinc-200 text-zinc-700' : 'text-zinc-400'}`}>
                            {eq.sla_name || '—'}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <button onClick={() => removeEquipment(eq._idx)} className="p-1 text-zinc-400 hover:text-red-500"><Trash2 size={14} /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ─────── STEP 5: Review & Create ─────── */
const FinalReviewStep = ({ form, setForm, mode, tier, selectedOrg, aiData }) => (
  <div className="space-y-6" data-testid="onboard-step-review">
    <div>
      <h3 className="text-lg font-semibold text-zinc-900 mb-1">Review & Confirm</h3>
      <p className="text-zinc-500 text-sm">Verify all details before {mode === 'existing' ? 'adding equipment' : 'creating the site'}. You can edit the gym name and address below.</p>
    </div>
    <Card className="p-6 border-zinc-200">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div><span className="text-zinc-500 text-xs">Mode:</span> <span className="font-medium text-zinc-900 ml-2">{mode === 'new' ? `New ${TIERS.find(t => t.id === tier)?.label || ''}` : `Existing — ${selectedOrg?.name}`}</span></div>
        <div>
          <label className="text-zinc-500 text-xs block mb-1">Gym / Site Name</label>
          <input
            value={form.site_name || selectedOrg?.name || ''}
            onChange={e => setForm(f => ({ ...f, site_name: e.target.value }))}
            className="w-full px-3 py-1.5 text-sm font-medium text-zinc-900 border border-zinc-200 rounded-lg focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none"
            placeholder="Gym name"
            data-testid="review-site-name"
          />
        </div>
        <div className="col-span-2">
          <label className="text-zinc-500 text-xs block mb-1">Address</label>
          <input
            value={form.address || ''}
            onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
            className="w-full px-3 py-1.5 text-sm font-medium text-zinc-900 border border-zinc-200 rounded-lg focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none"
            placeholder="Site address (optional)"
            data-testid="review-address"
          />
        </div>
        {form.account_ref && <div><span className="text-zinc-500 text-xs">Account:</span> <span className="font-medium text-zinc-900 ml-2">{form.account_ref}</span></div>}
        {aiData?.supplier_name && <div><span className="text-zinc-500 text-xs">Supplier:</span> <span className="font-medium text-zinc-900 ml-2">{aiData.supplier_name}</span></div>}
        {aiData?.warranty_code && <div><span className="text-zinc-500 text-xs">Warranty:</span> <span className="font-medium text-zinc-900 ml-2">{aiData.sla_name} — {aiData.warranty_expiry}</span></div>}
      </div>
      {mode === 'new' && (
        <div className="mt-4 pt-4 border-t border-zinc-200 text-sm">
          <span className="text-zinc-500 text-xs">Owner:</span> <span className="font-medium text-zinc-900 ml-2">{form.owner_name} ({form.owner_email})</span>
          {form.users.length > 0 && <span className="text-zinc-500 ml-4">+ {form.users.length} staff</span>}
        </div>
      )}
      <div className="mt-4 pt-4 border-t border-zinc-200">
        <span className="text-zinc-500 text-xs">Equipment:</span> <span className="font-semibold text-zinc-900 ml-2">{form.equipment.length} items</span>
        {form.equipment.length > 0 && (
          <span className="text-zinc-500 text-xs ml-4">
            Total: £{form.equipment.reduce((s, e) => s + (e.unit_price || 0), 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        )}
      </div>
    </Card>
    {aiData?.import_id && (
      <p className="text-xs text-zinc-400 text-center">
        Sicon-compatible CSV{(aiData?.batch_import_ids?.length || 0) > 1 ? 's (combined + per-invoice)' : ''} will be available for download after creation.
      </p>
    )}
  </div>
);

/* ─────── HELPERS ─────── */
function classifyEquipment(model) {
  const m = model.toLowerCase();
  if (m.includes('treadmill')) return 'Treadmill';
  if (m.includes('cycle') || m.includes('bike')) return 'Cycle';
  if (m.includes('elliptical') || m.includes('cross-trainer')) return 'Cross-Trainer';
  if (m.includes('rower') || m.includes('rowing')) return 'Rower';
  if (m.includes('stepmill') || m.includes('stepper')) return 'Stepper';
  if (m.includes('press') || m.includes('curl') || m.includes('pulldown') || m.includes('fly') || m.includes('deltoid') || m.includes('leg') || m.includes('abdom') || m.includes('calf') || m.includes('hip') || m.includes('row ') || m.includes('chin') || m.includes('dip') || m.includes('abduct') || m.includes('adduct')) return 'Strength';
  if (m.includes('smith') || m.includes('station') || m.includes('multi')) return 'Strength';
  if (m.includes('ski') || m.includes('sled') || m.includes('ube') || m.includes('upper body')) return 'Functional';
  return 'Other';
}

/* ─────── MAIN WIZARD ─────── */
const PulseOnboardingWizard = ({ onComplete }) => {
  const { token: authToken } = useAuth();
  const token = authToken || localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [mode, setMode] = useState(''); // 'new' | 'existing'
  const [tier, setTier] = useState('pro');
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [step, setStep] = useState(0);
  const [aiData, setAiData] = useState(null);
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState(null);

  const [form, setForm] = useState({
    site_name: '', address: '', postcode: '', phone: '',
    default_location: 'Main Floor', account_ref: '', install_date: '', supplier_name: '',
    tier: 'pro',
    owner_name: '', owner_email: '', owner_password: '', ownerShowPw: false,
    users: [],
    equipment: [],
  });

  useEffect(() => {
    axios.get(`${API}/master-admin/organizations`, { headers })
      .then(res => setOrgs(res.data.organizations || []))
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: context helpers re-create each render but read the latest token / handler at call time; adding them would invalidate the memo every render and break the optimisation.
  }, []);

  const getSteps = () => {
    if (mode === 'existing') {
      return [
        { id: 'choose', label: 'Choose', icon: Building2 },
        { id: 'invoice', label: 'Upload Invoice', icon: Sparkles },
        { id: 'equipment', label: 'Equipment', icon: Wrench },
        { id: 'review', label: 'Review & Add', icon: CheckCircle },
      ];
    }
    return [
      { id: 'choose', label: 'Choose', icon: Building2 },
      { id: 'invoice', label: 'Upload Invoice', icon: Sparkles },
      { id: 'site', label: 'Site Details', icon: Building2 },
      { id: 'users', label: 'Users', icon: Users },
      { id: 'equipment', label: 'Equipment', icon: Wrench },
      { id: 'review', label: 'Review & Create', icon: CheckCircle },
    ];
  };

  const steps = getSteps();
  const maxStep = steps.length - 1;

  const validate = () => {
    const currentStepId = steps[step]?.id;
    if (currentStepId === 'choose') {
      if (!mode) { notify.error('Please choose new site or existing customer'); return false; }
      if (mode === 'new' && !tier) { notify.error('Please select a service tier'); return false; }
      if (mode === 'existing' && !selectedOrg) { notify.error('Please select a customer'); return false; }
    }
    if (currentStepId === 'site') {
      if (!form.site_name.trim()) { notify.error('Site name is required'); return false; }
    }
    if (currentStepId === 'users') {
      if (!form.owner_name.trim() || !form.owner_email.trim() || !form.owner_password.trim()) { notify.error('Owner details required'); return false; }
      if (form.owner_password.length < 8) { notify.error('Password must be 8+ characters'); return false; }
    }
    return true;
  };

  const next = () => { if (validate()) setStep(s => Math.min(s + 1, maxStep)); };
  const back = () => setStep(s => Math.max(s - 1, 0));

  const handleCreate = async () => {
    setCreating(true);
    try {
      if (mode === 'new') {
        const payload = {
          site_name: form.site_name, tier: tier === 'gymaxis' ? 'pro' : tier,
          account_type: tier === 'gymaxis' ? 'gymaxis' : 'full',
          address: form.address, postcode: form.postcode, phone: form.phone,
          default_location: form.default_location,
          owner_name: form.owner_name, owner_email: form.owner_email, owner_password: form.owner_password,
          users: form.users.filter(u => u.email && u.name && u.password),
          equipment: form.equipment.map(e => ({
            name: e.name, equipment_type: e.equipment_type || classifyEquipment(e.name),
            manufacturer: e.manufacturer, serial_number: e.serial_number,
            location: e.location || form.default_location,
            unit_price: e.unit_price || 0,
            warranty_code: e.warranty_code || '',
            warranty_expiry: e.warranty_expiry || '',
            sla_name: e.sla_name || '',
            install_date: e.install_date || '',
          })),
        };
        const res = await axios.post(`${API}/master-admin/onboard-pulse-site`, payload, { headers });
        setResult(res.data);
        notify.success('Site created successfully!');
      } else {
        // Existing customer — import equipment (supports multiple invoices)
        const importIds = aiData?.batch_import_ids || (aiData?.import_id ? [aiData.import_id] : []);
        if (importIds.length === 0 && form.equipment.length === 0) {
          notify.error('No equipment to import');
          setCreating(false);
          return;
        }

        let totalCreated = 0;
        for (const importId of importIds) {
          try {
            // Get equipment belonging to this import
            const importEquipment = (form.equipment || [])
              .filter(eq => eq._import_id === importId)
              .map(eq => ({ ...eq, location: eq.location || form.default_location || '' }));

            if (importEquipment.length > 0) {
              await axios.put(`${API}/equipment-import/update/${importId}`, {
                equipment: importEquipment,
                default_location: form.default_location,
              }, { headers });
            }

            const res = await axios.post(`${API}/equipment-import/confirm/${importId}`, {
              target_organization_id: selectedOrg?.id,
            }, { headers });
            totalCreated += res.data.created || 0;
          } catch (err) {
            notify.error(`Invoice import failed: ${err.response?.data?.detail || err.message}`);
          }
        }

        setResult({ existing: true, org: selectedOrg, imported: totalCreated, invoiceCount: importIds.length });
        notify.success(`${totalCreated} equipment imported from ${importIds.length} invoice${importIds.length > 1 ? 's' : ''} to ${selectedOrg.name}`);
      }
    } catch (err) {
      notifyApiError(notify, err, 'Failed');
    }
    setCreating(false);
  };

  const handleDownloadSicon = async (importId = null) => {
    const targetId = importId || aiData?.import_id;
    if (!targetId) return;
    try {
      const res = await axios.get(`${API}/equipment-import/download/${targetId}`, { headers, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `Sicon_Import_${form.site_name || selectedOrg?.name || 'export'}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch { notify.error('Download failed'); }
  };

  const handleDownloadAllSicon = async () => {
    const importIds = aiData?.batch_import_ids || [];
    if (importIds.length <= 1) { handleDownloadSicon(); return; }
    // Download each individually and combine or just download individually
    for (const id of importIds) {
      try {
        const imp = await axios.get(`${API}/equipment-import/download/${id}`, { headers, responseType: 'blob' });
        const url = window.URL.createObjectURL(new Blob([imp.data]));
        const a = document.createElement('a');
        a.href = url;
        a.download = `Sicon_Import_${id.substring(0, 8)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } catch { /* skip failed downloads */ }
    }
    notify.success(`Downloaded ${importIds.length} Sicon CSV files`);
  };

  // Success screen
  if (result) {
    return (
      <div className="max-w-2xl mx-auto text-center py-8" data-testid="onboard-success">
        <div className="w-16 h-16 rounded-2xl bg-green-50 border border-green-200 flex items-center justify-center mx-auto mb-4">
          <CheckCircle size={32} className="text-green-600" />
        </div>
        <h2 className="text-2xl font-bold text-zinc-900 mb-2">
          {result.existing ? 'Equipment Added' : 'Site Created Successfully'}
        </h2>
        <p className="text-zinc-500 mb-6">
          {result.existing
            ? `${result.imported} equipment items added${result.invoiceCount > 1 ? ` from ${result.invoiceCount} invoices` : ''} to ${result.org?.name}`
            : `${result.organization?.name} is now live`
          }
        </p>

        {!result.existing && result.organization && (
          <Card className="bg-zinc-50 border-zinc-200 p-6 text-left mb-6">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div><p className="text-zinc-500 text-xs">Company Code</p><p className="text-zinc-900 font-mono text-lg">{result.organization.company_code}</p></div>
              <div><p className="text-zinc-500 text-xs">Tier</p><p className="text-zinc-900 font-semibold">{tier.toUpperCase()}</p></div>
              <div><p className="text-zinc-500 text-xs">Users</p><p className="text-zinc-900 font-semibold">{result.users?.length}</p></div>
              <div><p className="text-zinc-500 text-xs">Equipment</p><p className="text-zinc-900 font-semibold">{result.equipment_count}</p></div>
            </div>
          </Card>
        )}

        <div className="flex gap-3 justify-center flex-wrap">
          {aiData?.batch_import_ids?.length > 1 ? (
            <>
              <Button variant="outline" onClick={handleDownloadAllSicon} className="border-zinc-200 text-zinc-600" data-testid="onboard-download-all-csv">
                <Download size={14} className="mr-2" /> Download All CSVs ({aiData.batch_import_ids.length})
              </Button>
              <Button variant="outline" onClick={() => handleDownloadSicon()} className="border-zinc-200 text-zinc-600" data-testid="onboard-download-combined-csv">
                <Download size={14} className="mr-2" /> Combined Sicon CSV
              </Button>
            </>
          ) : aiData?.import_id ? (
            <Button variant="outline" onClick={() => handleDownloadSicon()} className="border-zinc-200 text-zinc-600" data-testid="onboard-download-csv">
              <Download size={14} className="mr-2" /> Download Sicon CSV
            </Button>
          ) : null}
          <Button onClick={() => { setResult(null); setStep(0); setMode(''); setAiData(null); setForm(f => ({ ...f, site_name: '', owner_name: '', owner_email: '', owner_password: '', users: [], equipment: [], account_ref: '' })); }}
            variant="outline" className="border-zinc-200 text-zinc-600" data-testid="onboard-create-another">
            Onboard Another Site
          </Button>
          {onComplete && <Button onClick={onComplete} className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" data-testid="onboard-done">Done</Button>}
        </div>
      </div>
    );
  }

  // Render current step
  const currentStepId = steps[step]?.id;

  return (
    <div className="max-w-3xl mx-auto" data-testid="pulse-onboarding-wizard">
      {/* Step indicator */}
      <div className="flex items-center gap-1 mb-8">
        {steps.map((s, i) => (
          <React.Fragment key={s.id}>
            <button
              onClick={() => i < step && setStep(i)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                i === step ? 'bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)]' : i < step ? 'text-green-600 hover:bg-zinc-50' : 'text-zinc-400'
              }`}
              disabled={i > step}
            >
              {i < step ? <CheckCircle size={16} /> : <s.icon size={16} />}
              <span className="hidden sm:inline">{s.label}</span>
            </button>
            {i < steps.length - 1 && <div className={`flex-1 h-px ${i < step ? 'bg-green-300' : 'bg-zinc-200'}`} />}
          </React.Fragment>
        ))}
      </div>

      {/* Step content */}
      {currentStepId === 'choose' && <ChooseModeStep mode={mode} setMode={setMode} tier={tier} setTier={setTier} orgs={orgs} selectedOrg={selectedOrg} setSelectedOrg={setSelectedOrg} />}
      {currentStepId === 'invoice' && <InvoiceUploadStep aiData={aiData} setAiData={setAiData} form={form} setForm={setForm} mode={mode} headers={headers} />}
      {currentStepId === 'site' && <SiteDetailsStep form={form} setForm={setForm} mode={mode} tier={tier} />}
      {currentStepId === 'users' && <UsersStep form={form} setForm={setForm} />}
      {currentStepId === 'equipment' && <EquipmentReviewStep form={form} setForm={setForm} />}
      {currentStepId === 'review' && <FinalReviewStep form={form} setForm={setForm} mode={mode} tier={tier} selectedOrg={selectedOrg} aiData={aiData} />}

      {/* Navigation */}
      <div className="flex items-center justify-between mt-8 pt-6 border-t border-zinc-200">
        <Button onClick={back} disabled={step === 0} variant="outline" className="border-zinc-200 text-zinc-600" data-testid="onboard-back">
          <ArrowLeft size={16} className="mr-2" /> Back
        </Button>
        {step < maxStep ? (
          <Button onClick={next} className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]" data-testid="onboard-next">
            {currentStepId === 'invoice' ? 'Continue' : 'Next'} <ArrowRight size={16} className="ml-2" />
          </Button>
        ) : (
          <Button onClick={handleCreate} disabled={creating} className="bg-green-600 text-white hover:bg-green-500" data-testid="onboard-create">
            {creating ? <Loader2 className="animate-spin mr-2" size={16} /> : <CheckCircle size={16} className="mr-2" />}
            {creating ? 'Processing...' : mode === 'existing' ? 'Import Equipment' : 'Create Site'}
          </Button>
        )}
      </div>
    </div>
  );
};

export default PulseOnboardingWizard;
