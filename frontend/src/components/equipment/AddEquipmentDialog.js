import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Loader2, Camera, X } from 'lucide-react';
import { notify } from '@/components/notifications';
import ManufacturerCombobox from './ManufacturerCombobox';
import DatePicker from '@/components/shared/DatePicker';
import SupplierAutocomplete from '@/components/shared/SupplierAutocomplete';
import { SLA_RESPONSE_TIME_OPTIONS, EQUIPMENT_LOCATION_PRESETS } from '@/utils/operationsDropdowns';

// Iter 216h193 — use the platform-wide SLA enum so reports compare
// across the estate. Kept the "Other" escape hatch for bespoke
// contracts that don't fit a standard tier.
const SLA_RESPONSE_OPTIONS = [
  ...SLA_RESPONSE_TIME_OPTIONS.filter((o) => o.value !== 'custom'),
  { value: '__other__', label: 'Other (enter manually)' },
];

const EMPTY_FORM = {
  name: '',
  equipment_type: '',
  manufacturer: '',
  model: '',
  serial_number: '',
  location: '',
  purchase_date: '',
  warranty_expiry: '',
  sla_response_time: '48h',
  sla_response_other: '',
  sla_contract_ref: '',
  sla_expiry: '',
  notes: '',
};

/**
 * Iter 224 — single-machine "Add Equipment" dialog used from the
 * Pulse Fitness Equipment tab. Replaces the old multi-step onboarding
 * wizard for the common case of "I just bought one new bike, log it".
 *
 * UX rules from operator feedback:
 *  - Manufacturer = searchable dropdown of curated brands + "Other".
 *  - SLA Response Time = 48h / 72h / Other (free text fallback).
 *  - Purchase / Warranty / SLA Expiry = native date pickers.
 *  - Photo upload at create-time (not just edit) — uploaded after the
 *    record is created via POST /api/equipment/{id}/photo.
 */
