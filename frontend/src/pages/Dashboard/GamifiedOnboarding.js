import { useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import { Button } from '@/components/ui/button';
import {
 CheckCircle2, Truck, Dumbbell, Users, Rocket,
 ArrowRight, Sparkles, X, Loader2,
} from 'lucide-react';

import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import StageSuppliers from './WizardSteps/StageSuppliers';
import StageEquipment from './WizardSteps/StageEquipment';
import StageStaff from './WizardSteps/StageStaff';
import StageLive from './WizardSteps/StageLive';

/**
 * GamifiedOnboarding — 4-stage, high-conversion onboarding experience.
 * Stages: Suppliers → Equipment → Staff → Go-Live
 *
 * Every stage awards micro-rewards (toasts + animated check), shows an
 * overall progress bar, and cleanly unlocks the next stage. Each stage
 * also offers a "Skip for now" escape hatch so users never feel trapped.
 */

const STAGE_DEFS = [
 { id: 'suppliers', label: 'Add Suppliers', short: 'Suppliers', icon: Truck },
 { id: 'equipment', label: 'Import Equipment', short: 'Equipment', icon: Dumbbell },
 { id: 'staff', label: 'Invite Your Team', short: 'Team', icon: Users },
 { id: 'live', label: 'Go Live', short: 'Go Live', icon: Rocket },
];

const EMPTY_SUPPLIER = { company_name: '', contact_email: '', phone: '', contact_person: '', supplier_type: '', supplier_types: [] };
const EMPTY_STAFF = { full_name: '', email: '', role: 'staff' };
const EMPTY_EQUIP = { name: '', equipment_type: 'cardio', manufacturer: '', model: '', serial_number: '', location: '' };

const GamifiedOnboarding = ({ open, onClose, API, user, onComplete }) => {
 const [status, setStatus] = useState(null);
 const [currentStage, setCurrentStage] = useState('suppliers');
 const [loading, setLoading] = useState(true);

 // Stage state
 const [suppliers, setSuppliers] = useState([{ ...EMPTY_SUPPLIER }]);
 const [equipmentMode, setEquipmentMode] = useState('manual');
 const [equipmentRows, setEquipmentRows] = useState([{ ...EMPTY_EQUIP }]);
 const [csvFile, setCsvFile] = useState(null);
 const [csvImporting, setCsvImporting] = useState(false);
 const [staffInvites, setStaffInvites] = useState([{ ...EMPTY_STAFF }]);
 const [saving, setSaving] = useState(false);

 const loadStatus = async () => {
 setLoading(true);
 try {
 const token = localStorage.getItem('token');
 const res = await axios.get(`${API}/onboarding/status`, { headers: { Authorization: `Bearer ${token}` } });
 setStatus(res.data);
 const firstIncomplete = STAGE_DEFS.find(s => !res.data.stages[s.id]);
 if (firstIncomplete) setCurrentStage(firstIncomplete.id);
 } catch {
 setStatus(null);
 } finally {
 setLoading(false);
 }
 };

 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { if (open) loadStatus();   }, [open]);

 const stages = status?.stages || {};
 const percent = status?.percent || 0;
 const completedCount = status?.completed_count || 0;

 const advanceStage = async (fromStage) => {
 await loadStatus();
 const nextIdx = STAGE_DEFS.findIndex(s => s.id === fromStage) + 1;
 if (nextIdx < STAGE_DEFS.length) setCurrentStage(STAGE_DEFS[nextIdx].id);
 };

 // ── Suppliers ──
 const addSupplierRow = () => setSuppliers([...suppliers, { ...EMPTY_SUPPLIER }]);
 const removeSupplierRow = (i) => setSuppliers(suppliers.filter((_, idx) => idx !== i));
 const updateSupplierRow = (i, k, v) => setSuppliers(suppliers.map((s, idx) => idx === i ? { ...s, [k]: v } : s));

 const saveSuppliers = async () => {
 const valid = suppliers.filter(s => s.company_name.trim() && s.contact_email.trim());
 if (valid.length === 0) { notify.error('Add at least one supplier with a name and email'); return; }
 setSaving(true);
 try {
 const token = localStorage.getItem('token');
 for (const s of valid) {
 await axios.post(`${API}/suppliers`, {
 name: s.company_name, email: s.contact_email, phone: s.phone,
 contact_person: s.contact_person,
 // Iter 216o-7 — multi-select. Send the array; keep `supplier_type`
 // populated with the first item for any legacy server reads.
 supplier_types: Array.isArray(s.supplier_types) && s.supplier_types.length
   ? s.supplier_types
   : (s.supplier_type ? [s.supplier_type] : []),
 supplier_type: (s.supplier_types && s.supplier_types[0]) || s.supplier_type || '',
 }, { headers: { Authorization: `Bearer ${token}` } });
 }
 notify.success(`Supplier${valid.length > 1 ? 's' : ''} added ✅`);
 await advanceStage('suppliers');
 setSuppliers([{ ...EMPTY_SUPPLIER }]);
 } catch (err) {
 notifyApiError(notify, err, 'Failed to save suppliers');
 } finally { setSaving(false); }
 };

 // ── Equipment ──
 const addEquipRow = () => setEquipmentRows([...equipmentRows, { ...EMPTY_EQUIP }]);
 const removeEquipRow = (i) => setEquipmentRows(equipmentRows.filter((_, idx) => idx !== i));
 const updateEquipRow = (i, k, v) => setEquipmentRows(equipmentRows.map((r, idx) => idx === i ? { ...r, [k]: v } : r));

 const downloadTemplate = async () => {
 try {
 const token = localStorage.getItem('token');
 const res = await axios.get(`${API}/onboarding/equipment-template.csv`, {
 headers: { Authorization: `Bearer ${token}` }, responseType: 'blob',
 });
 const url = window.URL.createObjectURL(new Blob([res.data]));
 const a = document.createElement('a');
 a.href = url; a.download = 'gymaxis-equipment-template.csv';
 a.click(); window.URL.revokeObjectURL(url);
 notify.success('Template downloaded');
 } catch { notify.error('Template download failed'); }
 };

 const handleCsvUpload = async () => {
 if (!csvFile) return;
 setCsvImporting(true);
 try {
 const text = await csvFile.text();
 const token = localStorage.getItem('token');
 const res = await axios.post(`${API}/onboarding/equipment-csv-import`, { csv_content: text }, {
 headers: { Authorization: `Bearer ${token}` },
 });
 notify.success(`${res.data.imported} machine${res.data.imported === 1 ? '' : 's'} imported 🚀`, { duration: 5000 });
 setCsvFile(null);
 await advanceStage('equipment');
 } catch { notify.error('CSV import failed — please check the file format'); }
 finally { setCsvImporting(false); }
 };

 const saveEquipmentManual = async () => {
 const valid = equipmentRows.filter(r => r.name.trim() || r.serial_number.trim());
 if (valid.length === 0) { notify.error('Add at least one machine'); return; }
 setSaving(true);
 try {
 const token = localStorage.getItem('token');
 for (const r of valid) {
 await axios.post(`${API}/equipment`, {
 name: r.name || r.serial_number, equipment_type: r.equipment_type,
 manufacturer: r.manufacturer, model: r.model,
 serial_number: r.serial_number, location: r.location,
 }, { headers: { Authorization: `Bearer ${token}` } });
 }
 notify.success(`${valid.length} machine${valid.length === 1 ? '' : 's'} onboarded 🚀`);
 try { window.dispatchEvent(new CustomEvent('gymaxis:equipment-added', { detail: { count: valid.length } })); } catch (_) {}
 await advanceStage('equipment');
 setEquipmentRows([{ ...EMPTY_EQUIP }]);
 } catch (err) {
 notifyApiError(notify, err, 'Failed to save equipment');
 } finally { setSaving(false); }
 };

 // ── Staff ──
 const addStaffRow = () => setStaffInvites([...staffInvites, { ...EMPTY_STAFF }]);
 const removeStaffRow = (i) => setStaffInvites(staffInvites.filter((_, idx) => idx !== i));
 const updateStaffRow = (i, k, v) => setStaffInvites(staffInvites.map((s, idx) => idx === i ? { ...s, [k]: v } : s));

 const saveStaff = async () => {
 const valid = staffInvites.filter(s => s.email.trim());
 if (valid.length === 0) { notify.error('Add at least one teammate with an email'); return; }
 setSaving(true);
 try {
 const token = localStorage.getItem('token');
 for (const s of valid) {
 await axios.post(`${API}/organization/invite`, {
 email: s.email, full_name: s.full_name, role: s.role,
 }, { headers: { Authorization: `Bearer ${token}` } });
 }
 notify.success(`${valid.length} invite${valid.length === 1 ? '' : 's'} sent ✉️`);
 await advanceStage('staff');
 setStaffInvites([{ ...EMPTY_STAFF }]);
 } catch (err) {
 notifyApiError(notify, err, 'Failed to send invites');
 } finally { setSaving(false); }
 };

 const skipStage = (stageId) => {
 const nextIdx = STAGE_DEFS.findIndex(s => s.id === stageId) + 1;
 if (nextIdx < STAGE_DEFS.length) setCurrentStage(STAGE_DEFS[nextIdx].id);
 notify.info(`Skipped for now — you can complete "${STAGE_DEFS[nextIdx - 1].short}" from Settings anytime`);
 };

 const finishOnboarding = async () => {
 try {
 const token = localStorage.getItem('token');
 await axios.post(`${API}/onboarding/complete`, {}, { headers: { Authorization: `Bearer ${token}` } });
 onComplete?.();
 onClose?.();
 } catch { onClose?.(); }
 };

 const gymName = user?.organization_name || user?.gym_name || 'your gym';
 const isLastStage = currentStage === 'live';

 return (
 <Dialog open={open} onOpenChange={(v) => { if (!v) onClose?.(); }}>
 <DialogContent
 className="max-w-4xl max-h-[92vh] overflow-y-auto bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] p-0"
 data-testid="gamified-onboarding-dialog"
 >
 <VisuallyHidden>
 <DialogTitle>GymAxis Service Onboarding Wizard</DialogTitle>
 <DialogDescription>Four-stage guided setup: Suppliers, Equipment, Team, and Go-Live.</DialogDescription>
 </VisuallyHidden>
 {/* Hero header */}
 <div className="relative px-8 pt-8 pb-6 border-b border-[var(--theme-border)] bg-gradient-to-br from-[rgb(var(--rgb-brand-blue)/0.1)] via-transparent to-[var(--color-accent-violet)]/10">
 <button
 type="button"
 onClick={() => onClose?.()}
 className="absolute top-4 right-4 text-white/40 hover:text-white transition-colors"
 data-testid="onboarding-close-btn"
 aria-label="Close"
 >
 <X size={18} />
 </button>
 <div className="flex items-start gap-3 mb-4">
 <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.2)] flex items-center justify-center flex-shrink-0">
 <Sparkles size={20} className="text-[var(--color-brand-blue)]" />
 </div>
 <div className="flex-1">
 <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">
 Welcome to GymAxis Service, {gymName} <span className="inline-block animate-waving-hand">👋</span>
 </h2>
 <p className="text-[var(--color-text-muted)] text-sm mt-1">
 Let&apos;s get your gym fully set up in just a few quick steps — takes about 5 minutes.
 </p>
 </div>
 </div>

 {/* Progress bar */}
 <div className="mt-2">
 <div className="flex items-center justify-between mb-2 text-xs text-[var(--color-text-muted)]">
 <span>Your setup progress</span>
 <span className="font-medium text-white">{percent}% complete · {completedCount} of {STAGE_DEFS.length} stages</span>
 </div>
 <div className="h-2 rounded-full bg-white/5 overflow-hidden dark:bg-zinc-900">
 <div
 className="h-full rounded-full bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-accent-violet)] transition-all duration-700 ease-out"
 style={{ width: `${percent}%` }}
 data-testid="onboarding-progress-bar"
 />
 </div>
 </div>

 {/* Stage pills */}
 <div className="flex items-center gap-2 mt-5 overflow-x-auto pb-1 -mx-1 px-1">
 {STAGE_DEFS.map((s, idx) => {
 const done = stages[s.id];
 const active = currentStage === s.id;
 const StageIcon = s.icon;
 return (
 <button
 key={s.id}
 type="button"
 onClick={() => setCurrentStage(s.id)}
 className={`flex-shrink-0 flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
 active ? 'bg-[var(--color-brand-blue)] text-white shadow-lg shadow-[rgb(var(--rgb-brand-blue)/0.3)]'
 : done ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
 : 'bg-white/5 text-[var(--color-text-muted)] border border-[var(--theme-border)] hover:text-white'
 }`}
 data-testid={`stage-pill-${s.id}`}
 >
 {done ? <CheckCircle2 size={13} /> : <StageIcon size={13} />}
 <span>{idx + 1}. {s.short}</span>
 </button>
 );
 })}
 </div>
 </div>

 {/* Body */}
 <div className="p-8">
 {loading && <div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-[var(--color-brand-blue)]" /></div>}

 {!loading && currentStage === 'suppliers' && (
 <StageSuppliers
 suppliers={suppliers}
 addRow={addSupplierRow} removeRow={removeSupplierRow} updateRow={updateSupplierRow}
 onSave={saveSuppliers} onSkip={() => skipStage('suppliers')} saving={saving}
 alreadyDone={stages.suppliers}
 />
 )}

 {!loading && currentStage === 'equipment' && (
 <StageEquipment
 mode={equipmentMode} setMode={setEquipmentMode}
 rows={equipmentRows} addRow={addEquipRow} removeRow={removeEquipRow} updateRow={updateEquipRow}
 onSaveManual={saveEquipmentManual}
 onDownloadTemplate={downloadTemplate}
 csvFile={csvFile} setCsvFile={setCsvFile} csvImporting={csvImporting} onCsvUpload={handleCsvUpload}
 onSkip={() => skipStage('equipment')} saving={saving}
 alreadyDone={stages.equipment}
 />
 )}

 {!loading && currentStage === 'staff' && (
 <StageStaff
 invites={staffInvites}
 addRow={addStaffRow} removeRow={removeStaffRow} updateRow={updateStaffRow}
 onSave={saveStaff} onSkip={() => skipStage('staff')} saving={saving}
 alreadyDone={stages.staff}
 />
 )}

 {!loading && currentStage === 'live' && (
 <StageLive status={status} onFinish={finishOnboarding} onLogFault={() => { onComplete?.('log_fault'); onClose?.(); }} />
 )}

 {!loading && !isLastStage && stages.suppliers && stages.equipment && stages.staff && (
 <div className="mt-6 pt-6 border-t border-[var(--theme-border)] flex items-center justify-between">
 <p className="text-sm text-emerald-300">All stages complete! Ready to go live 🎉</p>
 <Button onClick={() => setCurrentStage('live')} className="bg-[var(--color-brand-blue)] text-white" data-testid="jump-to-live-btn">
 Go Live <ArrowRight size={16} className="ml-1" />
 </Button>
 </div>
 )}
 </div>
 </DialogContent>
 </Dialog>
 );
};

export default GamifiedOnboarding;
