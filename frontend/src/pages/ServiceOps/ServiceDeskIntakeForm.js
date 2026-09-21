/**
 * ServiceDeskIntakeForm — iter 215ec (cascade redesign).
 *
 * Modal-based intake form for service-desk operators logging cases.
 * Cascade order matches the operations portal flow so info inherits
 * site → contact → equipment → serial → contract coverage:
 *
 *   1. Site
 *   2. Contact (filtered by site, with manual fallback)
 *   3. Equipment type (filtered by site)
 *   4. Serial number (auto-filled from equipment)
 *   5. Cover type + SLA (auto from equipment coverage; chargeable opens Quote / PO inputs)
 *   6. Description
 *   7. Attach pictures / videos
 *   8. AI triage
 *   9. Fault code
 *
 * Uses the shared `_serviceops.css` design layer.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import {
  X, Phone, Loader2, Sparkles, MapPin, User as UserIcon, Wrench, Hash,
  ShieldCheck, FileText, Camera, AlertTriangle, CheckCircle2, Trash2, Upload,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import './_serviceops.css';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export default function ServiceDeskIntakeForm({ onClose, onCreated }) {
  const { t } = useTranslation();
  const PRIORITY_OPTIONS = [
    { v: 'p1', label: t('service.intake_prio_p1', 'P1 — Critical (1h response, 4h resolve)') },
    { v: 'p2', label: t('service.intake_prio_p2', 'P2 — High (4h response, 24h resolve)') },
    { v: 'p3', label: t('service.intake_prio_p3', 'P3 — Standard (8h response, 72h resolve)') },
    { v: 'p4', label: t('service.intake_prio_p4', 'P4 — Low (24h response, 7d resolve)') },
  ];
  // Cascade selections
  const [customerOrgId, setCustomerOrgId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [contactMode, setContactMode] = useState('existing'); // existing | manual
  const [contactId, setContactId] = useState('');
  const [equipmentId, setEquipmentId] = useState('');
  const [serial, setSerial] = useState('');

  // Lookup data
  const [customers, setCustomers] = useState([]);
  const [sites, setSites] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [equipmentList, setEquipmentList] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [coverageLoading, setCoverageLoading] = useState(false);

  // Manual contact entry (used as fallback)
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');

  // Description / chargeable / media / triage
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [coverType, setCoverType] = useState('contract'); // contract | warranty | chargeable
  const [caseType, setCaseType] = useState('repair');     // repair | ppm | install
  const [priority, setPriority] = useState('p3');
  const [quoteRequired, setQuoteRequired] = useState(false);
  const [customerPONumber, setCustomerPONumber] = useState('');
  const [attachments, setAttachments] = useState([]); // [{id, name, url, mime}]
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const [aiBusy, setAiBusy] = useState(false);
  const [ai, setAi] = useState(null);
  const [faultCode, setFaultCode] = useState('');

  const [saving, setSaving] = useState(false);

  // ── Initial customer list (operator + CRM-linked imported customers)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/desk/customers`, auth());
        if (cancelled) return;
        const list = r.data?.customers || [];
        setCustomers(list);
        // Default to the operator's own org so existing behaviour is unchanged.
        const op = list.find((c) => c.is_operator) || list[0];
        if (op) setCustomerOrgId(op.organization_id);
      } catch {
        // silent — operators can still type customer details manually
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // ── Customer → sites
  useEffect(() => {
    let cancelled = false;
    setSiteId(''); setEquipmentId(''); setSerial(''); setSites([]);
    if (!customerOrgId) return undefined;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/desk/customer-sites?organization_id=${encodeURIComponent(customerOrgId)}`, auth());
        if (!cancelled) setSites(r.data?.sites || []);
      } catch {
        if (!cancelled) setSites([]);
      }
    })();
    return () => { cancelled = true; };
  }, [customerOrgId]);

  // ── Site → equipment + contacts
  useEffect(() => {
    let cancelled = false;
    if (!siteId) {
      setEquipmentList([]); setContacts([]); setEquipmentId(''); setSerial('');
      return undefined;
    }
    (async () => {
      try {
        const [eqRes, staffRes] = await Promise.all([
          axios.get(`${API}/svc/desk/customer-equipment?organization_id=${encodeURIComponent(customerOrgId)}&site_id=${encodeURIComponent(siteId)}`, auth()).catch(() => ({ data: { equipment: [] } })),
          axios.get(`${API}/gym-floor/staff`, auth()).catch(() => ({ data: { staff: [] } })),
        ]);
        if (cancelled) return;
        const eqs = (eqRes.data?.equipment || []).filter((e) => !e.site_id || e.site_id === siteId);
        setEquipmentList(eqs);
        setContacts(staffRes.data?.staff || []);
      } catch {
        if (!cancelled) { setEquipmentList([]); setContacts([]); }
      }
    })();
    return () => { cancelled = true; };
  }, [siteId, customerOrgId]);

  // ── Equipment → serial + coverage
  useEffect(() => {
    let cancelled = false;
    if (!equipmentId) {
      setCoverage(null); setSerial('');
      return undefined;
    }
    const equip = equipmentList.find((e) => e.id === equipmentId);
    if (equip) setSerial(equip.serial_number || '');
    (async () => {
      setCoverageLoading(true); setCoverage(null);
      try {
        const r = await axios.get(`${API}/equipment/${encodeURIComponent(equipmentId)}/coverage`, auth());
        if (!cancelled) {
          setCoverage(r.data || null);
          if (r.data?.covered) {
            const ct = (r.data.type || 'contract').toLowerCase();
            setCoverType(ct === 'warranty' ? 'warranty' : 'contract');
            setQuoteRequired(false);
          } else {
            setCoverType('chargeable');
            setQuoteRequired(true);
          }
        }
      } catch {
        if (!cancelled) setCoverage(null);
      } finally {
        if (!cancelled) setCoverageLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [equipmentId, equipmentList]);

  // ── Resolve customer details from selected contact
  const selectedContact = useMemo(
    () => contacts.find((c) => c.id === contactId),
    [contacts, contactId],
  );
  useEffect(() => {
    if (contactMode !== 'existing' || !selectedContact) return;
    setCustomerName(selectedContact.name || '');
    setCustomerEmail(selectedContact.email || '');
    setCustomerPhone(selectedContact.mobile || '');
  }, [contactMode, selectedContact]);

  const selectedSite = useMemo(() => sites.find((s) => s.id === siteId), [sites, siteId]);
  const selectedEquipment = useMemo(() => equipmentList.find((e) => e.id === equipmentId), [equipmentList, equipmentId]);

  // ── Media upload
  const onPickFiles = async (filesIn) => {
    const files = Array.from(filesIn || []);
    if (files.length === 0) return;
    setUploading(true);
    try {
      const next = [];
      for (const f of files) {
        const fd = new FormData();
        fd.append('file', f);
        try {
          const r = await axios.post(`${API}/files/upload`, fd, {
            headers: { ...auth().headers, 'Content-Type': 'multipart/form-data' },
          });
          next.push({
            id: r.data?.id || `${Date.now()}-${f.name}`,
            name: f.name,
            url: r.data?.url || r.data?.file_url || '',
            mime: f.type || 'application/octet-stream',
          });
        } catch {
          next.push({ id: `local-${Date.now()}-${f.name}`, name: f.name, url: '', mime: f.type, _local: true });
        }
      }
      setAttachments((prev) => [...prev, ...next]);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const removeAttachment = (id) => setAttachments((prev) => prev.filter((a) => a.id !== id));

  // ── AI triage
  const runTriage = async () => {
    const desc = (description || title || '').trim();
    if (desc.length < 12) { notify.error(t('service.intake_err_ai_desc', 'Add a fault description (at least a sentence) before AI triage')); return; }
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/svc/ai/triage`, {
        description: desc,
        site_name: selectedSite?.name || '',
        asset_name: selectedEquipment?.name || '',
        customer_name: customerName,
      }, auth());
      if (r.data?.ok) {
        setAi(r.data);
        notify.success(t('service.intake_ai_ready', 'AI triage ready'), t('service.intake_ai_suggested', 'Suggested {{prio}} · {{code}}', { prio: (r.data.priority || '').toUpperCase(), code: r.data.fault_code || '—' }));
      } else {
        notify.error(t('service.intake_ai_unavailable', 'AI triage unavailable'), r.data?.error || t('service.intake_ai_try', 'Try again or fill in manually'));
      }
    } catch (e) {
      notify.error(t('service.intake_ai_failed', 'AI triage failed'), e?.response?.data?.detail || e.message);
    } finally { setAiBusy(false); }
  };

  const acceptAi = () => {
    if (!ai) return;
    if (ai.priority) setPriority(ai.priority);
    if (ai.fault_code) setFaultCode(ai.fault_code);
    notify.success(t('service.intake_ai_applied', 'AI suggestions applied'));
  };

  // ── Submit
  const submit = async () => {
    if (!siteId) { notify.error(t('service.intake_err_site', 'Pick a site first')); return; }
    if (contactMode === 'existing' && !contactId) { notify.error(t('service.intake_err_contact', 'Pick a contact (or switch to manual entry)')); return; }
    if (!customerName.trim()) { notify.error(t('service.intake_err_name', 'Contact name required')); return; }
    if (!customerEmail.trim() && !customerPhone.trim()) { notify.error(t('service.intake_err_reach', 'Contact phone or email required')); return; }
    if (!title.trim() && !description.trim()) { notify.error(t('service.intake_err_title_desc', 'Title or description required')); return; }
    if (coverType === 'chargeable' && quoteRequired && !customerPONumber.trim()) {
      // PO is "required" only when explicitly toggled — soft warning, not blocking
      // (we still let the operator submit so they can chase the PO after).
    }
    setSaving(true);
    try {
      const payload = {
        title: title.trim() || (description.trim().slice(0, 80)),
        description: description.trim(),
        priority,
        cover_type: coverType,
        site_id: siteId,
        site_name: selectedSite?.name || '',
        site_postcode: selectedSite?.postcode || selectedSite?.address || '',
        asset_id: equipmentId || '',
        asset_name: selectedEquipment?.name || '',
        equipment_ids: equipmentId ? [equipmentId] : [],
        equipment_serials: serial ? [serial] : [],
        fault_code: faultCode,
        contact_id: contactMode === 'existing' ? contactId : '',
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim(),
        customer_phone: customerPhone.trim(),
        quote_required: quoteRequired,
        customer_po_number: customerPONumber.trim(),
        attachments: attachments.filter((a) => a.url).map((a) => ({ id: a.id, name: a.name, url: a.url, mime: a.mime })),
        contract_id: coverage?.sla_contract_ref || '',
      };
      const r = await axios.post(`${API}/svc/intake/phone`, payload, auth());
      // Iter 215ed — chargeable + quote_required cases auto-draft a Sage SLQuote.
      // Surface the confirmation so the operator knows the quote is queued.
      const draft = r.data?.sage_quote_outbox;
      if (draft?.id) {
        notify.success(
          t('service.intake_quote_drafted', 'Quote drafted in Sage outbox'),
          t('service.intake_quote_drafted_detail', 'Reference {{ref}} · status {{status}}', { ref: r.data?.reference || '', status: draft.status || 'pending' }),
        );
      }
      onCreated?.(r.data);
    } catch (e) {
      notify.error(t('service.intake_log_failed', 'Failed to log case'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  // ── Render
  return (
    <div
      className="svc-modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      data-testid="svc-intake-form"
    >
      <div className="svc-modal" role="dialog" aria-label={t('service.intake_log_new_case', 'Log new service case')}>
        {/* Header */}
        <div className="svc-drawer-head flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="svc-h1" style={{ fontSize: 20, textAlign: 'left' }}>{t('service.intake_log_new_case', 'Log new service case')}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label={t('service.intake_close', 'Close')} data-testid="svc-intake-close" className="svc-icon-btn">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="svc-drawer-body space-y-4">
          {/* Step 1 — Customer & site */}
          <Step n={1} icon={<MapPin size={12} />} label={t('service.intake_step_customer_site', 'Customer & site')}>
            {customers.length > 1 && (
              <select
                value={customerOrgId}
                onChange={(e) => setCustomerOrgId(e.target.value)}
                className="svc-select mb-2"
                data-testid="intake-customer-select"
              >
                {customers.map((c) => (
                  <option key={c.organization_id} value={c.organization_id}>
                    {c.name}{c.is_operator ? t('service.intake_cust_mine', ' (my org)') : ''}
                    {c.site_count != null ? ` · ${t('service.intake_sites_n', '{{n}} sites', { n: c.site_count })}` : ''}
                  </option>
                ))}
              </select>
            )}
            <select
              value={siteId}
              onChange={(e) => { setSiteId(e.target.value); setContactId(''); setEquipmentId(''); }}
              className="svc-select"
              data-testid="intake-site-select"
            >
              <option value="">{sites.length ? t('service.intake_select_site', '— Select site —') : t('service.intake_no_sites', 'No sites for this customer')}</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.equipment_count != null ? ` · ${t('service.intake_machines', '{{n}} machines', { n: s.equipment_count })}` : ''}
                </option>
              ))}
            </select>
          </Step>

          {/* Step 2 — Contact */}
          <Step n={2} icon={<UserIcon size={12} />} label={t('service.intake_step_contact', 'Contact at site')} disabled={!siteId}>
            <div className="flex gap-2 mb-2 text-[11px]">
              <ToggleChip
                active={contactMode === 'existing'}
                onClick={() => setContactMode('existing')}
                testid="intake-contact-mode-existing"
              >{t('service.intake_pick_directory', 'Pick from directory')}</ToggleChip>
              <ToggleChip
                active={contactMode === 'manual'}
                onClick={() => setContactMode('manual')}
                testid="intake-contact-mode-manual"
              >{t('service.intake_enter_manually', 'Enter manually')}</ToggleChip>
            </div>
            {contactMode === 'existing' ? (
              <select
                value={contactId}
                onChange={(e) => setContactId(e.target.value)}
                className="svc-select"
                data-testid="intake-contact-select"
                disabled={!siteId}
              >
                <option value="">{contacts.length ? t('service.intake_select_contact', '— Select contact —') : t('service.intake_no_contacts', 'No contacts on file (switch to manual)')}</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}{c.email ? ` · ${c.email}` : ''}{c.mobile ? ` · ${c.mobile}` : ''}
                  </option>
                ))}
              </select>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder={t('service.intake_ph_name', 'Name')} className="svc-input" data-testid="intake-contact-name" />
                <input value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder={t('service.intake_ph_phone', 'Phone')} className="svc-input" data-testid="intake-contact-phone" />
                <input value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} placeholder={t('service.intake_ph_email', 'Email')} className="svc-input" data-testid="intake-contact-email" />
              </div>
            )}
            {contactMode === 'existing' && selectedContact ? (
              <p className="svc-fieldset-hint mt-2">
                <strong>{selectedContact.name}</strong>
                {selectedContact.email ? ` · ${selectedContact.email}` : ''}
                {selectedContact.mobile ? ` · ${selectedContact.mobile}` : ''}
              </p>
            ) : null}
          </Step>

          {/* Step 3 — Equipment */}
          <Step n={3} icon={<Wrench size={12} />} label={t('service.intake_step_equipment', 'Equipment')} disabled={!siteId}>
            <select
              value={equipmentId}
              onChange={(e) => setEquipmentId(e.target.value)}
              className="svc-select"
              data-testid="intake-equipment-select"
              disabled={!siteId}
            >
              <option value="">{equipmentList.length ? t('service.intake_select_equipment', '— Select equipment —') : t('service.intake_no_equipment', 'No equipment on this site')}</option>
              {equipmentList.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.name || e.display_name || t('service.intake_unknown', 'Unknown')}
                  {e.manufacturer ? ` · ${e.manufacturer}` : ''}
                  {e.model ? ` · ${e.model}` : ''}
                </option>
              ))}
            </select>
          </Step>

          {/* Step 4 — Serial */}
          <Step n={4} icon={<Hash size={12} />} label={t('service.intake_step_serial', 'Serial number')} disabled={!equipmentId}>
            <input
              value={serial}
              onChange={(e) => setSerial(e.target.value)}
              placeholder={equipmentId ? t('service.intake_serial_autofill', 'Auto-filled from equipment') : t('service.intake_serial_pickfirst', 'Pick equipment first')}
              className="svc-input"
              style={{ letterSpacing: '0.04em', fontVariantNumeric: 'tabular-nums' }}
              data-testid="intake-serial"
              disabled={!equipmentId}
            />
            {selectedEquipment?.serial_number && serial !== selectedEquipment.serial_number ? (
              <p className="svc-fieldset-hint mt-1" style={{ color: 'var(--svc-warn-text)' }}>
                {t('service.intake_serial_differs', 'Differs from registered serial')} <strong>{selectedEquipment.serial_number}</strong>
              </p>
            ) : null}
          </Step>

          {/* Step 5 — Cover & SLA */}
          <Step n={5} icon={<ShieldCheck size={12} />} label={t('service.intake_step_cover', 'Cover type & SLA')} disabled={!equipmentId}>
            <CoveragePanel
              loading={coverageLoading}
              coverage={coverage}
              coverType={coverType}
              setCoverType={setCoverType}
              quoteRequired={quoteRequired}
              setQuoteRequired={setQuoteRequired}
              customerPONumber={customerPONumber}
              setCustomerPONumber={setCustomerPONumber}
            />
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
              <Field label={t('service.intake_f_job_type', 'Job type')}>
                {/* Iter 220dt — surface friendly labels (the customer
                    + engineer Summary reads from the same source). */}
                <select
                  value={caseType}
                  onChange={(e) => setCaseType(e.target.value)}
                  className="svc-select"
                  data-testid="intake-case-type"
                >
                  <option value="repair">{t('service.intake_jt_repair', 'Repair')}</option>
                  <option value="ppm">{t('service.intake_jt_ppm', 'Preventative Maintenance Service')}</option>
                  <option value="install">{t('service.intake_jt_install', 'Installation')}</option>
                  <option value="inspection">{t('service.intake_jt_inspection', 'Safety / compliance inspection')}</option>
                  <option value="callout">{t('service.intake_jt_callout', 'Emergency callout')}</option>
                  <option value="audit">{t('service.intake_jt_audit', 'Asset audit')}</option>
                </select>
              </Field>
              <Field label={t('service.intake_f_cover', 'Cover type')}>
                <select value={coverType} onChange={(e) => setCoverType(e.target.value)} className="svc-select" data-testid="intake-cover-type">
                  <option value="contract">{t('service.intake_cover_contract', 'Contract')}</option>
                  <option value="warranty">{t('service.intake_cover_warranty', 'Warranty')}</option>
                  <option value="chargeable">{t('service.intake_cover_chargeable', 'Chargeable')}</option>
                </select>
              </Field>
              <Field label={t('service.intake_f_priority', 'Priority')}>
                <select value={priority} onChange={(e) => setPriority(e.target.value)} className="svc-select" data-testid="intake-priority">
                  {PRIORITY_OPTIONS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
                </select>
              </Field>
            </div>
          </Step>

          {/* Step 6 — Description */}
          <Step n={6} icon={<FileText size={12} />} label={t('service.intake_step_desc', 'Description of issue')}>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('service.intake_ph_title', 'Title (e.g. Treadmill #14 belt frayed)')}
              className="svc-input mb-2"
              data-testid="intake-title"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder={t('service.intake_ph_desc', 'Customer reports rubber peeling on the left edge of the running belt. Belt makes a slapping sound at higher speeds.')}
              className="svc-textarea"
              style={{ fontFamily: 'inherit', fontSize: 13 }}
              data-testid="intake-description"
            />
          </Step>

          {/* Step 7 — Media */}
          <Step n={7} icon={<Camera size={12} />} label={t('service.intake_step_media', 'Attach photos / videos')}>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="svc-btn svc-btn-secondary svc-btn-sm"
                data-testid="intake-media-pick"
              >
                {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                {uploading ? t('service.intake_uploading', 'Uploading…') : t('service.intake_choose_files', 'Choose files')}
              </button>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept="image/*,video/*"
                hidden
                onChange={(e) => onPickFiles(e.target.files)}
                data-testid="intake-media-input"
              />
              <span className="svc-fieldset-hint">{t('service.intake_media_hint', 'Photos and short videos help the engineer arrive prepared.')}</span>
            </div>
            {attachments.length > 0 ? (
              <ul className="mt-2 space-y-1" data-testid="intake-media-list">
                {attachments.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 text-[11.5px] svc-pill" style={{ width: '100%', justifyContent: 'space-between' }}>
                    <span className="truncate">
                      {a.url ? <a href={a.url} target="_blank" rel="noreferrer" style={{ color: 'var(--svc-link)' }}>{a.name}</a> : a.name}
                      {a._local ? <span className="svc-muted ml-2">{t('service.intake_saved_locally', '(saved locally — re-pick when online)')}</span> : null}
                    </span>
                    <button type="button" onClick={() => removeAttachment(a.id)} className="svc-icon-btn" aria-label={t('service.intake_remove', 'Remove {{name}}', { name: a.name })} data-testid={`intake-media-remove-${a.id}`}>
                      <Trash2 size={11} />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </Step>

          {/* Step 8 — AI triage */}
          <Step n={8} icon={<Sparkles size={12} />} label={t('service.intake_step_ai', 'AI triage')}>
            <div className="svc-ai-block" data-testid="intake-ai-block">
              <div className="flex items-center justify-between gap-2">
                <p className="svc-ai-eyebrow"><Sparkles size={12} /> {t('service.intake_ai_assistant', 'AI triage assistant')}</p>
                <button
                  type="button"
                  onClick={runTriage}
                  disabled={aiBusy}
                  className="svc-btn svc-btn-primary svc-btn-sm"
                  data-testid="intake-ai-run"
                >
                  {aiBusy ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
                  {aiBusy ? t('service.intake_thinking', 'Thinking…') : ai ? t('service.intake_rerun', 'Re-run') : t('service.intake_suggest', 'Suggest priority + parts')}
                </button>
              </div>
              {ai ? (
                <div className="space-y-1.5 mt-2" data-testid="intake-ai-result">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`svc-prio svc-prio--${(ai.priority || 'p3').toLowerCase()}`} style={{ width: 'auto', padding: '2px 8px' }}>
                      {(ai.priority || '').toUpperCase()}
                    </span>
                    <span className="text-[11.5px]"><strong>{t('service.intake_fault_label', 'Fault:')}</strong> {ai.fault_code || '—'}</span>
                    <span className="svc-muted text-[11px] ml-auto tabular-nums">{t('service.intake_conf', 'conf {{p}}% · {{ms}}ms', { p: Math.round((ai.confidence || 0) * 100), ms: ai.latency_ms ?? 0 })}</span>
                  </div>
                  {ai.rationale ? <p className="text-xs">{ai.rationale}</p> : null}
                  {Array.isArray(ai.likely_parts) && ai.likely_parts.length > 0 ? (
                    <ul className="text-[11.5px] list-disc pl-4 space-y-0.5">
                      {ai.likely_parts.map((p, i) => (
                        <li key={`${p.sku}-${i}`}>
                          <strong>{p.sku}</strong> — {p.name}
                          {p.reason ? <span className="svc-muted"> · {p.reason}</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <div className="flex gap-2 pt-1">
                    <button type="button" onClick={acceptAi} className="svc-btn svc-btn-primary svc-btn-sm" data-testid="intake-ai-accept">
                      {t('service.intake_apply', 'Apply suggestions')}
                    </button>
                    <button type="button" onClick={() => setAi(null)} className="svc-btn svc-btn-ghost svc-btn-sm" data-testid="intake-ai-dismiss">
                      {t('service.intake_dismiss', 'Dismiss')}
                    </button>
                  </div>
                </div>
              ) : (
                <p className="text-[11.5px] svc-muted mt-2">
                  {t('service.intake_ai_hint', 'Type the fault description and click Suggest priority + parts. Claude returns a recommended priority, fault code, and parts to allocate.')}
                </p>
              )}
            </div>
          </Step>

          {/* Step 9 — Fault code */}
          <Step n={9} icon={<AlertTriangle size={12} />} label={t('service.intake_step_fault', 'Fault code')}>
            <input
              value={faultCode}
              onChange={(e) => setFaultCode(e.target.value)}
              placeholder={ai?.fault_code ? t('service.intake_ph_fault_suggested', 'Suggested: {{code}}', { code: ai.fault_code }) : 'TM-BLT-WEAR'}
              className="svc-input"
              data-testid="intake-fault"
            />
          </Step>
        </div>

        {/* Footer */}
        <div className="svc-drawer-foot flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="svc-btn svc-btn-ghost" data-testid="intake-cancel">
            {t('service.intake_cancel', 'Cancel')}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="svc-btn svc-btn-primary"
            data-testid="intake-submit"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Phone size={13} />}
            {saving ? t('service.intake_logging', 'Logging…') : t('service.intake_log_case', 'Log case')}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <label className="block">
      <span className="svc-label">{label}{required ? <span className="svc-req">*</span> : null}</span>
      {children}
    </label>
  );
}

function Step({ n, icon, label, disabled, children }) {
  return (
    <fieldset className="svc-fieldset" data-testid={`intake-step-${n}`} style={disabled ? { opacity: 0.55 } : undefined}>
      <legend>
        <span className="svc-step-num" aria-hidden="true">{n}</span>
        {icon}
        {label}
      </legend>
      {children}
    </fieldset>
  );
}

function ToggleChip({ active, onClick, children, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={`svc-pill ${active ? 'svc-pill--info' : ''}`}
      style={{
        cursor: 'pointer',
        opacity: active ? 1 : 0.7,
        borderWidth: active ? 1 : 1,
      }}
    >
      {children}
    </button>
  );
}

function CoveragePanel({
  loading, coverage,
  quoteRequired, setQuoteRequired,
  customerPONumber, setCustomerPONumber,
}) {
  const { t } = useTranslation();
  if (loading) {
    return (
      <div className="svc-pill" data-testid="intake-coverage-loading">
        <Loader2 size={11} className="animate-spin" /> {t('service.intake_checking', 'Checking contract coverage…')}
      </div>
    );
  }
  if (!coverage) return null;
  if (coverage.covered) {
    const pillClass = coverage.type === 'warranty' ? 'svc-pill--info' : 'svc-pill--good';
    return (
      <div className="rounded-lg p-3" style={{ background: 'var(--svc-surface-soft)', border: '1px solid var(--svc-border)' }} data-testid="intake-coverage-panel">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`svc-pill ${pillClass}`} data-testid="intake-coverage-pill">
            <CheckCircle2 size={11} /> {coverage.label || t('service.intake_covered', 'Covered')}
          </span>
          {coverage.warranty_active && coverage.warranty_days_remaining != null ? (
            <span className="text-[11.5px] svc-muted">{t('service.intake_warranty_remaining', 'Warranty · {{n}}d remaining', { n: coverage.warranty_days_remaining })}</span>
          ) : null}
          {coverage.contract_active && coverage.contract_days_remaining != null ? (
            <span className="text-[11.5px] svc-muted">{t('service.intake_contract_remaining', 'Contract · {{n}}d remaining', { n: coverage.contract_days_remaining })}</span>
          ) : null}
          {coverage.sla_contract_ref ? (
            <span className="text-[11.5px] svc-muted">{t('service.intake_ref', 'Ref · {{ref}}', { ref: coverage.sla_contract_ref })}</span>
          ) : null}
        </div>
        <p className="svc-fieldset-hint mt-1.5">{t('service.intake_cover_autoset', "Cover type and SLA are auto-set from the equipment's active contract.")}</p>
      </div>
    );
  }
  // Not covered — chargeable workflow
  return (
    <div className="rounded-lg p-3 space-y-2" style={{ background: 'var(--svc-warn-bg)', border: '1px solid var(--svc-warn-border)' }} data-testid="intake-coverage-panel">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="svc-pill svc-pill--warn" data-testid="intake-coverage-pill">
          <AlertTriangle size={11} /> {t('service.intake_out_of_cover', 'Out of cover · chargeable')}
        </span>
        {coverage.warranty_expiry ? (
          <span className="text-[11.5px] svc-muted">{t('service.intake_warranty_ended', 'Warranty ended {{d}}', { d: coverage.warranty_expiry })}</span>
        ) : null}
        {coverage.sla_expiry ? (
          <span className="text-[11.5px] svc-muted">{t('service.intake_contract_ended', 'Contract ended {{d}}', { d: coverage.sla_expiry })}</span>
        ) : null}
      </div>
      <p className="svc-fieldset-hint" style={{ margin: 0 }}>{t('service.intake_chargeable_hint', 'This work falls outside contract / warranty cover. Quote the customer and capture their PO before dispatching an engineer.')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
        <label className="flex items-center gap-2 text-[12px]" data-testid="intake-quote-required">
          <input
            type="checkbox"
            checked={quoteRequired}
            onChange={(e) => setQuoteRequired(e.target.checked)}
            data-testid="intake-quote-required-input"
          />
          {t('service.intake_quote_required_lbl', 'Quote required before dispatch')}
        </label>
        <Field label={t('service.intake_f_customer_po', 'Customer PO number')}>
          <input
            value={customerPONumber}
            onChange={(e) => setCustomerPONumber(e.target.value)}
            placeholder={t('service.intake_ph_po', 'e.g. PO-2026-0145')}
            className="svc-input"
            data-testid="intake-customer-po"
          />
        </Field>
      </div>
    </div>
  );
}