const AddEquipmentDialog = ({ open, onClose, onCreated }) => {
  const { API } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setForm(EMPTY_FORM);
    setPhotoFile(null);
    setPhotoPreview(null);
  }, [open]);

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }));

  const handlePhotoPick = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      notify.error('Please choose an image file (JPG, PNG, HEIC).');
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      notify.error('Photo too large — please pick something under 12 MB.');
      return;
    }
    setPhotoFile(file);
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhotoPreview(URL.createObjectURL(file));
  };

  const clearPhoto = () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhotoFile(null);
    setPhotoPreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.equipment_type.trim()) {
      notify.error('Name and Equipment Type are required.');
      return;
    }
    setSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const sla_response_time = form.sla_response_time === '__other__'
        ? form.sla_response_other.trim()
        : form.sla_response_time;
      const payload = {
        name: form.name.trim(),
        equipment_type: form.equipment_type.trim(),
        manufacturer: form.manufacturer.trim() || null,
        model: form.model.trim() || null,
        serial_number: form.serial_number.trim() || null,
        location: form.location.trim() || null,
        purchase_date: form.purchase_date || null,
        warranty_expiry: form.warranty_expiry || null,
        sla_response_time: sla_response_time || null,
        sla_contract_ref: form.sla_contract_ref.trim() || null,
        sla_expiry: form.sla_expiry || null,
        notes: form.notes.trim() || null,
      };
      const r = await axios.post(`${API}/equipment`, payload, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const created = r.data;

      // Photo upload (best-effort — equipment is already saved).
      if (photoFile && created?.id) {
        try {
          const fd = new FormData();
          fd.append('file', photoFile);
          await axios.post(`${API}/equipment/${created.id}/photo`, fd, {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'multipart/form-data',
            },
          });
        } catch (err) {
          notify.warning('Equipment saved, but the photo failed to upload — try the Edit dialog.', err.response?.data?.detail);
        }
      }

      notify.success(`Added "${created.name}"`, 'Equipment is now visible in your fleet.');
      try {
        window.dispatchEvent(new CustomEvent('gymaxis:equipment-added', { detail: { count: 1 } }));
      } catch (_) { /* no-op */ }
      onCreated && onCreated(created);
      onClose && onClose();
    } catch (err) {
      notify.error('Could not add equipment', err.response?.data?.detail || 'Please try again.');
    }
    setSubmitting(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose && onClose(); }}>
      <DialogContent
        className="bg-[var(--theme-surface)] border-white/10 text-white max-w-2xl max-h-[90vh] overflow-y-auto"
        data-testid="add-equipment-dialog-iter224"
      >
        <DialogHeader>
          <DialogTitle className="text-white">Add Equipment</DialogTitle>
          <p className="text-[var(--color-text-muted)] text-xs mt-1">
            Logs a single machine onto your fleet. For bulk imports use the AI Invoice Import or onboarding wizard.
          </p>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Name *</Label>
              <Input
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
                placeholder="e.g. Treadmill 1"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-name"
                required
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Equipment Type *</Label>
              <Input
                value={form.equipment_type}
                onChange={(e) => setField('equipment_type', e.target.value)}
                placeholder="e.g. Treadmill, Spin Bike"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-type"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Manufacturer</Label>
              <ManufacturerCombobox
                value={form.manufacturer}
                onChange={(v) => setField('manufacturer', v)}
                testId="add-equip-manufacturer"
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Model</Label>
              <Input
                value={form.model}
                onChange={(e) => setField('model', e.target.value)}
                placeholder="e.g. T5-Go"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-model"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Serial Number</Label>
              <Input
                value={form.serial_number}
                onChange={(e) => setField('serial_number', e.target.value)}
                placeholder="SN123456789"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-serial"
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Location</Label>
              <Input
                value={form.location}
                onChange={(e) => setField('location', e.target.value)}
                placeholder="e.g. Cardio Zone"
                list="add-equip-location-presets"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-location"
              />
              <datalist id="add-equip-location-presets">
                {EQUIPMENT_LOCATION_PRESETS.map((loc) => <option key={loc} value={loc} />)}
              </datalist>
            </div>
          </div>

          {/* Date pickers — DD/MM/YYYY platform-standard */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Purchase Date</Label>
              <DatePicker
                value={form.purchase_date}
                onChange={(iso) => setField('purchase_date', iso)}
                placeholder="DD/MM/YYYY"
                inputClassName="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                testid="add-equip-purchase-date"
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">Warranty Expiry</Label>
              <DatePicker
                value={form.warranty_expiry}
                onChange={(iso) => setField('warranty_expiry', iso)}
                placeholder="DD/MM/YYYY"
                inputClassName="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                testid="add-equip-warranty-expiry"
              />
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">SLA Expiry</Label>
              <DatePicker
                value={form.sla_expiry}
                onChange={(iso) => setField('sla_expiry', iso)}
                placeholder="DD/MM/YYYY"
                inputClassName="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                testid="add-equip-sla-expiry"
              />
            </div>
          </div>

          {/* SLA Response Time */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">SLA Response Time</Label>
              <select
                value={form.sla_response_time}
                onChange={(e) => setField('sla_response_time', e.target.value)}
                className="w-full bg-[var(--color-ink-alt)] border border-white/10 text-white mt-1 rounded-md px-3 py-2 text-sm"
                data-testid="add-equip-sla-response"
              >
                {SLA_RESPONSE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              {form.sla_response_time === '__other__' && (
                <Input
                  value={form.sla_response_other}
                  onChange={(e) => setField('sla_response_other', e.target.value)}
                  placeholder="e.g. 4 hours, Next business day"
                  className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-2"
                  data-testid="add-equip-sla-response-other"
                />
              )}
            </div>
            <div>
              <Label className="text-[var(--color-text-muted)] text-sm">SLA Contract Reference</Label>
              <Input
                value={form.sla_contract_ref}
                onChange={(e) => setField('sla_contract_ref', e.target.value)}
                placeholder="Contract reference"
                className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
                data-testid="add-equip-sla-contract"
              />
            </div>
          </div>

          {/* Photo upload */}
          <div>
            <Label className="text-[var(--color-text-muted)] text-sm">Photo (optional)</Label>
            {photoPreview ? (
              <div className="relative mt-1 inline-block">
                <img
                  src={photoPreview}
                  alt="Preview"
                  className="h-32 w-32 object-cover rounded-md border border-white/10"
                  data-testid="add-equip-photo-preview"
                />
                <button
                  type="button"
                  onClick={clearPhoto}
                  className="absolute -top-2 -right-2 bg-red-500 hover:bg-red-600 text-white rounded-full p-1"
                  data-testid="add-equip-photo-clear"
                  aria-label="Remove photo"
                >
                  <X size={12} />
                </button>
              </div>
            ) : (
              <label className="mt-1 flex items-center justify-center gap-2 border-2 border-dashed border-white/10 rounded-md p-4 cursor-pointer hover:border-[rgb(var(--rgb-brand-blue)/0.4)] transition-colors" data-testid="add-equip-photo-dropzone">
                <Camera size={16} className="text-[var(--color-text-muted)]" />
                <span className="text-[var(--color-text-muted)] text-xs">
                  Tap to upload a machine photo (JPG/PNG, ≤12 MB)
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handlePhotoPick}
                  className="hidden"
                  data-testid="add-equip-photo-input"
                />
              </label>
            )}
          </div>

          <div>
            <Label className="text-[var(--color-text-muted)] text-sm">Notes</Label>
            <Input
              value={form.notes}
              onChange={(e) => setField('notes', e.target.value)}
              placeholder="Anything else worth knowing"
              className="bg-[var(--color-ink-alt)] border-white/10 text-white mt-1"
              data-testid="add-equip-notes"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              className="border-white/10 text-[var(--color-text-muted)] hover:text-white"
              data-testid="add-equip-cancel-btn"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
              data-testid="add-equip-submit-btn"
            >
              {submitting ? (
                <><Loader2 size={14} className="mr-2 animate-spin" /> Saving…</>
              ) : 'Add equipment'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AddEquipmentDialog;
