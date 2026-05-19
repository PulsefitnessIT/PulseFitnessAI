import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import axios from 'axios';
import { useInlineBanner, useConfirm, notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { EquipmentDetailContent } from './LiteDashboard/LiteDialogs';
import { Search, Download, FileText, Wrench, CheckCircle, Clock, Edit, QrCode, Filter, Loader2, AlertTriangle, X, Image, ExternalLink, Sparkles } from 'lucide-react';
import AuditDetailPanel from './AuditDetailPanel';
import { EquipmentCardSkeleton } from '@/components/shared/Skeleton';
import ManufacturerCombobox from '@/components/equipment/ManufacturerCombobox';
import EquipmentPlaceholder from '@/components/equipment/EquipmentPlaceholder';
import EquipmentCoveragePanel from '@/components/equipment/EquipmentCoveragePanel';
import DatePicker from '@/components/shared/DatePicker';
import { SLA_RESPONSE_TIME_OPTIONS, EQUIPMENT_LOCATION_PRESETS } from '@/utils/operationsDropdowns';

const SLA_RESPONSE_OPTIONS = [
  ...SLA_RESPONSE_TIME_OPTIONS.filter((o) => o.value !== 'custom'),
  { value: '__other__', label: 'Other (enter manually)' },
];

const EquipmentInfoTab = ({ expiryFilterIds, onClearExpiryFilter, onOpenInvoiceImport }) => {
 const { API, user } = useAuth();
 const { t } = useTranslation();
 const [equipment, setEquipment] = useState([]);
 const [filteredEquipment, setFilteredEquipment] = useState([]);
 const [searchQuery, setSearchQuery] = useState('');
 const [filterType, setFilterType] = useState('all');
 const [filterLocation, setFilterLocation] = useState('all');
 const [selectedEquipment, setSelectedEquipment] = useState(null);
 const [showDetailsDialog, setShowDetailsDialog] = useState(false);
 const [summary, setSummary] = useState(null);
 const [importing, setImporting] = useState(false);
 // Page-level banner for export / import / audit flows — replaces floating toasts.
 const { banner: equipBanner, show: showEquipBanner } = useInlineBanner();
 const confirm = useConfirm();
 const [showEditDialog, setShowEditDialog] = useState(false);
 const [editForm, setEditForm] = useState({});
 const [qrBlobUrl, setQrBlobUrl] = useState(null);
 const [qrLabelSize, setQrLabelSize] = useState('62x35');
 const [auditForm, setAuditForm] = useState({ usage_frequency: '', last_maintenance: '', notes: '' });
 const [auditLoading, setAuditLoading] = useState(false);
 const [viewAudit, setViewAudit] = useState(null);
 const [photoUploading, setPhotoUploading] = useState(false);
 const [suppliers, setSuppliers] = useState([]);
 const [viewingManual, setViewingManual] = useState(null); // {equipmentId, manual}
 const [manualBlobUrl, setManualBlobUrl] = useState(null);
 const canManagePhotos = user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin;
 const canEditSupplier = user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin;

 useEffect(() => {
 loadData();
 if (canEditSupplier) loadSuppliers();
 }, []);

 // Fetch the selected manual as a blob URL so the iframe viewer is
 // authenticated. Revoke previous URL on change/unmount to avoid leaks.
 useEffect(() => {
 if (!viewingManual) {
 if (manualBlobUrl) {
 URL.revokeObjectURL(manualBlobUrl);
 setManualBlobUrl(null);
 }
 return;
 }
 let revoked = false;
 let createdUrl = null;
 (async () => {
 try {
 const token = localStorage.getItem('token');
 const res = await axios.get(
 `${API}/equipment/${viewingManual.equipmentId}/manual/${viewingManual.manual.id}`,
 { headers: { Authorization: `Bearer ${token}` }, responseType: 'blob' },
 );
 if (revoked) return;
 createdUrl = URL.createObjectURL(res.data);
 setManualBlobUrl(createdUrl);
 } catch (e) {
 notify.error('Failed to load manual', e.response?.data?.detail || 'Try again');
 }
 })();
 return () => {
 revoked = true;
 if (createdUrl) URL.revokeObjectURL(createdUrl);
 };
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [viewingManual]);

 const handleDownloadManual = async (equipmentId, manual) => {
 try {
 const token = localStorage.getItem('token');
 const res = await axios.get(`${API}/equipment/${equipmentId}/manual/${manual.id}`, {
 headers: { Authorization: `Bearer ${token}` }, responseType: 'blob',
 });
 const url = URL.createObjectURL(res.data);
 const a = document.createElement('a');
 a.href = url;
 a.download = manual.original_filename || 'manual.pdf';
 document.body.appendChild(a);
 a.click();
 a.remove();
 setTimeout(() => URL.revokeObjectURL(url), 1000);
 } catch (e) {
 notify.error('Download failed', e.response?.data?.detail || 'Try again');
 }
 };

 const loadSuppliers = async () => {
 const token = localStorage.getItem('token');
 try {
 const r = await axios.get(`${API}/suppliers`, { headers: { Authorization: `Bearer ${token}` } });
 setSuppliers(r.data?.suppliers || r.data || []);
 } catch { /* non-critical */ }
 };

 useEffect(() => {
 let filtered = equipment;
 if (expiryFilterIds && expiryFilterIds.length > 0) {
 filtered = filtered.filter(e => expiryFilterIds.includes(e.id));
 }
 if (searchQuery.trim()) {
 filtered = filtered.filter(e => 
 e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
 e.equipment_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
 e.manufacturer?.toLowerCase().includes(searchQuery.toLowerCase()) ||
 e.serial_number?.toLowerCase().includes(searchQuery.toLowerCase())
 );
 }
 if (filterType !== 'all') {
 filtered = filtered.filter(e => e.equipment_type === filterType);
 }
 if (filterLocation !== 'all') {
 filtered = filtered.filter(e => e.location === filterLocation);
 }
 setFilteredEquipment(filtered);
 }, [searchQuery, equipment, filterType, filterLocation, expiryFilterIds]);

 const equipmentTypes = [...new Set(equipment.map(e => e.equipment_type).filter(Boolean))];
 const equipmentLocations = [...new Set(equipment.map(e => e.location).filter(Boolean))];

 const loadData = async () => {
 const token = localStorage.getItem('token');
 try {
 const [equipmentRes, summaryRes] = await Promise.all([
 axios.get(`${API}/equipment`, { headers: { Authorization: `Bearer ${token}` } }),
 axios.get(`${API}/reports/equipment-summary`, { headers: { Authorization: `Bearer ${token}` } })
 ]);
 
 setEquipment(equipmentRes.data.equipment || []);
 setFilteredEquipment(equipmentRes.data.equipment || []);
 setSummary(summaryRes.data);
 } catch (error) {
 console.error('Failed to load equipment:', error);
 }
 };

 const handleViewDetails = async (equip) => {
 const token = localStorage.getItem('token');
 try {
 const response = await axios.get(`${API}/equipment/${equip.id}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setSelectedEquipment(response.data);
 setShowDetailsDialog(true);
 // Load branded QR card as blob (img src can't pass auth headers)
 try {
 const qrRes = await axios.get(`${API}/equipment/${equip.id}/qr-card?size=${qrLabelSize}`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'arraybuffer'
 });
 const blob = new Blob([qrRes.data], { type: 'image/png' });
 if (qrBlobUrl) URL.revokeObjectURL(qrBlobUrl);
 setQrBlobUrl(URL.createObjectURL(blob));
 } catch { setQrBlobUrl(null); }
 } catch (error) {
 notify.error('Failed to load equipment details');
 }
 };

 const handleUploadManual = async (equipmentId, file) => {
 const token = localStorage.getItem('token');
 const formData = new FormData();
 formData.append('file', file);

 try {
 await axios.post(`${API}/equipment/${equipmentId}/manual`, formData, {
 headers: { 
 Authorization: `Bearer ${token}`,
 'Content-Type': 'multipart/form-data'
 }
 });
 notify.success('Manual uploaded successfully');
 loadData();
 } catch (error) {
 notify.error('Failed to upload manual');
 }
 };

 const getSeverityColor = (count) => {
 if (count === 0) return 'bg-green-500/20 text-green-400';
 if (count < 3) return 'bg-yellow-500/20 text-yellow-400';
 return 'bg-red-500/20 text-red-400';
 };

 const handleDownloadTemplate = async () => {
 const token = localStorage.getItem('token');
 try {
 const response = await axios.get(`${API}/equipment/template/csv`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'blob'
 });
 const url = window.URL.createObjectURL(new Blob([response.data]));
 const link = document.createElement('a');
 link.href = url;
 link.setAttribute('download', 'equipment_template.csv');
 document.body.appendChild(link);
 link.click();
 link.remove();
 } catch (error) {
 notify.error('Failed to download template');
 }
 };

 const handleExportCSV = async () => {
 const token = localStorage.getItem('token');
 try {
 const response = await axios.get(`${API}/equipment/export/csv`, {
 headers: { Authorization: `Bearer ${token}` },
 responseType: 'blob'
 });
 const url = window.URL.createObjectURL(new Blob([response.data]));
 const link = document.createElement('a');
 link.href = url;
 link.setAttribute('download', 'equipment_export.csv');
 document.body.appendChild(link);
 link.click();
 link.remove();
 notify.success('Equipment data exported');
 } catch (error) {
 notify.error('Failed to export equipment');
 }
 };

 const handleImportCSV = async (e) => {
 const file = e.target.files[0];
 if (!file) return;
 setImporting(true);
 const token = localStorage.getItem('token');
 const formData = new FormData();
 formData.append('file', file);
 
 try {
 const response = await axios.post(`${API}/equipment/import/csv`, formData, {
 headers: { 
 Authorization: `Bearer ${token}`,
 'Content-Type': 'multipart/form-data'
 }
 });
 const { imported, errors } = response.data;
 notify.success(`Imported ${imported} equipment items`);
 if (errors.length > 0) {
 notify.error(`${errors.length} rows had errors`);
 }
 loadData();
 try { if (imported > 0) window.dispatchEvent(new CustomEvent('gymaxis:equipment-added', { detail: { count: imported } })); } catch (_) {}
 } catch (error) {
 notify.error('Failed to import CSV');
 } finally {
 setImporting(false);
 e.target.value = '';
 }
 };

 const openEditForm = (equip) => {
 setEditForm({
 name: equip.name || '',
 equipment_type: equip.equipment_type || '',
 manufacturer: equip.manufacturer || '',
 model: equip.model || '',
 serial_number: equip.serial_number || '',
 purchase_date: equip.purchase_date || '',
 warranty_expiry: equip.warranty_expiry || '',
 location: equip.location || '',
 sla_response_time: equip.sla_response_time || '',
 sla_contract_ref: equip.sla_contract_ref || '',
 sla_expiry: equip.sla_expiry || '',
 notes: equip.notes || '',
 supplier: equip.supplier || '',
 });
 setShowEditDialog(true);
 };

 const [notifySupplier, setNotifySupplier] = useState(false);

 const handleSaveEdit = async () => {
 const token = localStorage.getItem('token');
 const supplierChanged = (editForm.supplier || '') !== (selectedEquipment?.supplier || '');
 const payload = { ...editForm };
 if (canEditSupplier && supplierChanged && editForm.supplier && notifySupplier) {
 payload.notify_supplier = true;
 }
 try {
 const r = await axios.patch(`${API}/equipment/${selectedEquipment.id}`, payload, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success( // kept as micro — detail below surfaces in the banner
 r.data?.notified_supplier
 ? `Equipment updated — ${editForm.supplier} has been notified`
 : 'Equipment updated',
 );
 showEquipBanner({
 tone: 'success',
 title: 'Equipment updated',
 detail: r.data?.notified_supplier
 ? `Changes saved. ${editForm.supplier} has been notified by email.`
 : 'Changes saved. You can keep editing or close the dialog.',
 });
 setShowEditDialog(false);
 setNotifySupplier(false);
 loadData();
 setSelectedEquipment({...selectedEquipment, ...editForm});
 } catch {
 showEquipBanner({
 tone: 'error',
 title: 'Couldn\'t save changes',
 detail: 'Please check required fields and try again. If the issue persists, refresh the page.',
 });
 }
 };

 const handleGenerateAudit = async (e) => {
 e.preventDefault();
 if (!selectedEquipment) return;
 setAuditLoading(true);
 const token = localStorage.getItem('token');
 try {
 const payload = {
 equipment_id: selectedEquipment.id,
 equipment_type: selectedEquipment.equipment_type,
 usage_frequency: auditForm.usage_frequency,
 last_maintenance: auditForm.last_maintenance,
 notes: auditForm.notes
 };
 const res = await axios.post(`${API}/audit/generate`, payload, {
 headers: { Authorization: `Bearer ${token}` }
 });
 notify.success('Audit report generated successfully!');
 setAuditForm({ usage_frequency: '', last_maintenance: '', notes: '' });
 // Refresh equipment details to get updated audit list
 const updatedRes = await axios.get(`${API}/equipment/${selectedEquipment.id}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setSelectedEquipment(updatedRes.data);
 loadData();
 } catch {
 notify.error('Failed to generate audit report');
 } finally {
 setAuditLoading(false);
 }
 };

 const handlePhotoUpload = async (e) => {
 const file = e.target.files[0];
 if (!file) return;
 if (!file.type.startsWith('image/')) { notify.error('Only image files allowed'); return; }
 if (file.size > 20 * 1024 * 1024) { notify.error('Max 20MB file size'); return; }
 setPhotoUploading(true);
 const token = localStorage.getItem('token');
 try {
 // Client-side compression — keeps equipment photos under ~1 MB each
 // and slashes upload time on 4G. Skips HEIC/HEIF (can't be decoded
 // via Image() in most browsers); backend handles those as-is.
 const shouldCompress = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type);
 let uploadFile = file;
 if (shouldCompress) {
 uploadFile = await new Promise((resolve, reject) => {
 const reader = new FileReader();
 reader.onload = () => {
 const img = new Image();
 img.onload = () => {
 const MAX = 1920;
 const scale = Math.min(1, MAX / Math.max(img.width, img.height));
 const w = Math.round(img.width * scale);
 const h = Math.round(img.height * scale);
 const canvas = document.createElement('canvas');
 canvas.width = w; canvas.height = h;
 const ctx = canvas.getContext('2d');
 ctx.imageSmoothingEnabled = true;
 ctx.imageSmoothingQuality = 'high';
 ctx.drawImage(img, 0, 0, w, h);
 canvas.toBlob((blob) => {
 if (!blob) return resolve(file);
 const name = (file.name || 'equipment').replace(/\.[^.]+$/, '') + '.jpg';
 resolve(new File([blob], name, { type: 'image/jpeg' }));
 }, 'image/jpeg', 0.82);
 };
 img.onerror = reject;
 img.src = reader.result;
 };
 reader.onerror = reject;
 reader.readAsDataURL(file);
 });
 }
 const formData = new FormData();
 formData.append('file', uploadFile);
 const res = await axios.post(`${API}/equipment/${selectedEquipment.id}/photos`, formData, {
 headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
 });
 setSelectedEquipment(prev => ({
 ...prev,
 photos: [...(prev.photos || []), res.data.photo],
 }));
 notify.success('Photo uploaded');
 } catch (err) {
 notifyApiError(notify, err, 'Upload failed');
 }
 setPhotoUploading(false);
 e.target.value = '';
 };

 const handleDeletePhoto = async (photoId) => {
 const ok = await confirm({
 title: 'Delete this photo?',
 detail: 'The photo will be permanently removed from this equipment record.',
 tone: 'danger',
 confirmLabel: 'Delete photo',
 });
 if (!ok) return;
 const token = localStorage.getItem('token');
 try {
 await axios.delete(`${API}/equipment/${selectedEquipment.id}/photos/${photoId}`, {
 headers: { Authorization: `Bearer ${token}` },
 });
 setSelectedEquipment(prev => ({
 ...prev,
 photos: (prev.photos || []).filter(p => p.id !== photoId),
 }));
 showEquipBanner({ tone: 'success', title: 'Photo deleted' });
 } catch {
 showEquipBanner({ tone: 'error', title: 'Delete failed', detail: 'Please check your connection and try again.' });
 }
 };


 return (
 <div className="space-y-6" data-testid="equipment-info-tab">
 {equipBanner && <div>{equipBanner}</div>}
 <div className="flex items-center justify-between flex-wrap gap-4">
 <div>
 <h2 className="text-2xl font-semibold text-white">Equipment Information Hub</h2>
 <p className="text-[var(--color-text-muted)]">Comprehensive view of all machines, manuals, and maintenance history</p>
 </div>
 <div className="flex items-center gap-2">
 {/* Iter 216n — AI Invoice Import lives in the page header now,
     replacing the standalone row above the equipment list that
     looked tacked-on. */}
 {onOpenInvoiceImport ? (
   <Button
     size="sm"
     onClick={onOpenInvoiceImport}
     className="bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)]"
     data-testid="ai-import-btn"
   >
     <Sparkles size={14} className="mr-1.5" /> AI Invoice Import
   </Button>
 ) : null}
 <Button
 size="sm"
 variant="outline"
 onClick={handleExportCSV}
 className="border-white/10 text-white hover:bg-white/10"
 data-testid="export-csv-btn"
 >
 <Download size={16} className="mr-1" /> Export CSV
 </Button>
 <Button
 size="sm"
 variant="outline"
 onClick={async () => {
 const token = localStorage.getItem('token');
 for (const eq of equipment) {
 try {
 const res = await axios.get(`${API}/equipment/${eq.id}/qr-card?size=62x35`, {
 headers: { Authorization: `Bearer ${token}` }, responseType: 'arraybuffer'
 });
 const blob = new Blob([res.data], { type: 'image/png' });
 const url = URL.createObjectURL(blob);
 const link = document.createElement('a');
 link.href = url;
 link.download = `gymaxis-qr-${eq.serial_number || eq.id}.png`;
 document.body.appendChild(link); link.click(); link.remove();
 URL.revokeObjectURL(url);
 await new Promise(r => setTimeout(r, 300));
 } catch { /* skip */ }
 }
 notify.success(`Downloading ${equipment.length} GymAxis QR labels`);
 }}
 className="border-white/10 text-white hover:bg-white/10"
 data-testid="bulk-download-qr-btn"
 >
 <QrCode size={16} className="mr-1" /> All QR Codes
 </Button>
 </div>
 </div>

 {/* Expiry Filter Banner */}
 {expiryFilterIds && expiryFilterIds.length > 0 && (
 <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between" data-testid="expiry-filter-banner">
 <div className="flex items-center gap-2">
 <AlertTriangle size={16} className="text-amber-400" />
 <span className="text-amber-400 text-sm font-medium">
 Showing {filteredEquipment.length} machine{filteredEquipment.length !== 1 ? 's' : ''} with expiring warranty/contract
 </span>
 </div>
 <Button size="sm" variant="ghost" className="text-amber-400 hover:bg-amber-500/10 h-7 px-2" onClick={onClearExpiryFilter} data-testid="clear-expiry-filter-btn">
 <X size={14} className="mr-1" /> Clear Filter
 </Button>
 </div>
 )}

 {/* Summary Stats */}
 {summary && (
 <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="stat-total-equipment">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-text-muted)] text-sm">Total Equipment</p>
 <p className="text-3xl font-bold text-white mt-2">{summary.total_equipment}</p>
 </div>
 <Wrench className="text-[var(--color-brand-blue)]" size={32} />
 </div>
 </Card>

 <Card className="bg-[var(--theme-surface)] border-white/10 p-6" data-testid="stat-warranty-expiring">
 <div className="flex items-center justify-between">
 <div>
 <p className="text-[var(--color-text-muted)] text-sm">Warranty Expiring</p>
 <p className="text-3xl font-bold text-white mt-2">{summary.warranty_expiring_soon}</p>
 </div>
 <Clock className="text-[var(--color-brand-blue)]" size={32} />
 </div>
 </Card>
 </div>
 )}

 {/* Search & Filters */}
 <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
 <div className="flex-1 relative">
 <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-[var(--color-text-muted)]" size={20} />
 <Input
 value={searchQuery}
 onChange={(e) => setSearchQuery(e.target.value)}
 placeholder="Search equipment by name, type, serial, or manufacturer..."
 className="bg-[var(--theme-surface)] border-white/10 text-white pl-10"
 data-testid="equipment-search-input"
 />
 </div>
 <Select value={filterType} onValueChange={setFilterType}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-white/10 text-white w-full sm:w-48" data-testid="equipment-filter-type">
 <Filter size={14} className="mr-1 text-[var(--color-text-muted)]" /><SelectValue placeholder="Machine Type" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 <SelectItem value="all" className="text-white">All Types</SelectItem>
 {equipmentTypes.map(t => <SelectItem key={t} value={t} className="text-white">{t}</SelectItem>)}
 </SelectContent>
 </Select>
 {equipmentLocations.length > 0 && (
 <Select value={filterLocation} onValueChange={setFilterLocation}>
 <SelectTrigger className="bg-[var(--theme-surface)] border-white/10 text-white w-full sm:w-48" data-testid="equipment-filter-location">
 <SelectValue placeholder="Location" />
 </SelectTrigger>
 <SelectContent className="bg-[var(--theme-surface)] border-white/10">
 <SelectItem value="all" className="text-white">All Locations</SelectItem>
 {equipmentLocations.map(l => <SelectItem key={l} value={l} className="text-white">{l}</SelectItem>)}
 </SelectContent>
 </Select>
 )}
 </div>

 {/* Equipment List */}
 <div className="space-y-2">
 {equipment.length === 0 && filteredEquipment.length === 0 ? (
 <>
 <EquipmentCardSkeleton />
 <EquipmentCardSkeleton />
 </>
 ) : filteredEquipment.map(equip => {
 const hasOpenFault = (equip.stats?.open_faults || 0) > 0;
 const eqBorderColor = hasOpenFault ? 'var(--color-danger)' : 'var(--color-success-alt-2)';
 // Iter 216o-7 — compact row layout matching Pulse Lite. Same data
 // density, ~70% smaller vertical footprint so a 50-machine site is
 // a 2-screen scroll instead of a 10-screen scroll.
 // Iter 216e — `spec_sheet_image` is populated by the master-admin
 // catalogue rematch (manufacturer-catalogue fallback). Sits between
 // the operator-triggered auto-lookup and the PDF spec hero so list
 // thumbnails show real product photos for any equipment whose
 // manufacturer is in the catalogue.
 const thumbUrl = equip.photo_url
   || equip.auto_image_url
   || equip.spec_sheet_image
   || (equip.spec_sheet_id ? `${API}/spec-sheets/image/${equip.spec_sheet_id}` : null);
 const installDate = equip.install_date || equip.installed_at || equip.created_at || null;
 const formattedInstallDate = installDate
   ? new Date(installDate).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
   : null;
 const openIssues = equip.stats?.open_issues || 0;
 const warrantyActive = equip.stats?.warranty_active;
 return (
 <Card
   key={equip.id}
   className="bg-[var(--theme-surface)] p-4 cursor-pointer hover:border-[var(--color-brand-blue)] transition-all duration-200"
   style={{ borderLeft: `4px solid ${eqBorderColor}`, borderColor: eqBorderColor }}
   onClick={() => handleViewDetails(equip)}
   data-testid={`equipment-card-${equip.id}`}
 >
   <div className="flex items-center gap-4">
     {/* Thumbnail */}
     <div className="relative w-12 h-12 rounded-lg overflow-hidden shrink-0">
       <EquipmentPlaceholder
         manufacturer={equip.manufacturer || equip.supplier}
         equipmentType={equip.equipment_type || equip.category}
         testId={`equipment-placeholder-${equip.id}`}
       />
       {thumbUrl && (
         <img
           src={thumbUrl}
           alt=""
           className="absolute inset-0 w-full h-full object-cover bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg"
           onError={(e) => { e.target.style.display = 'none'; }}
         />
       )}
     </div>

     {/* Title block */}
     <div className="flex-1 min-w-0">
       <div className="flex items-center gap-2 flex-wrap">
         <h3 className="text-sm sm:text-base font-semibold text-white truncate type-h1" title={equip.name}>
           {equip.display_name || equip.name}
         </h3>
         <Badge className="bg-[rgb(var(--rgb-brand-blue)/0.15)] text-[var(--color-brand-blue)] text-[10px] px-2 py-0">
           {equip.equipment_type}
         </Badge>
         {warrantyActive && (
           <Badge className="bg-green-500/15 text-green-400 text-[10px] px-2 py-0 border-0">
             <CheckCircle size={10} className="mr-0.5" /> Warranty
           </Badge>
         )}
       </div>
       <p className="text-xs text-[var(--color-text-muted)] truncate mt-0.5">
         {equip.manufacturer || '—'}
         {equip.model ? ` · ${equip.model}` : ''}
         {equip.serial_number ? ` · ${equip.serial_number}` : ''}
       </p>
       <p className="text-[11px] text-[var(--color-text-faint)] truncate mt-0.5 flex items-center gap-2 flex-wrap">
         {equip.location && <span>📍 {equip.location}</span>}
         {formattedInstallDate && (
           <span data-testid={`equipment-install-date-${equip.id}`}>
             🛠 Installed {formattedInstallDate}
           </span>
         )}
         {equip.stats?.manuals_count > 0 && (
           <span>📄 {equip.stats.manuals_count} manual{equip.stats.manuals_count > 1 ? 's' : ''}</span>
         )}
       </p>
     </div>

     {/* Right rail — open issues + actions */}
     <div className="flex items-center gap-2 shrink-0">
       {openIssues > 0 && (
         <Badge className="bg-red-500/15 text-red-400 border-0 text-xs">
           {openIssues} fault{openIssues > 1 ? 's' : ''}
         </Badge>
       )}
       <Button
         size="sm"
         variant="outline"
         onClick={async (e) => {
           e.stopPropagation();
           const token = localStorage.getItem('token');
           try {
             const res = await axios.get(`${API}/equipment/${equip.id}/qr-card?size=62x35`, {
               headers: { Authorization: `Bearer ${token}` }, responseType: 'arraybuffer'
             });
             const blob = new Blob([res.data], { type: 'image/png' });
             const url = URL.createObjectURL(blob);
             const link = document.createElement('a');
             link.href = url;
             link.download = `gymaxis-qr-${equip.serial_number || equip.id}.png`;
             document.body.appendChild(link); link.click(); link.remove();
             URL.revokeObjectURL(url);
           } catch { notify.error('Failed to download QR'); }
         }}
         className="h-8 px-2 border-white/10 text-white hover:bg-white/10"
         data-testid={`download-qr-btn-${equip.id}`}
         title="Download QR card"
       >
         <QrCode size={14} />
       </Button>
       <Button
         size="sm"
         onClick={(e) => { e.stopPropagation(); handleViewDetails(equip); }}
         className="h-8 px-3 text-xs"
         data-testid={`view-details-btn-${equip.id}`}
       >
         Details
       </Button>
     </div>
   </div>
 </Card>
 );
 })}

 {filteredEquipment.length === 0 && (
 <Card className="bg-[var(--theme-surface)] border-white/10 p-12 text-center">
 <Wrench size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">{searchQuery ? 'No equipment found matching your search' : 'No equipment added yet'}</p>
 </Card>
 )}
 </div>

 {/* Equipment Details Dialog */}
 <Dialog open={showDetailsDialog} onOpenChange={setShowDetailsDialog}>
 {/* Iter 216o-10 — modal sized to match Pulse Lite exactly:
     w-[calc(100vw-2rem)] max-w-2xl max-h-[85vh] */}
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-[calc(100vw-2rem)] max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="equipment-details-dialog">
 <DialogHeader>
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0">
 <DialogTitle className="text-[var(--theme-text)] text-2xl truncate">{selectedEquipment?.name}</DialogTitle>
 <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
 {selectedEquipment?.manufacturer || 'Unknown manufacturer'}
 {selectedEquipment?.equipment_type ? ` · ${selectedEquipment.equipment_type}` : ''}
 </p>
 </div>
 <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-brand-blue)] hover:bg-[rgb(var(--rgb-brand-blue)/0.1)] shrink-0" onClick={() => openEditForm(selectedEquipment)} data-testid="edit-equipment-btn">
 <Edit size={14} className="mr-1.5" /> Edit Details
 </Button>
 </div>
 </DialogHeader>

 {selectedEquipment && (
 <div data-testid="equipment-detail-body">
 {/* Iter 216h198 — Phase 2 Coverage Panel: contract status at the
    top of the modal so engineers see warranty/aftersales coverage
    before they pick up tools. */}
 <EquipmentCoveragePanel equipmentId={selectedEquipment.id} />

  {/* Iter 216o-9 — Equipment detail uses ONLY the shared
     EquipmentDetailContent (the same component Pulse Fitness uses).
     This gives us 2 tabs ("Details" + "Spec Sheet") — identical to
     Pulse — instead of the legacy 6-tab GymAxis layout. The deeper
     features (audit generation, manual upload, QR card, photos) are
     accessed via the Edit Details button or the row-level QR button
     so the modal stays clean and platform-agnostic for white-label. */}
  <EquipmentDetailContent
    selectedEquipment={selectedEquipment}
    getEquipmentFaults={(eq) => Array.isArray(eq?.issues) ? eq.issues : []}
    getEquipmentFiles={(eq) => Array.isArray(eq?.manuals) ? eq.manuals : []}
    getSeverityStyle={(s) => {
      const map = {
        critical: 'bg-red-500/15 text-red-400',
        high:     'bg-amber-500/15 text-amber-400',
        medium:   'bg-blue-500/15 text-blue-400',
        low:      'bg-zinc-500/15 text-zinc-400',
      };
      return map[s] || map.low;
    }}
    getSeverityLabel={(s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Low')}
    getStatusColor={(s) => (s === 'resolved' ? 'text-emerald-400' : s === 'in_progress' ? 'text-amber-400' : 'text-red-400')}
    onLogFaultForEquipment={(eq) => {
      try { window.location.href = `/dashboard?tab=issues&equipment=${eq.id}`; } catch { /* noop */ }
    }}
    onDownloadFile={async (file) => {
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API}/equipment/${selectedEquipment.id}/manuals/${file.id}`, {
          headers: { Authorization: `Bearer ${token}` },
          responseType: 'blob',
        });
        const url = URL.createObjectURL(new Blob([res.data]));
        const a = document.createElement('a');
        a.href = url;
        a.download = file.filename || `manual-${file.id}.pdf`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch { notify.error('Download failed'); }
    }}
    brandAccent="var(--color-brand-blue)"
  />
 </div>
 )}
 </DialogContent>
 </Dialog>

 {/* Edit Equipment Dialog */}
 <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
 <DialogContent className="bg-[var(--theme-surface)] border-white/10 text-white max-w-lg max-h-[85vh] overflow-y-auto" data-testid="edit-equipment-dialog">
 <DialogHeader>
 <DialogTitle className="text-white">Edit Equipment</DialogTitle>
 </DialogHeader>
 <div className="space-y-3">
 {[
 { key: 'name', label: 'Name', placeholder: 'Equipment name' },
 { key: 'equipment_type', label: 'Type', placeholder: 'e.g. Treadmill' },
 { key: 'model', label: 'Model', placeholder: 'Model' },
 { key: 'serial_number', label: 'Serial Number', placeholder: 'Serial number' },
 { key: 'location', label: 'Location', placeholder: 'e.g. Cardio Zone', datalist: 'edit-location-presets' },
 { key: 'purchase_date', label: 'Purchase Date', type: 'date' },
 { key: 'warranty_expiry', label: 'Warranty Expiry', type: 'date' },
 { key: 'sla_contract_ref', label: 'SLA Contract Reference', placeholder: 'Contract reference number' },
 { key: 'sla_expiry', label: 'SLA Expiry Date', type: 'date' },
 { key: 'notes', label: 'Notes', placeholder: 'Additional notes' },
 ].map(field => (
 <div key={field.key}>
 <label className="text-[var(--color-text-muted)] text-sm">{field.label}</label>
 {field.type === 'date' ? (
   <DatePicker
     value={editForm[field.key] || ''}
     onChange={(iso) => setEditForm({ ...editForm, [field.key]: iso })}
     placeholder="DD/MM/YYYY"
     inputClassName="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
     testid={`edit-${field.key}`}
   />
 ) : (
   <>
     <Input
       type="text"
       value={editForm[field.key] || ''}
       onChange={e => setEditForm({...editForm, [field.key]: e.target.value})}
       placeholder={field.placeholder}
       list={field.datalist}
       className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
       data-testid={`edit-${field.key}`}
     />
     {field.datalist === 'edit-location-presets' && (
       <datalist id="edit-location-presets">
         {EQUIPMENT_LOCATION_PRESETS.map((loc) => <option key={loc} value={loc} />)}
       </datalist>
     )}
   </>
 )}
 </div>
 ))}

 {/* Manufacturer — searchable curated dropdown + Other (iter 224) */}
 <div data-testid="edit-manufacturer-wrapper">
 <label className="text-[var(--color-text-muted)] text-sm">Manufacturer</label>
 <ManufacturerCombobox
 value={editForm.manufacturer || ''}
 onChange={(v) => setEditForm({ ...editForm, manufacturer: v })}
 testId="edit-manufacturer"
 />
 </div>

 {/* SLA Response Time — 48h / 72h / Other (iter 224) */}
 <div data-testid="edit-sla-response-wrapper">
 <label className="text-[var(--color-text-muted)] text-sm">SLA Response Time</label>
 <select
 value={SLA_RESPONSE_OPTIONS.some(o => o.value === editForm.sla_response_time)
   ? editForm.sla_response_time
   : (editForm.sla_response_time ? '__other__' : '48h')}
 onChange={e => {
   const v = e.target.value;
   if (v === '__other__') {
     // Preserve any existing custom value; otherwise blank for free-text.
     if (SLA_RESPONSE_OPTIONS.some(o => o.value === editForm.sla_response_time)) {
       setEditForm({ ...editForm, sla_response_time: '' });
     }
   } else {
     setEditForm({ ...editForm, sla_response_time: v });
   }
 }}
 className="w-full bg-[var(--color-ink-alt)] border border-white/10 text-white mt-1 rounded-md px-3 py-2 text-sm"
 data-testid="edit-sla_response_time"
 >
 {SLA_RESPONSE_OPTIONS.map(opt => (
 <option key={opt.value} value={opt.value}>{opt.label}</option>
 ))}
 </select>
 {!SLA_RESPONSE_OPTIONS.slice(0, 2).some(o => o.value === editForm.sla_response_time) && (
 <Input
 value={editForm.sla_response_time || ''}
 onChange={e => setEditForm({ ...editForm, sla_response_time: e.target.value })}
 placeholder="e.g. 4 hours, Next business day"
 className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-2"
 data-testid="edit-sla_response_time_other"
 />
 )}
 </div>

 {canEditSupplier && (
 <div data-testid="edit-supplier-wrapper">
 <label className="text-[var(--color-text-muted)] text-sm flex items-center gap-2">
 Supplier
 <span className="text-[10px] text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-1.5 py-0.5 rounded">Owners & Managers only</span>
 </label>
 <select
 value={editForm.supplier || ''}
 onChange={e => setEditForm({ ...editForm, supplier: e.target.value })}
 className="w-full bg-[var(--color-ink-alt)] border border-white/10 text-white mt-1 rounded-md px-3 py-2 text-sm"
 data-testid="edit-supplier"
 >
 <option value="">— No supplier —</option>
 {suppliers.map((s) => (
 <option key={s.id} value={s.name}>{s.name}</option>
 ))}
 {editForm.supplier && !suppliers.find((s) => s.name === editForm.supplier) && (
 <option value={editForm.supplier}>{editForm.supplier} (not in supplier list)</option>
 )}
 </select>
 <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
 Changes the service provider for this machine. Fault emails will route accordingly.
 </p>
 {editForm.supplier
 && (editForm.supplier || '') !== (selectedEquipment?.supplier || '')
 && (
 <label
 className="flex items-start gap-2 mt-3 p-2.5 bg-indigo-500/10 border border-indigo-500/20 rounded-md cursor-pointer"
 data-testid="edit-supplier-notify-wrapper"
 >
 <input
 type="checkbox" checked={notifySupplier}
 onChange={(e) => setNotifySupplier(e.target.checked)}
 className="mt-0.5 accent-indigo-500"
 data-testid="edit-supplier-notify"
 />
 <span className="text-xs text-white leading-snug">
 <strong>Email {editForm.supplier}</strong> to tell them this machine has been assigned to them
 <span className="block text-[10px] text-[var(--color-text-muted)] mt-0.5">
 (Includes machine name, serial and location. No email is sent if left unticked.)
 </span>
 </span>
 </label>
 )}
 </div>
 )}

 <Button onClick={handleSaveEdit} className="w-full bg-[var(--color-brand-blue)] text-white" data-testid="save-edit-btn">Save Changes</Button>
 </div>
 </DialogContent>
 </Dialog>

 {/* Audit Detail Dialog */}
 {viewAudit && <AuditDetailPanel audit={viewAudit} onClose={() => setViewAudit(null)} />}

 {/* Inline manual viewer */}
 {viewingManual && (
 <Dialog open onOpenChange={(o) => !o && setViewingManual(null)}>
 <DialogContent className="max-w-5xl bg-[var(--color-neutral-950)] border border-white/10" data-testid="manual-viewer-dialog">
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2 text-white">
 <FileText size={18} className="text-[var(--color-brand-blue)]" />
 {viewingManual.manual.original_filename}
 <div className="ml-auto flex items-center gap-1">
 {manualBlobUrl && (
 <a href={manualBlobUrl} target="_blank" rel="noopener noreferrer"
 className="px-2 py-1 text-[11px] rounded bg-zinc-800 text-white hover:bg-zinc-700 inline-flex items-center gap-1"
 data-testid="manual-open-newtab">
 <ExternalLink size={11} /> New tab
 </a>
 )}
 <button onClick={() => handleDownloadManual(viewingManual.equipmentId, viewingManual.manual)}
 className="px-2 py-1 text-[11px] rounded bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-alt)] inline-flex items-center gap-1"
 data-testid="manual-download-from-viewer">
 <Download size={11} /> Download
 </button>
 </div>
 </DialogTitle>
 </DialogHeader>
 <div className="rounded-lg overflow-hidden bg-white" style={{ height: 'calc(85vh - 120px)', minHeight: '500px' }}>
 {manualBlobUrl ? (
 <iframe src={manualBlobUrl} title={viewingManual.manual.original_filename}
 className="w-full h-full" style={{ border: 'none' }} data-testid="manual-iframe" />
 ) : (
 <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-zinc-400" size={24} /></div>
 )}
 </div>
 </DialogContent>
 </Dialog>
 )}
 </div>
 );
};

export default EquipmentInfoTab;
