/**
 * Iter 220e8 — CRM Lead Conversion modal.
 *
 * One-screen conversion wizard launched from the Pipeline detail.
 * Lets the operator confirm/create:
 *   1. Company (existing / create new / skip = reuse deal data)
 *   2. Contact (existing / create new / skip)
 *   3. Site (existing / create new / skip)
 *   4. Starter artifact (none / contract draft / quote draft)
 *   5. Target pipeline stage (default `qualified`)
 *
 * Reuses the deal's existing free-text company/contact names as
 * defaults so the operator usually only needs to confirm + click.
 * Behaviour is idempotent end-to-end — re-opening a converted deal
 * shows the previous results, not a fresh wizard.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { CheckCircle, X as XIcon, Building2, User as UserIcon, MapPin, FileText, ArrowRight } from 'lucide-react';
import { Modal } from '@/components/shared/Modal';

const MODES = [
  { value: 'create', label: 'Create new' },
  { value: 'existing', label: 'Use existing' },
  { value: 'skip', label: 'Skip / reuse' },
];

const ARTIFACTS = [
  { value: 'none', label: 'No starter artifact' },
  { value: 'contract_draft', label: 'Contract draft (Silver)' },
  { value: 'quote_draft', label: 'Quote draft' },
];

const TARGET_STAGES = ['qualified', 'proposal', 'negotiation'];

export default function LeadConversionModal({ opp, open, onClose, onConverted, API, headers, c, isDark }) {
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [sites, setSites] = useState([]);
  const [form, setForm] = useState({
    company:  { mode: 'create', data: { name: opp?.company_name || opp?.company?.name || '' } },
    contact:  { mode: 'create', data: { first_name: (opp?.contact_name || '').split(' ')[0]
                                                    || opp?.contact?.first_name || '',
                                        last_name: (opp?.contact_name || '').split(' ').slice(1).join(' ')
                                                    || opp?.contact?.last_name || '' } },
    site:     { mode: 'skip', data: {} },
    artifact: { kind: 'contract_draft' },
    target_stage: 'qualified',
  });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Pre-fill the existing-record dropdowns lazily — only when the
  // operator picks "Use existing" for that step.
  useEffect(() => {
    if (!open) return;
    if (form.company?.mode === 'existing' && companies.length === 0) {
      axios.get(`${API}/crm/v2/companies?limit=500`, { headers: headers() })
        .then(r => setCompanies(r.data.companies || []))
        .catch(() => setCompanies([]));
    }
  }, [open, form.company?.mode, API, headers, companies.length]);

  useEffect(() => {
    if (!open) return;
    if (form.contact?.mode === 'existing' && contacts.length === 0) {
      axios.get(`${API}/crm/v2/contacts?limit=500`, { headers: headers() })
        .then(r => setContacts(r.data.contacts || []))
        .catch(() => setContacts([]));
    }
  }, [open, form.contact?.mode, API, headers, contacts.length]);

  useEffect(() => {
    if (!open) return;
    const coId = form.company?.company_id;
    if (form.site?.mode === 'existing' && coId) {
      axios.get(`${API}/crm/v2/companies/${coId}/sites-and-equipment`, { headers: headers() })
        .then(r => setSites((r.data.sites || []).map(s => ({ id: s.id, name: s.name }))))
        .catch(() => setSites([]));
    }
  }, [open, form.site?.mode, form.company?.company_id, API, headers]);

  const submit = async () => {
    setSubmitting(true); setError(null);
    try {
      const res = await axios.post(`${API}/crm/v2/opportunities/${opp.id}/convert`, form, { headers: headers() });
      setResult(res.data);
      onConverted?.(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Conversion failed');
    }
    setSubmitting(false);
  };

  const inp = useMemo(() => ({
    className: 'w-full px-3 py-1.5 text-sm rounded-md',
    style: { background: isDark ? 'var(--color-ink-alt)' : '#fff',
             border: `1px solid ${c.border}`, color: c.text },
  }), [isDark, c]);

  if (!open) return null;

  if (result) {
    // Success state — celebrate and link to next-step artifacts.
    return (
      <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 backdrop-blur-sm" data-testid="lead-convert-success" onClick={onClose}>
        <div className="w-full max-w-md mx-4 rounded-2xl p-6 shadow-2xl"
             style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
             onClick={e => e.stopPropagation()}>
          <div className="text-center mb-4">
            <CheckCircle size={36} className="text-emerald-500 mx-auto mb-2" />
            <h2 className="text-base font-extrabold" style={{ color: c.text }}>Lead converted</h2>
            <p className="text-xs mt-1" style={{ color: c.textDim }}>
              Moved to <strong>{result.target_stage}</strong>. Records created and linked.
            </p>
          </div>
          <div className="space-y-1.5 text-xs">
            {result.company_id && (
              <div className="flex items-center gap-2 px-3 py-2 rounded border" data-testid="result-company"
                   style={{ borderColor: c.border }}>
                <Building2 size={12} className="text-[var(--color-info-ios)]" />
                <span style={{ color: c.textDim }}>Company:</span>
                <span className="font-semibold flex-1" style={{ color: c.text }}>{result.company_name}</span>
              </div>
            )}
            {result.contact_id && (
              <div className="flex items-center gap-2 px-3 py-2 rounded border" data-testid="result-contact"
                   style={{ borderColor: c.border }}>
                <UserIcon size={12} className="text-[var(--color-info-ios)]" />
                <span style={{ color: c.textDim }}>Contact:</span>
                <span className="font-semibold flex-1" style={{ color: c.text }}>{result.contact_name}</span>
              </div>
            )}
            {result.site_id && (
              <div className="flex items-center gap-2 px-3 py-2 rounded border" data-testid="result-site"
                   style={{ borderColor: c.border }}>
                <MapPin size={12} className="text-[var(--color-info-ios)]" />
                <span style={{ color: c.textDim }}>Site:</span>
                <span className="font-semibold flex-1" style={{ color: c.text }}>{result.site_name}</span>
              </div>
            )}
            {result.artifact?.id && (
              <div className="flex items-center gap-2 px-3 py-2 rounded border" data-testid="result-artifact"
                   style={{ borderColor: 'var(--color-success-alt)40',
                            background: 'var(--color-success-alt)08' }}>
                <FileText size={12} className="text-emerald-600" />
                <span className="font-semibold flex-1" style={{ color: c.text }}>
                  {result.artifact.type === 'contract_draft' ? 'Contract draft' : 'Quote draft'} created:
                  {' '}{result.artifact.contract_number || result.artifact.number || result.artifact.id.slice(0, 8)}
                </span>
                <ArrowRight size={11} style={{ color: 'var(--color-success-alt)' }} />
              </div>
            )}
          </div>
          <button onClick={onClose} data-testid="lead-convert-success-close"
                  className="mt-5 w-full py-2 rounded-md bg-[var(--color-info-ios)] text-white text-sm font-semibold">
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      variant="center"
      size="lg"
      zClassName="z-[90]"
      backdropClassName="bg-black/60 backdrop-blur-sm"
      testId="lead-convert-modal"
      bodyClassName="px-5 py-4 space-y-4"
      panelStyle={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
      header={(
        <header className="px-5 py-3 flex items-center justify-between border-b"
                style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
          <div>
            <p className="text-[10px] uppercase tracking-widest font-bold" style={{ color: c.textDim }}>Convert lead</p>
            <h2 className="text-base font-extrabold" style={{ color: c.text }}>{opp?.title || 'Opportunity'}</h2>
          </div>
          <button onClick={onClose} data-testid="lead-convert-close"
                  className="p-1.5" style={{ color: c.textDim }}><XIcon size={16} /></button>
        </header>
      )}
      footer={(
        <footer className="px-5 py-3 border-t flex justify-end gap-2"
                style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', borderColor: c.border }}>
          <button onClick={onClose} className="px-3 py-1.5 text-xs font-semibold rounded-md" style={{ color: c.textMuted }}>
            Cancel
          </button>
          <button onClick={submit} disabled={submitting} data-testid="convert-submit-btn"
                  className="px-4 py-1.5 text-xs font-extrabold rounded-md bg-emerald-600 text-white disabled:opacity-50">
            {submitting ? 'Converting…' : 'Convert lead'}
          </button>
        </footer>
      )}
    >
      {/* Company */}
      <SectionCard label="Company" icon={Building2} c={c} isDark={isDark} testId="convert-section-company">
        <ModePicker value={form.company.mode} onChange={mode => setForm({ ...form, company: { ...form.company, mode } })} testIdPrefix="company" />
        {form.company.mode === 'create' && (
          <input value={form.company.data?.name || ''} placeholder="Company name *"
                 onChange={e => setForm({ ...form, company: { ...form.company, data: { ...form.company.data, name: e.target.value } } })}
                 {...inp} data-testid="convert-company-name" />
        )}
        {form.company.mode === 'existing' && (
          <select value={form.company.company_id || ''}
                  onChange={e => setForm({ ...form, company: { ...form.company, company_id: e.target.value } })}
                  {...inp} data-testid="convert-company-select">
            <option value="">Select existing customer…</option>
            {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
          </select>
        )}
      </SectionCard>

      {/* Contact */}
      <SectionCard label="Contact" icon={UserIcon} c={c} isDark={isDark} testId="convert-section-contact">
        <ModePicker value={form.contact.mode} onChange={mode => setForm({ ...form, contact: { ...form.contact, mode } })} testIdPrefix="contact" />
        {form.contact.mode === 'create' && (
          <div className="grid grid-cols-2 gap-2">
            <input value={form.contact.data?.first_name || ''} placeholder="First name"
                   onChange={e => setForm({ ...form, contact: { ...form.contact, data: { ...form.contact.data, first_name: e.target.value } } })}
                   {...inp} data-testid="convert-contact-first-name" />
            <input value={form.contact.data?.last_name || ''} placeholder="Last name"
                   onChange={e => setForm({ ...form, contact: { ...form.contact, data: { ...form.contact.data, last_name: e.target.value } } })}
                   {...inp} data-testid="convert-contact-last-name" />
            <input value={form.contact.data?.email || ''} placeholder="Email" type="email"
                   onChange={e => setForm({ ...form, contact: { ...form.contact, data: { ...form.contact.data, email: e.target.value } } })}
                   {...inp} data-testid="convert-contact-email" />
            <input value={form.contact.data?.phone || ''} placeholder="Phone"
                   onChange={e => setForm({ ...form, contact: { ...form.contact, data: { ...form.contact.data, phone: e.target.value } } })}
                   {...inp} />
          </div>
        )}
        {form.contact.mode === 'existing' && (
          <select value={form.contact.contact_id || ''}
                  onChange={e => setForm({ ...form, contact: { ...form.contact, contact_id: e.target.value } })}
                  {...inp} data-testid="convert-contact-select">
            <option value="">Select existing contact…</option>
            {contacts.map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
          </select>
        )}
      </SectionCard>

      {/* Site */}
      <SectionCard label="Site (optional)" icon={MapPin} c={c} isDark={isDark} testId="convert-section-site">
        <ModePicker value={form.site.mode} onChange={mode => setForm({ ...form, site: { ...form.site, mode } })} testIdPrefix="site" />
        {form.site.mode === 'create' && (
          <input value={form.site.data?.name || ''} placeholder="Site name"
                 onChange={e => setForm({ ...form, site: { ...form.site, data: { ...form.site.data, name: e.target.value } } })}
                 {...inp} data-testid="convert-site-name" />
        )}
        {form.site.mode === 'existing' && (
          <select value={form.site.site_id || ''}
                  onChange={e => setForm({ ...form, site: { ...form.site, site_id: e.target.value } })}
                  {...inp} data-testid="convert-site-select" disabled={!form.company?.company_id}>
            <option value="">{form.company?.company_id ? 'Select site…' : 'Pick an existing company first'}</option>
            {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
      </SectionCard>

      {/* Artifact */}
      <SectionCard label="Starter artifact" icon={FileText} c={c} isDark={isDark} testId="convert-section-artifact">
        <select value={form.artifact.kind}
                onChange={e => setForm({ ...form, artifact: { kind: e.target.value } })}
                {...inp} data-testid="convert-artifact-kind">
          {ARTIFACTS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
      </SectionCard>

      {/* Target stage */}
      <SectionCard label="Move deal to" c={c} isDark={isDark} testId="convert-section-stage">
        <select value={form.target_stage}
                onChange={e => setForm({ ...form, target_stage: e.target.value })}
                {...inp} data-testid="convert-target-stage">
          {TARGET_STAGES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </SectionCard>

      {error && (
        <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-800" data-testid="convert-error">
          {error}
        </div>
      )}
    </Modal>
  );
}

function SectionCard({ label, icon: Icon, children, c, isDark, testId }) {
  return (
    <div className="p-3 rounded-xl border" data-testid={testId}
         style={{ background: isDark ? '#0F1419' : 'var(--color-neutral-50)', borderColor: c.border }}>
      <p className="text-[10px] uppercase tracking-wider font-bold mb-2 flex items-center gap-1.5"
         style={{ color: c.textDim }}>
        {Icon && <Icon size={11} />}{label}
      </p>
      {children}
    </div>
  );
}
SectionCard.displayName = 'ConvertSectionCard';

function ModePicker({ value, onChange, testIdPrefix }) {
  return (
    <div className="flex gap-1.5 mb-2" data-testid={`convert-${testIdPrefix}-mode`}>
      {MODES.map(m => (
        <button key={m.value} onClick={() => onChange(m.value)}
                data-testid={`convert-${testIdPrefix}-mode-${m.value}`}
                className={`flex-1 py-1.5 rounded text-[11px] font-semibold ${
                  value === m.value ? 'bg-[var(--color-info-ios)] text-white' : 'bg-slate-200 text-slate-700'
                }`}>
          {m.label}
        </button>
      ))}
    </div>
  );
}
ModePicker.displayName = 'ConvertModePicker';

LeadConversionModal.displayName = 'LeadConversionModal';
