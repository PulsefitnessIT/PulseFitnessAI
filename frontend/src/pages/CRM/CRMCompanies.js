import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useCRM } from './CRMApp';
import {
  Building2, Plus, Search, ChevronRight, Users, Target, AlertTriangle,
  Shield, Phone, Mail, Globe, MapPin, Tag, MoreHorizontal, ArrowLeft,
  FileText, Calendar, Activity, DollarSign, CheckCircle, Clock, Edit2, Trash2, X,
  Upload, Download, Sparkles, Loader2, Hash
} from 'lucide-react';
import axios from 'axios';
import CRMAuditTrail from './CRMAuditTrail';
import CompanyAutocomplete from '@/components/shared/CompanyAutocomplete';

const TYPES = ['all', 'prospect', 'customer', 'partner', 'former'];
const TYPE_COLORS = { prospect: 'var(--color-warning)', customer: 'var(--color-success-alt)', partner: 'var(--color-info-ios)', former: 'var(--color-text-faint-alt)' };

/* ═══ COMPANY LIST ═══ */
function CompanyList({ onSelect, c, isDark, API, headers }) {
  const [companies, setCompanies] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', sector: '', type: 'prospect', phone: '', email: '', website: '', address: '', address_line1: '', address_line2: '', address_line3: '', city: '', county: '', postcode: '', country: 'United Kingdom', company_number: '', description: '', directors: [] });
  const [saving, setSaving] = useState(false);
  const [aiLookup, setAiLookup] = useState(false);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ search, skip: '0', limit: '50' });
      if (typeFilter !== 'all') params.set('type', typeFilter);
      const res = await axios.get(`${API}/crm/v2/companies?${params}`, { headers: headers() });
      setCompanies(res.data.companies);
      setTotal(res.data.total);
    } catch (e) { console.error(e); }
  }, [API, headers, search, typeFilter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API}/crm/v2/companies`, form, { headers: headers() });
      onSelect(res.data.id);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleNameChange = (val) => {
    setForm({ ...form, name: val });
  };

  const autoRecognize = async (query) => {
    if (!query || query.length < 3) return;
    setAiLookup(true);
    try {
      const res = await axios.post(`${API}/crm/v2/companies/auto-recognize`, { query }, { headers: headers() });
      if (res.data.success && res.data.company_info) {
        const info = res.data.company_info;
        setForm(prev => ({
          ...prev,
          address: info.address || prev.address,
          // Iter 215eq — when CH gives us the structured shape, use it.
          address_line1: info.address_line1 || info.address || prev.address_line1,
          address_line2: info.address_line2 || prev.address_line2,
          address_line3: info.address_line3 || prev.address_line3,
          phone: info.phone || prev.phone,
          website: info.website || prev.website,
          sector: info.industry || prev.sector,
          city: info.city || prev.city,
          county: info.county || prev.county,
          country: info.country || prev.country,
          postcode: info.postcode || prev.postcode,
          company_number: info.company_number || prev.company_number,
          description: info.description || prev.description,
          directors: info.directors || prev.directors,
        }));
      }
    } catch (e) { /* silent */ }
    setAiLookup(false);
  };

  return (
    <div data-testid="crm-companies-list">
      {/* Toolbar — search + filters + count + new company */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search companies..." className="w-full pl-9 pr-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'}`, color: c.text }} data-testid="company-search" />
        </div>
        <div className="flex gap-1">
          {TYPES.map(t => (
            <button key={t} onClick={() => setTypeFilter(t)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${typeFilter === t ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
              style={typeFilter !== t ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
              {t === 'all' ? 'All' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <p className="text-xs ml-auto" style={{ color: c.textDim }}>{total} account{total !== 1 ? 's' : ''}</p>
        <button type="button" onClick={() => setShowCreate(true)} className="btn-primary" data-testid="create-company-btn">
          <Plus size={14} /> New Company
        </button>
      </div>

      {/* Company Cards */}
      <div className="space-y-2">
        {companies.map(co => (
          <div key={co.id} onClick={() => onSelect(co.id)} className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.005]"
            style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`company-row-${co.id}`}>
            <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${TYPE_COLORS[co.type] || 'var(--color-text-faint-alt)'}15` }}>
              <Building2 size={18} style={{ color: TYPE_COLORS[co.type] || 'var(--color-text-faint-alt)' }} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{co.name}</p>
                <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${TYPE_COLORS[co.type] || 'var(--color-text-faint-alt)'}20`, color: TYPE_COLORS[co.type] || 'var(--color-text-faint-alt)' }}>{co.type}</span>
              </div>
              <div className="flex items-center gap-3 mt-0.5">
                {co.sector && <span className="text-[11px]" style={{ color: c.textDim }}>{co.sector}</span>}
                {co.city && <span className="text-[11px]" style={{ color: c.textDim }}>{co.city}</span>}
              </div>
            </div>
            <div className="flex items-center gap-4 shrink-0 text-xs">
              <div className="text-center hidden sm:block"><p className="font-bold" style={{ color: c.text }}>{co.contact_count || 0}</p><p style={{ color: c.textDim }}>contacts</p></div>
              <div className="text-center hidden sm:block"><p className="font-bold" style={{ color: 'var(--color-info-ios)' }}>{co.opportunity_count || 0}</p><p style={{ color: c.textDim }}>deals</p></div>
              <div className="text-center hidden md:block"><p className="font-bold" style={{ color: co.open_cases > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)' }}>{co.open_cases || 0}</p><p style={{ color: c.textDim }}>cases</p></div>
              <ChevronRight size={16} style={{ color: c.textDim }} />
            </div>
          </div>
        ))}
        {companies.length === 0 && (
          <div className="text-center py-16 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <Building2 size={40} className="mx-auto mb-3" style={{ color: c.textDim }} />
            <p className="text-sm font-medium" style={{ color: c.textMuted }}>No companies yet</p>
            <button onClick={() => setShowCreate(true)} className="text-sm text-[var(--color-info-ios)] mt-2 hover:underline">Create your first company</button>
          </div>
        )}
      </div>

      {/* Create Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-company-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>New Company</h2>
            {aiLookup && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-md" style={{ background: 'var(--color-info-ios)08', border: '1px solid var(--color-info-ios)20' }}>
                <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-info-ios)' }} />
                <span className="text-xs" style={{ color: 'var(--color-info-ios)' }}>AI looking up company details...</span>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium flex items-center gap-1" style={{ color: c.textDim }}>
                  Company Name * <Sparkles size={10} style={{ color: 'var(--color-info-ios)' }} />
                </label>
                <div className="flex gap-2 mt-1">
                  <div className="flex-1">
                    <CompanyAutocomplete
                      value={form.name}
                      onChange={(v) => setForm(prev => ({ ...prev, name: v }))}
                      onPick={(picked) => {
                        // Iter 215et — pre-fill the CRM company form when
                        // the user picks a suggestion. CH picks set
                        // company_number + structured address; internal
                        // (existing-CRM) picks pull the full record.
                        const isCH = picked.source === 'companies_house';
                        setForm(prev => ({
                          ...prev,
                          name: (isCH ? picked.company_name : picked.name) || prev.name,
                          company_number: picked.company_number || prev.company_number,
                          phone: isCH ? prev.phone : (picked.phone || prev.phone),
                          address_line1: picked.address_line1 || prev.address_line1,
                          address_line2: picked.address_line2 || prev.address_line2,
                          address_line3: picked.address_line3 || prev.address_line3,
                          city: picked.city || prev.city,
                          county: picked.county || prev.county,
                          postcode: picked.postcode || prev.postcode,
                          country: picked.country || prev.country,
                        }));
                      }}
                      testIdPrefix="company-name-autocomplete"
                      includeInternal={false}
                      placeholder="Type to search Companies House (UK)"
                      inputClassName="text-sm"
                    />
                  </div>
                  <button type="button" onClick={() => autoRecognize(form.name)} disabled={aiLookup || form.name.length < 3}
                    className="px-3 py-2 text-xs font-medium rounded-md flex items-center gap-1.5 transition-all disabled:opacity-40 shrink-0"
                    style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid="company-lookup-btn">
                    {aiLookup ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                    {aiLookup ? 'Searching...' : 'AI fill'}
                  </button>
                </div>
                <p className="text-[9px] mt-0.5" style={{ color: c.textDim }}>Pick from the dropdown for instant fill, or click "AI fill" for fuzzy AI-powered enrichment</p>
              </div>
              {[
                { key: 'company_number', label: 'Company Number', readOnly: true },
                { key: 'sector', label: 'Sector / Industry' },
                { key: 'type', label: 'Type', type: 'select', options: ['prospect', 'customer', 'partner'] },
                { key: 'phone', label: 'Phone' },
                { key: 'email', label: 'Email' },
                { key: 'website', label: 'Website', span: 2 },
                { key: 'address_line1', label: 'Address 1', span: 2 },
                { key: 'address_line2', label: 'Address 2', span: 2 },
                { key: 'address_line3', label: 'Address 3', span: 2 },
                { key: 'postcode', label: 'Post code', lookupPostcode: true },
                { key: 'city', label: 'City' },
                { key: 'county', label: 'County' },
                { key: 'country', label: 'Country' },
              ].map(f => (
                <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{f.label}</label>
                  {f.type === 'select' ? (
                    <select value={form[f.key]} onChange={e => setForm({...form, [f.key]: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: c.inputBg || (isDark ? 'var(--color-ink-alt)' : '#fff'), border: `1px solid ${c.border}`, color: c.text }}>
                      {f.options.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
                    </select>
                  ) : (
                    <input
                      value={form[f.key] || ''}
                      readOnly={f.readOnly}
                      onChange={e => setForm({...form, [f.key]: e.target.value})}
                      onBlur={f.lookupPostcode ? async (e) => {
                        // Iter 215eq — auto-fill city/county/country from
                        // postcodes.io when the user finishes typing the
                        // postcode. Doesn't clobber values already typed.
                        const pc = (e.target.value || '').trim();
                        if (!pc || pc.replace(/\s+/g, '').length < 5) return;
                        try {
                          const r = await axios.get(`${API}/integrations/postcode/lookup`, { headers: headers(), params: { postcode: pc } });
                          if (r.data?.found) {
                            setForm(prev => ({
                              ...prev,
                              postcode: r.data.postcode || prev.postcode,
                              city: prev.city || r.data.city || '',
                              county: prev.county || r.data.county || '',
                              country: r.data.country || prev.country,
                            }));
                          }
                        } catch { /* silent */ }
                      } : undefined}
                      className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                      style={{ background: f.readOnly ? (isDark ? '#111' : 'var(--color-neutral-25-alt)') : (c.inputBg || (isDark ? 'var(--color-ink-alt)' : '#fff')), border: `1px solid ${c.border}`, color: c.text, opacity: f.readOnly ? 0.8 : 1 }}
                      data-testid={`company-field-${f.key}`}
                    />
                  )}
                </div>
              ))}
              {form.directors?.length > 0 && (
                <div className="col-span-2">
                  <label className="text-[10px] uppercase tracking-wider font-medium flex items-center gap-1" style={{ color: c.textDim }}>
                    Directors <Shield size={10} style={{ color: 'var(--color-success-alt)' }} />
                  </label>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {form.directors.map((d, i) => (
                      <span key={i} className="px-2 py-1 text-xs rounded-md" style={{ background: isDark ? 'var(--color-navy-900)' : 'var(--color-info-bg)', color: 'var(--color-info-ios)', border: `1px solid ${isDark ? 'var(--color-navy-800)' : 'var(--color-blue-200)'}` }}>{d}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm rounded-md" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.name.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)] disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Company'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ COMPANY FILE TAB (Drawings / Surveys / Invoices) ═══ */
function CompanyFileTab({ companyId, category, label, accept, API, headers, c, isDark }) {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = React.useRef(null);

  const load = React.useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/companies/${companyId}/files?category=${category}`, { headers: headers() });
      setFiles(res.data.files);
    } catch (e) { console.error(e); }
  }, [API, headers, companyId, category]);

  React.useEffect(() => { load(); }, [load]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(`${API}/crm/v2/companies/${companyId}/files?category=${category}`, formData,
        { headers: { ...headers(), 'Content-Type': 'multipart/form-data' } });
      load();
    } catch (e) { console.error(e); }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleDelete = async (fileId) => {
    try { await axios.delete(`${API}/crm/v2/companies/${companyId}/files/${fileId}`, { headers: headers() }); load(); } catch (e) { console.error(e); }
  };

  const formatSize = (b) => b < 1024 ? `${b} B` : b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;

  return (
    <div data-testid={`company-files-${category}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold" style={{ color: c.text }}>{label}</h3>
        <div>
          <input type="file" accept={accept} onChange={handleUpload} ref={fileRef} className="hidden" id={`upload-${category}`} />
          <label htmlFor={`upload-${category}`} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md cursor-pointer hover:bg-[var(--color-brand-blue-deep)]">
            <Upload size={12} /> {uploading ? 'Uploading...' : 'Upload'}
          </label>
        </div>
      </div>
      {files.length > 0 ? (
        <div className="space-y-2">
          {files.map(f => (
            <div key={f.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <FileText size={16} style={{ color: category === 'drawings' ? 'var(--color-info-ios)' : category === 'surveys' ? 'var(--color-success-alt)' : 'var(--color-warning)' }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: c.text }}>{f.original_filename}</p>
                <p className="text-[11px]" style={{ color: c.textDim }}>{formatSize(f.size)} &middot; {f.uploaded_by_name} &middot; {new Date(f.created_at).toLocaleDateString('en-GB')}</p>
              </div>
              <a href={`${API}/crm/v2/companies/${companyId}/files/${f.id}/download`} className="p-1.5 rounded-md" style={{ color: 'var(--color-info-ios)' }}>
                <Download size={14} />
              </a>
              <button onClick={() => handleDelete(f.id)} className="p-1.5 rounded-md" style={{ color: c.textDim }}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8 border border-dashed rounded-md" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <Upload size={24} className="mx-auto mb-2" style={{ color: c.textDim }} />
          <p className="text-xs" style={{ color: c.textDim }}>No {label.toLowerCase()} uploaded yet</p>
        </div>
      )}
    </div>
  );
}

/* ═══ PORTAL EQUIPMENT TAB ═══ */
function PortalEquipmentTab({ companyId, API, headers, c, isDark }) {
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);

  React.useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/crm/v2/companies/${companyId}/portal-equipment`, { headers: headers() });
        setEquipment(res.data.equipment || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    })();
  }, [API, headers, companyId]);

  if (loading) return <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div data-testid="company-portal-equipment">
      <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>Operations Portal Equipment</h3>
      {equipment.length > 0 ? (
        <div className="space-y-2">
          {equipment.map((eq, i) => (
            <div key={eq.id || i} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
              <Shield size={16} style={{ color: 'var(--color-accent-magenta)' }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: c.text }}>{eq.name || eq.equipment_name || 'Equipment'}</p>
                <p className="text-[11px]" style={{ color: c.textDim }}>
                  {eq.model_code || eq.model || ''} {eq.serial_number ? `| S/N: ${eq.serial_number}` : ''} {eq.location ? `| ${eq.location}` : ''}
                </p>
              </div>
              <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: 'var(--color-accent-magenta)20', color: 'var(--color-accent-magenta)' }}>
                {eq.status || 'Active'}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8">
          <Shield size={32} className="mx-auto mb-2" style={{ color: c.textDim }} />
          <p className="text-sm" style={{ color: c.textDim }}>No equipment found in Operations Portal for this company</p>
          <p className="text-xs mt-1" style={{ color: c.textDim }}>Equipment is matched by company name</p>
        </div>
      )}
    </div>
  );
}

/* ═══ COMPANY DETAIL ═══ */
function CompanyDetail({ companyId, onBack, c, isDark, API, headers, setActiveTab, navigateTo }) {
  const [company, setCompany] = useState(null);
  const [activeSection, setActiveSection] = useState('overview');
  const [showAddNote, setShowAddNote] = useState(false);
  const [noteForm, setNoteForm] = useState({ subject: '', body: '', type: 'note' });
  const [saving, setSaving] = useState(false);
  const [showAddContact, setShowAddContact] = useState(false);
  const [contactForm, setContactForm] = useState({ first_name: '', last_name: '', email: '', phone: '', job_title: '', is_decision_maker: false });
  // Iter 238h — email duplicate detection. Once the user types a
  // valid-looking email into the Add Contact form, we look it up
  // across the org's contacts. If a match exists, we surface the
  // existing record with a one-click "Link to this company" instead
  // of creating a duplicate.
  const [emailMatch, setEmailMatch] = useState(null); // matched contact or null
  const [emailLookupBusy, setEmailLookupBusy] = useState(false);
  const [showAddQuote, setShowAddQuote] = useState(false);
  const [quoteLines, setQuoteLines] = useState([{ description: '', quantity: 1, unit_price: 0, discount: 0 }]);
  const [quoteNotes, setQuoteNotes] = useState('');
  const [contacts, setContacts] = useState([]);
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/companies/${companyId}`, { headers: headers() });
      setCompany(res.data);
    } catch (e) { console.error(e); }
  }, [API, headers, companyId]);

  useEffect(() => { load(); }, [load]);

  const handleAddActivity = async () => {
    if (!noteForm.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/activities`, { ...noteForm, company_id: companyId }, { headers: headers() });
      setShowAddNote(false);
      setNoteForm({ subject: '', body: '', type: 'note' });
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const handleAddContact = async () => {
    if (!contactForm.first_name.trim()) return;
    if (emailMatch) {
      // Email already exists — block create to prevent duplicates.
      // The dialog surfaces a "Link to this company" action instead.
      return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/contacts`, {
        ...contactForm, company_id: companyId, company_name: company?.name || '',
      }, { headers: headers() });
      setShowAddContact(false);
      setContactForm({ first_name: '', last_name: '', email: '', phone: '', job_title: '', is_decision_maker: false });
      setEmailMatch(null);
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  // Iter 238h — link an already-existing contact (matched by email) to
  // this company. Uses the existing PUT endpoint so we keep all
  // historical activity / notes / deals.
  const handleAttachExistingContact = async () => {
    if (!emailMatch?.id) return;
    setSaving(true);
    try {
      await axios.put(
        `${API}/crm/v2/contacts/${emailMatch.id}`,
        { company_id: companyId, company_name: company?.name || '' },
        { headers: headers() },
      );
      setShowAddContact(false);
      setContactForm({ first_name: '', last_name: '', email: '', phone: '', job_title: '', is_decision_maker: false });
      setEmailMatch(null);
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  // Debounced email lookup. Fires 350ms after the user stops typing,
  // skips invalid-looking strings to avoid noise.
  useEffect(() => {
    const email = (contactForm.email || '').trim().toLowerCase();
    if (!email || !email.includes('@') || email.length < 5) {
      setEmailMatch(null);
      return undefined;
    }
    const t = setTimeout(async () => {
      setEmailLookupBusy(true);
      try {
        const res = await axios.get(
          `${API}/crm/v2/contacts?search=${encodeURIComponent(email)}&limit=5`,
          { headers: headers() },
        );
        const exact = (res.data?.contacts || []).find(
          (ct) => (ct.email || '').toLowerCase() === email,
        );
        setEmailMatch(exact || null);
      } catch (e) {
        // silent — duplicate detection is a nicety, not a hard requirement.
      }
      setEmailLookupBusy(false);
    }, 350);
    return () => clearTimeout(t);
  }, [contactForm.email, API, headers]);

  const handleAddQuote = async () => {
    if (quoteLines.every(l => !l.description.trim())) return;
    setSaving(true);
    try {
      // Load contacts for this company to pick a contact
      const ctRes = await axios.get(`${API}/crm/v2/contacts?limit=200`, { headers: headers() });
      const coContacts = (ctRes.data.contacts || []).filter(c => c.company_id === companyId);
      await axios.post(`${API}/crm/v2/quotes`, {
        company_id: companyId, contact_id: coContacts[0]?.id || '',
        lines: quoteLines, vat_rate: 20, notes: quoteNotes,
      }, { headers: headers() });
      setShowAddQuote(false);
      setQuoteLines([{ description: '', quantity: 1, unit_price: 0, discount: 0 }]);
      setQuoteNotes('');
      load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  if (!company) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const openEdit = () => {
    setEditForm({
      name: company.name || '', sector: company.sector || '', type: company.type || 'prospect',
      phone: company.phone || '', email: company.email || '', website: company.website || '',
      address: company.address || '',
      address_line1: company.address_line1 || company.address || '',
      address_line2: company.address_line2 || '',
      address_line3: company.address_line3 || '',
      city: company.city || '',
      county: company.county || '',
      postcode: company.postcode || '',
      country: company.country || 'United Kingdom',
      sla_tier: company.sla_tier || 'standard', notes: company.notes || '',
    });
    setShowEdit(true);
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API}/crm/v2/companies/${companyId}`, editForm, { headers: headers() });
      setShowEdit(false);
      load();
    } catch (e) { console.error(e); }
    setSavingEdit(false);
  };

  const sections = [
    { id: 'overview', label: 'Overview' },
    { id: 'contacts', label: `Contacts (${company.contacts?.length || 0})` },
    { id: 'opportunities', label: `Deals (${company.opportunities?.length || 0})` },
    { id: 'cases', label: `Cases (${company.cases?.length || 0})` },
    { id: 'assets', label: `Assets (${company.assets?.length || 0})` },
    { id: 'quotes', label: `Quotes (${company.quotes?.length || 0})` },
    { id: 'drawings', label: 'Drawings' },
    { id: 'surveys', label: 'Site Surveys' },
    { id: 'invoices', label: 'Invoices' },
    { id: 'equipment', label: 'Equipment' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'audit', label: 'Audit' },
  ];

  const actIcons = { note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle, system: Activity, visit: MapPin };

  return (
    <div data-testid="crm-company-detail">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <button onClick={onBack} className="p-1.5 rounded-md transition-colors hover:bg-white/5" style={{ color: c.textDim }}><ArrowLeft size={18} /></button>
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: `${TYPE_COLORS[company.type] || 'var(--color-text-faint-alt)'}15` }}>
          <Building2 size={20} style={{ color: TYPE_COLORS[company.type] || 'var(--color-text-faint-alt)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-bold truncate" style={{ color: c.text }}>{company.name}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${TYPE_COLORS[company.type] || 'var(--color-text-faint-alt)'}20`, color: TYPE_COLORS[company.type] || 'var(--color-text-faint-alt)' }}>{company.type}</span>
            {company.sector && <span className="text-xs" style={{ color: c.textDim }}>{company.sector}</span>}
            {company.sla_tier && <span className="text-xs" style={{ color: c.textDim }}>SLA: {company.sla_tier}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={openEdit} className="px-3 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: c.border, color: c.textMuted }} data-testid="company-edit-btn">
            <Edit2 size={12} className="inline mr-1" /> Edit
          </button>
          <button onClick={() => setShowAddNote(true)} className="px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]" data-testid="add-activity-btn">
            <Plus size={12} className="inline mr-1" /> Log Activity
          </button>
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Total Revenue</p>
          <p className="text-lg font-bold" style={{ color: 'var(--color-success-alt)' }}>£{(company.total_revenue || 0).toLocaleString()}</p>
        </div>
        <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Open Pipeline</p>
          <p className="text-lg font-bold" style={{ color: 'var(--color-info-ios)' }}>£{(company.open_pipeline || 0).toLocaleString()}</p>
        </div>
        <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Contacts</p>
          <p className="text-lg font-bold" style={{ color: c.text }}>{company.contacts?.length || 0}</p>
        </div>
        <div className="p-3 rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>Open Cases</p>
          <p className="text-lg font-bold" style={{ color: (company.cases?.filter(cs => !['closed','resolved'].includes(cs.status)).length || 0) > 0 ? 'var(--color-accent-amber)' : 'var(--color-success-alt)' }}>{company.cases?.filter(cs => !['closed','resolved'].includes(cs.status)).length || 0}</p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        {sections.map(s => (
          <button key={s.id} onClick={() => setActiveSection(s.id)} className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap transition-all ${activeSection === s.id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
            style={activeSection !== s.id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
            {s.label}
          </button>
        ))}
      </div>

      {/* Section Content */}
      <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        {activeSection === 'overview' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Company Details</h3>
              {[
                { icon: Hash, label: 'Company No.', value: company.company_number },
                { icon: Globe, label: 'Website', value: company.website },
                { icon: Phone, label: 'Phone', value: company.phone },
                { icon: Mail, label: 'Email', value: company.email },
                { icon: MapPin, label: 'Address', value: [company.address_line1 || company.address, company.address_line2, company.address_line3, company.city, company.county, company.postcode, company.country].filter(Boolean).join(', ') },
                { icon: Tag, label: 'Sector', value: company.sector },
                { icon: Users, label: 'Account Owner', value: company.account_owner_name },
              ].map((item, i) => {
                if (!item.value) return null;
                const Icon = item.icon;
                return (
                  <div key={i} className="flex items-center gap-3">
                    <Icon size={14} style={{ color: c.textDim }} />
                    <span className="text-xs" style={{ color: c.textDim }}>{item.label}</span>
                    <span className="text-sm" style={{ color: c.text }}>{item.value}</span>
                  </div>
                );
              })}
            </div>
            {company.notes && (
              <div>
                <h3 className="text-sm font-semibold mb-2" style={{ color: c.text }}>Notes</h3>
                <p className="text-sm whitespace-pre-wrap" style={{ color: c.textMuted }}>{company.notes}</p>
              </div>
            )}
            {company.directors?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5" style={{ color: c.text }}>
                  <Shield size={14} style={{ color: 'var(--color-info-ios)' }} /> Directors
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {company.directors.map((d, i) => (
                    <span key={i} className="px-2.5 py-1 text-xs font-medium rounded-md" data-testid={`director-tag-${i}`}
                      style={{ background: isDark ? 'var(--color-navy-900)' : 'var(--color-info-bg)', color: 'var(--color-info-ios)', border: `1px solid ${isDark ? 'var(--color-navy-800)' : 'var(--color-blue-200)'}` }}>{d}</span>
                  ))}
                </div>
              </div>
            )}
            {company.description && (
              <div className="col-span-2">
                <h3 className="text-sm font-semibold mb-2" style={{ color: c.text }}>Description</h3>
                <p className="text-sm whitespace-pre-wrap" style={{ color: c.textMuted }}>{company.description}</p>
              </div>
            )}
          </div>
        )}

        {activeSection === 'contacts' && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Contacts</h3>
              <button onClick={() => setShowAddContact(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]" data-testid="company-add-contact-btn">
                <Plus size={12} /> Add Contact
              </button>
            </div>
            <div className="space-y-2">
              {(company.contacts || []).map(ct => (
                <div key={ct.id} className="flex items-center gap-3 p-3 rounded-md border cursor-pointer hover:opacity-80" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                  onClick={() => navigateTo && navigateTo('contact', ct.id)}>
                  <div className="w-8 h-8 rounded-full bg-[var(--color-accent-indigo)]/15 flex items-center justify-center text-xs font-bold" style={{ color: 'var(--color-accent-indigo)' }}>
                    {ct.first_name?.[0]}{ct.last_name?.[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: c.text }}>{ct.first_name} {ct.last_name}</p>
                    <p className="text-[11px]" style={{ color: c.textDim }}>{ct.job_title || ct.email}</p>
                  </div>
                  {ct.is_decision_maker && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500">DM</span>}
                  {ct.is_champion && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-green-500/15 text-green-500">Champion</span>}
                </div>
              ))}
              {(company.contacts || []).length === 0 && (
                <div className="text-center py-6">
                  <p className="text-sm" style={{ color: c.textDim }}>No contacts linked to this company</p>
                  <button onClick={() => setShowAddContact(true)} className="text-xs text-[var(--color-info-ios)] mt-1 hover:underline">Add the first contact</button>
                </div>
              )}
            </div>
          </div>
        )}

        {activeSection === 'opportunities' && (
          <div className="space-y-2">
            {(company.opportunities || []).map(opp => (
              <div key={opp.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <Target size={16} style={{ color: 'var(--color-info-ios)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: c.text }}>{opp.title}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>{opp.stage} | Close: {opp.close_date || 'TBD'}</p>
                </div>
                <span className="text-sm font-bold" style={{ color: c.text }}>£{(opp.value || 0).toLocaleString()}</span>
              </div>
            ))}
            {(company.opportunities || []).length === 0 && <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No deals yet</p>}
          </div>
        )}

        {activeSection === 'cases' && (
          <div className="space-y-2">
            {(company.cases || []).map(cs => (
              <div key={cs.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <AlertTriangle size={16} style={{ color: cs.severity === 'high' ? 'var(--color-danger-alt)' : cs.severity === 'medium' ? 'var(--color-accent-amber)' : 'var(--color-success-alt)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: c.text }}>{cs.case_number}: {cs.subject}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>{cs.status} | {cs.severity}</p>
                </div>
              </div>
            ))}
            {(company.cases || []).length === 0 && <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No service cases</p>}
          </div>
        )}

        {activeSection === 'assets' && (
          <div className="space-y-2">
            {(company.assets || []).map(a => (
              <div key={a.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <Shield size={16} style={{ color: 'var(--color-accent-magenta)' }} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate" style={{ color: c.text }}>{a.name}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>S/N: {a.serial_number || 'N/A'} | {a.status}</p>
                </div>
              </div>
            ))}
            {(company.assets || []).length === 0 && <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No assets installed</p>}
          </div>
        )}

        {activeSection === 'quotes' && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Quotes</h3>
              <button onClick={() => setShowAddQuote(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]" data-testid="company-add-quote-btn">
                <Plus size={12} /> Create Quote
              </button>
            </div>
            <div className="space-y-2">
              {(company.quotes || []).map(q => {
                const sc = { draft: 'var(--color-text-faint-alt)', sent: 'var(--color-info-ios)', accepted: 'var(--color-success-alt)', rejected: 'var(--color-danger)', pending_approval: 'var(--color-warning)', approved: 'var(--color-success-alt-2)', superseded: 'var(--color-accent-violet)' }[q.status] || 'var(--color-text-faint-alt)';
                return (
                  <div key={q.id} onClick={() => { if (navigateTo) navigateTo('quote', q.id); }} className="flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-all hover:scale-[1.005]" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`company-quote-${q.id}`}>
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${sc}15` }}>
                      <FileText size={14} style={{ color: sc }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate" style={{ color: c.text }}>{q.quote_number}</p>
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${sc}20`, color: sc }}>{q.status?.replace('_', ' ')}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>v{q.version || 1}</span>
                      </div>
                      <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>
                        {q.lines?.length || 0} items &middot; {q.created_by || ''} &middot; {q.created_at ? new Date(q.created_at).toLocaleDateString('en-GB') : ''}
                      </p>
                    </div>
                    <span className="text-sm font-bold shrink-0" style={{ color: 'var(--color-success-alt)' }}>£{(q.total || 0).toLocaleString()}</span>
                    <ChevronRight size={14} style={{ color: c.textDim }} />
                  </div>
                );
              })}
              {(company.quotes || []).length === 0 && (
                <div className="text-center py-6">
                  <p className="text-sm" style={{ color: c.textDim }}>No quotes for this company</p>
                  <button onClick={() => setShowAddQuote(true)} className="text-xs text-[var(--color-info-ios)] mt-1 hover:underline">Create the first quote</button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Drawings tab */}
        {activeSection === 'drawings' && (
          <CompanyFileTab companyId={companyId} category="drawings" label="CAD Drawings & Plans" accept=".pdf,.dwg,.dxf" API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {/* Site Surveys tab */}
        {activeSection === 'surveys' && (
          <CompanyFileTab companyId={companyId} category="surveys" label="Site Survey Files" accept="*" API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {/* Invoices tab */}
        {activeSection === 'invoices' && (
          <CompanyFileTab companyId={companyId} category="invoices" label="Invoices" accept=".pdf" API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {/* Equipment from Portal */}
        {activeSection === 'equipment' && (
          <PortalEquipmentTab companyId={companyId} API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {activeSection === 'timeline' && (
          <div className="space-y-0">
            {(company.activities || []).map((act, i) => {
              const Icon = actIcons[act.type] || Activity;
              const time = new Date(act.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
              return (
                <div key={act.id || i} className="flex gap-3 relative">
                  {i < (company.activities?.length || 0) - 1 && <div className="absolute left-3.5 top-8 w-px h-full" style={{ background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} />}
                  <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}>
                    <Icon size={12} style={{ color: c.textDim }} />
                  </div>
                  <div className="flex-1 pb-4 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate" style={{ color: c.text }}>{act.subject}</p>
                      <span className="text-[10px] shrink-0" style={{ color: c.textDim }}>{time}</span>
                    </div>
                    {act.body && <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{act.body}</p>}
                    <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>by {act.owner_name}</p>
                  </div>
                </div>
              );
            })}
            {(company.activities || []).length === 0 && <p className="text-sm text-center py-6" style={{ color: c.textDim }}>No activity yet</p>}
          </div>
        )}

        {activeSection === 'audit' && (
          <CRMAuditTrail entityType="company" entityId={companyId} emptyText="No edits logged on this company yet." />
        )}
      </div>

      {/* Edit Company Dialog */}
      {showEdit && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowEdit(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="edit-company-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Edit Company</h2>
              <button onClick={() => setShowEdit(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="edit-company-close"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { key: 'name', label: 'Company Name', span: 2 },
                { key: 'sector', label: 'Sector / Industry' },
                { key: 'type', label: 'Type', type: 'select', options: ['prospect', 'customer', 'partner', 'former'] },
                { key: 'phone', label: 'Phone' },
                { key: 'email', label: 'Email' },
                { key: 'website', label: 'Website', span: 2 },
                { key: 'address_line1', label: 'Address 1', span: 2 },
                { key: 'address_line2', label: 'Address 2', span: 2 },
                { key: 'address_line3', label: 'Address 3', span: 2 },
                { key: 'postcode', label: 'Post code', lookupPostcode: true },
                { key: 'city', label: 'City' },
                { key: 'county', label: 'County' },
                { key: 'country', label: 'Country' },
                { key: 'sla_tier', label: 'SLA Tier', type: 'select', options: ['standard', 'premium', 'enterprise'] },
              ].map(f => (
                <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{f.label}</label>
                  {f.type === 'select' ? (
                    <select value={editForm[f.key] || ''} onChange={e => setEditForm({...editForm, [f.key]: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid={`edit-company-${f.key}`}>
                      {f.options.map(o => <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>)}
                    </select>
                  ) : (
                    <input
                      value={editForm[f.key] || ''}
                      onChange={e => setEditForm({...editForm, [f.key]: e.target.value})}
                      onBlur={f.lookupPostcode ? async (e) => {
                        const pc = (e.target.value || '').trim();
                        if (!pc || pc.replace(/\s+/g, '').length < 5) return;
                        try {
                          const r = await axios.get(`${API}/integrations/postcode/lookup`, { headers: headers(), params: { postcode: pc } });
                          if (r.data?.found) {
                            setEditForm(prev => ({
                              ...prev,
                              postcode: r.data.postcode || prev.postcode,
                              city: prev.city || r.data.city || '',
                              county: prev.county || r.data.county || '',
                              country: r.data.country || prev.country,
                            }));
                          }
                        } catch { /* silent */ }
                      } : undefined}
                      className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                      style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                      data-testid={`edit-company-${f.key}`}
                    />
                  )}
                </div>
              ))}
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Notes</label>
                <textarea value={editForm.notes || ''} onChange={e => setEditForm({...editForm, notes: e.target.value})} rows={3} className="w-full mt-1 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowEdit(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={saveEdit} disabled={savingEdit} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-company-edit-btn">
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Activity Dialog */}
      {showAddNote && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddNote(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-3 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Log Activity</h2>
              <button onClick={() => setShowAddNote(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="company-add-activity-close"><X size={16} /></button>
            </div>
            <div className="flex gap-1 mb-3 flex-wrap">
              {['note', 'call', 'email', 'meeting', 'task'].map(t => (
                <button key={t} onClick={() => setNoteForm({...noteForm, type: t})} className={`px-3 py-1.5 text-xs font-medium rounded-md ${noteForm.type === t ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
                  style={noteForm.type !== t ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <input value={noteForm.subject} onChange={e => setNoteForm({...noteForm, subject: e.target.value})} placeholder="Subject *" className="w-full mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
            <textarea value={noteForm.body} onChange={e => setNoteForm({...noteForm, body: e.target.value})} placeholder="Details..." rows={3} className="w-full mb-2 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
            {noteForm.type === 'email' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input value={noteForm.email_from||''} onChange={e => setNoteForm({...noteForm, email_from: e.target.value})} placeholder="From email" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <input value={noteForm.email_to||''} onChange={e => setNoteForm({...noteForm, email_to: e.target.value})} placeholder="To email" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'call' && (
              <div className="grid grid-cols-3 gap-2 mb-2">
                <input type="number" value={noteForm.call_duration||''} onChange={e => setNoteForm({...noteForm, call_duration: e.target.value})} placeholder="Mins" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <select value={noteForm.call_outcome||'connected'} onChange={e => setNoteForm({...noteForm, call_outcome: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="connected">Connected</option><option value="voicemail">Voicemail</option><option value="no_answer">No Answer</option>
                </select>
                <input type="date" value={noteForm.follow_up_date||''} onChange={e => setNoteForm({...noteForm, follow_up_date: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'meeting' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input value={noteForm.meeting_location||''} onChange={e => setNoteForm({...noteForm, meeting_location: e.target.value})} placeholder="Location" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <input type="number" value={noteForm.meeting_duration||''} onChange={e => setNoteForm({...noteForm, meeting_duration: e.target.value})} placeholder="Duration (mins)" className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <input value={noteForm.attendees||''} onChange={e => setNoteForm({...noteForm, attendees: e.target.value})} placeholder="Attendees" className="col-span-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
            )}
            {noteForm.type === 'task' && (
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input type="date" value={noteForm.due_date||''} onChange={e => setNoteForm({...noteForm, due_date: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
                <select value={noteForm.priority||'normal'} onChange={e => setNoteForm({...noteForm, priority: e.target.value})} className="px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }}>
                  <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option>
                </select>
              </div>
            )}
            <div className="flex gap-2 justify-end mt-3">
              <button onClick={() => setShowAddNote(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleAddActivity} disabled={saving || !noteForm.subject.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">Save</button>
            </div>
          </div>
        </div>
      )}

      {/* Add Contact Dialog (from Company) */}
      {showAddContact && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddContact(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="company-add-contact-dialog">
            <h2 className="text-lg font-semibold mb-1" style={{ color: c.text }}>Add Contact</h2>
            <p className="text-xs mb-4" style={{ color: c.textDim }}>Contact will be linked to <strong>{company?.name}</strong></p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>First Name *</label>
                <input value={contactForm.first_name} onChange={e => setContactForm({...contactForm, first_name: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Last Name</label>
                <input value={contactForm.last_name} onChange={e => setContactForm({...contactForm, last_name: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>
                  Email {emailLookupBusy && <span className="ml-1 text-[9px] opacity-60">checking…</span>}
                </label>
                <input value={contactForm.email} onChange={e => setContactForm({...contactForm, email: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${emailMatch ? 'var(--color-warning)' : c.border}`, color: c.text }} data-testid="company-add-contact-email" />
                {emailMatch && (
                  <div className="mt-2 p-2.5 rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-900/20" data-testid="company-add-contact-email-match">
                    <p className="text-[11px] font-semibold text-amber-800 dark:text-amber-300">
                      A contact with this email already exists.
                    </p>
                    <div className="flex items-center justify-between gap-2 mt-1.5">
                      <div className="min-w-0">
                        <p className="text-xs font-medium truncate" style={{ color: c.text }}>
                          {emailMatch.first_name} {emailMatch.last_name}
                          {emailMatch.job_title && <span className="text-[10px] opacity-70 ml-1.5">· {emailMatch.job_title}</span>}
                        </p>
                        <p className="text-[10px] opacity-60 truncate" style={{ color: c.textDim }}>
                          {emailMatch.company_name
                            ? (emailMatch.company_id === companyId
                              ? 'Already linked to this company'
                              : `Currently linked to ${emailMatch.company_name}`)
                            : 'Not linked to any company yet'}
                        </p>
                      </div>
                      {emailMatch.company_id !== companyId && (
                        <button
                          onClick={handleAttachExistingContact}
                          disabled={saving}
                          className="shrink-0 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider rounded-md bg-amber-500 hover:bg-amber-600 text-white disabled:opacity-50"
                          data-testid="company-add-contact-attach-existing"
                        >
                          Link to {company?.name?.slice(0, 18) || 'this company'}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Phone</label>
                <input value={contactForm.phone} onChange={e => setContactForm({...contactForm, phone: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Job Title</label>
                <input value={contactForm.job_title} onChange={e => setContactForm({...contactForm, job_title: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
              </div>
              <div className="col-span-2">
                <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                  <input type="checkbox" checked={contactForm.is_decision_maker} onChange={e => setContactForm({...contactForm, is_decision_maker: e.target.checked})} /> Decision Maker
                </label>
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button onClick={() => setShowAddContact(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleAddContact} disabled={saving || !contactForm.first_name.trim() || !!emailMatch} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" title={emailMatch ? 'Resolve the duplicate-email warning above first' : undefined}>
                {saving ? 'Creating...' : 'Create Contact'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Quote Dialog (from Company) */}
      {showAddQuote && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddQuote(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="company-add-quote-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-start justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <div>
                <h2 className="text-lg font-semibold" style={{ color: c.text }}>Create Quote</h2>
                <p className="text-xs mt-0.5" style={{ color: c.textDim }}>Quote for <strong>{company?.name}</strong></p>
              </div>
              <button onClick={() => setShowAddQuote(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="company-add-quote-close"><X size={16} /></button>
            </div>
            <div className="space-y-2 mb-4">
              {quoteLines.map((line, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-5">
                    {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Description</span>}
                    <input value={line.description} onChange={e => { const l = [...quoteLines]; l[i] = {...l[i], description: e.target.value}; setQuoteLines(l); }} placeholder="Product/service"
                      className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                  </div>
                  <div className="col-span-2">
                    {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Qty</span>}
                    <input type="number" min="1" value={line.quantity} onChange={e => { const l = [...quoteLines]; l[i] = {...l[i], quantity: parseFloat(e.target.value)||0}; setQuoteLines(l); }}
                      className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                  </div>
                  <div className="col-span-3">
                    {i === 0 && <span className="text-[9px]" style={{ color: c.textDim }}>Unit Price (£)</span>}
                    <input type="number" min="0" step="0.01" value={line.unit_price} onChange={e => { const l = [...quoteLines]; l[i] = {...l[i], unit_price: parseFloat(e.target.value)||0}; setQuoteLines(l); }}
                      className="w-full px-2 py-1.5 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                  </div>
                  <div className="col-span-2 flex justify-center">
                    {quoteLines.length > 1 && <button onClick={() => setQuoteLines(quoteLines.filter((_,idx) => idx !== i))} style={{ color: 'var(--color-danger-alt)' }}><X size={14} /></button>}
                  </div>
                </div>
              ))}
              <button onClick={() => setQuoteLines([...quoteLines, { description: '', quantity: 1, unit_price: 0, discount: 0 }])} className="text-xs text-[var(--color-info-ios)] hover:underline">+ Add line item</button>
            </div>
            <textarea value={quoteNotes} onChange={e => setQuoteNotes(e.target.value)} placeholder="Notes (optional)" rows={2}
              className="w-full mb-3 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs" style={{ color: c.textDim }}>Subtotal (ex VAT)</span>
              <span className="text-sm font-bold" style={{ color: c.text }}>
                £{quoteLines.reduce((s, l) => s + (l.quantity * l.unit_price), 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowAddQuote(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleAddQuote} disabled={saving || quoteLines.every(l => !l.description.trim())} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">
                {saving ? 'Creating...' : 'Create Quote'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ MAIN COMPONENT ═══ */
export default function CRMCompanies() {
  const crm = useCRM();
  const { navTarget, setNavTarget } = crm;
  const [selectedId, setSelectedId] = useState(null);

  // Cross-module navigation: auto-open company detail if navigated from another module
  useEffect(() => {
    if (navTarget?.type === 'company' && navTarget?.id) {
      setSelectedId(navTarget.id);
      setNavTarget(null);
    }
  }, [navTarget, setNavTarget]);

  if (selectedId) {
    return <CompanyDetail companyId={selectedId} onBack={() => setSelectedId(null)} {...crm} />;
  }
  return <CompanyList onSelect={setSelectedId} {...crm} />;
}
