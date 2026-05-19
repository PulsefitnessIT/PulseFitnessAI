import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useCRM } from './CRMApp';
import {
  Users, Plus, ChevronRight, Phone, Mail, Building2, ArrowLeft, ArrowRightLeft,
  FileText, Calendar, Activity, Target, CheckCircle, Star, Shield, Tag, Globe, Edit2, X, Loader2, Database, Sparkles
} from 'lucide-react';
import axios from 'axios';
import CustomFieldsPanel from '@/components/shared/CustomFieldsPanel';
import ExportCsvButton from '@/components/shared/ExportCsvButton';
import CRMAuditTrail from './CRMAuditTrail';
import HelpHint from '@/components/HelpHint';
import ListPanel from '@/components/shared/ListPanel';
import PicklistSelect from '@/components/shared/PicklistSelect';

function ContactList({ onSelect, c, isDark, API, headers }) {
  const [contacts, setContacts] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', phone: '', job_title: '', company_id: '', company_name: '', is_decision_maker: false, lifecycle: 'lead', opt_out_email: false, opt_out_sms: false, opt_out_phone: false });
  const [saving, setSaving] = useState(false);
  // Iter 238h — duplicate-email detection on the create form.
  const [emailMatch, setEmailMatch] = useState(null);
  const [emailLookupBusy, setEmailLookupBusy] = useState(false);

  useEffect(() => {
    const email = (form.email || '').trim().toLowerCase();
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
      } catch (e) { /* nicety, not critical */ }
      setEmailLookupBusy(false);
    }, 350);
    return () => clearTimeout(t);
  }, [form.email, API, headers]);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/contacts?search=${search}`, { headers: headers() });
      setContacts(res.data.contacts); setTotal(res.data.total);
    } catch (e) { console.error(e); }
  }, [API, headers, search]);
  useEffect(() => { load(); }, [load]);

  const loadCompanies = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/companies?limit=500`, { headers: headers() });
      setCompanies(res.data.companies || []);
    } catch (e) { console.error(e); }
  }, [API, headers]);

  // Preload companies on mount so dropdown is ready
  useEffect(() => { loadCompanies(); }, [loadCompanies]);

  const handleCreate = async () => {
    if (!form.first_name.trim() || emailMatch) return;
    setSaving(true);
    try {
      const res = await axios.post(`${API}/crm/v2/contacts`, form, { headers: headers() });
      onSelect(res.data.id);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const openCreate = () => { loadCompanies(); setShowCreate(true); setForm({ first_name: '', last_name: '', email: '', phone: '', job_title: '', company_id: '', company_name: '', is_decision_maker: false, lifecycle: 'lead', opt_out_email: false, opt_out_sms: false, opt_out_phone: false }); };

  return (
    <>
      <ListPanel
      data-testid="crm-contacts-list"
      search={{ value: search, onChange: setSearch, placeholder: 'Search contacts...', testId: 'contact-search' }}
      count={{ value: total, label: 'contact' }}
      secondaryActions={[
        <ExportCsvButton key="csv" module="contacts" label="Export" testId="contacts-export-csv" />,
      ]}
      primaryAction={{ label: 'New Contact', icon: Plus, onClick: openCreate, testId: 'create-contact-btn' }}
      empty={{
        when: contacts.length === 0,
        icon: Users,
        title: 'No contacts in your CRM yet',
        hint: "Add leads manually, import from CSV, or let the inbound webhook capture them from your marketing forms. Every lead lives here until it's qualified into a deal.",
        primaryAction: { label: 'Add your first contact', onClick: () => setShowCreate(true), testId: 'crm-empty-add-contact' },
        testId: 'crm-contacts-empty',
      }}
    >
      {contacts.map(ct => (
        <div key={ct.id} onClick={() => onSelect(ct.id)} className="flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all hover:scale-[1.005]"
          style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`contact-row-${ct.id}`}>
          <div className="w-10 h-10 rounded-full bg-[var(--color-accent-indigo)]/15 flex items-center justify-center text-sm font-bold shrink-0" style={{ color: 'var(--color-accent-indigo)' }}>
            {ct.first_name?.[0]}{ct.last_name?.[0]}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold truncate" style={{ color: c.text }}>{ct.first_name} {ct.last_name}</p>
              {ct.is_decision_maker && <Star size={12} className="text-amber-500 shrink-0" />}
              {ct.is_champion && <Shield size={12} className="text-green-500 shrink-0" />}
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              {ct.job_title && <span className="text-[11px]" style={{ color: c.textDim }}>{ct.job_title}</span>}
            </div>
          </div>
          {ct.company_name && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md shrink-0" style={{ background: isDark ? 'var(--color-navy-900)' : 'var(--color-info-bg)', border: `1px solid ${isDark ? 'var(--color-navy-800)' : 'var(--color-blue-200)'}` }} data-testid={`contact-company-tag-${ct.id}`}>
              <Building2 size={11} style={{ color: 'var(--color-info-ios)' }} />
              <span className="text-[11px] font-medium" style={{ color: 'var(--color-info-ios)' }}>{ct.company_name}</span>
            </div>
          )}
          {!ct.company_name && (
            <span className="text-[10px] px-2 py-0.5 rounded shrink-0" style={{ background: isDark ? '#2D1B1B' : 'var(--color-rose-50)', color: 'var(--color-danger)' }}>Unassigned</span>
          )}
          <div className="flex items-center gap-3 shrink-0">
            {ct.email && <Mail size={14} style={{ color: c.textDim }} />}
            {ct.phone && <Phone size={14} style={{ color: c.textDim }} />}
            <ChevronRight size={16} style={{ color: c.textDim }} />
          </div>
        </div>
      ))}
      </ListPanel>

      {showCreate && createPortal((
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => setShowCreate(false)} data-testid="crm-new-contact-backdrop">
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl relative max-h-[calc(100vh-8rem)] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" data-testid="create-contact-dialog">
            {/* Iter 215d7 — explicit X close button; CRM modals previously had no
                escape other than clicking the backdrop, which users couldn't see on mobile. */}
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="absolute top-4 right-4 h-9 w-9 rounded-full flex items-center justify-center border shrink-0 transition-colors"
              style={{ borderColor: c.border, color: c.text, background: 'transparent' }}
              aria-label="Close"
              data-testid="create-contact-close"
            >
              <X size={18} />
            </button>
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-1.5 pr-12" style={{ color: c.text }}>
              New Contact
              <HelpHint guideId="crm-add-contact" testId="help-hint-new-contact" />
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company (optional)</label>
                <select value={form.company_id} onChange={e => {
                  const co = companies.find(cx => cx.id === e.target.value);
                  setForm({ ...form, company_id: e.target.value, company_name: co?.name || '' });
                }} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="contact-company-select">
                  <option value="">— No company (standalone contact)</option>
                  {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                </select>
              </div>
              {[
                { key: 'first_name', label: 'First Name *' },
                { key: 'last_name', label: 'Last Name *' },
                { key: 'email', label: 'Email *', span: 2 },
                { key: 'phone', label: 'Phone' },
              ].map(f => (
                <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{f.label}</label>
                  <input value={form[f.key]} onChange={e => setForm({...form, [f.key]: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} />
                </div>
              ))}
              {/* Iter 216h223 — Job Title now uses the centralised
                  picklist instead of a free-text input. Falls back to
                  free-text via the "Other" option so org-custom titles
                  still work. */}
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Job Title</label>
                <PicklistSelect
                  pickKey="job_title"
                  value={form.job_title}
                  onChange={v => setForm({ ...form, job_title: v })}
                  placeholder="Select a job title"
                  api={API}
                  headers={headers}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  testId="contact-job-title-picklist"
                />
              </div>
              <div className="col-span-2 flex items-center gap-3 flex-wrap">
                <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                  <input type="checkbox" checked={form.is_decision_maker} onChange={e => setForm({...form, is_decision_maker: e.target.checked})} className="rounded" /> Decision Maker
                </label>
                <div className="flex-1" />
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Stage</label>
                <select
                  value={form.lifecycle}
                  onChange={e => setForm({...form, lifecycle: e.target.value})}
                  className="px-2 py-1 text-xs rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="contact-lifecycle-select"
                >
                  <option value="lead">Lead</option>
                  <option value="prospect">Prospect</option>
                  <option value="customer">Customer</option>
                  <option value="champion">Champion</option>
                  <option value="lost">Lost</option>
                </select>
              </div>
              <div className="col-span-2 border-t border-zinc-200 pt-3 mt-1 dark:border-zinc-800">
                <div className="text-[10px] uppercase tracking-wider font-bold mb-2" style={{ color: c.textDim }}>
                  GDPR · marketing opt-outs
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                  <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                    <input
                      type="checkbox"
                      checked={form.opt_out_email}
                      onChange={(e) => setForm({ ...form, opt_out_email: e.target.checked })}
                      className="rounded"
                      data-testid="contact-optout-email"
                    /> No marketing email
                  </label>
                  <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                    <input
                      type="checkbox"
                      checked={form.opt_out_sms}
                      onChange={(e) => setForm({ ...form, opt_out_sms: e.target.checked })}
                      className="rounded"
                      data-testid="contact-optout-sms"
                    /> No SMS
                  </label>
                  <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                    <input
                      type="checkbox"
                      checked={form.opt_out_phone}
                      onChange={(e) => setForm({ ...form, opt_out_phone: e.target.checked })}
                      className="rounded"
                      data-testid="contact-optout-phone"
                    /> No phone calls
                  </label>
                </div>
                <p className="text-[10px] mt-2" style={{ color: c.textDim }}>
                  Per-channel opt-outs override any marketing campaign — UK GDPR Article 21.
                </p>
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={handleCreate} disabled={saving || !form.first_name.trim() || !!emailMatch} title={emailMatch ? 'Resolve the duplicate-email warning above first' : undefined} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">{saving ? 'Creating...' : 'Create Contact'}</button>
            </div>
          </div>
        </div>
      ), document.body)}
    </>
  );
}

function ContactDetail({ contactId, onBack, c, isDark, API, headers, navigateTo }) {
  const [contact, setContact] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showAddNote, setShowAddNote] = useState(false);
  const [noteForm, setNoteForm] = useState({ subject: '', body: '', type: 'note' });
  const [saving, setSaving] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [savingEdit, setSavingEdit] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [showConvert, setShowConvert] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/contacts/${contactId}`, { headers: headers() });
      setContact(res.data);
    } catch (e) { console.error(e); }
  }, [API, headers, contactId]);
  useEffect(() => { load(); }, [load]);

  const openEdit = async () => {
    setEditForm({
      first_name: contact.first_name || '', last_name: contact.last_name || '',
      email: contact.email || '', phone: contact.phone || '',
      job_title: contact.job_title || '', is_decision_maker: contact.is_decision_maker || false,
      linkedin: contact.linkedin || '', source: contact.source || '',
      company_id: contact.company_id || '', company_name: contact.company_name || '',
    });
    try {
      const res = await axios.get(`${API}/crm/v2/companies?limit=500`, { headers: headers() });
      setCompanies(res.data.companies || []);
    } catch (e) { console.error(e); }
    setShowEdit(true);
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      await axios.put(`${API}/crm/v2/contacts/${contactId}`, editForm, { headers: headers() });
      setShowEdit(false);
      load();
    } catch (e) { console.error(e); }
    setSavingEdit(false);
  };

  const addActivity = async () => {
    if (!noteForm.subject.trim()) return;
    setSaving(true);
    try {
      await axios.post(`${API}/crm/v2/activities`, { ...noteForm, contact_id: contactId, company_id: contact?.company_id }, { headers: headers() });
      setShowAddNote(false); setNoteForm({ subject: '', body: '', type: 'note' }); load();
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  if (!contact) return <div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" /></div>;

  const actIcons = { note: FileText, call: Phone, email: Mail, meeting: Calendar, task: CheckCircle, system: Activity };

  return (
    <div data-testid="crm-contact-detail">
      <div className="flex items-center gap-3 mb-4">
        <button onClick={onBack} className="p-1.5 rounded-md" style={{ color: c.textDim }}><ArrowLeft size={18} /></button>
        <div className="w-12 h-12 rounded-full bg-[var(--color-accent-indigo)]/15 flex items-center justify-center text-lg font-bold" style={{ color: 'var(--color-accent-indigo)' }}>
          {contact.first_name?.[0]}{contact.last_name?.[0]}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold" style={{ color: c.text }}>{contact.first_name} {contact.last_name}</h1>
            {contact.is_decision_maker && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500">Decision Maker</span>}
            {contact.is_champion && <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-green-500/15 text-green-500">Champion</span>}
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            {contact.job_title && <span className="text-xs" style={{ color: c.textDim }}>{contact.job_title}</span>}
            {contact.company?.name && <span className="text-xs flex items-center gap-1" style={{ color: 'var(--color-info-ios)' }}><Building2 size={11} />{contact.company.name}</span>}
          </div>
        </div>
        <button onClick={openEdit} className="px-3 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5" style={{ borderColor: c.border, color: c.textMuted }} data-testid="contact-edit-btn"><Edit2 size={12} className="inline mr-1" /> Edit</button>
        {contact.lifecycle === 'lead' && (
          <button
            onClick={() => setShowConvert(true)}
            className="px-3 py-1.5 text-xs font-bold rounded-md transition-all hover:opacity-90 flex items-center gap-1.5"
            style={{ background: 'var(--color-success-alt, #16A34A)', color: '#fff' }}
            data-testid="contact-convert-btn"
            title="Convert this lead — link/create a company and optionally open a deal"
          >
            <ArrowRightLeft size={12} /> Convert
          </button>
        )}
        <button onClick={() => setShowAddNote(true)} className="px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md"><Plus size={12} className="inline mr-1" /> Activity</button>
      </div>

      {/* Contact info strip */}
      <div className="flex flex-wrap gap-3 mb-4">
        {contact.email && <a href={`mailto:${contact.email}`} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs" style={{ background: isDark ? 'var(--color-surface-dark-1)' : 'var(--color-neutral-100)', color: c.textMuted }}><Mail size={12} />{contact.email}</a>}
        {contact.phone && <a href={`tel:${contact.phone}`} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs" style={{ background: isDark ? 'var(--color-surface-dark-1)' : 'var(--color-neutral-100)', color: c.textMuted }}><Phone size={12} />{contact.phone}</a>}
        {contact.linkedin && <a href={contact.linkedin} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs" style={{ background: isDark ? 'var(--color-surface-dark-1)' : 'var(--color-neutral-100)', color: c.textMuted }}><Globe size={12} />LinkedIn</a>}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4">
        {['overview', `deals (${contact.opportunities?.length || 0})`, `cases (${contact.cases?.length || 0})`, 'custom', 'timeline', 'audit'].map((tab, i) => {
          const id = tab.split(' ')[0];
          return (
            <button key={id} onClick={() => setActiveTab(id)} className={`px-3 py-1.5 text-xs font-medium rounded-md ${activeTab === id ? 'bg-[var(--color-info-ios)] text-white' : ''}`}
              style={activeTab !== id ? { background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)', color: c.textMuted } : {}}
              data-testid={`contact-tab-${id}`}>
              {id === 'custom' ? <span className="inline-flex items-center gap-1"><Database size={10} /> Custom</span> : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          );
        })}
      </div>

      <div className="rounded-lg border p-5" style={{ background: isDark ? 'var(--color-surface-dark-1)' : '#fff', borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
        {activeTab === 'overview' && (
          <div className="space-y-3">
            {[{ l: 'Source', v: contact.source }, { l: 'Status', v: contact.status }, { l: 'Owner', v: contact.owner_name }, { l: 'GDPR Consent', v: contact.gdpr_consent ? 'Yes' : 'No' }].map(r => r.v ? (
              <div key={r.l} className="flex items-center gap-3">
                <span className="text-xs w-28" style={{ color: c.textDim }}>{r.l}</span>
                <span className="text-sm" style={{ color: c.text }}>{r.v}</span>
              </div>
            ) : null)}
            {contact.tags?.length > 0 && (
              <div className="flex items-center gap-2">
                <Tag size={12} style={{ color: c.textDim }} />
                {contact.tags.map(t => <span key={t} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--color-info-ios)20', color: 'var(--color-info-ios)' }}>{t}</span>)}
              </div>
            )}
          </div>
        )}
        {activeTab === 'deals' && (
          <div className="space-y-2">
            {(contact.opportunities || []).map(o => (
              <div key={o.id} className="flex items-center gap-3 p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <Target size={16} style={{ color: 'var(--color-info-ios)' }} />
                <div className="flex-1"><p className="text-sm font-medium" style={{ color: c.text }}>{o.title}</p><p className="text-[11px]" style={{ color: c.textDim }}>{o.stage}</p></div>
                <span className="text-sm font-bold" style={{ color: c.text }}>£{(o.value||0).toLocaleString()}</span>
              </div>
            ))}
            {(contact.opportunities || []).length === 0 && <p className="text-center py-6 text-sm" style={{ color: c.textDim }}>No linked deals</p>}
          </div>
        )}
        {activeTab === 'cases' && (
          <div className="space-y-2">
            {(contact.cases || []).map(cs => (
              <div key={cs.id} className="p-3 rounded-md border" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
                <p className="text-sm font-medium" style={{ color: c.text }}>{cs.case_number}: {cs.subject}</p>
                <p className="text-[11px]" style={{ color: c.textDim }}>{cs.status} | {cs.severity}</p>
              </div>
            ))}
            {(contact.cases || []).length === 0 && <p className="text-center py-6 text-sm" style={{ color: c.textDim }}>No cases</p>}
          </div>
        )}
        {activeTab === 'custom' && (
          <CustomFieldsPanel
            entityType="contact"
            entityId={contactId}
            values={contact.custom_fields || {}}
            isDark={isDark}
            headers={headers()}
            onSave={async (patch) => {
              const next = { ...(contact.custom_fields || {}), ...patch };
              await axios.put(
                `${API}/crm/v2/contacts/${contactId}`,
                { custom_fields: next },
                { headers: headers() },
              );
              setContact((prev) => ({ ...prev, custom_fields: next }));
            }}
          />
        )}
        {activeTab === 'timeline' && (
          <div className="space-y-0">
            {(contact.activities || []).map((act, i) => {
              const Icon = actIcons[act.type] || Activity;
              const time = new Date(act.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
              return (
                <div key={act.id||i} className="flex gap-3 relative">
                  {i < (contact.activities?.length||0)-1 && <div className="absolute left-3.5 top-8 w-px h-full" style={{ background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} />}
                  <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-100)' }}><Icon size={12} style={{ color: c.textDim }} /></div>
                  <div className="flex-1 pb-4">
                    <div className="flex items-center gap-2"><p className="text-sm font-medium" style={{ color: c.text }}>{act.subject}</p><span className="text-[10px]" style={{ color: c.textDim }}>{time}</span></div>
                    {act.body && <p className="text-xs mt-0.5" style={{ color: c.textDim }}>{act.body}</p>}
                  </div>
                </div>
              );
            })}
            {(contact.activities||[]).length === 0 && <p className="text-center py-6 text-sm" style={{ color: c.textDim }}>No activity</p>}
          </div>
        )}
        {activeTab === 'audit' && (
          <CRMAuditTrail entityType="contact" entityId={contactId} emptyText="No edits logged on this contact yet." />
        )}
      </div>

      {showEdit && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowEdit(false)}>
          <div className="w-full max-w-lg mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()} data-testid="edit-contact-dialog">
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Edit Contact</h2>
              <button onClick={() => setShowEdit(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="edit-contact-close"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { key: 'first_name', label: 'First Name' },
                { key: 'last_name', label: 'Last Name' },
                { key: 'email', label: 'Email', span: 2 },
                { key: 'phone', label: 'Phone' },
                { key: 'job_title', label: 'Job Title' },
                { key: 'linkedin', label: 'LinkedIn', span: 2 },
                { key: 'source', label: 'Source' },
              ].map(f => (
                <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
                  <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>{f.label}</label>
                  <input value={editForm[f.key] || ''} onChange={e => setEditForm({...editForm, [f.key]: e.target.value})} className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid={`edit-contact-${f.key}`} />
                </div>
              ))}
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company</label>
                <select value={editForm.company_id || ''} onChange={e => { const co = companies.find(cx => cx.id === e.target.value); setEditForm({...editForm, company_id: e.target.value, company_name: co?.name || ''}); }}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }} data-testid="edit-contact-company">
                  <option value="">No company (unassigned)</option>
                  {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
                </select>
              </div>
              <div className="col-span-2 flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: c.textMuted }}>
                  <input type="checkbox" checked={editForm.is_decision_maker || false} onChange={e => setEditForm({...editForm, is_decision_maker: e.target.checked})} className="rounded" /> Decision Maker
                </label>
              </div>
            </div>
            <div className="flex gap-2 mt-5 justify-end">
              <button onClick={() => setShowEdit(false)} className="px-4 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={saveEdit} disabled={savingEdit} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50" data-testid="save-contact-edit-btn">
                {savingEdit ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showConvert && (
        <ConvertLeadModal
          API={API}
          headers={headers}
          contact={contact}
          c={c}
          isDark={isDark}
          onClose={() => setShowConvert(false)}
          onConverted={({ opportunity_id }) => {
            setShowConvert(false);
            load();
            if (opportunity_id && navigateTo) {
              navigateTo('opportunity', opportunity_id);
            }
          }}
        />
      )}

      {showAddNote && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddNote(false)}>
          <div className="w-full max-w-md mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }} onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-3 flex items-center justify-between border-b" style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
              <h2 className="text-lg font-semibold" style={{ color: c.text }}>Log Activity</h2>
              <button onClick={() => setShowAddNote(false)} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="add-note-close"><X size={16} /></button>
            </div>
            <div className="flex gap-1 mb-3 flex-wrap">
              {['note','call','email','meeting','task'].map(t => (
                <button key={t} onClick={() => setNoteForm({...noteForm, type: t})} className={`px-3 py-1.5 text-xs font-medium rounded-md ${noteForm.type===t?'bg-[var(--color-info-ios)] text-white':''}`}
                  style={noteForm.type!==t?{background: isDark?'var(--color-surface-dark-2)':'var(--color-neutral-100)', color: c.textMuted}:{}}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>
              ))}
            </div>
            <input value={noteForm.subject} onChange={e => setNoteForm({...noteForm, subject: e.target.value})} placeholder="Subject *" className="w-full mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
            <textarea value={noteForm.body} onChange={e => setNoteForm({...noteForm, body: e.target.value})} placeholder="Details..." rows={3} className="w-full mb-2 px-3 py-2 text-sm rounded-md resize-none" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
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
                <input value={noteForm.attendees||''} onChange={e => setNoteForm({...noteForm, attendees: e.target.value})} placeholder="Attendees (comma separated)" className="col-span-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark?'var(--color-ink-alt)':'#fff', border: `1px solid ${c.border}`, color: c.text }} />
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
              <button onClick={addActivity} disabled={saving||!noteForm.subject.trim()} className="px-4 py-2 bg-[var(--color-info-ios)] text-white text-sm font-medium rounded-md disabled:opacity-50">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CRMContacts() {
  const crm = useCRM();
  const { navTarget, setNavTarget } = crm;
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    if (navTarget?.type === 'contact' && navTarget?.id) {
      setSelectedId(navTarget.id);
      setNavTarget(null);
    }
  }, [navTarget, setNavTarget]);

  if (selectedId) return <ContactDetail contactId={selectedId} onBack={() => setSelectedId(null)} {...crm} />;
  return <ContactList onSelect={setSelectedId} {...crm} />;
}

/* ───────────────────────── Convert Lead Modal ─────────────────────────
 * Iter 216h66 — Salesforce-style "Convert Lead":
 *   - Link existing company OR create a new one inline.
 *   - Optionally create an Opportunity in one click.
 *   - Bump the contact's lifecycle to "Customer" (default).
 * Backend: POST /api/crm/v2/contacts/{id}/convert (see crm_v2.py).
 */
const CONVERT_STAGES = [
  { id: 'qualified', label: 'Qualified' },
  { id: 'discovery', label: 'Discovery' },
  { id: 'solution', label: 'Solution Review' },
  { id: 'proposal', label: 'Proposal Sent' },
];

function ConvertLeadModal({ API, headers, contact, c, isDark, onClose, onConverted }) {
  const hasExistingCompany = !!contact?.company_id;
  const [step, setStep] = useState({
    company_action: hasExistingCompany ? 'link' : 'create',
    company_id: contact?.company_id || '',
    new_company: {
      name: contact?.company_name || '',
      sector: '',
      website: '',
    },
    create_opportunity: false,
    opportunity: {
      title: contact ? `${contact.first_name || ''} ${contact.last_name || ''}`.trim() + ' — new business' : '',
      value: '',
      stage: 'qualified',
      close_date: '',
    },
    new_lifecycle: 'customer',
  });
  const [companies, setCompanies] = useState([]);
  const [companySearch, setCompanySearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get(`${API}/crm/v2/companies?limit=200`, { headers: headers() });
        if (!cancelled) setCompanies(res.data?.companies || []);
      } catch (e) { /* tolerated */ }
    })();
    return () => { cancelled = true; };
  }, [API, headers]);

  const filteredCompanies = companySearch.trim()
    ? companies.filter((co) => (co.name || '').toLowerCase().includes(companySearch.toLowerCase()))
    : companies;

  const valid = (() => {
    if (step.company_action === 'link' && !step.company_id) return false;
    if (step.company_action === 'create' && !step.new_company.name.trim()) return false;
    if (step.create_opportunity && !step.opportunity.title.trim()) return false;
    return true;
  })();

  const submit = async () => {
    if (!valid) return;
    setBusy(true);
    setError('');
    try {
      const body = {
        company_action: step.company_action,
        new_lifecycle: step.new_lifecycle,
        create_opportunity: step.create_opportunity,
      };
      if (step.company_action === 'link') body.company_id = step.company_id;
      if (step.company_action === 'create') body.company_data = step.new_company;
      if (step.create_opportunity) {
        body.opportunity = {
          title: step.opportunity.title.trim(),
          value: parseFloat(step.opportunity.value) || 0,
          stage: step.opportunity.stage,
          close_date: step.opportunity.close_date,
        };
      }
      const res = await axios.post(`${API}/crm/v2/contacts/${contact.id}/convert`, body, { headers: headers() });
      onConverted?.(res.data || {});
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || 'Conversion failed';
      setError(typeof detail === 'string' ? detail : 'Conversion failed');
    } finally {
      setBusy(false);
    }
  };

  return createPortal((
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-xl mx-4 rounded-xl p-6 shadow-2xl max-h-[90vh] overflow-y-auto"
        style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
        onClick={(e) => e.stopPropagation()}
        data-testid="convert-lead-dialog"
      >
        <div className="sticky top-0 z-10 -mx-6 -mt-6 px-6 pt-6 pb-3 mb-4 flex items-center justify-between border-b"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
          <div>
            <div className="text-[10px] uppercase tracking-wider font-bold flex items-center gap-1.5" style={{ color: 'var(--color-success-alt, #16A34A)' }}>
              <Sparkles size={11} /> Lead conversion
            </div>
            <h2 className="text-lg font-bold mt-0.5" style={{ color: c.text }}>
              Convert {contact?.first_name} {contact?.last_name}
            </h2>
            <p className="text-xs mt-0.5" style={{ color: c.textDim }}>
              Link or create the account, optionally open a deal, and mark the contact as a customer.
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:opacity-70" style={{ color: c.textDim }} data-testid="convert-lead-close">
            <X size={16} />
          </button>
        </div>

        {/* ── 1. Account ── */}
        <section className="mb-5">
          <div className="text-[10px] uppercase tracking-wider font-bold mb-2 flex items-center gap-1.5" style={{ color: c.textDim }}>
            <Building2 size={11} /> Account
          </div>
          <div className="flex gap-2 mb-3">
            <button
              onClick={() => setStep({ ...step, company_action: 'link' })}
              className={`flex-1 px-3 py-2 text-xs font-medium rounded-md border transition-all ${step.company_action === 'link' ? 'border-[var(--color-info-ios)]' : ''}`}
              style={{
                background: step.company_action === 'link' ? 'var(--color-info-ios)20' : (isDark ? 'var(--color-surface-dark-1)' : '#fff'),
                color: step.company_action === 'link' ? 'var(--color-info-ios)' : c.textMuted,
                borderColor: step.company_action === 'link' ? 'var(--color-info-ios)' : c.border,
              }}
              data-testid="convert-link-existing"
            >
              Link existing company
            </button>
            <button
              onClick={() => setStep({ ...step, company_action: 'create' })}
              className={`flex-1 px-3 py-2 text-xs font-medium rounded-md border transition-all ${step.company_action === 'create' ? 'border-[var(--color-info-ios)]' : ''}`}
              style={{
                background: step.company_action === 'create' ? 'var(--color-info-ios)20' : (isDark ? 'var(--color-surface-dark-1)' : '#fff'),
                color: step.company_action === 'create' ? 'var(--color-info-ios)' : c.textMuted,
                borderColor: step.company_action === 'create' ? 'var(--color-info-ios)' : c.border,
              }}
              data-testid="convert-create-new"
            >
              Create new company
            </button>
            <button
              onClick={() => setStep({ ...step, company_action: 'skip', company_id: '' })}
              className={`px-3 py-2 text-xs font-medium rounded-md border transition-all ${step.company_action === 'skip' ? 'border-[var(--color-info-ios)]' : ''}`}
              style={{
                background: step.company_action === 'skip' ? 'var(--color-info-ios)20' : (isDark ? 'var(--color-surface-dark-1)' : '#fff'),
                color: step.company_action === 'skip' ? 'var(--color-info-ios)' : c.textMuted,
                borderColor: step.company_action === 'skip' ? 'var(--color-info-ios)' : c.border,
              }}
              data-testid="convert-skip-company"
              title="Skip — leave the contact's current account link as-is"
            >
              Skip
            </button>
          </div>

          {step.company_action === 'link' && (
            <div>
              <input
                value={companySearch}
                onChange={(e) => setCompanySearch(e.target.value)}
                placeholder="Search companies..."
                className="w-full mb-2 px-3 py-2 text-sm rounded-md"
                style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                data-testid="convert-company-search"
              />
              <div className="max-h-40 overflow-y-auto rounded-md border" style={{ borderColor: c.border }}>
                {filteredCompanies.length === 0 ? (
                  <p className="text-center text-xs py-4" style={{ color: c.textDim }}>No companies match.</p>
                ) : filteredCompanies.slice(0, 30).map((co) => (
                  <button
                    key={co.id}
                    onClick={() => setStep({ ...step, company_id: co.id })}
                    className={`w-full flex items-center justify-between text-left px-3 py-2 text-sm border-b transition-colors`}
                    style={{
                      background: step.company_id === co.id ? 'var(--color-info-ios)15' : 'transparent',
                      borderColor: c.border,
                      color: step.company_id === co.id ? 'var(--color-info-ios)' : c.text,
                    }}
                    data-testid={`convert-company-pick-${co.id}`}
                  >
                    <span className="truncate">{co.name}</span>
                    {step.company_id === co.id && <CheckCircle size={14} />}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step.company_action === 'create' && (
            <div className="grid grid-cols-2 gap-2">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Company Name *</label>
                <input
                  value={step.new_company.name}
                  onChange={(e) => setStep({ ...step, new_company: { ...step.new_company, name: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-new-company-name"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Sector</label>
                <input
                  value={step.new_company.sector}
                  onChange={(e) => setStep({ ...step, new_company: { ...step.new_company, sector: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-new-company-sector"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Website</label>
                <input
                  value={step.new_company.website}
                  onChange={(e) => setStep({ ...step, new_company: { ...step.new_company, website: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-new-company-website"
                />
              </div>
            </div>
          )}

          {step.company_action === 'skip' && (
            <p className="text-xs px-3 py-2 rounded-md" style={{ background: isDark ? 'var(--color-surface-dark-1)' : 'var(--color-neutral-100)', color: c.textMuted }}>
              {contact?.company_name
                ? `The contact will keep its existing link to "${contact.company_name}".`
                : 'The contact will not be linked to any company. You can add one later from the contact detail.'}
            </p>
          )}
        </section>

        {/* ── 2. Opportunity (optional) ── */}
        <section className="mb-5">
          <label className="flex items-center gap-2 cursor-pointer mb-3" data-testid="convert-create-opp-toggle">
            <input
              type="checkbox"
              checked={step.create_opportunity}
              onChange={(e) => setStep({ ...step, create_opportunity: e.target.checked })}
              className="rounded"
            />
            <span className="text-[10px] uppercase tracking-wider font-bold flex items-center gap-1.5" style={{ color: c.textDim }}>
              <Target size={11} /> Open a deal in pipeline
            </span>
          </label>
          {step.create_opportunity && (
            <div className="grid grid-cols-2 gap-2 pl-6">
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Deal Title *</label>
                <input
                  value={step.opportunity.title}
                  onChange={(e) => setStep({ ...step, opportunity: { ...step.opportunity, title: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-opp-title"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Value (£)</label>
                <input
                  type="number"
                  value={step.opportunity.value}
                  onChange={(e) => setStep({ ...step, opportunity: { ...step.opportunity, value: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-opp-value"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Stage</label>
                <select
                  value={step.opportunity.stage}
                  onChange={(e) => setStep({ ...step, opportunity: { ...step.opportunity, stage: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-opp-stage"
                >
                  {CONVERT_STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>Close Date</label>
                <input
                  type="date"
                  value={step.opportunity.close_date}
                  onChange={(e) => setStep({ ...step, opportunity: { ...step.opportunity, close_date: e.target.value } })}
                  className="w-full mt-1 px-3 py-2 text-sm rounded-md"
                  style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
                  data-testid="convert-opp-close-date"
                />
              </div>
            </div>
          )}
        </section>

        {/* ── 3. Lifecycle ── */}
        <section className="mb-5">
          <div className="text-[10px] uppercase tracking-wider font-bold mb-2 flex items-center gap-1.5" style={{ color: c.textDim }}>
            <CheckCircle size={11} /> Mark contact as
          </div>
          <select
            value={step.new_lifecycle}
            onChange={(e) => setStep({ ...step, new_lifecycle: e.target.value })}
            className="w-full px-3 py-2 text-sm rounded-md"
            style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${c.border}`, color: c.text }}
            data-testid="convert-new-lifecycle"
          >
            <option value="customer">Customer</option>
            <option value="prospect">Prospect</option>
            <option value="champion">Champion</option>
          </select>
        </section>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-md text-xs" style={{ background: 'var(--color-danger)15', color: 'var(--color-danger)' }} data-testid="convert-lead-error">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm" style={{ color: c.textMuted }} data-testid="convert-lead-cancel">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!valid || busy}
            className="px-4 py-2 text-sm font-bold rounded-md flex items-center gap-1.5 disabled:opacity-50"
            style={{ background: 'var(--color-success-alt, #16A34A)', color: '#fff' }}
            data-testid="convert-lead-submit"
          >
            {busy ? <><Loader2 size={12} className="animate-spin" /> Converting...</> : <><ArrowRightLeft size={12} /> Convert lead</>}
          </button>
        </div>
      </div>
    </div>
  ), document.body);
}
