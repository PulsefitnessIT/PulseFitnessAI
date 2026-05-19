/* Customer Onboarding Wizard — public, token-based, no login required.
 * Matches backend /api/onboarding/public/{token}
 * Progress auto-saves on step change (debounced).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Building2, MapPin, Users, Wrench, Truck, FileText,
  CheckCircle2, ArrowLeft, ArrowRight, Loader2, Save,
  Plus, Trash2, AlertCircle, Package,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const STEPS = [
  { id: 'organisation', label: 'Organisation', icon: Building2 },
  { id: 'sites', label: 'Sites', icon: MapPin },
  { id: 'staff', label: 'Staff', icon: Users },
  { id: 'equipment', label: 'Equipment', icon: Wrench },
  { id: 'suppliers', label: 'Suppliers', icon: Truck },
  { id: 'contracts', label: 'Contracts', icon: FileText },
  { id: 'review', label: 'Review', icon: CheckCircle2 },
];

const EMPTY_SITE = { name: '', address_line1: '', address_line2: '', city: '', postcode: '', square_footage: 0, operating_hours: '', on_site_contact_name: '', on_site_contact_phone: '' };
const EMPTY_STAFF = { full_name: '', email: '', phone: '', role: 'manager', default_site_index: 0 };
const EMPTY_EQ = { name: '', equipment_type: '', brand: '', model: '', serial_number: '', install_date: '', warranty_expiry: '', supplier: '', site_index: 0 };
const EMPTY_SUPPLIER = { name: '', contact_email: '', phone: '', categories: [], notes: '' };
const EMPTY_CONTRACT = { contract_number: '', provider: '', tier: 'standard', start_date: '', end_date: '', annual_value: 0, sla_response_hours: 24, sla_resolution_hours: 72 };

export default function CustomerOnboardingForm() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [packet, setPacket] = useState(null);
  const [currentStep, setCurrentStep] = useState('organisation');
  const saveTimer = useRef(null);

  const loadPacket = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await axios.get(`${API}/onboarding/public/${token}`);
      setPacket(res.data);
      setCurrentStep(res.data.current_step || 'organisation');
      if (res.data.status === 'submitted' || res.data.status === 'provisioned' || res.data.status === 'approved') {
        setSubmitted(true);
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Unable to load this onboarding form');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadPacket(); }, [loadPacket]);

  // Auto-save (debounced) when packet changes
  const savePacket = useCallback(async (next) => {
    try {
      setSaving(true);
      const payload = {
        organisation: next.organisation,
        sites: next.sites,
        staff: next.staff,
        equipment: next.equipment,
        suppliers: next.suppliers,
        contracts: next.contracts,
        current_step: next.current_step,
      };
      await axios.put(`${API}/onboarding/public/${token}`, payload);
    } catch (e) {
      console.error('Autosave failed', e);
    } finally {
      setSaving(false);
    }
  }, [token]);

  const update = useCallback((patch) => {
    setPacket((prev) => {
      const next = { ...prev, ...patch };
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => savePacket(next), 700);
      return next;
    });
  }, [savePacket]);

  const goto = (id) => {
    update({ current_step: id });
    setCurrentStep(id);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      // Force a save first
      if (saveTimer.current) clearTimeout(saveTimer.current);
      await savePacket(packet);
      await axios.post(`${API}/onboarding/public/${token}/submit`);
      notify.success('Submitted successfully');
      setSubmitted(true);
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'object' ? (detail.errors || []).join(' • ') : (detail || 'Submission failed');
      notify.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <CenterBox><Loader2 className="animate-spin text-zinc-400" /></CenterBox>;
  if (error) return <CenterBox><ErrorCard error={error} /></CenterBox>;
  if (submitted) return <CenterBox><SubmittedCard packet={packet} /></CenterBox>;
  if (!packet) return null;

  const stepIdx = STEPS.findIndex(s => s.id === currentStep);

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-50 via-white to-blue-50" data-testid="customer-onboarding-form">
      {/* Header */}
      <div className="border-b border-zinc-200 bg-white/80 backdrop-blur">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-zinc-900">Customer Onboarding</h1>
            <div className="text-xs text-zinc-500 flex items-center gap-2">
              <span>{packet.customer_display_name || 'Welcome'}</span>
              <span>·</span>
              <span>Tier:</span>
              <Badge className="bg-blue-100 text-blue-800 capitalize">{packet.target_tier}</Badge>
            </div>
          </div>
          <div className="text-xs text-zinc-400 flex items-center gap-2" data-testid="autosave-status">
            {saving ? <><Loader2 size={12} className="animate-spin" /> Saving…</> : <><Save size={12} /> Autosaved</>}
          </div>
        </div>
      </div>

      {/* Stepper */}
      <div className="max-w-5xl mx-auto px-6 pt-6">
        <div className="flex items-center justify-between gap-1 mb-6">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const done = i < stepIdx;
            const active = i === stepIdx;
            return (
              <button key={s.id} onClick={() => goto(s.id)}
                data-testid={`step-nav-${s.id}`}
                className={`flex-1 flex flex-col items-center gap-1 py-2 px-1 rounded-lg border transition-all ${active ? 'bg-blue-600 border-blue-600 text-white shadow-md' : done ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-zinc-200 text-zinc-500 hover:border-zinc-300'}`}>
                <Icon size={16} />
                <span className="text-[10px] font-semibold uppercase tracking-wider">{s.label}</span>
              </button>
            );
          })}
        </div>

        <Card className="p-6 lg:p-8 border-zinc-200 shadow-sm bg-white">
          {currentStep === 'organisation' && <OrganisationStep packet={packet} update={update} />}
          {currentStep === 'sites' && <SitesStep packet={packet} update={update} />}
          {currentStep === 'staff' && <StaffStep packet={packet} update={update} />}
          {currentStep === 'equipment' && <EquipmentStep packet={packet} update={update} />}
          {currentStep === 'suppliers' && <SuppliersStep packet={packet} update={update} />}
          {currentStep === 'contracts' && <ContractsStep packet={packet} update={update} />}
          {currentStep === 'review' && <ReviewStep packet={packet} onSubmit={handleSubmit} submitting={submitting} />}
        </Card>

        {/* Nav buttons */}
        <div className="flex justify-between mt-6 pb-10">
          <Button variant="outline" disabled={stepIdx === 0} onClick={() => goto(STEPS[stepIdx - 1].id)} data-testid="btn-prev">
            <ArrowLeft size={14} className="mr-1" /> Back
          </Button>
          {currentStep !== 'review' ? (
            <Button onClick={() => goto(STEPS[stepIdx + 1].id)} className="bg-blue-600 hover:bg-blue-700" data-testid="btn-next">
              Next <ArrowRight size={14} className="ml-1" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700" data-testid="btn-submit">
              {submitting ? <Loader2 size={14} className="animate-spin mr-1" /> : <CheckCircle2 size={14} className="mr-1" />}
              Submit for review
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Helpers ────────────────────────────────────────────────────── */

function CenterBox({ children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 p-4">
      {children}
    </div>
  );
}

function ErrorCard({ error }) {
  return (
    <Card className="max-w-md p-8 text-center" data-testid="onboarding-error">
      <AlertCircle size={32} className="text-red-500 mx-auto mb-2" />
      <h2 className="text-lg font-semibold text-zinc-900">Unable to open</h2>
      <p className="text-sm text-zinc-500 mt-2">{error}</p>
    </Card>
  );
}

function SubmittedCard({ packet }) {
  return (
    <Card className="max-w-md p-10 text-center" data-testid="onboarding-submitted">
      <CheckCircle2 size={40} className="text-emerald-500 mx-auto mb-3" />
      <h2 className="text-xl font-semibold text-zinc-900">Thank you{packet?.customer_display_name ? `, ${packet.customer_display_name}` : ''}</h2>
      <p className="text-sm text-zinc-500 mt-3">
        Your onboarding pack has been submitted. Your account manager will review it and provision your workspace shortly. Each of your staff members will receive a secure email to set their password.
      </p>
    </Card>
  );
}

function Field({ label, children, required, col = 1 }) {
  return (
    <div className={`col-span-${col}`}>
      <Label className="text-xs font-semibold text-zinc-600 uppercase tracking-wider">
        {label} {required && <span className="text-red-500">*</span>}
      </Label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

/* ── Step 1: Organisation ───────────────────────────────────────── */

function OrganisationStep({ packet, update }) {
  const o = packet.organisation || {};
  const set = (k, v) => update({ organisation: { ...o, [k]: v } });
  // Iter 215et — postcode-on-blur lookup. Public unauth endpoint, no headers.
  const lookupBilling = async (pc) => {
    const trimmed = (pc || '').trim();
    if (!trimmed || trimmed.replace(/\s+/g, '').length < 5) return;
    try {
      const r = await axios.get(`${API}/integrations/postcode/lookup`, { params: { postcode: trimmed } });
      if (r.data?.found) {
        update({ organisation: {
          ...o,
          billing_postcode: r.data.postcode || o.billing_postcode,
          billing_city: o.billing_city || r.data.city || '',
          billing_country: o.billing_country || r.data.country || 'United Kingdom',
        }});
      }
    } catch { /* silent */ }
  };
  return (
    <div data-testid="step-organisation">
      <StepHeader icon={Building2} title="Your organisation" subtitle="Legal details we use to set up your billing account and primary contact." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Legal name" required><Input data-testid="org-legal-name" value={o.legal_name || ''} onChange={e => set('legal_name', e.target.value)} /></Field>
        <Field label="Trading name"><Input data-testid="org-trading-name" value={o.trading_name || ''} onChange={e => set('trading_name', e.target.value)} /></Field>
        <Field label="VAT number"><Input data-testid="org-vat" value={o.vat_number || ''} onChange={e => set('vat_number', e.target.value)} /></Field>
        <Field label="Company registration"><Input data-testid="org-company-number" value={o.company_number || ''} onChange={e => set('company_number', e.target.value)} /></Field>
        <Field label="Address line 1" col={2}><Input data-testid="org-addr1" value={o.billing_address_line1 || ''} onChange={e => set('billing_address_line1', e.target.value)} /></Field>
        <Field label="Address line 2" col={2}><Input data-testid="org-addr2" value={o.billing_address_line2 || ''} onChange={e => set('billing_address_line2', e.target.value)} /></Field>
        <Field label="City"><Input data-testid="org-city" value={o.billing_city || ''} onChange={e => set('billing_city', e.target.value)} /></Field>
        <Field label="Postcode" required><Input data-testid="org-postcode" value={o.billing_postcode || ''} onChange={e => set('billing_postcode', e.target.value)} onBlur={e => lookupBilling(e.target.value)} /></Field>
        <Field label="Country"><Input data-testid="org-country" value={o.billing_country || 'United Kingdom'} onChange={e => set('billing_country', e.target.value)} /></Field>
        <Field label="Website"><Input data-testid="org-website" value={o.website || ''} onChange={e => set('website', e.target.value)} /></Field>
        <Field label="Primary contact name"><Input data-testid="org-pc-name" value={o.primary_contact_name || ''} onChange={e => set('primary_contact_name', e.target.value)} /></Field>
        <Field label="Primary contact email" required><Input type="email" data-testid="org-pc-email" value={o.primary_contact_email || ''} onChange={e => set('primary_contact_email', e.target.value)} /></Field>
        <Field label="Primary contact phone"><Input data-testid="org-pc-phone" value={o.primary_contact_phone || ''} onChange={e => set('primary_contact_phone', e.target.value)} /></Field>
      </div>
    </div>
  );
}

/* ── Step 2: Sites ──────────────────────────────────────────────── */

function SitesStep({ packet, update }) {
  const sites = packet.sites || [];
  const add = () => update({ sites: [...sites, { ...EMPTY_SITE }] });
  const remove = (i) => update({ sites: sites.filter((_, idx) => idx !== i) });
  const setField = (i, k, v) => {
    const next = sites.map((s, idx) => idx === i ? { ...s, [k]: v } : s);
    update({ sites: next });
  };
  // Iter 215et — postcode-on-blur lookup for each site row.
  const lookupSite = async (i, pc) => {
    const trimmed = (pc || '').trim();
    if (!trimmed || trimmed.replace(/\s+/g, '').length < 5) return;
    try {
      const r = await axios.get(`${API}/integrations/postcode/lookup`, { params: { postcode: trimmed } });
      if (r.data?.found) {
        const next = sites.map((s, idx) => idx === i ? {
          ...s,
          postcode: r.data.postcode || s.postcode,
          city: s.city || r.data.city || '',
        } : s);
        update({ sites: next });
      }
    } catch { /* silent */ }
  };
  return (
    <div data-testid="step-sites">
      <StepHeader icon={MapPin} title="Sites" subtitle="Each physical location where equipment is managed. Most customers have one, but add all of yours — you can always add more later." action={<Button onClick={add} size="sm" data-testid="btn-add-site"><Plus size={14} className="mr-1" />Add site</Button>} />
      {sites.length === 0 && <EmptyBlock label="No sites added yet" />}
      <div className="space-y-4">
        {sites.map((s, i) => (
          <div key={i} className="border border-zinc-200 rounded-lg p-4 bg-zinc-50/50" data-testid={`site-card-${i}`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-zinc-800">Site #{i + 1}</h4>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} data-testid={`btn-remove-site-${i}`}><Trash2 size={14} className="text-red-500" /></Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Site name" required><Input value={s.name || ''} onChange={e => setField(i, 'name', e.target.value)} data-testid={`site-${i}-name`} /></Field>
              <Field label="Operating hours"><Input placeholder="e.g. Mon–Sun 06:00–22:00" value={s.operating_hours || ''} onChange={e => setField(i, 'operating_hours', e.target.value)} /></Field>
              <Field label="Address line 1" col={2}><Input value={s.address_line1 || ''} onChange={e => setField(i, 'address_line1', e.target.value)} /></Field>
              <Field label="Address line 2" col={2}><Input value={s.address_line2 || ''} onChange={e => setField(i, 'address_line2', e.target.value)} /></Field>
              <Field label="City"><Input value={s.city || ''} onChange={e => setField(i, 'city', e.target.value)} /></Field>
              <Field label="Postcode" required><Input value={s.postcode || ''} onChange={e => setField(i, 'postcode', e.target.value)} onBlur={e => lookupSite(i, e.target.value)} data-testid={`site-${i}-postcode`} /></Field>
              <Field label="Square footage"><Input type="number" value={s.square_footage || 0} onChange={e => setField(i, 'square_footage', Number(e.target.value))} /></Field>
              <Field label="On-site contact"><Input value={s.on_site_contact_name || ''} onChange={e => setField(i, 'on_site_contact_name', e.target.value)} /></Field>
              <Field label="Contact phone"><Input value={s.on_site_contact_phone || ''} onChange={e => setField(i, 'on_site_contact_phone', e.target.value)} /></Field>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Step 3: Staff ──────────────────────────────────────────────── */

function StaffStep({ packet, update }) {
  const staff = packet.staff || [];
  const sites = packet.sites || [];
  const add = () => update({ staff: [...staff, { ...EMPTY_STAFF }] });
  const remove = (i) => update({ staff: staff.filter((_, idx) => idx !== i) });
  const setField = (i, k, v) => {
    const next = staff.map((s, idx) => idx === i ? { ...s, [k]: v } : s);
    update({ staff: next });
  };
  return (
    <div data-testid="step-staff">
      <StepHeader icon={Users} title="Staff members" subtitle="We'll email each person a secure link to set their own password — no shared credentials. At least one person must be an Owner." action={<Button onClick={add} size="sm" data-testid="btn-add-staff"><Plus size={14} className="mr-1" />Add staff</Button>} />
      {staff.length === 0 && <EmptyBlock label="No staff added yet" />}
      <div className="space-y-3">
        {staff.map((m, i) => (
          <div key={i} className="border border-zinc-200 rounded-lg p-4 bg-zinc-50/50" data-testid={`staff-card-${i}`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-zinc-800">Member #{i + 1}</h4>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} data-testid={`btn-remove-staff-${i}`}><Trash2 size={14} className="text-red-500" /></Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Full name" required><Input value={m.full_name || ''} onChange={e => setField(i, 'full_name', e.target.value)} data-testid={`staff-${i}-name`} /></Field>
              <Field label="Email" required><Input type="email" value={m.email || ''} onChange={e => setField(i, 'email', e.target.value)} data-testid={`staff-${i}-email`} /></Field>
              <Field label="Phone"><Input value={m.phone || ''} onChange={e => setField(i, 'phone', e.target.value)} /></Field>
              <Field label="Role">
                <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm bg-white" value={m.role || 'manager'} onChange={e => setField(i, 'role', e.target.value)} data-testid={`staff-${i}-role`}>
                  <option value="owner">Owner (admin)</option>
                  <option value="manager">Manager</option>
                  <option value="maintenance">Maintenance</option>
                  <option value="viewer">Viewer</option>
                </select>
              </Field>
              <Field label="Default site" col={2}>
                <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm bg-white" value={m.default_site_index ?? 0} onChange={e => setField(i, 'default_site_index', Number(e.target.value))}>
                  {sites.length === 0 ? <option value={0}>(add sites first)</option> : sites.map((s, si) => (
                    <option key={si} value={si}>{s.name || `Site #${si + 1}`}</option>
                  ))}
                </select>
              </Field>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Step 4: Equipment ──────────────────────────────────────────── */

function EquipmentStep({ packet, update }) {
  const eq = packet.equipment || [];
  const sites = packet.sites || [];
  const [csvText, setCsvText] = useState('');
  const add = () => update({ equipment: [...eq, { ...EMPTY_EQ }] });
  const remove = (i) => update({ equipment: eq.filter((_, idx) => idx !== i) });
  const setField = (i, k, v) => {
    const next = eq.map((s, idx) => idx === i ? { ...s, [k]: v } : s);
    update({ equipment: next });
  };
  const importCsv = () => {
    const lines = csvText.split('\n').map(l => l.trim()).filter(Boolean);
    if (!lines.length) return;
    // Detect header row
    const first = lines[0].toLowerCase();
    const hasHeader = ['type', 'brand', 'model', 'serial'].some(h => first.includes(h));
    const rows = (hasHeader ? lines.slice(1) : lines).map(l => l.split(/[\t,]/).map(c => c.trim()));
    const parsed = rows.map(cols => ({
      equipment_type: cols[0] || '', brand: cols[1] || '', model: cols[2] || '',
      serial_number: cols[3] || '', install_date: cols[4] || '', warranty_expiry: cols[5] || '',
      supplier: cols[6] || '', site_index: 0,
      name: `${cols[1] || ''} ${cols[2] || ''}`.trim(),
    }));
    update({ equipment: [...eq, ...parsed] });
    setCsvText('');
    notify.success(`Imported ${parsed.length} rows`);
  };
  return (
    <div data-testid="step-equipment">
      <StepHeader icon={Wrench} title="Equipment" subtitle="List every machine you'd like us to manage. You can paste rows from Excel below or add one at a time." action={<Button onClick={add} size="sm" data-testid="btn-add-equipment"><Plus size={14} className="mr-1" />Add equipment</Button>} />

      {/* CSV paste panel */}
      <div className="border border-dashed border-blue-300 bg-blue-50/50 rounded-lg p-4 mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Package size={16} className="text-blue-600" />
          <span className="text-sm font-medium text-blue-900">Bulk paste from Excel</span>
        </div>
        <p className="text-xs text-zinc-600 mb-2">Columns: <code className="text-[11px]">type, brand, model, serial, install_date, warranty_expiry, supplier</code> (tab or comma separated).</p>
        <Textarea rows={4} value={csvText} onChange={e => setCsvText(e.target.value)} placeholder="Treadmill, Life Fitness, Integrity X, TM-001, 2024-01-15, 2027-01-15, Life Fitness"
          data-testid="equipment-csv-paste" className="font-mono text-xs bg-white" />
        <div className="flex justify-end mt-2">
          <Button size="sm" onClick={importCsv} disabled={!csvText.trim()} data-testid="btn-csv-import">Import rows</Button>
        </div>
      </div>

      {eq.length === 0 && <EmptyBlock label="No equipment added yet" />}
      <div className="space-y-2">
        {eq.map((m, i) => (
          <div key={i} className="border border-zinc-200 rounded-lg p-3 bg-zinc-50/50" data-testid={`equipment-card-${i}`}>
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-medium text-zinc-800 text-sm">#{i + 1} · {m.brand || ''} {m.model || ''}</h4>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} data-testid={`btn-remove-equipment-${i}`}><Trash2 size={14} className="text-red-500" /></Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Field label="Type"><Input value={m.equipment_type || ''} onChange={e => setField(i, 'equipment_type', e.target.value)} placeholder="Treadmill" /></Field>
              <Field label="Brand"><Input value={m.brand || ''} onChange={e => setField(i, 'brand', e.target.value)} /></Field>
              <Field label="Model"><Input value={m.model || ''} onChange={e => setField(i, 'model', e.target.value)} /></Field>
              <Field label="Serial"><Input value={m.serial_number || ''} onChange={e => setField(i, 'serial_number', e.target.value)} /></Field>
              <Field label="Install date"><Input type="date" value={m.install_date || ''} onChange={e => setField(i, 'install_date', e.target.value)} /></Field>
              <Field label="Warranty expiry"><Input type="date" value={m.warranty_expiry || ''} onChange={e => setField(i, 'warranty_expiry', e.target.value)} /></Field>
              <Field label="Supplier"><Input value={m.supplier || ''} onChange={e => setField(i, 'supplier', e.target.value)} /></Field>
              <Field label="Site">
                <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm bg-white" value={m.site_index ?? 0} onChange={e => setField(i, 'site_index', Number(e.target.value))}>
                  {sites.length === 0 ? <option value={0}>—</option> : sites.map((s, si) => (
                    <option key={si} value={si}>{s.name || `Site #${si + 1}`}</option>
                  ))}
                </select>
              </Field>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Step 5: Suppliers ──────────────────────────────────────────── */

function SuppliersStep({ packet, update }) {
  const suppliers = packet.suppliers || [];
  const add = () => update({ suppliers: [...suppliers, { ...EMPTY_SUPPLIER }] });
  const remove = (i) => update({ suppliers: suppliers.filter((_, idx) => idx !== i) });
  const setField = (i, k, v) => {
    const next = suppliers.map((s, idx) => idx === i ? { ...s, [k]: v } : s);
    update({ suppliers: next });
  };
  return (
    <div data-testid="step-suppliers">
      <StepHeader icon={Truck} title="Preferred suppliers" subtitle="Optional. Adding suppliers means faster engineer dispatch when a fault is logged." action={<Button onClick={add} size="sm" data-testid="btn-add-supplier"><Plus size={14} className="mr-1" />Add supplier</Button>} />
      {suppliers.length === 0 && <EmptyBlock label="No suppliers yet (optional)" />}
      <div className="space-y-3">
        {suppliers.map((s, i) => (
          <div key={i} className="border border-zinc-200 rounded-lg p-4 bg-zinc-50/50" data-testid={`supplier-card-${i}`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-zinc-800">Supplier #{i + 1}</h4>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} data-testid={`btn-remove-supplier-${i}`}><Trash2 size={14} className="text-red-500" /></Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Name" required><Input value={s.name || ''} onChange={e => setField(i, 'name', e.target.value)} /></Field>
              <Field label="Contact email"><Input type="email" value={s.contact_email || ''} onChange={e => setField(i, 'contact_email', e.target.value)} /></Field>
              <Field label="Phone"><Input value={s.phone || ''} onChange={e => setField(i, 'phone', e.target.value)} /></Field>
              <Field label="Categories (comma separated)"><Input value={(s.categories || []).join(', ')} onChange={e => setField(i, 'categories', e.target.value.split(',').map(x => x.trim()).filter(Boolean))} placeholder="Cardio, Strength, Plumbing" /></Field>
              <Field label="Notes" col={2}><Textarea rows={2} value={s.notes || ''} onChange={e => setField(i, 'notes', e.target.value)} /></Field>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Step 6: Contracts ──────────────────────────────────────────── */

function ContractsStep({ packet, update }) {
  const contracts = packet.contracts || [];
  const add = () => update({ contracts: [...contracts, { ...EMPTY_CONTRACT }] });
  const remove = (i) => update({ contracts: contracts.filter((_, idx) => idx !== i) });
  const setField = (i, k, v) => {
    const next = contracts.map((s, idx) => idx === i ? { ...s, [k]: v } : s);
    update({ contracts: next });
  };
  return (
    <div data-testid="step-contracts">
      <StepHeader icon={FileText} title="Existing service contracts" subtitle="Optional. Share any existing maintenance contracts you want us to honour." action={<Button onClick={add} size="sm" data-testid="btn-add-contract"><Plus size={14} className="mr-1" />Add contract</Button>} />
      {contracts.length === 0 && <EmptyBlock label="No contracts yet (optional)" />}
      <div className="space-y-3">
        {contracts.map((c, i) => (
          <div key={i} className="border border-zinc-200 rounded-lg p-4 bg-zinc-50/50" data-testid={`contract-card-${i}`}>
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-zinc-800">Contract #{i + 1}</h4>
              <Button variant="ghost" size="sm" onClick={() => remove(i)} data-testid={`btn-remove-contract-${i}`}><Trash2 size={14} className="text-red-500" /></Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Contract number"><Input value={c.contract_number || ''} onChange={e => setField(i, 'contract_number', e.target.value)} /></Field>
              <Field label="Provider"><Input value={c.provider || ''} onChange={e => setField(i, 'provider', e.target.value)} /></Field>
              <Field label="Tier">
                <select className="w-full h-10 rounded-md border border-zinc-200 px-3 text-sm bg-white" value={c.tier || 'standard'} onChange={e => setField(i, 'tier', e.target.value)}>
                  <option value="standard">Standard</option>
                  <option value="silver">Silver</option>
                  <option value="gold">Gold</option>
                  <option value="platinum">Platinum</option>
                </select>
              </Field>
              <Field label="Annual value (£)"><Input type="number" value={c.annual_value || 0} onChange={e => setField(i, 'annual_value', Number(e.target.value))} /></Field>
              <Field label="Start date"><Input type="date" value={c.start_date || ''} onChange={e => setField(i, 'start_date', e.target.value)} /></Field>
              <Field label="End date"><Input type="date" value={c.end_date || ''} onChange={e => setField(i, 'end_date', e.target.value)} /></Field>
              <Field label="SLA response (hours)"><Input type="number" value={c.sla_response_hours || 24} onChange={e => setField(i, 'sla_response_hours', Number(e.target.value))} /></Field>
              <Field label="SLA resolution (hours)"><Input type="number" value={c.sla_resolution_hours || 72} onChange={e => setField(i, 'sla_resolution_hours', Number(e.target.value))} /></Field>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Step 7: Review ─────────────────────────────────────────────── */

function ReviewStep({ packet, onSubmit, submitting }) {
  const rows = useMemo(() => ([
    { label: 'Organisation', value: packet.organisation?.legal_name || '—' },
    { label: 'Sites', value: (packet.sites || []).length },
    { label: 'Staff', value: (packet.staff || []).length },
    { label: 'Equipment', value: (packet.equipment || []).length },
    { label: 'Suppliers', value: (packet.suppliers || []).length },
    { label: 'Contracts', value: (packet.contracts || []).length },
  ]), [packet]);
  return (
    <div data-testid="step-review">
      <StepHeader icon={CheckCircle2} title="Review & submit" subtitle="A summary of what you've added. You can go back and edit anything." />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {rows.map(r => (
          <div key={r.label} className="border border-zinc-200 rounded-lg p-4 bg-white">
            <p className="text-xs uppercase tracking-wider text-zinc-400 font-semibold">{r.label}</p>
            <p className="text-xl font-bold text-zinc-900 mt-1">{r.value}</p>
          </div>
        ))}
      </div>
      <div className="mt-6 border-t border-zinc-200 pt-4 text-sm text-zinc-600">
        Clicking <strong>Submit for review</strong> sends this pack to your account manager. They'll provision your workspace and your team will receive email invitations to set their passwords.
      </div>
    </div>
  );
}

/* ── Shared ─────────────────────────────────────────────────────── */

function StepHeader({ icon: Icon, title, subtitle, action }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5 pb-4 border-b border-zinc-100">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
          <Icon size={18} />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-zinc-900">{title}</h2>
          <p className="text-sm text-zinc-500 mt-0.5">{subtitle}</p>
        </div>
      </div>
      {action}
    </div>
  );
}

function EmptyBlock({ label }) {
  return (
    <div className="border-2 border-dashed border-zinc-200 rounded-lg p-6 text-center text-sm text-zinc-400 bg-zinc-50/30 mb-3">
      {label}
    </div>
  );
}
