import React, { useState, useRef } from 'react';
import axios from 'axios';
import { uploadInvoiceSmart } from '@/lib/uploadInvoice';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Upload, Check, Download, ChevronLeft, ChevronRight, Loader2, Trash2, AlertTriangle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import InvoiceParseProgress from '@/components/shared/InvoiceParseProgress';
import SupplierMultiPicker from '@/components/shared/SupplierMultiPicker';

const API = process.env.REACT_APP_BACKEND_URL;
// Iter 216o — five fixed equipment categories matching the AI extractor.
// Operators can re-assign per-row in the review table; the original
// nine-bucket list (Treadmill / Cycle / Cross-Trainer / Rower / etc.)
// stays as the legacy `equipment_type` field below.
const CATEGORIES = ['Cardiovascular', 'Strength', 'Free Weights', 'Functional', 'Accessories'];
const _LEGACY_TYPES = ['Treadmill', 'Cycle', 'Cross-Trainer', 'Rower', 'Stepper', 'Strength', 'Functional', 'Multi-Station', 'Other'];

export default function InvoiceImportWizard({ onComplete, _onClose }) {
 const { token, activeSite } = useAuth();
 const headers = { Authorization: `Bearer ${token}` };
 const fileRef = useRef(null);

 const [step, setStep] = useState(1);
 const [uploading, setUploading] = useState(false);
 const [importId, setImportId] = useState(null);
 const [importData, setImportData] = useState(null);
 const [confirming, setConfirming] = useState(false);
 const [downloading, setDownloading] = useState(false);
 const [confirmed, setConfirmed] = useState(false);
 const [dragOver, setDragOver] = useState(false);
 // Iter 216o — phased AI parse progress (matches HeadOffice wizard).
 const [parseProgress, setParseProgress] = useState(null);

 // Step 1: Upload invoice
 const processFile = async (file) => {
 if (!file) return;
 if (!file.name.toLowerCase().endsWith('.pdf')) {
 notify.error('Please upload a PDF invoice');
 return;
 }
 setUploading(true);
 setParseProgress({ phase: 'upload', pct: 0 });
 // Cheap local PDF page count for honest "Reading page X of Y" copy.
 let pageCount = 20;
 try {
   const peek = await file.slice(0, Math.min(file.size, 200 * 1024)).text();
   const m = peek.match(/\/Type\s*\/Page[^s]/g);
   if (m && m.length) pageCount = m.length;
 } catch { /* best effort */ }
 try {
 const res = { data: await uploadInvoiceSmart(file, {
   API: `${API}/api`,
   headers,
   onProgress: (pct) => setParseProgress((p) => ({ phase: pct >= 100 ? 'parse' : (p?.phase === 'parse' ? 'parse' : 'upload'), pct, pageCount: p?.pageCount || pageCount })),
   onStatus: (job) => { if (job?.phase === 'extracting') setParseProgress((p) => ({ phase: 'parse', pct: p?.pct || 85, pageCount: job.page_count || p?.pageCount || pageCount })); },
 }) };
 setImportId(res.data.import_id);
 setImportData(res.data);
 setParseProgress({ phase: 'done', itemCount: res.data.equipment_count || res.data.equipment?.length || 0 });
 setTimeout(() => setParseProgress(null), 2500);
 setStep(2);
 notify.success(`Extracted ${res.data.equipment_count} equipment items`);
 } catch (err) {
 const detail = err?.response?.data?.detail
   || (err?.code === 'ECONNABORTED' ? 'Invoice took too long to parse (>3 min). Try splitting the PDF or a smaller invoice.' : null)
   || 'Failed to process invoice';
 setParseProgress({ phase: 'error', message: detail });
 setTimeout(() => setParseProgress(null), 6000);
 notifyApiError(notify, err, 'Failed to process invoice');
 }
 setUploading(false);
 if (fileRef.current) fileRef.current.value = '';
 };

 const handleFileInput = (e) => processFile(e.target.files?.[0]);
 // Iter 216h33 — file dropzones must guard dragenter too (Safari fires
 // it before dragover; missing preventDefault locks the cursor to
 // "no-drop" and the eventual drop falls back to the document default).
 const handleDragEnter = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
 const handleDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); };
 const handleDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); };
 const handleDrop = (e) => {
 e.preventDefault();
 e.stopPropagation();
 setDragOver(false);
 processFile(e.dataTransfer?.files?.[0]);
 };

 // Step 2: Edit equipment
 const updateEquipment = (index, field, value) => {
 setImportData(prev => {
 const updated = { ...prev };
 updated.equipment = [...updated.equipment];
 updated.equipment[index] = { ...updated.equipment[index], [field]: value };
 return updated;
 });
 };

 const removeEquipment = (index) => {
 setImportData(prev => {
 const updated = { ...prev };
 updated.equipment = updated.equipment.filter((_, i) => i !== index);
 updated.equipment_count = updated.equipment.length;
 return updated;
 });
 };

 // Step 3: Confirm & Import
 const handleConfirm = async () => {
 setConfirming(true);
 try {
 // Save edits first
 await axios.put(`${API}/api/equipment-import/update/${importId}`, {
 equipment: importData.equipment,
 account_ref: importData.account_ref,
 site_name: importData.site_name,
 warranty_code: importData.warranty_code,
 }, { headers });

 // Confirm import — Iter 216h194 — pass active site so imported
 // equipment matches the per-site filter on the Equipment list.
 const res = await axios.post(
   `${API}/api/equipment-import/confirm/${importId}`,
   activeSite?.id ? { site_id: activeSite.id } : {},
   { headers },
 );
 notify.success(res.data.message);
 setConfirmed(true);
 } catch (err) {
 notifyApiError(notify, err, 'Import failed');
 }
 setConfirming(false);
 };

 const handleDownload = async () => {
 setDownloading(true);
 try {
 const res = await axios.get(`${API}/api/equipment-import/download/${importId}`, {
 headers,
 responseType: 'blob',
 });
 const url = window.URL.createObjectURL(new Blob([res.data]));
 const link = document.createElement('a');
 link.href = url;
 link.setAttribute('download', `Sicon_Import_${importData.site_name?.replace(/\s/g, '_')}_${importData.invoice_number}.csv`);
 document.body.appendChild(link);
 link.click();
 link.remove();
 window.URL.revokeObjectURL(url);
 notify.success('Sicon import file downloaded');
 } catch (err) {
 notify.error('Download failed');
 }
 setDownloading(false);
 };

 return (
 <div data-testid="invoice-import-wizard">
 {/* Progress bar */}
 <div className="flex items-center gap-2 mb-8">
 {[
 { num: 1, label: 'Upload Invoice' },
 { num: 2, label: 'Review & Edit' },
 { num: 3, label: 'Confirm Import' },
 ].map((s, i) => (
 <React.Fragment key={s.num}>
 <div className={`flex items-center gap-2 ${step >= s.num ? 'text-[var(--color-brand-blue)]' : 'text-zinc-400'}`}>
 <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors ${
 step > s.num ? 'bg-[var(--color-brand-blue)] border-[var(--color-brand-blue)] text-white' :
 step === s.num ? 'border-[var(--color-brand-blue)] text-[var(--color-brand-blue)]' :
 'border-zinc-300 text-zinc-400'
 }`}>
 {step > s.num ? <Check size={14} /> : s.num}
 </div>
 <span className="text-sm font-medium hidden sm:inline">{s.label}</span>
 </div>
 {i < 2 && <div className={`flex-1 h-0.5 ${step > s.num ? 'bg-[var(--color-brand-blue)]' : 'bg-zinc-200'}`} />}
 </React.Fragment>
 ))}
 </div>

 {/* Step 1: Upload */}
 {step === 1 && (
 <div className="text-center" data-testid="import-step-upload">
 <Sparkles size={40} className="mx-auto text-[var(--color-brand-blue)] mb-4" />
 <h2 className="text-2xl font-semibold tracking-tight mb-2" style={{ fontFamily: 'Outfit' }}>AI Equipment Import</h2>
 <p className="text-zinc-500 text-sm mb-8 max-w-md mx-auto">
 Upload a supplier invoice (PDF) and our AI will extract all equipment details — make, model, serial numbers, warranty, and pricing — ready for Sicon import.
 </p>

 <Card
 className={`max-w-lg mx-auto p-8 border-2 border-dashed transition-colors cursor-pointer ${dragOver ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)]' : 'border-[var(--theme-border)] hover:border-[rgb(var(--rgb-brand-blue)/0.6)]'}`}
 style={{ background: 'var(--theme-surface)' }}
 onClick={() => fileRef.current?.click()}
 onDragEnter={handleDragEnter}
 onDragOver={handleDragOver}
 onDragLeave={handleDragLeave}
 onDrop={handleDrop}
 >
 <input type="file" accept=".pdf" onChange={handleFileInput} ref={fileRef} className="hidden" data-testid="import-file-input" />
 {uploading ? (
 <div className="flex flex-col items-center gap-3">
 <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)]" />
 <p className="text-sm font-medium" style={{ color: 'var(--theme-text)' }}>AI is extracting equipment data...</p>
 <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>This may take up to 30 seconds</p>
 </div>
 ) : (
 <div className="flex flex-col items-center gap-3">
 <div className="w-16 h-16 rounded-full bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center">
 <Upload size={24} className="text-[var(--color-brand-blue)]" />
 </div>
 <p className="text-sm" style={{ color: 'var(--theme-text)' }}>Drop your invoice PDF here or click to browse</p>
 <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Supports Pulse Fitness and other supplier invoices</p>
 {/* Iter 216o-7 — explicit "Choose file" button so the upload
     affordance isn't hidden behind a dashed-border dropzone (which
     can be hard to see in dark mode). */}
 <Button
   type="button"
   size="sm"
   className="mt-2 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
   onClick={(e) => { e.stopPropagation(); fileRef.current?.click(); }}
   data-testid="import-file-pick-btn"
 >
   <Upload size={14} className="mr-1.5" /> Choose invoice PDF
 </Button>
 </div>
 )}
 </Card>
 </div>
 )}

 {/* Iter 216o — phased AI parse progress (matches HeadOffice) */}
 {parseProgress ? <div className="max-w-lg mx-auto mt-3"><InvoiceParseProgress state={parseProgress} /></div> : null}

 {/* Step 2: Review */}
 {step === 2 && importData && (
 <div data-testid="import-step-review">
 <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
 <div>
 <h2 className="text-xl font-semibold tracking-tight" style={{ fontFamily: 'Outfit' }}>Review Extracted Data</h2>
 <p className="text-zinc-500 text-sm mt-1">Verify and edit before importing</p>
 </div>
 <div className="flex gap-2">
 <Button variant="outline" size="sm" onClick={() => setStep(1)}>
 <ChevronLeft size={14} className="mr-1" /> Back
 </Button>
 <Button size="sm" className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)]" onClick={() => setStep(3)}>
 Continue <ChevronRight size={14} className="ml-1" />
 </Button>
 </div>
 </div>

 {/* Invoice header info */}
 <Card className="p-5 mb-6">
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Account Ref</label>
 <input value={importData.account_ref || ''} onChange={e => setImportData({...importData, account_ref: e.target.value})}
 className="w-full mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" data-testid="import-account-ref" />
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Site / Gym Name</label>
 <input value={importData.site_name || ''} onChange={e => setImportData({...importData, site_name: e.target.value})}
 className="w-full mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" data-testid="import-site-name" />
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Invoice Number</label>
 <input value={importData.invoice_number || ''} onChange={e => setImportData({...importData, invoice_number: e.target.value})}
 className="w-full mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" data-testid="import-invoice-number" />
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Install Date</label>
 <input value={importData.install_date || ''} onChange={e => setImportData({...importData, install_date: e.target.value})}
 className="w-full mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
 </div>
 </div>
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Supplier</label>
 <div className="mt-1">
 <SupplierMultiPicker
 single
 value={importData.supplier_name || ''}
 onChange={(v) => setImportData({ ...importData, supplier_name: v })}
 placeholder="Pick a supplier or add a new one…"
 testid="invoice-import-supplier"
 />
 </div>
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Warranty Code</label>
 <input value={importData.warranty_code || ''} onChange={e => setImportData({...importData, warranty_code: e.target.value})}
 className="w-full mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" data-testid="import-warranty-code" />
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">SLA Level</label>
 <div className="mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md bg-zinc-50 text-zinc-700">
 {importData.sla_name || '—'}
 </div>
 </div>
 <div>
 <label className="text-xs text-zinc-400 uppercase tracking-wider font-medium">Warranty Expiry</label>
 <div className="mt-1 px-3 py-1.5 text-sm border border-zinc-200 rounded-md bg-zinc-50 text-zinc-700">
 {importData.warranty_expiry || '—'}
 </div>
 </div>
 </div>
 </Card>

 {/* Equipment table */}
 <div className="flex items-center justify-between mb-3">
 <h3 className="text-sm font-semibold text-zinc-700">{importData.equipment?.length || 0} Equipment Items</h3>
 </div>

 <div className="border border-zinc-200 rounded-md overflow-x-auto">
 <table className="w-full text-sm text-left min-w-[800px]" data-testid="import-equipment-table">
 <thead>
 <tr className="bg-zinc-50 border-b border-zinc-200">
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium w-8">#</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium">Make</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium min-w-[250px]">Model / Description</th>
 {/* Iter 216o — AI-assigned category column (matches HeadOffice). */}
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium">Category</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium">Serial Number</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium">Unit Price</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium">SLA</th>
 <th className="px-3 py-2 text-xs text-zinc-500 uppercase tracking-wider font-medium w-10"></th>
 </tr>
 </thead>
 <tbody>
 {importData.equipment?.map((eq, i) => (
 <tr key={i} className="border-b border-zinc-100 hover:bg-zinc-50/50" data-testid={`import-row-${i}`}>
 <td className="px-3 py-2 text-zinc-400">{i + 1}</td>
 <td className="px-3 py-2">
 <input value={eq.make || ''} onChange={e => updateEquipment(i, 'make', e.target.value)}
 className="w-full px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
 </td>
 <td className="px-3 py-2">
 <input value={eq.model || ''} onChange={e => updateEquipment(i, 'model', e.target.value)}
 className="w-full px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
 </td>
 <td className="px-3 py-2">
 <select
   value={eq.equipment_category || ''}
   onChange={e => updateEquipment(i, 'equipment_category', e.target.value)}
   className="w-full px-2 py-1 text-sm border border-zinc-200 rounded bg-white focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none"
   data-testid={`import-row-${i}-category`}
 >
   <option value="">—</option>
   {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
 </select>
 </td>
 <td className="px-3 py-2">
 <input value={eq.serial_number || ''} onChange={e => updateEquipment(i, 'serial_number', e.target.value)}
 className="w-full px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
 </td>
 <td className="px-3 py-2">
 <input type="number" step="0.01" value={eq.unit_price || ''} onChange={e => updateEquipment(i, 'unit_price', parseFloat(e.target.value) || 0)}
 className="w-24 px-2 py-1 text-sm border border-zinc-200 rounded focus:ring-1 focus:ring-[var(--color-brand-blue)] focus:outline-none" />
 </td>
 <td className="px-3 py-2">
 <span className={`text-xs px-2 py-0.5 rounded font-medium ${
 eq.sla_name === 'Platinum' ? 'bg-purple-100 text-purple-700' :
 eq.sla_name === 'Gold' ? 'bg-amber-100 text-amber-700' :
 eq.sla_name === 'Silver' ? 'bg-zinc-200 text-zinc-700' :
 'bg-zinc-100 text-zinc-500'
 }`}>{eq.sla_name || '—'}</span>
 </td>
 <td className="px-3 py-2">
 <button onClick={() => removeEquipment(i)} className="p-1 text-zinc-400 hover:text-red-500 transition-colors">
 <Trash2 size={14} />
 </button>
 </td>
 </tr>
 ))}
 </tbody>
 </table>
 </div>

 {importData.equipment?.length === 0 && (
 <div className="text-center py-8">
 <AlertTriangle size={24} className="mx-auto text-amber-500 mb-2" />
 <p className="text-sm text-zinc-500">No equipment items. Go back and upload a different invoice.</p>
 </div>
 )}
 </div>
 )}

 {/* Step 3: Confirm */}
 {step === 3 && importData && (
 <div data-testid="import-step-confirm">
 <div className="text-center mb-8">
 <h2 className="text-xl font-semibold tracking-tight" style={{ fontFamily: 'Outfit' }}>
 {confirmed ? 'Import Complete' : 'Confirm Import'}
 </h2>
 <p className="text-zinc-500 text-sm mt-1">
 {confirmed
 ? `${importData.equipment?.length} items imported to ${importData.site_name}`
 : 'Review the summary below and confirm'
 }
 </p>
 </div>

 <Card className="max-w-2xl mx-auto p-6 mb-6">
 <div className="grid grid-cols-2 gap-4 text-sm mb-6">
 <div><span className="text-zinc-400">Site:</span> <span className="font-medium ml-2">{importData.site_name}</span></div>
 <div><span className="text-zinc-400">Account:</span> <span className="font-medium ml-2">{importData.account_ref}</span></div>
 <div><span className="text-zinc-400">Invoice:</span> <span className="font-medium ml-2">{importData.invoice_number}</span></div>
 <div><span className="text-zinc-400">Supplier:</span> <span className="font-medium ml-2">{importData.supplier_name}</span></div>
 <div><span className="text-zinc-400">Install Date:</span> <span className="font-medium ml-2">{importData.install_date}</span></div>
 <div><span className="text-zinc-400">Warranty:</span> <span className="font-medium ml-2">{importData.sla_name} — {importData.warranty_expiry}</span></div>
 </div>

 <div className="border-t border-zinc-200 pt-4">
 <div className="flex items-center justify-between mb-3">
 <span className="text-sm text-zinc-600 font-medium">{importData.equipment?.length} equipment items</span>
 <span className="text-sm text-zinc-400">
 Total: £{importData.equipment?.reduce((s, e) => s + (e.unit_price || 0), 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
 </span>
 </div>
 <div className="max-h-48 overflow-y-auto space-y-1">
 {importData.equipment?.map((eq, i) => (
 <div key={i} className="flex items-center justify-between text-xs px-3 py-1.5 bg-zinc-50 rounded">
 <span className="truncate flex-1">{eq.make} — {eq.model}</span>
 <span className="text-zinc-400 ml-2 shrink-0">{eq.serial_number || 'No S/N'}</span>
 </div>
 ))}
 </div>
 </div>
 </Card>

 <div className="flex justify-center gap-3">
 {!confirmed && (
 <>
 <Button variant="outline" onClick={() => setStep(2)}>
 <ChevronLeft size={14} className="mr-1" /> Edit
 </Button>
 <Button onClick={handleConfirm} disabled={confirming} className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)]" data-testid="import-confirm-btn">
 {confirming ? <Loader2 size={16} className="animate-spin mr-1" /> : <Check size={16} className="mr-1" />}
 {confirming ? 'Importing...' : 'Confirm & Import'}
 </Button>
 </>
 )}
 <Button variant="outline" onClick={handleDownload} disabled={downloading} data-testid="import-download-btn">
 {downloading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Download size={14} className="mr-1" />}
 Download Sicon CSV
 </Button>
 {confirmed && onComplete && (
 <Button onClick={onComplete} className="bg-green-600 hover:bg-green-700">
 Done
 </Button>
 )}
 </div>
 </div>
 )}
 </div>
 );
}
