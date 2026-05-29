import React, { useState, useEffect, useCallback } from 'react';
import { useCRM } from './CRMApp';
import {
  Building2, Plus, ChevronRight, Users, Target, AlertTriangle,
  Shield, Phone, Mail, Globe, MapPin, Tag, ArrowLeft,
  FileText, Calendar, Activity, CheckCircle, Edit2, Trash2, X,
  Upload, Download, Sparkles, Loader2, Hash, Award
} from 'lucide-react';
import axios from 'axios';
import CRMAuditTrail from './CRMAuditTrail';
import { CrossModuleTimeline, EnrichFromWebsiteButton } from './CRMPhase3Panels';
import CompanyAutocomplete from '@/components/shared/CompanyAutocomplete';
import Button from '@/components/shared/Button';
import ListPanel from '@/components/shared/ListPanel';
import TimelinePanel from '@/components/CRM/TimelinePanel';
import {
  FITNESS_SECTOR_OPTIONS,
  UK_COUNTIES,
  COUNTRIES,
} from '@/utils/crmDropdowns';

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
  // Iter 216h268 — website-first recognition. Sales reps prefer the
  // company's actual trading website over Companies House (which
  // usually points at an accountant's office).
  const [websiteLookupUrl, setWebsiteLookupUrl] = useState('');
  const [websiteLookup, setWebsiteLookup] = useState(false);
  const [websiteLookupError, setWebsiteLookupError] = useState('');
  const [websiteSummary, setWebsiteSummary] = useState(null);

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

  const _handleNameChange = (val) => {
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

  // Iter 216h268 — fetch company info from a homepage URL. This is now
  // the recommended primary source (trading address + decision-makers
  // live on the website, not on the Companies House registered office).
  const autoRecognizeFromWebsite = async () => {
    const url = (websiteLookupUrl || '').trim();
    if (!url) {
      setWebsiteLookupError('Paste the prospect\u2019s website URL first');
      return;
    }
    setWebsiteLookup(true);
    setWebsiteLookupError('');
    setWebsiteSummary(null);
    try {
      const res = await axios.post(
        `${API}/crm/v2/companies/recognize-from-website`,
        { url },
        { headers: headers() },
      );
      const info = res.data?.company_info || {};
      setForm(prev => ({
        ...prev,
        name: info.name || prev.name,
        phone: info.phone || prev.phone,
        email: info.email || prev.email,
        website: info.website || url,
        address_line1: info.address_line1 || prev.address_line1,
        city: info.city || prev.city,
        county: info.county || prev.county,
        postcode: info.postcode || prev.postcode,
        country: info.country || prev.country,
        description: info.description || prev.description,
      }));
      setWebsiteSummary({
        url: res.data?.url || url,
        pagesFetched: res.data?.pages_fetched || [],
        cached: !!res.data?.cached,
        filled: Object.keys(info).filter(k => info[k]).length,
        socialLinks: info.social_links || [],
      });
    } catch (e) {
      setWebsiteLookupError(e?.response?.data?.detail || 'Could not read that website');
    }
    setWebsiteLookup(false);
  };

  return (
    <>
      <ListPanel
      data-testid="crm-companies-list"
      search={{ value: search, onChange: setSearch, placeholder: 'Search companies...', testId: 'company-search' }}
      count={{ value: total, label: 'account' }}
      primaryAction={{ label: 'New Company', icon: Plus, onClick: () => setShowCreate(true), testId: 'create-company-btn' }}
      empty={{
        when: companies.length === 0,
        icon: Building2,
        title: 'No companies yet',
        primaryAction: { label: 'Create your first company', onClick: () => setShowCreate(true) },
        testId: 'crm-companies-empty',
      }}
      toolbarRight={(
        <div className="flex gap-1">
          {TYPES.map(t => (
            <button key={t} onClick={() => setTypeFilter(t)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${typeFilter === t ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
              style={typeFilter !== t ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
              data-testid={`company-type-filter-${t}`}>
              {t === 'all' ? 'All' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      )}
    >
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
              {/* Iter 216h276 — visual badge so master admins can tell
                  Pulse-tenant mirrors apart from CRM-native rows. */}
              {co.source === 'tenant_mirror' && (
                <span
                  className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded inline-flex items-center gap-0.5"
                  style={{ background: 'rgba(99,102,241,0.15)', color: 'var(--color-accent-violet)' }}
                  data-testid={`company-tenant-mirror-badge-${co.id}`}
                  title="Auto-mirrored from a Pulse tenant org. Edits here don't push back to the tenant."
                >
                  ↺ Tenant
                </span>
              )}
              {co.status === 'former' && (
                <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: 'rgba(113,113,122,0.15)', color: 'var(--color-text-dim)' }}>Former</span>
              )}
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
      </ListPanel>

      {/* Create Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowCreate(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="create-company-dialog">
            <h2 className="text-lg font-semibold mb-4" style={{ color: c.text }}>New Company</h2>
            {/* Iter 216h268 — website-first recognition. Recommended
                primary source: paste the prospect's actual trading
                website (not Companies House) so the right typing
                (trading address, switchboard, decision-makers) flows
                through to the rest of the CRM. */}
            <div
              className="mb-4 rounded-lg p-3"
              style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-25-alt)', border: `1px solid ${c.border}` }}
              data-testid="company-website-recognise-panel"
            >
              <label className="text-[10px] uppercase tracking-wider font-medium flex items-center gap-1.5" style={{ color: c.textDim }}>
                <Globe size={11} style={{ color: 'var(--color-info-ios)' }} />
                Start from website URL <span className="text-[9px] opacity-70">(recommended)</span>
              </label>
              <div className="flex gap-2 mt-1.5">
                <input
                  type="url"
                  value={websiteLookupUrl}
                  onChange={e => { setWebsiteLookupUrl(e.target.value); setWebsiteLookupError(''); }}
                  placeholder="https://acmegym.co.uk"
                  className="flex-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: c.inputBg || (isDark ? 'var(--color-ink-alt)' : '#fff'), border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="company-website-url-input"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); autoRecognizeFromWebsite(); } }}
                />
                <button
                  type="button"
                  onClick={autoRecognizeFromWebsite}
                  disabled={websiteLookup || !websiteLookupUrl.trim()}
                  className="px-3 py-2 text-xs font-medium rounded-md flex items-center gap-1.5 transition-all disabled:opacity-40 shrink-0"
                  style={{ background: 'var(--color-info-ios)', color: '#fff' }}
                  data-testid="company-website-lookup-btn"
                >
                  {websiteLookup ? <Loader2 size={12} className="animate-spin" /> : <Globe size={12} />}
                  {websiteLookup ? 'Reading…' : 'Fetch'}
                </button>
              </div>
              <p className="text-[9px] mt-1" style={{ color: c.textDim }}>
                We&apos;ll pull name, phone, email, address, description &amp; social links straight from the company&apos;s site. Cached for 24h.
              </p>
              {websiteLookupError && (
                <p className="text-[10px] mt-1.5" style={{ color: 'var(--color-danger-alt)' }} data-testid="company-website-lookup-error">{websiteLookupError}</p>
              )}
              {websiteSummary && (
                <div className="mt-2 text-[10px] flex items-center gap-2 flex-wrap" style={{ color: c.textDim }} data-testid="company-website-lookup-summary">
                  <span style={{ color: 'var(--color-success-alt)' }}>{websiteSummary.filled} fields filled</span>
                  <span>·</span>
                  <span>{websiteSummary.pagesFetched.length} page{websiteSummary.pagesFetched.length === 1 ? '' : 's'} read{websiteSummary.cached ? ' (cached)' : ''}</span>
                  {websiteSummary.socialLinks.length > 0 && (
                    <>
                      <span>·</span>
                      <span>{websiteSummary.socialLinks.length} social link{websiteSummary.socialLinks.length === 1 ? '' : 's'}</span>
                    </>
                  )}
                </div>
              )}
            </div>
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
                      placeholder="Or type a name to search Companies House (UK)"
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
                // Iter 216h195 — Wave 2 dropdown audit: sector is now a
                // curated UK fitness-industry taxonomy (Gym Chain,
                // Boutique Studio, Hotel Health Club, etc.) so reports
                // can slice the pipeline by segment without dirty data.
                { key: 'sector', label: 'Sector / Industry', type: 'select', options: FITNESS_SECTOR_OPTIONS },
                { key: 'type', label: 'Type', type: 'select', options: ['prospect', 'customer', 'partner'] },
                { key: 'phone', label: 'Phone' },
                { key: 'email', label: 'Email' },
                { key: 'website', label: 'Website', span: 2 },
                { key: 'address_line1', label: 'Address 1', span: 2 },
                { key: 'address_line2', label: 'Address 2', span: 2 },
                { key: 'address_line3', label: 'Address 3', span: 2 },
                { key: 'postcode', label: 'Post code', lookupPostcode: true },
                { key: 'city', label: 'City' },
                // County / Country use datalist so users get a typeahead
                // list yet can still enter bespoke values (overseas
                // territories, edge cases) without being blocked.
                { key: 'county', label: 'County', datalist: 'crm-county-presets' },
                { key: 'country', label: 'Country', datalist: 'crm-country-presets' },
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
                      list={f.datalist}
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
              {/* Iter 216h195 — shared datalists for County / Country
                  on this form. Rendered once, referenced by `list=` on
                  individual inputs above. */}
              <datalist id="crm-county-presets">
                {UK_COUNTIES.map((c) => <option key={c} value={c} />)}
              </datalist>
              <datalist id="crm-country-presets">
                {COUNTRIES.map((c) => <option key={c} value={c} />)}
              </datalist>
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
    </>
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


/* ═══ SITES & EQUIPMENT TAB (Phase 1 of Ops↔CRM↔ServiceDesk link) ═══
   Iter 216h196 — Lee's ask: Pulse Fitness HQ wants its child sites
   (iGym Carshalton, iGym Congleton) surfaced inside CRM with each
   piece of equipment showing its live contract-coverage badge, plus a
   one-click "Add coverage" action to attach equipment to a new or
   existing aftersales contract. Backend endpoint:
     GET  /api/crm/v2/companies/{id}/sites-and-equipment
     POST /api/crm/v2/companies/{id}/equipment-coverage
     POST /api/crm/v2/companies/{id}/link-organization
   The link-organization endpoint is used when the company isn't
   auto-linked by name (returns linked_via='unlinked' from the GET). */
function SitesAndEquipmentTab({ companyId, companyName, API, headers, c, isDark }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [coverageModal, setCoverageModal] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/crm/v2/companies/${companyId}/sites-and-equipment`, { headers: headers() });
      setData(r.data);
      if (r.data?.sites?.length) {
        setExpanded((prev) => ({ ...prev, [r.data.sites[0].id]: true }));
      }
    } catch {
      setData({ sites: [], totals: {}, linked_via: 'error' });
    }
    setLoading(false);
  }, [API, headers, companyId]);

  useEffect(() => { load(); }, [load]);

  const linkSelf = async () => {
    try {
      const meRes = await axios.get(`${API}/auth/me`, { headers: headers() }).catch(() => null);
      const orgId = meRes?.data?.organization_id || meRes?.data?.user?.organization_id;
      if (!orgId) {
        window.alert('Could not detect your organisation id — please contact support.');
        return;
      }
      await axios.post(`${API}/crm/v2/companies/${companyId}/link-organization`,
        { organization_id: orgId }, { headers: headers() });
      load();
    } catch (e) {
      window.alert(e?.response?.data?.detail || 'Link failed');
    }
  };

  if (loading) {
    return <div className="py-10 text-center text-xs" style={{ color: c.textDim }}>Loading sites & equipment…</div>;
  }

  if (!data || data.linked_via === 'unlinked') {
    return (
      <div className="rounded-xl p-8 text-center" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)', border: `1px dashed ${c.border}` }} data-testid="sites-equipment-unlinked">
        <MapPin size={32} className="mx-auto mb-2" style={{ color: c.textDim }} />
        <p className="text-sm font-semibold mb-1" style={{ color: c.text }}>This company isn't linked to an operations estate yet</p>
        <p className="text-xs mb-4" style={{ color: c.textDim }}>
          Link "{companyName}" to your own organisation to surface its sites + equipment + active contract coverage here.
        </p>
        <button onClick={linkSelf}
          className="px-4 py-2 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white hover:bg-[var(--color-brand-blue-deep)]"
          data-testid="sites-equipment-link-self">
          Link to my organisation
        </button>
      </div>
    );
  }

  const { sites, totals, linked_via } = data;
  return (
    <div className="space-y-3" data-testid="sites-equipment-panel">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: 'Sites', value: totals?.sites ?? 0, tint: 'var(--color-info-ios)' },
          { label: 'Equipment', value: totals?.equipment ?? 0, tint: 'var(--color-text-muted)' },
          { label: 'Covered', value: totals?.covered ?? 0, tint: 'var(--color-success-alt)' },
          { label: 'Expiring < 90d', value: totals?.expiring_soon ?? 0, tint: 'var(--color-warning)' },
        ].map((k) => (
          <div key={k.label} className="rounded-lg p-3 border" style={{ background: isDark ? 'var(--color-surface-dark-2)' : '#fff', borderColor: c.border }}>
            <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: c.textDim }}>{k.label}</p>
            <p className="text-xl font-bold mt-0.5" style={{ color: k.tint }}>{k.value}</p>
          </div>
        ))}
      </div>
      {linked_via === 'name_match' && (
        <p className="text-[10px] italic" style={{ color: c.textDim }} data-testid="sites-equipment-linked-by-name">
          Auto-linked to your organisation by name match.
        </p>
      )}
      {sites.length === 0 && (
        <div className="rounded-xl p-6 text-center" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)', border: `1px dashed ${c.border}` }}>
          <p className="text-sm" style={{ color: c.textDim }}>No sites yet — onboard a site in Operations to see it here.</p>
        </div>
      )}
      {sites.map((s) => (
        <div key={s.id} className="rounded-lg border" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: c.border }} data-testid={`sites-equipment-site-${s.id}`}>
          <button type="button" onClick={() => setExpanded((p) => ({ ...p, [s.id]: !p[s.id] }))}
            className="w-full px-3 py-2 flex items-center justify-between text-left">
            <div className="flex items-center gap-2">
              <ChevronRight size={14} style={{ color: c.textDim, transform: expanded[s.id] ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
              <MapPin size={13} style={{ color: 'var(--color-info-ios)' }} />
              <span className="text-sm font-semibold" style={{ color: c.text }}>{s.name}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-3)' : 'var(--color-neutral-100)', color: c.textDim }}>
                {s.equipment_count} eq
              </span>
            </div>
          </button>
          {expanded[s.id] && (
            <div className="border-t" style={{ borderColor: c.border }}>
              {s.equipment.length === 0 && (
                <p className="px-3 py-3 text-xs" style={{ color: c.textDim }}>No equipment at this site yet.</p>
              )}
              {s.equipment.map((eq) => (
                <div key={eq.id} className="px-3 py-2 flex items-center justify-between gap-3 border-b last:border-b-0" style={{ borderColor: c.border }} data-testid={`sites-equipment-eq-${eq.id}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: c.text }}>{eq.name || '(unnamed)'}</p>
                    <p className="text-[11px] truncate" style={{ color: c.textDim }}>
                      {[eq.manufacturer, eq.model, eq.serial_number && `S/N ${eq.serial_number}`].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                  <CoverageBadge coverage={eq.coverage} isDark={isDark} />
                  <button type="button"
                    onClick={() => setCoverageModal({ equipment_id: eq.id, equipment_name: eq.name, site_id: s.id === '__unassigned__' ? '' : s.id, current_coverage: eq.coverage })}
                    className="text-[11px] px-2 py-1 rounded font-semibold"
                    style={{ background: eq.coverage.has_coverage ? 'transparent' : 'var(--color-info-ios)',
                             color: eq.coverage.has_coverage ? 'var(--color-info-ios)' : '#fff',
                             border: eq.coverage.has_coverage ? `1px solid var(--color-info-ios)` : 'none' }}
                    data-testid={`sites-equipment-add-cover-${eq.id}`}>
                    {eq.coverage.has_coverage ? 'Manage' : '+ Add coverage'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {coverageModal && (
        <AddCoverageModal
          companyId={companyId} state={coverageModal}
          onClose={() => setCoverageModal(null)} onSaved={() => { setCoverageModal(null); load(); }}
          API={API} headers={headers} c={c} isDark={isDark}
        />
      )}
    </div>
  );
}

function CoverageBadge({ coverage, isDark }) {
  if (!coverage?.has_coverage) {
    return (
      <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0" data-testid="coverage-badge-none"
        style={{ background: isDark ? 'rgba(239, 68, 68, 0.15)' : '#FEE2E2', color: '#DC2626' }}>
        Not covered
      </span>
    );
  }
  const tier = coverage.tier || 'covered';
  const end = coverage.end_date || '';
  const endFmt = end ? end.split('-').reverse().join('/') : '';
  const today = new Date();
  const cutoff = new Date(today.getTime() + 90 * 86400000);
  const endDate = end ? new Date(end + 'T00:00:00Z') : null;
  const expiringSoon = endDate && endDate <= cutoff;
  const bg = expiringSoon ? (isDark ? 'rgba(245, 158, 11, 0.15)' : '#FEF3C7') : (isDark ? 'rgba(34, 197, 94, 0.15)' : '#DCFCE7');
  const fg = expiringSoon ? '#D97706' : '#16A34A';
  return (
    <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded shrink-0" data-testid="coverage-badge-active"
      style={{ background: bg, color: fg }} title={`${coverage.contract_title || ''} — ${coverage.coverage_type || ''}`}>
      {tier} · {endFmt || '—'}
    </span>
  );
}

function AddCoverageModal({ companyId, state, onClose, onSaved, API, headers, c, isDark }) {
  const [contracts, setContracts] = useState([]);
  const [form, setForm] = useState({
    contract_id: '',
    coverage_type: 'full',
    warranty_end: '',
    contract_title: `Aftersales — ${state.equipment_name || 'equipment'}`,
    tier: 'bronze',
    start_date: new Date().toISOString().slice(0, 10),
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/crm/v2/contracts?company_id=${companyId}&status=active`, { headers: headers() })
      .then((r) => setContracts(r.data?.contracts || r.data || []))
      .catch(() => setContracts([]));
  }, [API, headers, companyId]);

  const submit = async () => {
    setSaving(true);
    try {
      const payload = {
        equipment_id: state.equipment_id,
        site_id: state.site_id,
        contract_id: form.contract_id || '',
        coverage_type: form.coverage_type,
        warranty_end: form.warranty_end || '',
      };
      if (!form.contract_id) {
        payload.contract_title = form.contract_title;
        payload.tier = form.tier;
        payload.start_date = form.start_date;
        payload.end_date = form.warranty_end || '';
      }
      await axios.post(`${API}/crm/v2/companies/${companyId}/equipment-coverage`, payload, { headers: headers() });
      onSaved();
    } catch (e) {
      window.alert(e?.response?.data?.detail || 'Save failed');
    }
    setSaving(false);
  };

  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text };
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md mx-4 rounded-xl p-5 shadow-2xl"
        style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
        onClick={(e) => e.stopPropagation()}
        data-testid="add-coverage-modal">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold" style={{ color: c.text }}>Add coverage — {state.equipment_name}</h3>
          <button onClick={onClose} style={{ color: c.textDim }}><X size={14} /></button>
        </div>
        <div className="space-y-2">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>Contract</span>
            <select value={form.contract_id} onChange={(e) => setForm({ ...form, contract_id: e.target.value })}
              className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-contract">
              <option value="">+ Create a new aftersales contract</option>
              {contracts.map((ct) => (
                <option key={ct.id} value={ct.id}>{ct.contract_number || ct.title} — {ct.tier} {ct.end_date ? `(until ${ct.end_date})` : ''}</option>
              ))}
            </select>
          </label>
          {!form.contract_id && (
            <>
              <label className="block">
                <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>New contract title</span>
                <input value={form.contract_title} onChange={(e) => setForm({ ...form, contract_title: e.target.value })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-title" />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="block">
                  <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>Tier</span>
                  <select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-tier">
                    {['warranty', 'bronze', 'silver', 'gold', 'platinum', 'bespoke'].map((t) => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>Start date</span>
                  <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                    className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-start" />
                </label>
              </div>
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>Coverage type</span>
              <select value={form.coverage_type} onChange={(e) => setForm({ ...form, coverage_type: e.target.value })}
                className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-type">
                <option value="full">Full (parts + labour)</option>
                <option value="parts_only">Parts only</option>
                <option value="labour_only">Labour only</option>
                <option value="inspection">Inspection only</option>
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: c.textDim }}>Cover until</span>
              <input type="date" value={form.warranty_end} onChange={(e) => setForm({ ...form, warranty_end: e.target.value })}
                className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={inputStyle} data-testid="add-coverage-end" />
            </label>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-1.5 text-xs" style={{ color: c.textMuted }}>Cancel</button>
          <button onClick={submit} disabled={saving}
            className="px-4 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-semibold rounded-md disabled:opacity-50"
            data-testid="add-coverage-save">
            {saving ? 'Saving…' : 'Add coverage'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══ COMPANY DETAIL ═══ */
function CompanyDetail({ companyId, onBack, c, isDark, API, headers, _setActiveTab, navigateTo }) {
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
  // Iter 216h266 — 360° UI: case & deal create dialogs directly on
  // the company drawer. Customer feedback: "I didn't seem to be
  // able to log a case and have it appear against the company
  // record." Backend already supports company_id on cases; we just
  // needed the UI affordances.
  const [showAddCase, setShowAddCase] = useState(false);
  const [caseForm, setCaseForm] = useState({ subject: '', description: '', severity: 'medium' });
  const [showAddDeal, setShowAddDeal] = useState(false);
  const [dealForm, setDealForm] = useState({ title: '', value: '', stage: 'lead', close_date: '' });
  const [_contacts, _setContacts] = useState([]);
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

  // Iter 216h266 — log a case directly from the company drawer.
  const handleAddCase = async () => {
    if (!caseForm.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/cases`, {
        ...caseForm,
        company_id: companyId,
        contact_id: company?.contacts?.[0]?.id || undefined,
      }, { headers: headers() });
      setShowAddCase(false);
      setCaseForm({ subject: '', description: '', severity: 'medium' });
      load();
    } catch (e) { console.error(e); window.alert(e?.response?.data?.detail || 'Could not log case'); }
    setSaving(false);
  };

  const handleAddDeal = async () => {
    if (!dealForm.title.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/opportunities`, {
        title: dealForm.title,
        value: Number(dealForm.value) || 0,
        stage: dealForm.stage,
        close_date: dealForm.close_date || undefined,
        company_id: companyId,
        contact_id: company?.contacts?.[0]?.id || undefined,
      }, { headers: headers() });
      setShowAddDeal(false);
      setDealForm({ title: '', value: '', stage: 'lead', close_date: '' });
      load();
    } catch (e) { console.error(e); window.alert(e?.response?.data?.detail || 'Could not create deal'); }
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
    // Iter 216h266 — dedicated Activities tab (data already loaded by
    // /companies/{id} timeline). Customer feedback: needed all
    // related activities in one 360° place.
    { id: 'activities', label: `Activity (${company.activities?.length || 0})` },
    // Iter 220bv — Unified Timeline (activities + quotes + cases +
    // tender events). The legacy "Activity" tab above is kept for
    // ops who prefer the focused view; this one is the 360° feed.
    { id: 'timeline', label: 'Timeline' },
    // Iter 216h196 — Phase 1 of the Ops↔CRM↔ServiceDesk linkage:
    // surfaces the company's linked-org sites + machines with live
    // contract-coverage badges, and lets operators attach aftersales
    // contracts directly from this view.
    { id: 'sites_equipment', label: 'Sites & Equipment' },
    { id: 'assets', label: `Assets (${company.assets?.length || 0})` },
    { id: 'quotes', label: `Quotes (${company.quotes?.length || 0})` },
    { id: 'tenders', label: `Tenders (${company.tenders?.length || 0})` },
    { id: 'drawings', label: 'Drawings' },
    { id: 'surveys', label: 'Site Surveys' },
    { id: 'invoices', label: 'Invoices' },
    { id: 'equipment', label: 'Equipment' },
    { id: 'timeline', label: 'Timeline' },
    { id: 'audit', label: 'Audit' },
  ];

  const _actIcons = { note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle, system: Activity, visit: MapPin };

  return (
    <div data-testid="crm-company-detail">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Button variant="ghost" size="iconSm" onClick={onBack} icon={ArrowLeft} title="Back" data-testid="crm-company-back" />
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
          {company.website && <EnrichFromWebsiteButton companyId={companyId} onEnriched={() => load()} />}
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
            <div className="flex justify-end">
              <button onClick={() => setShowAddDeal(true)} className="text-xs px-3 py-1.5 rounded-md font-medium flex items-center gap-1" style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid="company-add-deal-btn">
                <Plus size={12} /> New deal
              </button>
            </div>
            {(company.opportunities || []).map(opp => (
              <div key={opp.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`company-deal-row-${opp.id}`}>
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
            <div className="flex justify-end">
              <button onClick={() => setShowAddCase(true)} className="text-xs px-3 py-1.5 rounded-md font-medium flex items-center gap-1" style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid="company-add-case-btn">
                <Plus size={12} /> Log case
              </button>
            </div>
            {(company.cases || []).map(cs => (
              <div key={cs.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`company-case-row-${cs.id}`}>
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

        {activeSection === 'activities' && (
          <div className="space-y-2" data-testid="company-activities-section">
            <div className="flex justify-end">
              <button onClick={() => setShowAddNote(true)} className="text-xs px-3 py-1.5 rounded-md font-medium flex items-center gap-1" style={{ background: 'var(--color-info-ios)', color: '#fff' }} data-testid="company-add-activity-btn">
                <Plus size={12} /> Log activity
              </button>
            </div>
            {(company.activities || []).map(a => (
              <div key={a.id} className="p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`company-activity-row-${a.id}`}>
                <div className="flex items-start gap-3">
                  <FileText size={14} style={{ color: 'var(--color-info-ios)', marginTop: 2 }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-sm font-medium" style={{ color: c.text }}>{a.subject || a.type || 'Activity'}</p>
                      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'var(--color-info-ios)20', color: 'var(--color-info-ios)' }}>{a.type || 'note'}</span>
                    </div>
                    {a.body && <p className="text-[12px] mt-1 whitespace-pre-wrap" style={{ color: c.textMuted }}>{a.body}</p>}
                    <p className="text-[11px] mt-1" style={{ color: c.textDim }}>
                      {a.owner_name || 'system'} · {a.created_at ? new Date(a.created_at).toLocaleString() : ''}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {(company.activities || []).length === 0 && (
              <p className="text-sm text-center py-6" style={{ color: c.textDim }}>
                No activities logged yet. Notes, emails and calls posted against this company will appear here.
              </p>
            )}
          </div>
        )}

        {/* Iter 220bv — Unified Timeline (activities + quotes + cases + tender events) */}
        {activeSection === 'timeline' && (
          <TimelinePanel
            scope={{ type: 'company', id: companyId }}
            API={API}
            headers={headers}
            isDark={isDark}
            c={c}
          />
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

        {/* Iter 220an — Tenders deep-linked from the company 360 view */}
        {activeSection === 'tenders' && (
          <div data-testid="company-tenders-section">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: c.text }}>Tenders</h3>
              <button
                onClick={() => navigateTo && navigateTo('tender', null)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md hover:bg-[var(--color-brand-blue-deep)]"
                data-testid="company-open-tenders-btn"
              >
                <Award size={12} /> Open Tenders module
              </button>
            </div>
            <div className="space-y-2">
              {(company.tenders || []).map(t => {
                const sc = {
                  draft: 'var(--color-text-faint-alt)', parsing: 'var(--color-info-ios)',
                  in_progress: 'var(--color-warning)', review: 'var(--color-accent-magenta)',
                  submitted: 'var(--color-success-alt)', won: 'var(--color-success-alt-2)',
                  lost: 'var(--color-danger)',
                }[t.status] || 'var(--color-text-faint-alt)';
                const progress = t.total_questions > 0
                  ? Math.round((t.answered_questions / t.total_questions) * 100)
                  : 0;
                return (
                  <div
                    key={t.id}
                    onClick={() => navigateTo && navigateTo('tender', t.id)}
                    className="flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-all hover:scale-[1.005]"
                    style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                    data-testid={`company-tender-${t.id}`}
                  >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${sc}15` }}>
                      <Award size={14} style={{ color: sc }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate" style={{ color: c.text }}>{t.title}</p>
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: `${sc}20`, color: sc }}>{t.status?.replace('_', ' ')}</span>
                        <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textDim }}>{t.type}</span>
                      </div>
                      <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>
                        {t.issuer && <>{t.issuer} &middot; </>}
                        {t.total_questions || 0} questions &middot; {t.answered_questions || 0} answered
                        {t.deadline && <> &middot; Due: {new Date(t.deadline).toLocaleDateString('en-GB')}</>}
                      </p>
                    </div>
                    <span className="text-xs font-semibold shrink-0" style={{ color: progress >= 80 ? 'var(--color-success-alt)' : progress >= 40 ? 'var(--color-warning)' : c.textDim }}>
                      {progress}%
                    </span>
                    <ChevronRight size={14} style={{ color: c.textDim }} />
                  </div>
                );
              })}
              {(company.tenders || []).length === 0 && (
                <p className="text-sm text-center py-6" style={{ color: c.textDim }} data-testid="company-tenders-empty">No tenders linked to this company yet</p>
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
        {activeSection === 'sites_equipment' && (
          <SitesAndEquipmentTab companyId={companyId} companyName={company.name} API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {activeSection === 'equipment' && (
          <PortalEquipmentTab companyId={companyId} API={API} headers={headers} c={c} isDark={isDark} />
        )}

        {activeSection === 'timeline' && (
          <CrossModuleTimeline companyId={companyId} />
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
                { key: 'sector', label: 'Sector / Industry', type: 'select', options: FITNESS_SECTOR_OPTIONS },
                { key: 'type', label: 'Type', type: 'select', options: ['prospect', 'customer', 'partner', 'former'] },
                { key: 'phone', label: 'Phone' },
                { key: 'email', label: 'Email' },
                { key: 'website', label: 'Website', span: 2 },
                { key: 'address_line1', label: 'Address 1', span: 2 },
                { key: 'address_line2', label: 'Address 2', span: 2 },
                { key: 'address_line3', label: 'Address 3', span: 2 },
                { key: 'postcode', label: 'Post code', lookupPostcode: true },
                { key: 'city', label: 'City' },
                { key: 'county', label: 'County', datalist: 'crm-edit-county-presets' },
                { key: 'country', label: 'Country', datalist: 'crm-edit-country-presets' },
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
                      list={f.datalist}
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
              <datalist id="crm-edit-county-presets">
                {UK_COUNTIES.map((c) => <option key={c} value={c} />)}
              </datalist>
              <datalist id="crm-edit-country-presets">
                {COUNTRIES.map((c) => <option key={c} value={c} />)}
              </datalist>
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

      {/* Iter 216h266 — Log a case dialog */}
      {showAddCase && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddCase(false)} data-testid="company-add-case-dialog">
          <div className="rounded-lg max-w-md w-full mx-4 p-5 shadow-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold" style={{ color: c.text }}>Log a case</h3>
              <button onClick={() => setShowAddCase(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="company-add-case-close"><X size={16} /></button>
            </div>
            <p className="text-xs mb-3" style={{ color: c.textDim }}>Linked to <b style={{ color: c.text }}>{company.name}</b>.</p>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Subject</label>
                <input value={caseForm.subject} onChange={e => setCaseForm({ ...caseForm, subject: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} placeholder="Treadmill belt slipping" data-testid="company-add-case-subject" />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Severity</label>
                <select value={caseForm.severity} onChange={e => setCaseForm({ ...caseForm, severity: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="company-add-case-severity">
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Description</label>
                <textarea rows={4} value={caseForm.description} onChange={e => setCaseForm({ ...caseForm, description: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="company-add-case-description" />
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setShowAddCase(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }} data-testid="company-add-case-cancel">Cancel</button>
              <button onClick={handleAddCase} disabled={saving || !caseForm.subject.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="company-add-case-submit">
                {saving ? 'Logging…' : 'Log case'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Iter 216h266 — Add deal dialog */}
      {showAddDeal && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddDeal(false)} data-testid="company-add-deal-dialog">
          <div className="rounded-lg max-w-md w-full mx-4 p-5 shadow-2xl" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold" style={{ color: c.text }}>New deal</h3>
              <button onClick={() => setShowAddDeal(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="company-add-deal-close"><X size={16} /></button>
            </div>
            <p className="text-xs mb-3" style={{ color: c.textDim }}>Linked to <b style={{ color: c.text }}>{company.name}</b>.</p>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Title</label>
                <input value={dealForm.title} onChange={e => setDealForm({ ...dealForm, title: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} placeholder="Q2 cardio refresh – 20 treadmills" data-testid="company-add-deal-title" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Value (£)</label>
                  <input type="number" value={dealForm.value} onChange={e => setDealForm({ ...dealForm, value: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="company-add-deal-value" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Close date</label>
                  <input type="date" value={dealForm.close_date} onChange={e => setDealForm({ ...dealForm, close_date: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="company-add-deal-close-date" />
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Stage</label>
                <select value={dealForm.stage} onChange={e => setDealForm({ ...dealForm, stage: e.target.value })} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="company-add-deal-stage">
                  <option value="lead">Lead</option>
                  <option value="qualified">Qualified</option>
                  <option value="discovery">Discovery</option>
                  <option value="solution">Solution Review</option>
                  <option value="proposal">Proposal Sent</option>
                  <option value="negotiation">Negotiation</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setShowAddDeal(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }} data-testid="company-add-deal-cancel">Cancel</button>
              <button onClick={handleAddDeal} disabled={saving || !dealForm.title.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="company-add-deal-submit">
                {saving ? 'Creating…' : 'Create deal'}
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
