import { useState } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import { notify } from '@/components/notifications';
import {
 Upload, Plus, Trash2, CheckCircle, Image, ArrowRight, ArrowLeft, Loader2,
 FileSpreadsheet, FileText, Download,
} from 'lucide-react';
import InvoiceImportWizard from './InvoiceImportWizard';
import DatePicker from '@/components/shared/DatePicker';
import SupplierAutocomplete from '@/components/shared/SupplierAutocomplete';
import {
  SLA_RESPONSE_TIME_OPTIONS,
  EQUIPMENT_LOCATION_PRESETS,
} from '@/utils/operationsDropdowns';

const EQUIPMENT_TYPES = [
 'Treadmill', 'Exercise Bike', 'Cross Trainer', 'Rower', 'Stair Climber',
 'Strength Machine', 'Free Weights', 'Cable Machine', 'Smith Machine',
 'Leg Press', 'Lat Pulldown', 'Chest Press', 'Functional Trainer', 'Other'
];

const OnboardingWizard = ({ open, onClose, onComplete, skipLogo = false }) => {
 const { API, activeSite } = useAuth();
 const [step, setStep] = useState(skipLogo ? 2 : 1);
 const [logoFile, setLogoFile] = useState(null);
 const [logoPreview, setLogoPreview] = useState(null);
 const [logoUploading, setLogoUploading] = useState(false);
 const [equipment, setEquipment] = useState([
 { name: '', serial_number: '', equipment_type: '', manufacturer: '', model: '', location: '', photo_url: null }
 ]);
 const [submitting, setSubmitting] = useState(false);
 const [csvImporting, setCsvImporting] = useState(false);
 const [showInvoiceImport, setShowInvoiceImport] = useState(false);

 const downloadCsvTemplate = () => {
 const token = localStorage.getItem('token');
 // Iter 216h108 — unified template (same one Master Admin ships).
 fetch(`${API}/account/import/equipment/template`, { headers: { Authorization: `Bearer ${token}` } })
 .then((r) => r.blob())
 .then((blob) => {
 const url = URL.createObjectURL(blob);
 const a = document.createElement('a');
 a.href = url;
 a.download = 'equipment-template.csv';
 a.click();
 URL.revokeObjectURL(url);
 })
 .catch(() => notify.error('Failed to download template'));
 };

 const handleLogoSelect = (e) => {
 const file = e.target.files[0];
 if (!file) return;
 setLogoFile(file);
 setLogoPreview(URL.createObjectURL(file));
 };

 const handleLogoUpload = async () => {
 if (!logoFile) { setStep(2); return; }
 setLogoUploading(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', logoFile);
 const _res = await axios.post(`${API}/organization/logo`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 notify.success('Logo uploaded');
 setStep(2);
 } catch {
 notify.error('Logo upload failed');
 } finally {
 setLogoUploading(false);
 }
 };

 const addEquipment = () => {
 setEquipment([...equipment, { name: '', serial_number: '', equipment_type: '', manufacturer: '', model: '', location: '', photo_url: null }]);
 };

 const updateEquipment = (idx, field, value) => {
 const updated = [...equipment];
 updated[idx] = { ...updated[idx], [field]: value };
 setEquipment(updated);
 };

 const removeEquipment = (idx) => {
 setEquipment(equipment.filter((_, i) => i !== idx));
 };

 const handlePhotoUpload = async (idx, e) => {
 const file = e.target.files[0];
 if (!file) return;
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 const res = await axios.post(`${API}/files/upload?category=equipment-photos`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 updateEquipment(idx, 'photo_url', res.data.download_url);
 notify.success('Photo uploaded');
 } catch {
 notify.error('Photo upload failed');
 }
 e.target.value = '';
 };

 const handleCSVImport = async (e) => {
 const file = e.target.files[0];
 if (!file) return;
 setCsvImporting(true);
 const token = localStorage.getItem('token');
 try {
 const formData = new FormData();
 formData.append('file', file);
 // Iter 216h108 — use the unified bulk-import endpoint so CSV + XLSX
 // both parse correctly (Excel-serial dates, header aliases, etc.).
 const res = await axios.post(`${API}/account/import/equipment`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
 });
 notify.success(`Imported ${res.data.imported || 0} items`);
 setStep(3);
 } catch {
 notify.error('Import failed');
 } finally {
 setCsvImporting(false);
 e.target.value = '';
 }
 };

 const handleSubmit = async () => {
 const valid = equipment.filter(e => e.name.trim() || e.serial_number.trim());
 if (valid.length === 0) {
 notify.error('Add at least one piece of equipment');
 return;
 }
 setSubmitting(true);
 const token = localStorage.getItem('token');
 try {
 // Iter 216h194 — pass the user's active site_id so the new rows
 // immediately match the per-site filter that drives the Equipment
 // list. Backend infers the site for single-site orgs too, but
 // sending it explicitly avoids any ambiguity.
 const payload = { items: valid };
 if (activeSite?.id) payload.site_id = activeSite.id;
 const res = await axios.post(`${API}/onboarding/equipment`, payload, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success(`${res.data.count} machines onboarded`);
 setStep(3);
 } catch {
 notify.error('Failed to onboard equipment');
 } finally {
 setSubmitting(false);
 }
 };

 const handleFinish = () => {
 if (onComplete) onComplete();
 onClose();
 };

 return (
 <>
 <Dialog open={open} onOpenChange={onClose}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="onboarding-wizard">
 <DialogHeader>
 <DialogTitle className="text-white text-xl">
 {step === 1 && !skipLogo && 'Step 1: Your Gym Branding'}
 {step === 2 && (skipLogo ? 'Step 1: Add Your Equipment' : 'Step 2: Add Your Equipment')}
 {step === 3 && 'Onboarding Complete'}
 </DialogTitle>
 </DialogHeader>

 {/* Progress */}
 <div className="flex items-center gap-2 mb-4">
 {(skipLogo ? [2, 3] : [1, 2, 3]).map(s => (
 <div key={s} className={`h-1.5 flex-1 rounded-full ${s <= step ? 'bg-[var(--color-brand-blue)]' : 'bg-white/10'}`} />
 ))}
 </div>

 {/* Step 1: Logo Upload */}
 {step === 1 && (
 <div className="space-y-6" data-testid="onboarding-step-1">
 <p className="text-[var(--color-text-muted)]">Upload your gym logo. It will appear alongside the Pulse Fitness AI logo throughout the platform.</p>
 <div className="flex flex-col items-center gap-4 p-8 border-2 border-dashed border-white/20 rounded-lg">
 {logoPreview ? (
 <img src={logoPreview} alt="Logo preview" className="h-24 object-contain rounded" data-testid="logo-preview" />
 ) : (
 <div className="w-24 h-24 bg-white/5 rounded-lg flex items-center justify-center">
 <Image size={32} className="text-[var(--color-text-muted)]" />
 </div>
 )}
 <label className="cursor-pointer">
 <input type="file" className="hidden" accept="image/*" onChange={handleLogoSelect} data-testid="logo-file-input" />
 <Button type="button" variant="outline" className="border-white/10 text-white pointer-events-none">
 <Upload size={16} className="mr-2" /> {logoPreview ? 'Change Logo' : 'Upload Logo'}
 </Button>
 </label>
 </div>
 <div className="flex justify-end gap-3">
 <Button variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={() => setStep(2)} data-testid="skip-logo-btn">Skip</Button>
 <Button onClick={handleLogoUpload} disabled={logoUploading} className="bg-[var(--color-brand-blue)] text-white" data-testid="upload-logo-btn">
 {logoUploading ? <><Loader2 size={16} className="mr-2 animate-spin" /> Uploading...</> : <>Continue <ArrowRight size={16} className="ml-1" /></>}
 </Button>
 </div>
 </div>
 )}

 {/* Step 2: Equipment */}
 {step === 2 && (
 <div className="space-y-4" data-testid="onboarding-step-2">
 <div className="flex items-start justify-between flex-wrap gap-3">
 <p className="text-[var(--color-text-muted)] max-w-md">
 Add your gym equipment — type it in manually, import a supplier <strong>invoice PDF</strong> (AI extracts every line item),
 or upload a CSV using our template.
 </p>
 <div className="flex flex-wrap items-center gap-2" data-testid="onboard-equip-import-bar">
 <Button
 size="sm"
 type="button"
 variant="outline"
 className="border-white/10 text-white"
 onClick={() => setShowInvoiceImport(true)}
 data-testid="onboard-invoice-btn"
 >
 <FileText size={14} className="mr-1" /> Import from Invoice
 </Button>
 <label className="cursor-pointer">
 <input type="file" accept=".csv,.xlsx,.xlsm" className="hidden" onChange={handleCSVImport} data-testid="onboard-csv-input" />
 <Button size="sm" variant="outline" className="border-white/10 text-white pointer-events-none" data-testid="onboard-csv-btn">
 <FileSpreadsheet size={14} className="mr-1" /> {csvImporting ? 'Importing…' : 'Import CSV'}
 </Button>
 </label>
 <Button
 size="sm"
 type="button"
 variant="ghost"
 className="text-[var(--color-brand-cyan-hover)] hover:text-white px-2"
 onClick={downloadCsvTemplate}
 data-testid="onboard-csv-template-btn"
 >
 <Download size={12} className="mr-1" /> CSV template
 </Button>
 </div>
 </div>

 <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
 {equipment.map((eq, idx) => (
              <Card key={idx} className="bg-[var(--color-ink-alt)] border-white/10 p-5" data-testid={`onboard-equip-${idx}`}>
                {/* Iter 216h227 — mobile layout: photo + photo-picker
                    stays in line above the field grid so the 9 inputs
                    don't squash to ~80px each on phone screens.
                    Above sm: revert to the original side-by-side. */}
                <div className="flex flex-col sm:flex-row items-stretch sm:items-start gap-3">
                  {/* Photo */}
                  <label className="cursor-pointer flex-shrink-0 self-start">
                    <input type="file" accept="image/*" className="hidden" onChange={(e) => handlePhotoUpload(idx, e)} data-testid={`equip-photo-input-${idx}`} />
                    <div className="w-16 h-16 bg-[var(--theme-surface)] border border-white/10 rounded-lg flex items-center justify-center overflow-hidden hover:border-[rgb(var(--rgb-brand-blue)/0.5)] transition-colors">
                      {eq.photo_url ? (
                        <img src={eq.photo_url} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <Image size={20} className="text-[var(--color-text-muted)]" />
                      )}
                    </div>
                  </label>

                  <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
 <Input value={eq.name} onChange={e => updateEquipment(idx, 'name', e.target.value)} placeholder="Name (e.g., Treadmill 1)" className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-name-${idx}`} />
 <Select value={eq.equipment_type} onValueChange={v => updateEquipment(idx, 'equipment_type', v)}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-type-${idx}`}><SelectValue placeholder="Type" /></SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10 text-white">{EQUIPMENT_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
 </Select>
 {/* Iter 216h193 — Supplier autocomplete (curated UK list + org's
     own suppliers). Triggers a photo-lookup on selection so newly
     onboarded equipment gets the right product image automatically. */}
 <SupplierAutocomplete
   value={eq.manufacturer}
   onChange={(v) => updateEquipment(idx, 'manufacturer', v)}
   onSelectSupplier={async (s) => {
     if (!s) return;
     try {
       const token = localStorage.getItem('token');
       const r = await axios.get(`${API}/suppliers/catalogue/photo-lookup`, {
         params: { supplier: s.name, model: eq.model || '' },
         headers: { Authorization: `Bearer ${token}` },
       });
       if (r.data?.photo_url && !eq.photo_url) {
         updateEquipment(idx, 'photo_url', r.data.photo_url);
       }
     } catch { /* photo lookup is best-effort */ }
   }}
   placeholder="Supplier / Manufacturer"
   inputClassName="bg-[var(--theme-surface)] border-white/10 text-white text-sm"
   testid={`equip-mfr-${idx}`}
 />
 <Input value={eq.model} onChange={e => updateEquipment(idx, 'model', e.target.value)} placeholder="Model" className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-model-${idx}`} />
 <Input value={eq.serial_number} onChange={e => updateEquipment(idx, 'serial_number', e.target.value)} placeholder="Serial Number" className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-sn-${idx}`} />
 {/* Iter 216h193 — Location now offers a suggestion list (Cardio Zone,
     Studio 1, Free Weights, …) via a native datalist while still
     allowing free-text for bespoke layouts. */}
 <span className="block">
   <Input
     value={eq.location}
     onChange={e => updateEquipment(idx, 'location', e.target.value)}
     placeholder="Location (e.g., Cardio Zone)"
     list={`equip-loc-list-${idx}`}
     className="bg-[var(--theme-surface)] border-white/10 text-white text-sm"
     data-testid={`equip-loc-${idx}`}
   />
   <datalist id={`equip-loc-list-${idx}`}>
     {EQUIPMENT_LOCATION_PRESETS.map((loc) => <option key={loc} value={loc} />)}
   </datalist>
 </span>
 {/* Iter 216h193 — SLA Response Time is now an enum dropdown (2h /
     4h / next business day / 5d / custom) so reports can compare
     SLA breach rates apples-to-apples across the estate. */}
 <Select value={eq.sla_response_time || ''} onValueChange={v => updateEquipment(idx, 'sla_response_time', v)}>
   <SelectTrigger className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-sla-${idx}`}>
     <SelectValue placeholder="SLA Response Time" />
   </SelectTrigger>
   <SelectContent className="bg-[var(--theme-surface)] border-white/10 text-white">
     {SLA_RESPONSE_TIME_OPTIONS.map((opt) => (
       <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
     ))}
   </SelectContent>
 </Select>
 <Input value={eq.sla_contract_ref || ''} onChange={e => updateEquipment(idx, 'sla_contract_ref', e.target.value)} placeholder="SLA Contract Ref" className="bg-[var(--theme-surface)] border-white/10 text-white text-sm" data-testid={`equip-sla-ref-${idx}`} />
 {/* Iter 216h193 — SLA Expiry Date now uses the platform-wide
     DD/MM/YYYY DatePicker (Shadcn calendar) so dates stay consistent
     across reports and exports. */}
 <DatePicker
   value={eq.sla_expiry || ''}
   onChange={(iso) => updateEquipment(idx, 'sla_expiry', iso)}
   placeholder="SLA Expiry Date"
   inputClassName="bg-[var(--theme-surface)] border-white/10 text-white text-sm"
   testid={`equip-sla-exp-${idx}`}
 />
 </div>

 {equipment.length > 1 && (
 <button onClick={() => removeEquipment(idx)} className="text-red-400 hover:text-red-300 p-1 flex-shrink-0"><Trash2 size={16} /></button>
 )}
 </div>
 </Card>
 ))}
 </div>

 <Button size="sm" variant="outline" className="border-white/10 text-[var(--color-text-muted)]" onClick={addEquipment} data-testid="add-more-equip-btn">
 <Plus size={14} className="mr-1" /> Add Another Machine
 </Button>

 <div className="flex justify-between pt-4 border-t border-white/10">
 <Button variant="outline" className="border-white/10 text-white" onClick={() => setStep(1)} data-testid="back-to-step1-btn">
 <ArrowLeft size={16} className="mr-1" /> Back
 </Button>
 <Button onClick={handleSubmit} disabled={submitting} className="bg-[var(--color-brand-blue)] text-white" data-testid="onboard-submit-btn">
 {submitting ? <><Loader2 size={16} className="mr-2 animate-spin" /> Onboarding...</> : <>Onboard Equipment <ArrowRight size={16} className="ml-1" /></>}
 </Button>
 </div>
 </div>
 )}

 {/* Step 3: Complete */}
 {step === 3 && (
 <div className="text-center py-8 space-y-4" data-testid="onboarding-step-3">
 <div className="w-20 h-20 bg-green-500/10 rounded-full flex items-center justify-center mx-auto">
 <CheckCircle size={40} className="text-green-400" />
 </div>
 <h3 className="text-xl font-semibold text-white">You're All Set!</h3>
 <p className="text-[var(--color-text-muted)]">Your equipment has been onboarded. You can now log faults, run audits, and manage maintenance for all your machines.</p>
 <Button onClick={handleFinish} className="bg-[var(--color-brand-blue)] text-white" data-testid="onboard-finish-btn">
 Go to Dashboard <ArrowRight size={16} className="ml-1" />
 </Button>
 </div>
 )}
 </DialogContent>
 </Dialog>
 {showInvoiceImport && (
 <InvoiceImportWizard
 onClose={() => setShowInvoiceImport(false)}
 onComplete={() => {
 setShowInvoiceImport(false);
 notify.success('Invoice imported — skipping to Done.');
 setStep(3);
 if (onComplete) onComplete();
 }}
 />
 )}
 </>
 );
};

export default OnboardingWizard;
