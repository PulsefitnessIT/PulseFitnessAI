import { notify } from '@/components/notifications';
import { useState, useEffect, useCallback, useRef } from 'react';
import ReactDOM from 'react-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AlertTriangle, CheckCircle, Shield, Download, FileText, Camera, Loader2, X, Wrench, Sparkles, Check, QrCode, ChevronDown } from 'lucide-react';
import axios from 'axios';
import FaultTemplatePicker from '../Dashboard/FaultTemplatePicker';
import FaultCodeSelect from '../Dashboard/FaultCodeSelect';
import SaveAsTemplateButton from '../Dashboard/SaveAsTemplateButton';
import { buildMachineTypeGroups, filterSerialsByGroup, deriveGroupKey } from '../Dashboard/faultMachineGrouping';
import { useBackGestureClose } from '@/lib/useBackGestureClose';
import EquipmentPhotoUpload from '../../components/equipment/EquipmentPhotoUpload';
import AuthImage from '../../components/shared/AuthImage';
import EquipmentSpecGrid from '@/components/shared/EquipmentSpecGrid';
import SupplierMultiPicker from '@/components/shared/SupplierMultiPicker';
import { useTranslation } from 'react-i18next';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api';

/* ─── Hook to fetch a PDF/image as blob URL ─── */
const useBlobUrl = (url) => {
  const [blobUrl, setBlobUrl] = useState(null);
  useEffect(() => {
    if (!url) { setBlobUrl(null); return; }
    let revoke;
    axios.get(url, { responseType: 'blob' })
      .then(res => { const u = URL.createObjectURL(res.data); revoke = u; setBlobUrl(u); })
      .catch(() => setBlobUrl(null));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [url]);
  return blobUrl;
};

/* ─── Equipment Detail with Tabs (Details | Spec Sheet) ─── */
const EquipmentDetailContent = ({ selectedEquipment, getEquipmentFaults, getEquipmentFiles, getSeverityStyle, getSeverityLabel, getStatusColor, onLogFaultForEquipment, onDownloadFile, brandAccent = 'var(--color-brand-cyan-hover)', userRole = 'staff', onSupplierChange }) => {
  const { t } = useTranslation();
  const specId = selectedEquipment.spec_sheet_id;
  const hasSpec = !!specId;
  const [activeTab, setActiveTab] = useState('details');
  const [photoUrl, setPhotoUrl] = useState(selectedEquipment.photo_url || null);
  const pdfBlobUrl = useBlobUrl(hasSpec && activeTab === 'spec-sheet' ? `${API_BASE}/spec-sheets/pdf/${specId}` : null);
  const authToken = typeof window !== 'undefined' ? localStorage.getItem('token') : '';

  // Iter 216h114 — Inline Supplier editor. Owners/managers see a
  // dropdown sourced from /api/suppliers so they can re-route fault
  // notifications without leaving the equipment drawer.
  const canEditSupplier = userRole === 'owner' || userRole === 'manager' || userRole === 'master_admin';
  const [supplierOptions, setSupplierOptions] = useState([]);
  const [editingSupplier, setEditingSupplier] = useState(false);
  const [savingSupplier, setSavingSupplier] = useState(false);
  const [currentSupplier, setCurrentSupplier] = useState(selectedEquipment.supplier || '');
  useEffect(() => { setCurrentSupplier(selectedEquipment.supplier || ''); }, [selectedEquipment.id, selectedEquipment.supplier]);
  useEffect(() => {
    if (!canEditSupplier) return;
    let cancelled = false;
    axios
      .get(`${API_BASE}/suppliers`, { headers: { Authorization: `Bearer ${authToken}` } })
      .then((r) => { if (!cancelled) setSupplierOptions(r.data?.suppliers || []); })
      .catch(() => { if (!cancelled) setSupplierOptions([]); });
    return () => { cancelled = true; };
  }, [canEditSupplier, authToken]);

  const handleSaveSupplier = async (supplierName, notifySupplier = false) => {
    setSavingSupplier(true);
    try {
      const match = supplierOptions.find((s) => s.name === supplierName);
      await axios.patch(
        `${API_BASE}/equipment/${selectedEquipment.id}`,
        {
          supplier: supplierName,
          supplier_id: match?.id || null,
          notify_supplier: notifySupplier,
        },
        { headers: { Authorization: `Bearer ${authToken}` } },
      );
      setCurrentSupplier(supplierName);
      selectedEquipment.supplier = supplierName;
      if (match?.id) selectedEquipment.supplier_id = match.id;
      setEditingSupplier(false);
      notify.success(notifySupplier ? 'Supplier updated and notified' : 'Supplier updated');
      if (onSupplierChange) onSupplierChange(selectedEquipment.id, supplierName, match?.id || null);
    } catch (err) {
      notify.error(err?.response?.data?.detail || 'Could not update supplier');
    } finally {
      setSavingSupplier(false);
    }
  };

  const eqFaults = getEquipmentFaults(selectedEquipment);
  const eqFiles = getEquipmentFiles(selectedEquipment);
  const warrantyActive = selectedEquipment.warranty_expiry && new Date(selectedEquipment.warranty_expiry) > new Date();
  const contractActive = selectedEquipment.sla_expiry && new Date(selectedEquipment.sla_expiry) > new Date();
  const formatDate = (d) => d ? new Date(d).toLocaleDateString('en-GB') : null;

  return (
    <div className="pt-2">
      {/* Tabs */}
      {hasSpec && (
        <div className="flex gap-1 border-b border-[var(--theme-border)] mb-4" data-testid="equip-detail-tabs">
          <button onClick={() => setActiveTab('details')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'details' ? '' : 'border-transparent text-[var(--color-text-muted)] hover:text-white'}`}
            style={activeTab === 'details' ? { borderColor: brandAccent, color: brandAccent } : undefined}
            data-testid="equip-tab-details">
            <Wrench size={13} className="inline mr-1.5 -mt-0.5" /> {t('dialog.details', 'Details')}
          </button>
          <button onClick={() => setActiveTab('spec-sheet')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'spec-sheet' ? '' : 'border-transparent text-[var(--color-text-muted)] hover:text-white'}`}
            style={activeTab === 'spec-sheet' ? { borderColor: brandAccent, color: brandAccent } : undefined}
            data-testid="equip-tab-spec-sheet">
            <FileText size={13} className="inline mr-1.5 -mt-0.5" /> {t('dialog.spec_sheet', 'Spec Sheet')}
          </button>
        </div>
      )}

      {activeTab === 'spec-sheet' && hasSpec ? (
        /* ── Spec Sheet Tab ── */
        <div data-testid="equip-spec-viewer">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-20 h-20 rounded-lg bg-[var(--theme-surface)] border border-[var(--theme-border)] flex items-center justify-center shrink-0 overflow-hidden" data-testid="equip-spec-image">
              <img src={`${API_BASE}/spec-sheets/image/${specId}`} alt={selectedEquipment.name}
                className="w-full h-full object-contain p-1"
                onError={(e) => { e.target.style.display = 'none'; }} />
            </div>
            <div>
              <p className="text-sm font-medium text-[var(--theme-text)]">{selectedEquipment.name}</p>
              <p className="text-xs text-[var(--color-text-muted)]">{selectedEquipment.manufacturer} · {selectedEquipment.equipment_type}</p>
            </div>
          </div>
          {/* PDF viewer must stay white in both themes — PDFs are white documents. */}
          <div className="rounded-lg border border-[var(--theme-border)] overflow-hidden bg-white dark:bg-white relative" style={{ height: 'calc(85vh - 220px)', minHeight: '400px' }}>
            {pdfBlobUrl ? (
              <>
                <div className="absolute top-2 right-2 z-10 flex gap-1">
                  <a
                    href={pdfBlobUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-1 text-[11px] rounded bg-zinc-900/80 text-white hover:bg-zinc-900 inline-flex items-center gap-1"
                    data-testid="spec-sheet-open-new-tab"
                  >
                    Open in new tab
                  </a>
                  <a
                    href={pdfBlobUrl}
                    download={`${selectedEquipment.name || 'spec-sheet'}.pdf`}
                    className="px-2 py-1 text-[11px] rounded bg-[var(--color-brand-blue)] text-white hover:bg-[var(--color-brand-blue-hover)] inline-flex items-center gap-1"
                    data-testid="spec-sheet-download"
                  >
                    Download
                  </a>
                </div>
                <iframe src={pdfBlobUrl} title="Spec Sheet" className="w-full h-full" style={{ border: 'none' }} />
              </>
            ) : (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="animate-spin text-gray-400" size={24} />
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ── Details Tab ── */
        <div className="space-y-4">
          {/* Product photo + info grid */}
          <div className="flex flex-col sm:flex-row gap-4">
            {/* Primary equipment photo — shows uploaded photo if present,
                otherwise an upload CTA (mobile camera + file picker).
                Always visible so owners can add a photo even when no
                spec-sheet exists. */}
            <div className="w-full sm:w-48 shrink-0" data-testid="equip-photo-slot">
              <EquipmentPhotoUpload
                equipmentId={selectedEquipment.id}
                photoUrl={photoUrl}
                manufacturer={selectedEquipment.manufacturer || selectedEquipment.supplier}
                equipmentType={selectedEquipment.equipment_type}
                equipmentModel={selectedEquipment.model}
                fallbackImageUrl={
                  !photoUrl
                    ? (selectedEquipment.auto_image_url
                        // Iter 216e — catalogue-fallback image populated
                        // by the master-admin rematch endpoint. Sits
                        // between the operator-triggered auto-lookup
                        // and the PDF spec-sheet hero so equipment with
                        // a Pulse / Technogym / etc match always shows
                        // a real product photo, not a placeholder.
                        || selectedEquipment.spec_sheet_image
                        || (specId ? `${API_BASE}/spec-sheets/image/${specId}` : null))
                    : null
                }
                fallbackSource={
                  selectedEquipment.auto_image_url ? 'manufacturer'
                  : selectedEquipment.spec_sheet_image ? 'manufacturer-catalogue'
                  : (specId ? 'spec-sheet' : null)
                }
                autoImageSourceUrl={
                  selectedEquipment.auto_image_source_url
                  || selectedEquipment.manufacturer_page_url
                  || null
                }
                canAutoLookup={!photoUrl && !selectedEquipment.auto_image_url && !selectedEquipment.spec_sheet_image && !specId}
                onAutoLookup={async () => {
                  try {
                    const r = await axios.post(
                      `${API_BASE}/equipment/${selectedEquipment.id}/lookup-image`,
                      {},
                      { headers: { Authorization: `Bearer ${authToken}` } },
                    );
                    if (r.data && r.data.image_url) {
                      notify.success(
                        r.data.verified ? 'Product image found & AI-verified' : 'Candidate image found — please review',
                      );
                      selectedEquipment.auto_image_url = r.data.image_url;
                      selectedEquipment.auto_image_source_url = r.data.source_url;
                      selectedEquipment.auto_image_verified = !!r.data.verified;
                      setPhotoUrl(null); // force re-render
                    } else {
                      notify.error(r.data?.message || 'No matching image found');
                    }
                  } catch (err) {
                    // Iter 216h57 — fixed runtime crash on the
                    // "Find manufacturer photo" button. Previously
                    // used a non-existent `sonner.notify` import path.
                    notify.error(err?.response?.data?.detail || 'Manufacturer photo lookup failed');
                  }
                }}
                onUploaded={(newUrl) => {
                  setPhotoUrl(newUrl);
                  if (selectedEquipment) selectedEquipment.photo_url = newUrl;
                }}
                apiBase={API_BASE}
                authToken={authToken}
              />
            </div>
            <div className="flex-1">
              {/* Iter 216o — shared atomic component (cross-portal parity).
                  Same grid renders in Pulse Fitness/Pulse with brand-correct
                  accent colour and zero drift between portals. */}
              <EquipmentSpecGrid
                columns={2}
                accent={brandAccent}
                tiles={[
                  { label: 'Type', value: selectedEquipment.equipment_type, testId: 'lite-equip-type' },
                  { label: 'Serial', value: selectedEquipment.serial_number, mono: true, testId: 'lite-equip-serial' },
                  {
                    label: 'Manufacturer',
                    /* Iter 216e — when the manufacturer-catalogue
                       backfill matched this equipment, render the
                       manufacturer name as a clickable link to the
                       brand's product page. Falls back to plain text
                       when no match. */
                    value: selectedEquipment.manufacturer_page_url ? (
                      <a
                        href={selectedEquipment.manufacturer_page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline decoration-dotted underline-offset-2 hover:opacity-80"
                        style={{ color: brandAccent }}
                        data-testid="lite-equip-manufacturer-link"
                        title={`View ${selectedEquipment.manufacturer || 'manufacturer'} page`}
                      >
                        {selectedEquipment.manufacturer} ↗
                      </a>
                    ) : selectedEquipment.manufacturer,
                    testId: 'lite-equip-manufacturer',
                  },
                  { label: 'Location', value: selectedEquipment.location, testId: 'lite-equip-location' },
                  { label: 'Supplier', value: currentSupplier, accent: !!currentSupplier, testId: 'lite-equip-supplier' },
                ]}
              />
              {/* Iter 216h114 — Per-machine supplier override (owners/managers only).
                  Lets MOD managers route fault notifications to the
                  correct supplier without leaving the drawer. */}
              {canEditSupplier && (
                <div className="mt-3" data-testid="lite-equip-supplier-editor">
                  {!editingSupplier ? (
                    <button
                      type="button"
                      onClick={() => setEditingSupplier(true)}
                      className="text-[11px] font-semibold uppercase tracking-wider px-2.5 py-1.5 rounded-md border border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-[var(--theme-text)] hover:border-[var(--color-brand-cyan-hover)]"
                      data-testid="lite-equip-supplier-edit-btn"
                    >
                      {currentSupplier ? 'Change supplier' : '+ Assign supplier'}
                    </button>
                  ) : (
                    <SupplierEditor
                      options={supplierOptions}
                      current={currentSupplier}
                      saving={savingSupplier}
                      onSave={handleSaveSupplier}
                      onCancel={() => setEditingSupplier(false)}
                      brandAccent={brandAccent}
                      authToken={authToken}
                      onSupplierAdded={(newSupplier) => {
                        setSupplierOptions((prev) => [...prev, newSupplier]);
                      }}
                    />
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-2" data-testid="lite-equip-coverage-section">
            <h4 className="font-medium text-[var(--theme-text)] text-sm">Warranty & Contract</h4>
            <div className="grid grid-cols-1 gap-2">
              <div className={`p-3 rounded-lg border text-sm ${warrantyActive ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-[var(--theme-surface)] border-[var(--theme-border)]'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2"><Shield size={14} className={warrantyActive ? 'text-emerald-400' : 'text-[var(--color-text-muted)]'} /><span className={warrantyActive ? 'text-emerald-400 font-medium' : 'text-[var(--color-text-muted)]'}>Warranty</span></div>
                  {selectedEquipment.warranty_expiry ? <span className={`text-xs ${warrantyActive ? 'text-emerald-400' : 'text-[var(--color-text-muted)]'}`}>{warrantyActive ? (() => { const d = Math.ceil((new Date(selectedEquipment.warranty_expiry) - new Date()) / 86400000); const y = Math.floor(d/365); const r = d%365; return y > 0 ? (r > 0 ? `${y}y ${r}d remaining` : `${y}y remaining`) : `${d}d remaining`; })() : 'Expired'}</span> : <span className="text-xs text-[var(--color-text-muted)]">Not set</span>}
                </div>
                {(selectedEquipment.purchase_date || selectedEquipment.warranty_expiry) && (
                  <div className="flex items-center gap-4 mt-2 text-xs text-[var(--color-text-muted)]">
                    {selectedEquipment.purchase_date && <span>Start: <span className="text-[var(--theme-text)]">{formatDate(selectedEquipment.purchase_date)}</span></span>}
                    {selectedEquipment.warranty_expiry && <span>End: <span className="text-[var(--theme-text)]">{formatDate(selectedEquipment.warranty_expiry)}</span></span>}
                    {selectedEquipment.sla_level && <span>SLA: <span className="text-[var(--theme-text)]">{selectedEquipment.sla_level}</span></span>}
                  </div>
                )}
              </div>
              <div className={`p-3 rounded-lg border text-sm ${contractActive ? 'bg-blue-500/10 border-blue-500/20' : 'bg-[var(--theme-surface)] border-[var(--theme-border)]'}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2"><FileText size={14} className={contractActive ? 'text-blue-400' : 'text-[var(--color-text-muted)]'} /><span className={contractActive ? 'text-blue-400 font-medium' : 'text-[var(--color-text-muted)]'}>Service Contract</span></div>
                  {selectedEquipment.sla_expiry ? <span className={`text-xs ${contractActive ? 'text-blue-400' : 'text-[var(--color-text-muted)]'}`}>{contractActive ? (() => { const d = Math.ceil((new Date(selectedEquipment.sla_expiry) - new Date()) / 86400000); const y = Math.floor(d/365); const r = d%365; return y > 0 ? (r > 0 ? `${y}y ${r}d remaining` : `${y}y remaining`) : `${d}d remaining`; })() : 'Expired'}</span> : <span className="text-xs text-[var(--color-text-muted)]">Not set</span>}
                </div>
              </div>
            </div>
          </div>

          <div>
            <h4 className="font-medium text-[var(--theme-text)] text-sm mb-2">Fault History ({eqFaults.length})</h4>
            {eqFaults.length > 0 ? (
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {eqFaults.map(f => (
                  <div key={f.id} className="p-2 bg-[var(--theme-surface)] rounded border border-[var(--theme-border)] text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className={`${getSeverityStyle(f.severity)} text-[10px]`}>{getSeverityLabel(f.severity)}</Badge>
                      <Badge className={`${getStatusColor(f.status)} text-[10px]`}>{f.status}</Badge>
                      <span className="text-[var(--color-text-muted)] ml-auto">{f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}</span>
                    </div>
                    <p className="text-[var(--color-text-muted)]">{f.issue_description?.slice(0, 120)}{f.issue_description?.length > 120 ? '...' : ''}</p>
                  </div>
                ))}
              </div>
            ) : <p className="text-xs text-[var(--color-text-muted)]">No faults recorded</p>}
          </div>

          <div>
            <h4 className="font-medium text-[var(--theme-text)] text-sm mb-2">Documents ({eqFiles.length + (hasSpec ? 1 : 0)})</h4>
            <div className="space-y-1">
              {/* Manufacturer manual — auto-linked from the Master Admin
                  spec-sheet catalogue. Read-only for everyone (only Master
                  Admin uploads these), viewable + downloadable by all roles. */}
              {hasSpec && (
                <div className="flex items-center gap-2 p-2 bg-[var(--theme-surface)] rounded text-xs border border-[var(--color-brand-blue)]/30" data-testid="equip-manufacturer-manual">
                  <FileText size={12} className="text-[var(--color-brand-blue)] shrink-0" />
                  <div className="flex-1 min-w-0">
                    <span className="text-[var(--theme-text)] block truncate">{selectedEquipment.name || 'Manufacturer manual'}</span>
                    <span className="text-[10px] text-[var(--color-text-muted)]">Manufacturer manual</span>
                  </div>
                  <Badge className="bg-[var(--color-brand-blue)]/15 text-[var(--color-brand-blue)] border-0 text-[9px] font-bold px-1.5 py-0 shrink-0">Read-only</Badge>
                  <button
                    type="button"
                    onClick={() => setActiveTab('spec-sheet')}
                    className="h-6 px-2 rounded text-[var(--color-text-muted)] hover:text-white inline-flex items-center"
                    title="View manual"
                    data-testid="equip-manual-view"
                  ><FileText size={12} /></button>
                  <a
                    href={`${API_BASE}/spec-sheets/pdf/${specId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    download={`${(selectedEquipment.name || 'manufacturer-manual')}.pdf`}
                    className="h-6 w-6 p-0 rounded text-[var(--color-text-muted)] hover:text-white inline-flex items-center justify-center"
                    title="Download manual"
                    data-testid="equip-manual-download"
                  ><Download size={12} /></a>
                </div>
              )}
              {eqFiles.map(f => (
                <div key={f.id} className="flex items-center gap-2 p-2 bg-[var(--theme-surface)] rounded text-xs border border-[var(--theme-border)]">
                  <FileText size={12} className="text-[var(--color-text-muted)]" />
                  <span className="flex-1 text-[var(--theme-text)] truncate">{f.original_filename}</span>
                  <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-[var(--color-text-muted)] hover:text-white" onClick={() => onDownloadFile(f)}><Download size={12} /></Button>
                </div>
              ))}
              {eqFiles.length === 0 && !hasSpec && <p className="text-xs text-[var(--color-text-muted)]">No documents attached</p>}
            </div>
          </div>

          <Button className="w-full bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" onClick={() => onLogFaultForEquipment(selectedEquipment)} data-testid="lite-equip-log-fault">
            <AlertTriangle size={14} className="mr-2" /> {t('dialog.log_fault_for_machine', 'Log Fault for this Machine')}
          </Button>

          {/* QR Code */}
          <div data-testid="equip-qr-section">
            <h4 className="font-medium text-[var(--theme-text)] text-sm mb-2">QR Code</h4>
            <div className="p-4 bg-[var(--theme-surface)] rounded-lg border border-[var(--theme-border)] flex items-center gap-4">
              <div className="shrink-0 flex flex-col items-center" data-testid="equip-qr-image">
                <div className="bg-white p-2 rounded-lg dark:bg-zinc-900">
                  {/* Self-hosted QR — served by /api/equipment/{id}/qr-code.
                      Requires auth, so we use <AuthImage> to fetch with the
                      JWT header and swap in a blob URL. Plain <img src> would
                      get a 401 because browsers cannot attach Bearer tokens
                      to image requests. */}
                  <AuthImage
                    src={`${API_BASE}/equipment/${selectedEquipment.id}/qr-code?size=120`}
                    alt="Equipment QR Code"
                    className="w-[120px] h-[120px]"
                    data-testid="equip-qr-img"
                  />
                </div>
                <img src="https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg" alt="Pulse Fitness" className="mt-1.5 h-5 rounded" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--theme-text)] font-medium mb-1">Scan to view — and add a photo</p>
                <p className="text-xs text-[var(--color-text-muted)] mb-2">Stick this on the machine. Staff can scan it to report a fault or snap a live photo so engineers know exactly what they're looking at on arrival.</p>
                <div className="bg-[var(--theme-surface)] rounded p-2 mb-3 border border-white/5">
                  <p className="text-[10px] text-[var(--color-text-muted)]"><span className="text-[var(--color-brand-cyan-hover)] font-semibold">Recommended printers:</span> Brother QL-820NWB or DYMO LabelWriter 450. Use 62mm x 62mm die-cut labels for best results. Laminated labels recommended for gym environments.</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-[var(--theme-border)] text-[var(--color-text-muted)] hover:text-white"
                  onClick={async () => {
                    const token = localStorage.getItem('token');
                    try {
                      const resp = await fetch(
                        `${API_BASE}/equipment/${selectedEquipment.id}/qr-code?size=600`,
                        { headers: { Authorization: `Bearer ${token}` } },
                      );
                      const blob = await resp.blob();
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `QR-${selectedEquipment.serial_number || selectedEquipment.name}.png`;
                      a.click();
                      URL.revokeObjectURL(url);
                    } catch { /* swallow — download failures only */ }
                  }}
                  data-testid="equip-qr-download"
                >
                  <QrCode size={14} className="mr-1.5" /> Download QR
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/* ─── Inline Supplier Editor (Iter 216h114) ───
   Dropdown selector for the per-machine supplier override. Lists the
   org's supplier directory PLUS the curated UK fitness supplier
   catalogue via SupplierMultiPicker (single mode). Owner/manager-only —
   the parent component gates visibility.

   Iter 216h218 — Replaced native <Select> with SupplierMultiPicker so
   the picker is consistent with PartsInventory / EquipmentInfoTab /
   InvoiceImport flows and standardises on the curated supplier list.
   The parent still passes `options` (the org's saved suppliers) so
   handleSaveSupplier can map the chosen name → supplier_id for fault
   email routing. */
const SupplierEditor = ({ options, current, saving, onSave, onCancel, brandAccent, authToken, onSupplierAdded }) => {
  const [value, setValue] = useState(current || '');
  const [notify_, setNotify] = useState(false);
  // Iter 216h262 — inline add-to-directory form. When the picked
  // supplier name doesn't match any directory entry, surface an email
  // input so owners/managers can fill in the missing email without
  // leaving the equipment drawer.
  const [supplierEmail, setSupplierEmail] = useState('');
  const [addingToDirectory, setAddingToDirectory] = useState(false);

  const directoryHit = !!value
    && !!options
    && options.find((s) => (s.name || '').toLowerCase() === value.toLowerCase());
  const notInDirectory = !!value && !directoryHit;

  // Reset the email field whenever the picked supplier changes
  useEffect(() => {
    setSupplierEmail('');
  }, [value]);

  const handleAddToDirectory = async () => {
    const email = supplierEmail.trim();
    if (!email) {
      notify.error('Add an email address first');
      return;
    }
    // basic email shape check
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      notify.error('That doesn\u2019t look like a valid email');
      return;
    }
    setAddingToDirectory(true);
    try {
      const r = await axios.post(
        `${API_BASE}/suppliers`,
        {
          name: value,
          email,
          send_welcome: false, // don't spam — engineer hasn't been briefed yet
        },
        { headers: { Authorization: `Bearer ${authToken}` } },
      );
      const newSupplier = r.data || {};
      notify.success(`${value} added to your supplier directory`);
      if (typeof onSupplierAdded === 'function') onSupplierAdded(newSupplier);
      setSupplierEmail('');
    } catch (err) {
      notify.error(err?.response?.data?.detail || 'Could not add supplier');
    } finally {
      setAddingToDirectory(false);
    }
  };

  return (
    <div className="rounded-lg border border-[var(--theme-border)] bg-[var(--theme-surface)] p-3" data-testid="lite-equip-supplier-form">
      <Label className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)] block mb-1.5">
        Supplier (used for fault routing)
      </Label>
      <SupplierMultiPicker
        single
        value={value}
        onChange={setValue}
        placeholder="Choose a supplier…"
        testid="lite-equip-supplier-picker"
      />
      <label className="flex items-center gap-2 mt-2.5 text-[11px] text-[var(--color-text-muted)] cursor-pointer" data-testid="lite-equip-supplier-notify-toggle">
        <input
          type="checkbox"
          checked={notify_}
          onChange={(e) => setNotify(e.target.checked)}
          className="accent-cyan-500"
        />
        Email the supplier about this assignment
      </label>
      {/* Iter 216h262 — if the picked name isn't in the org's
          directory, show an inline email field + "Add to directory"
          action so owners/managers can fill in the missing address
          right here. Without an email on file, fault auto-routing
          can't fire. */}
      {notInDirectory && (
        <div
          className="mt-2.5 rounded-md border border-amber-400/40 bg-amber-50 dark:bg-amber-500/10 p-2.5"
          data-testid="lite-equip-supplier-not-in-directory"
        >
          <p className="text-[11px] text-amber-700 dark:text-amber-300 leading-snug">
            <b>&quot;{value}&quot;</b> isn&apos;t in your supplier directory yet.
            Add an email address below so fault notifications can be
            auto-routed to them.
          </p>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 mt-2">
            <input
              type="email"
              value={supplierEmail}
              onChange={(e) => setSupplierEmail(e.target.value)}
              placeholder="service@supplier.co.uk"
              className="flex-1 min-w-0 px-2.5 py-1.5 text-xs rounded-md border border-amber-300 bg-white text-slate-900 placeholder:text-slate-400 dark:bg-zinc-900 dark:text-zinc-100 dark:border-amber-500/40 focus:outline-none focus:border-amber-500"
              data-testid="lite-equip-supplier-add-email"
            />
            <Button
              type="button"
              size="sm"
              onClick={handleAddToDirectory}
              disabled={addingToDirectory || !supplierEmail.trim()}
              className="h-7 text-[11px] text-white shrink-0"
              style={{ background: brandAccent }}
              data-testid="lite-equip-supplier-add-to-directory"
            >
              {addingToDirectory ? <Loader2 size={12} className="animate-spin" /> : '+ Add to directory'}
            </Button>
          </div>
        </div>
      )}
      <div className="flex items-center justify-end gap-1.5 mt-3">
        <Button size="sm" variant="ghost" onClick={onCancel} className="h-7 text-[11px] text-[var(--color-text-muted)]" data-testid="lite-equip-supplier-cancel">
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => onSave(value, notify_)}
          disabled={saving || !value || value === current}
          className="h-7 text-[11px] text-white"
          style={{ background: brandAccent }}
          data-testid="lite-equip-supplier-save"
        >
          {saving ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
        </Button>
      </div>
    </div>
  );
};

/* ─── Fault Machine Selector: Group by type, then pick serial ───
   Iter 216d2 — uses the shared helper (see Dashboard/faultMachineGrouping.js)
   so Lite + Pulse Fitness dashboards both group by the same "name → equipment_type"
   fallback chain, with comma-suffixed names ("Treadmill, Bay 3") collapsed
   into one group. Pinned by `faultMachineGrouping.test.js`. */
const FaultMachineSelector = ({ equipment, faultForm, selectEquipmentForFault }) => {
  const { t } = useTranslation();
  const groupRows = buildMachineTypeGroups(equipment);

  // Find selected group from the current equipment selection.
  const selectedEq = equipment.find(e => e.id === faultForm.equipment_id);
  const selectedGroup = selectedEq ? deriveGroupKey(selectedEq) : '';
  const groupItems = filterSerialsByGroup(equipment, selectedGroup);
  const needsSerialPick = groupItems.length > 1;

  const handleGroupChange = (groupName) => {
    const items = filterSerialsByGroup(equipment, groupName);
    if (items.length >= 1) selectEquipmentForFault(items[0]);
  };

  const handleSerialChange = (eqId) => {
    const eq = equipment.find(e => e.id === eqId);
    if (eq) selectEquipmentForFault(eq);
  };

  return (
    <>
      <div>
        <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.machine_type', 'Machine Type')}</Label>
        <Select value={selectedGroup} onValueChange={handleGroupChange}>
          <SelectTrigger className="bg-[var(--theme-surface-2)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1.5 min-h-[44px] h-auto py-2 items-start text-left [&>span]:whitespace-normal [&>span]:break-words [&>span]:line-clamp-none" data-testid="lite-fault-machine-select">
            <SelectValue placeholder={t('dialog.choose_machine_type', 'Choose machine type...')} />
          </SelectTrigger>
          <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] max-h-60 max-w-[calc(100vw-80px)]" style={{ scrollBehavior: 'smooth' }}>
            {groupRows.map(g => (
              <SelectItem key={g.type} value={g.type} className="text-[var(--theme-text)] py-3 whitespace-normal">
                <span className="whitespace-normal break-words block">{g.label}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {selectedGroup && needsSerialPick && (
        <div>
          <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.select_serial', 'Select Serial Number')}</Label>
          <Select value={faultForm.equipment_id} onValueChange={handleSerialChange}>
            <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1.5 h-11" data-testid="lite-fault-serial-select">
              <SelectValue placeholder={t('dialog.choose_serial', 'Choose serial number...')} />
            </SelectTrigger>
            <SelectContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] max-h-60">
              {groupItems.map(eq => (
                <SelectItem key={eq.id} value={eq.id} className="text-[var(--theme-text)]">
                  {eq.serial_number || 'No serial'} {eq.location ? `· ${eq.location}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      {selectedGroup && !needsSerialPick && faultForm.serial_number && (
        <div>
          <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.serial_number', 'Serial Number')}</Label>
          <div className="mt-1.5 p-3 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg text-sm text-[var(--theme-text)]" data-testid="lite-fault-serial">
            {faultForm.serial_number}
          </div>
        </div>
      )}
    </>
  );
};

const LiteDialogs = ({
  // Equipment Detail
  selectedEquipment, onCloseEquipment,
  getEquipmentFaults, getEquipmentFiles,
  onDownloadFile, onLogFaultForEquipment,
  getSeverityStyle, getSeverityLabel, getStatusColor,
  // Log Fault Dialog
  showFaultDialog, onCloseFaultDialog,
  equipment, faultForm, setFaultForm,
  requireReporter = false, siteStaff = [], reporterStaffId = '', setReporterStaffId,
  allowOtherStaff = false, requireStaffPin = false, reporterPin = '', setReporterPin,
  reporterOther = {}, setReporterOther,
  selectEquipmentForFault, coverage,
  faultMedia, onMediaUpload, onRemoveMedia,
  onFaultSubmit, submitting, faultBanner,
  SEVERITY_OPTIONS,
  // Duplicate Modal
  duplicateModal, onDuplicateCancel, onDuplicateContinue,
  // Success Modal
  successModal, onSuccessDismiss,
  // Iter 216d — multi-machine staging
  stagedMachines = [],
  onAddMachineToJob,
  onRemoveStagedMachine,
  // Pro features
  isPro, headers,
  // Iter 216h114 — caller role + supplier-change callback used to
  // power the inline supplier editor in the equipment detail dialog.
  userRole = 'staff', onSupplierChange,
  // Iter 216h115 — flag classification hint on free-text fields when
  // the caller is on a MOD-scoped account.
  isMOD = false,
}) => {
  const { t } = useTranslation();
  const [triageResult, setTriageResult] = useState(null);
  const [triaging, setTriaging] = useState(false);
  const [showFixMethod, setShowFixMethod] = useState(false);

  const FIX_METHODS = [
    { value: 'followed_ai_steps', label: 'Followed AI repair steps' },
    { value: 'own_knowledge', label: 'Used own knowledge / experience' },
    { value: 'replaced_part', label: 'Replaced a part' },
    { value: 'reset_recalibrated', label: 'Reset / recalibrated the machine' },
    { value: 'cleaned_lubricated', label: 'Cleaned / lubricated' },
    { value: 'tightened_adjusted', label: 'Tightened / adjusted components' },
    { value: 'other', label: 'Other fix' },
  ];

  const API = process.env.REACT_APP_BACKEND_URL + '/api';

  const handleTriage = async () => {
    setTriaging(true);
    try {
      const payload = {
        serial_number: faultForm.serial_number,
        machine_type: faultForm.machine_type,
        issue_description: faultForm.issue_description,
        severity: faultForm.severity,
        supplier: faultForm.supplier,
        steps_taken: faultForm.steps_taken || '',
      };
      const res = await axios.post(`${API}/issues/triage`, payload, { headers });
      setTriageResult(res.data);
      // Back-fill AI-suggested fault_code (only if user didn't manually pick one)
      if (res.data?.fault_code && !faultForm.fault_code) {
        setFaultForm(prev => ({ ...prev, fault_code: res.data.fault_code }));
      }
    } catch {
      onFaultSubmit();
    }
    setTriaging(false);
  };

  const handleConfirmAfterTriage = () => {
    // Iter 216h300 — pass the triage payload through to the parent
    // so it lands on the persisted issue record. Without this the
    // fault detail page renders no AI section even though the
    // assessment was generated. Stored as a JSON string because
    // `IssueCreate.ai_triage` is `Optional[str]` (the backend's
    // `_parse_ai_triage` then re-hydrates it into a dict).
    const triagePayload = triageResult ? { ai_triage: JSON.stringify(triageResult) } : {};
    setTriageResult(null);
    onFaultSubmit(triagePayload);
  };

  const handleCloseDialog = (open) => {
    if (!open) { setTriageResult(null); }
    onCloseFaultDialog(open);
  };

  // Iter 216f — back-gesture close on the Lite/Pulse fault dialog and
  // the Equipment Detail dialog. Mobile operators expect swipe-back
  // to dismiss a modal, not exit the dashboard.
  // See `lib/useBackGestureClose.js`.
  // Once a photo/video is added the OS file chooser can emit a (sometimes
  // delayed) popstate that the back-gesture hook would treat as a back-gesture
  // and close the whole fault card. Disable back-gesture-close for the rest of
  // the dialog session once media is touched (user closes via X / submit).
  const faultMediaInputRef = useRef(null);
  const faultUploadActiveRef = useRef(false);
  useEffect(() => { if (showFaultDialog) faultUploadActiveRef.current = false; }, [showFaultDialog]);
  const closeFaultDialog = useCallback(() => {
    setTriageResult(null);
    onCloseFaultDialog && onCloseFaultDialog(false);
  }, [onCloseFaultDialog, setTriageResult]);
  const backGestureCloseFault = useCallback(() => {
    if (faultUploadActiveRef.current) {
      try { window.history.pushState({ 'gymaxis-lite-fault-dialog': true }, '', window.location.href); } catch { /* noop */ }
      return;
    }
    closeFaultDialog();
  }, [closeFaultDialog]);
  useBackGestureClose(showFaultDialog, backGestureCloseFault, 'gymaxis-lite-fault-dialog');

  const closeEquipmentDialog = useCallback(() => {
    onCloseEquipment && onCloseEquipment();
  }, [onCloseEquipment]);
  useBackGestureClose(!!selectedEquipment, closeEquipmentDialog, 'gymaxis-lite-equipment-dialog');

  return (
    <>
      {/* Equipment Detail Dialog */}
      <Dialog open={!!selectedEquipment} onOpenChange={() => onCloseEquipment()}>
        <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-[calc(100vw-2rem)] max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="equipment-detail-dialog">
          <DialogHeader>
            <DialogTitle className="text-[var(--theme-text)]">{selectedEquipment?.name}</DialogTitle>
          </DialogHeader>
          {selectedEquipment && <EquipmentDetailContent
            selectedEquipment={selectedEquipment}
            getEquipmentFaults={getEquipmentFaults}
            getEquipmentFiles={getEquipmentFiles}
            getSeverityStyle={getSeverityStyle}
            getSeverityLabel={getSeverityLabel}
            getStatusColor={getStatusColor}
            onLogFaultForEquipment={onLogFaultForEquipment}
            onDownloadFile={onDownloadFile}
            userRole={userRole}
            onSupplierChange={onSupplierChange}
          />}
        </DialogContent>
      </Dialog>

      {/* Log Fault Dialog */}
      <Dialog open={showFaultDialog} onOpenChange={handleCloseDialog}>
        <DialogContent
          className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] w-[calc(100vw-2rem)] max-w-3xl max-h-[85vh] overflow-y-auto"
          data-testid="log-fault-dialog"
          onPointerDownOutside={(e) => { if (duplicateModal || successModal) e.preventDefault(); }}
          onInteractOutside={(e) => { if (duplicateModal || successModal) e.preventDefault(); }}
          onEscapeKeyDown={(e) => { if (duplicateModal || successModal) e.preventDefault(); }}
        >
          <DialogHeader>
            <DialogTitle className="text-[var(--theme-text)] text-xl">{t('dashboard.log_fault', 'Log a Fault')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-2">
            {faultBanner}
            {/* Site Staff Shared Login — mandatory "who is logging this?" */}
            {requireReporter && (
              <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3" data-testid="lite-fault-reporter">
                <Label className="text-[var(--theme-text)] font-semibold">{t('dialog.who_logging', 'Who is logging this fault?')} <span className="text-red-500">*</span></Label>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5 mb-2">
                  {t('dialog.who_logging_help', 'Select your name so our service team knows who to contact if they need more information.')}
                </p>
                {siteStaff.length === 0 ? (
                  <p className="text-xs text-amber-600" data-testid="lite-fault-reporter-empty">
                    {t('dialog.no_staff', "Can't see your name? Please ask your site manager to add you to the site staff list.")}
                  </p>
                ) : (
                  <Select value={reporterStaffId || ''} onValueChange={(v) => setReporterStaffId && setReporterStaffId(v)}>
                    <SelectTrigger className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] h-11" data-testid="lite-fault-reporter-select">
                      <SelectValue placeholder={t('dialog.select_name', 'Select your name...')} />
                    </SelectTrigger>
                    <SelectContent>
                      {siteStaff.map((s) => (
                        <SelectItem key={s.id} value={s.id} data-testid={`lite-fault-reporter-${s.id}`}>
                          {s.full_name} — {s.job_title}
                        </SelectItem>
                      ))}
                      {allowOtherStaff && <SelectItem value="__other__" data-testid="lite-fault-reporter-other">Other staff member…</SelectItem>}
                    </SelectContent>
                  </Select>
                )}
                {/* Other staff member — manual contact details */}
                {reporterStaffId === '__other__' && (
                  <div className="grid grid-cols-2 gap-2 mt-3" data-testid="lite-fault-other-fields">
                    <Input placeholder="Full name" value={reporterOther.name || ''} onChange={(e) => setReporterOther({ ...reporterOther, name: e.target.value })} data-testid="lite-fault-other-name" />
                    <Input placeholder="Job title" value={reporterOther.job_title || ''} onChange={(e) => setReporterOther({ ...reporterOther, job_title: e.target.value })} data-testid="lite-fault-other-title" />
                    <Input placeholder="Email" value={reporterOther.email || ''} onChange={(e) => setReporterOther({ ...reporterOther, email: e.target.value })} data-testid="lite-fault-other-email" />
                    <Input placeholder="Phone" value={reporterOther.phone || ''} onChange={(e) => setReporterOther({ ...reporterOther, phone: e.target.value })} data-testid="lite-fault-other-phone" />
                  </div>
                )}
                {/* Optional staff PIN confirmation */}
                {requireStaffPin && reporterStaffId && reporterStaffId !== '__other__' && siteStaff.find((s) => s.id === reporterStaffId)?.has_pin && (
                  <div className="mt-3">
                    <Label className="text-xs text-[var(--color-text-muted)]">Staff PIN</Label>
                    <Input type="password" inputMode="numeric" value={reporterPin || ''} onChange={(e) => setReporterPin && setReporterPin(e.target.value.replace(/\D/g, '').slice(0, 8))} placeholder="Enter your PIN" className="h-10 mt-1" data-testid="lite-fault-reporter-pin" />
                  </div>
                )}
              </div>
            )}
            {/* Iter 216d — staged-machines bar (multi-machine job).
                Each chip = one machine already added to this job. The
                user can drop a chip if they staged it by mistake. */}
            {stagedMachines.length > 0 && (
              <div className="rounded-lg border border-blue-500/30 bg-[rgb(var(--rgb-brand-blue)/0.08)] p-3" data-testid="lite-staged-machines">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-[var(--color-brand-cyan-hover)] uppercase tracking-wide">
                    Job: {stagedMachines.length} machine{stagedMachines.length === 1 ? '' : 's'} staged
                  </p>
                  <span className="text-[10px] text-[var(--color-text-muted)]">
                    Add this one to submit them all together
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {stagedMachines.map((m, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded-md border border-blue-500/30 bg-[var(--theme-surface)] px-2 py-1 text-xs text-[var(--theme-text)]"
                      data-testid={`lite-staged-chip-${i}`}
                    >
                      <span className="font-medium">{m.machine_type || 'Machine'}</span>
                      <span className="text-[var(--color-text-muted)]">· {m.serial_number}</span>
                      <button
                        type="button"
                        onClick={() => onRemoveStagedMachine && onRemoveStagedMachine(i)}
                        className="ml-1 text-[var(--color-text-muted)] hover:text-red-400"
                        aria-label="Remove from job"
                        data-testid={`lite-staged-remove-${i}`}
                      ><X size={11} /></button>
                    </span>
                  ))}
                </div>
              </div>
            )}
            <FaultTemplatePicker
              API={API}
              onApply={(vals) => setFaultForm(prev => ({ ...prev, ...vals }))}
            />
            <FaultMachineSelector
              equipment={equipment}
              faultForm={faultForm}
              selectEquipmentForFault={selectEquipmentForFault}
            />
            {coverage && (
              <div className={`p-3 rounded-lg text-sm border ${coverage.warranty_active ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : coverage.contract_active ? 'bg-blue-500/10 border-blue-500/20 text-blue-400' : 'bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--color-text-muted)]'}`} data-testid="lite-coverage-info">
                <Shield size={14} className="inline mr-1" />
                {coverage.label || 'No warranty or contract on file'}
              </div>
            )}
            <div>
              <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.issue_description', 'Issue Description')}</Label>
              <Textarea value={faultForm.issue_description} onChange={e => setFaultForm({ ...faultForm, issue_description: e.target.value })} placeholder={t('dialog.describe_fault', 'Describe the fault...')} className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1.5 min-h-[100px]" data-testid="lite-fault-description" />
              {isMOD && (
                <div className="text-[10px] text-amber-500 font-semibold mt-1" data-testid="lite-fault-classification-hint">
                  ◆ OFFICIAL only — do NOT include NSN, operation names, callsigns or anything above OFFICIAL.
                </div>
              )}
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.steps_taken', 'Any Steps Already Taken?')}</Label>
              <Textarea
                value={faultForm.steps_taken || ''}
                onChange={e => setFaultForm({ ...faultForm, steps_taken: e.target.value })}
                /* Iter 216h301 — AI hint only when the tenant actually
                   has AI (Pulse Pro / trial / MOD-HQ). Pulse Lite users
                   were seeing "(helps AI diagnose faster)" even though
                   their portal has no AI features, which is confusing. */
                placeholder={isPro
                  ? t('dialog.steps_hint_pro', 'Have you tried anything to fix this? (helps AI diagnose faster)')
                  : t('dialog.steps_hint_lite', 'Have you tried anything to fix this? (gives the engineer a head start)')}
                className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1.5 min-h-[60px]"
                data-testid="lite-fault-steps-taken"
              />
              {/* Iter 216h299 — AI Triage Assessment dropdown. Lives
                  directly under Steps Already Taken (per BA request)
                  so the engineer sees the AI's read on what's
                  happening, then can add detail. Collapsible via
                  native <details> for zero new deps; opens by default
                  the first time triage results come back. */}
              {triageResult && isPro && (
                <details
                  className="mt-2 rounded-lg border border-[rgb(var(--rgb-brand-blue)/0.25)] bg-[rgb(var(--rgb-brand-blue)/0.08)]"
                  open
                  data-testid="ai-triage-result-dropdown"
                >
                  <summary className="cursor-pointer list-none px-3 py-2 flex items-center gap-2 text-sm font-semibold text-[var(--color-brand-cyan-hover)]">
                    <Sparkles size={14} />
                    <span className="flex-1">AI Triage Assessment</span>
                    <ChevronDown size={14} className="transition-transform [details[open]_&]:rotate-180" />
                  </summary>
                  <div className="px-3 pb-3 pt-1 space-y-2.5" data-testid="ai-triage-result">
                    {triageResult.warranty_notice && (
                      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3" data-testid="triage-warranty-notice">
                        <div className="flex items-center gap-2 mb-1">
                          <Shield size={14} className="text-amber-400" />
                          <span className="text-sm font-semibold text-amber-400">{triageResult.warranty_notice.title || 'Under manufacturer warranty'}</span>
                        </div>
                        <p className="text-xs text-[var(--theme-text)] leading-relaxed">{triageResult.warranty_notice.message}</p>
                        <p className="text-[11px] text-amber-300/90 mt-1.5 font-medium">Contact the manufacturer / authorised service agent before any repair — the AI triage below is informational only.</p>
                      </div>
                    )}
                    {triageResult.priority && (
                      <div className="text-xs"><span className="text-[var(--color-text-muted)]">Priority:</span> <span className="text-[var(--theme-text)] font-medium ml-1">{triageResult.priority}</span></div>
                    )}
                    {triageResult.diagnosis && (
                      <div><p className="text-xs text-[var(--color-text-muted)] mb-1">Diagnosis:</p><p className="text-sm text-[var(--theme-text)]">{triageResult.diagnosis}</p></div>
                    )}
                    {triageResult.fault_code && (
                      <div className="text-xs flex items-center gap-2" data-testid="lite-triage-fault-code">
                        <span className="text-[var(--color-text-muted)]">AI-suggested fault code:</span>
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold">
                          {triageResult.fault_code}
                        </span>
                      </div>
                    )}
                    {triageResult.repair_steps?.length > 0 && (
                      <div>
                        <p className="text-xs text-[var(--color-text-muted)] mb-1">Suggested Steps:</p>
                        <div className="space-y-1.5">
                          {triageResult.repair_steps.map((step, idx) => (
                            <div key={idx} className="flex gap-2 text-sm">
                              <span className="text-[var(--color-brand-cyan-hover)] font-bold text-xs mt-0.5">{idx + 1}.</span>
                              <span className="text-[var(--theme-text)]">{step.instruction || step}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {triageResult.parts_likely && (
                      <div className="text-xs"><span className="text-[var(--color-text-muted)]">Parts likely needed:</span> <span className="text-[var(--theme-text)] ml-1">{triageResult.parts_likely}</span></div>
                    )}
                    {triageResult.estimated_downtime && (
                      <div className="text-xs"><span className="text-[var(--color-text-muted)]">Est. downtime:</span> <span className="text-[var(--theme-text)] ml-1">{triageResult.estimated_downtime}</span></div>
                    )}
                  </div>
                </details>
              )}
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.severity', 'Severity')}</Label>
              <div className="grid gap-2 mt-2">
                {SEVERITY_OPTIONS.map(sev => (
                  <button key={sev.value} type="button" onClick={() => setFaultForm({ ...faultForm, severity: sev.value })} className={`w-full text-left p-3 rounded-lg border-2 transition-all ${faultForm.severity === sev.value ? 'border-[var(--color-brand-cyan-hover)] bg-[rgb(var(--rgb-brand-cyan-hover)/0.1)]' : 'border-[var(--theme-border)] hover:border-[var(--theme-border)] bg-[var(--theme-surface)]'}`} data-testid={`lite-sev-${sev.value}`}>
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-medium ${faultForm.severity === sev.value ? 'text-[var(--color-brand-cyan-hover)]' : 'text-[var(--theme-text)]'}`}>{t(`severity.${sev.value}`, sev.label)}</span>
                      {faultForm.severity === sev.value && <CheckCircle size={16} className="text-[var(--color-brand-cyan-hover)]" />}
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{t(`severity.${sev.value}_desc`, sev.desc)}</p>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <FaultCodeSelect
                API={API}
                value={faultForm.fault_code}
                onChange={(code) => setFaultForm({ ...faultForm, fault_code: code })}
              />
              <SaveAsTemplateButton
                API={API}
                issueForm={faultForm}
                privileged={isPro}
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] font-medium">{t('dialog.upload_media', 'Upload Photos / Videos')}</Label>
              <input ref={faultMediaInputRef} type="file" className="hidden" accept="image/*,video/*" multiple onChange={(e) => { faultUploadActiveRef.current = true; Array.from(e.target.files).forEach(f => onMediaUpload({ target: { files: [f] } })); e.target.value = ''; }} data-testid="lite-fault-media-input" />
              <div
                role="button"
                tabIndex={0}
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); faultUploadActiveRef.current = true; faultMediaInputRef.current?.click(); }}
                className="mt-1.5 flex items-center justify-center gap-2 p-4 border-2 border-dashed border-[var(--theme-border)] rounded-lg cursor-pointer hover:border-[var(--color-brand-cyan-hover)] hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.05)] transition-colors" data-testid="lite-fault-upload">
                <Camera size={20} className="text-[var(--color-text-muted)]" />
                <span className="text-sm text-[var(--color-text-muted)]">{faultMedia.length > 0 ? t('dialog.add_more_media', 'Add more photos/videos') : t('dialog.tap_upload', 'Tap to upload photos or videos')}</span>
              </div>
              {faultMedia.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {faultMedia.map((m, i) => (
                    <div key={i} className="flex items-center gap-1.5 bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-lg px-2.5 py-1.5 text-xs text-[var(--color-text-muted)]">
                      {m.type?.startsWith('video') ? <FileText size={12} /> : <Camera size={12} />}
                      <span className="max-w-[120px] truncate">{m.name}</span>
                      <X size={12} className="cursor-pointer hover:text-red-400 shrink-0" onClick={() => onRemoveMedia(i)} />
                    </div>
                  ))}
                </div>
              )}
            </div>
            {/* AI Triage Results moved into a dropdown under
                "Steps Already Taken" above — iter 216h299 (BA req).
                Submission UI below still gates on `triageResult`. */}

            {triageResult && isPro ? (
              showFixMethod ? (
                <div className="space-y-2" data-testid="fix-method-selection">
                  <p className="text-sm text-[var(--color-brand-cyan-hover)] font-medium">{t('dialog.how_fixed', 'How did you fix it?')}</p>
                  {FIX_METHODS.map(m => (
                    <button key={m.value} onClick={() => { setShowFixMethod(false); setTriageResult(null); onFaultSubmit({ resolution_type: 'self_fix', resolved_by: 'gymaxis_ai', fix_method: m.value, status: 'resolved' }); }}
                      className="w-full text-left p-3 rounded-lg border border-[var(--theme-border)] hover:border-[var(--color-brand-cyan-hover)] hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.05)] transition-all text-sm text-[var(--theme-text)]" data-testid={`fix-method-${m.value}`}>
                      {m.label}
                    </button>
                  ))}
                  <Button variant="ghost" onClick={() => setShowFixMethod(false)} className="w-full text-[var(--color-text-muted)] text-xs">Back</Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <Button onClick={() => setShowFixMethod(true)} disabled={submitting} variant="outline" className="flex-1 h-12 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 font-medium" data-testid="lite-fault-self-fix">
                      <Check size={18} className="mr-2" /> {t('dialog.i_fixed_it', 'I Fixed It')}
                    </Button>
                    <Button onClick={handleConfirmAfterTriage} disabled={submitting} className="flex-1 h-12 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white font-medium" data-testid="lite-fault-confirm-submit">
                      {submitting ? <Loader2 className="animate-spin mr-2" size={18} /> : <CheckCircle size={18} className="mr-2" />}
                      {stagedMachines.length > 0
                        ? t('dialog.submit_job', { count: stagedMachines.length + 1, defaultValue: 'Submit job ({{count}} machines)' })
                        : t('dialog.log_fault_report', 'Log Fault Report')}
                    </Button>
                  </div>
                  {/* Iter 216d — Add another machine to the same job (multi-machine flow). */}
                  {onAddMachineToJob && (
                    <Button
                      variant="outline"
                      onClick={() => { setTriageResult(null); onAddMachineToJob(); }}
                      disabled={submitting}
                      className="w-full h-10 border-[var(--theme-border)] text-[var(--color-brand-cyan-hover)] bg-transparent hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.05)] text-sm font-medium"
                      data-testid="lite-fault-add-another-machine"
                    >
                      + Add another machine to this job
                    </Button>
                  )}
                </div>
              )
            ) : isPro ? (
              <div className="space-y-2">
                <Button onClick={handleTriage} disabled={triaging || submitting || !faultForm.serial_number || !faultForm.issue_description} className="w-full h-12 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white font-medium text-base" data-testid="lite-fault-submit">
                  {triaging ? <><Loader2 className="animate-spin mr-2" size={18} /> {t('dialog.ai_analysing', 'AI Analysing...')}</> : <><Sparkles size={18} className="mr-2" /> {t('dialog.get_ai_triage', 'Get AI Triage & Submit')}</>}
                </Button>
                {/* Iter 216d — non-Pro users without triage can still queue
                    multiple machines: add this one and pick the next. */}
                {onAddMachineToJob && faultForm.serial_number && faultForm.issue_description && (
                  <Button
                    variant="outline"
                    onClick={() => onAddMachineToJob()}
                    disabled={submitting}
                    className="w-full h-10 border-[var(--theme-border)] text-[var(--color-brand-cyan-hover)] bg-transparent hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.05)] text-sm font-medium"
                    data-testid="lite-fault-add-another-machine-pretriage"
                  >
                    + Add another machine to this job
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {/* Iter 216h301 — wrap onFaultSubmit so React's click
                    event isn't passed in as `overrides`. The synthetic
                    event was spread into the payload by
                    `_buildMachinePayload(...overrides)`, leading to
                    POST failures (and confusing toast on Pulse Lite). */}
                <Button onClick={() => onFaultSubmit()} disabled={submitting || !faultForm.serial_number || !faultForm.issue_description} className="w-full h-12 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white font-medium text-base" data-testid="lite-fault-submit">
                  {submitting ? <Loader2 className="animate-spin mr-2" size={18} /> : <AlertTriangle size={18} className="mr-2" />}
                  {stagedMachines.length > 0
                    ? t('dialog.submit_job', { count: stagedMachines.length + 1, defaultValue: 'Submit job ({{count}} machines)' })
                    : t('dialog.submit_fault_report', 'Submit Fault Report')}
                </Button>
                {onAddMachineToJob && faultForm.serial_number && faultForm.issue_description && (
                  <Button
                    variant="outline"
                    onClick={() => onAddMachineToJob()}
                    disabled={submitting}
                    className="w-full h-10 border-[var(--theme-border)] text-[var(--color-brand-cyan-hover)] bg-transparent hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.05)] text-sm font-medium"
                    data-testid="lite-fault-add-another-machine-basic"
                  >
                    + Add another machine to this job
                  </Button>
                )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Duplicate Fault Modal — Portal to escape Radix Dialog focus trap */}
      {duplicateModal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60" data-testid="duplicate-fault-modal">
          <div className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-xl shadow-xl max-w-md w-full mx-4 p-6 text-center" style={{ pointerEvents: 'auto' }}>
            <div className="w-12 h-12 rounded-full bg-amber-500/20 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle size={24} className="text-amber-400" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--theme-text)] mb-2">Existing Fault Detected</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-6">
              There {duplicateModal.count === 1 ? 'is' : 'are'} already <strong className="text-[var(--theme-text)]">{duplicateModal.count} open fault{duplicateModal.count > 1 ? 's' : ''}</strong> logged for <strong className="text-[var(--theme-text)]">{duplicateModal.machineName}</strong>. Do you want to continue?
            </p>
            <div className="flex gap-3">
              <button className="flex-1 h-11 rounded-md border border-[var(--theme-border)] text-[var(--theme-text)] bg-transparent hover:bg-[var(--theme-surface-hover)] text-sm font-medium" onClick={onDuplicateCancel} data-testid="duplicate-cancel-btn">{t('dialog.cancel', 'Cancel')}</button>
              <button className="flex-1 h-11 rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white text-sm font-medium" onClick={onDuplicateContinue} data-testid="duplicate-continue-btn">Continue Logging</button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Fault Success Modal — Portal to escape Radix Dialog focus trap */}
      {successModal && ReactDOM.createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60" data-testid="fault-success-modal">
          <div className="bg-[var(--theme-surface)] border border-[var(--theme-border)] rounded-xl shadow-xl max-w-md w-full mx-4 p-6 text-center" style={{ pointerEvents: 'auto' }}>
            <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
              <CheckCircle size={24} className="text-emerald-400" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--theme-text)] mb-2">{successModal.count > 1 ? 'Job Logged Successfully' : 'Fault Logged Successfully'}</h3>
            <p className="text-sm text-[var(--color-text-muted)] mb-2">
              {successModal.count > 1
                ? `Your fault job covering ${successModal.count} machines has been submitted and assigned reference:`
                : 'Your fault report has been submitted and assigned reference:'}
            </p>
            <p className="text-xl font-bold text-[var(--color-brand-cyan-hover)] mb-6" data-testid="fault-ref-number">{successModal.ref}</p>
            <button className="w-full h-11 rounded-md bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white text-sm font-medium" onClick={onSuccessDismiss} data-testid="fault-success-ok-btn">OK</button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export default LiteDialogs;
// Iter 216n — expose `EquipmentDetailContent` so the Pulse Fitness dashboard
// can reuse the exact same all-in-one card layout (Pulse uses cyan,
// Pulse Fitness passes brandAccent="var(--color-brand-blue)" to switch the
// tab highlight to the Pulse Fitness blue without any visual fork).
export { EquipmentDetailContent };
