/**
 * EquipmentPhotoUpload
 * --------------------
 * Drop-in photo capture / upload for a single piece of equipment.
 *
 * UX:
 *   - If `photoUrl` is set → thumbnail with a "Replace" button on hover.
 *   - If not → dashed drop-zone with two CTAs: "Take Photo" (mobile camera,
 *     uses `capture="environment"`) and "Choose File" (desktop/gallery).
 *   - Drag-and-drop works on desktop (visual feedback on drag-over).
 *
 * Compression:
 *   - Runs 100% client-side via canvas — no extra npm dep.
 *   - Output: max 1920 px on the longest edge, JPEG q=0.82.
 *   - Typical 8 MB iPhone shot → ~400 KB upload. Saves bandwidth and
 *     keeps the S3/B2 storage bill sane.
 *
 * Contract:
 *   Props:
 *     equipmentId  (string, required)
 *     photoUrl     (string | null)
 *     onUploaded   (newUrl: string) => void
 *     apiBase      (string)  — e.g. `${REACT_APP_BACKEND_URL}/api`
 *     authToken    (string)  — Bearer token
 */
import React, { useRef, useState, useCallback } from 'react';
import { Camera, Upload, Loader2, RefreshCw, Sparkles } from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';

import { notify } from '@/components/notifications';
import EquipmentPlaceholder from './EquipmentPlaceholder';
const MAX_DIM = 1920;
const QUALITY = 0.82;
const MAX_RAW_BYTES = 20 * 1024 * 1024; // 20 MB absolute ceiling (pre-compression)
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'];

/** Compress any user-selected image file to a JPEG Blob. */
async function compressImage(file) {
  if (!file.type.startsWith('image/')) throw new Error('Not an image file');
  if (file.size > MAX_RAW_BYTES) throw new Error('File too large (max 20 MB)');

  // HEIC / HEIF on iOS: browsers often can't decode these via Image(). The
  // upload endpoint accepts the original bytes in that case — the backend
  // will serve them; compression is a best-effort optimisation, not a
  // requirement.
  const needsCompression = ['image/jpeg', 'image/png', 'image/webp'].includes(file.type);
  if (!needsCompression) return file;

  const dataUrl = await new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });

  const img = await new Promise((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = reject;
    i.src = dataUrl;
  });

  const scale = Math.min(1, MAX_DIM / Math.max(img.width, img.height));
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(img, 0, 0, w, h);

  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => {
        // Build a File so multipart upload keeps the filename.
        const filename = (file.name || 'equipment-photo').replace(/\.[^.]+$/, '') + '.jpg';
        resolve(new File([blob], filename, { type: 'image/jpeg' }));
      },
      'image/jpeg',
      QUALITY,
    );
  });
}

export default function EquipmentPhotoUpload({
  equipmentId,
  photoUrl,
  fallbackImageUrl,
  fallbackSource,
  autoImageSourceUrl,
  canAutoLookup,
  onAutoLookup,
  onUploaded,
  apiBase,
  authToken,
  // Used to render a uniform-style logo placeholder when we have nothing else.
  manufacturer,
  equipmentType,
  equipmentModel,
  testId = 'equipment-photo-upload',
}) {
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [progress, setProgress] = useState(0);

  const doUpload = useCallback(async (file) => {
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type) && !file.type.startsWith('image/')) {
      notify.error('Please choose an image file (JPG, PNG, WEBP, or HEIC)');
      return;
    }
    setUploading(true);
    setProgress(0);
    try {
      const compressed = await compressImage(file);
      const fd = new FormData();
      fd.append('file', compressed);

      const res = await axios.post(
        `${apiBase}/equipment/${equipmentId}/photo`,
        fd,
        {
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (e) => {
            if (e.total) setProgress(Math.round((e.loaded / e.total) * 100));
          },
        },
      );
      const url = res.data?.photo_url;
      if (!url) throw new Error('No URL returned');
      notify.success('Photo uploaded');
      onUploaded?.(url);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Upload failed';
      notify.error(`Upload failed: ${msg}`);
    } finally {
      setUploading(false);
      setProgress(0);
    }
  }, [apiBase, authToken, equipmentId, onUploaded]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) doUpload(file);
  }, [doUpload]);

  // ─── Render: existing photo ───────────────────────────────────
  if (photoUrl && !uploading) {
    return (
      <div className="relative group w-full" data-testid={testId}>
        <div className="relative w-full h-48 rounded-lg overflow-hidden bg-[var(--color-ink-alt)] border border-white/10">
          <img
            src={photoUrl}
            alt="Equipment"
            className="w-full h-full object-contain"
            onError={(e) => { e.target.style.display = 'none'; }}
            data-testid="equipment-photo-img"
          />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-white text-black text-xs font-semibold rounded-md hover:bg-white/90"
              data-testid="equipment-photo-replace-btn"
            >
              <RefreshCw size={12} /> Replace
            </button>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => doUpload(e.target.files?.[0])}
          data-testid="equipment-photo-file-input"
        />
      </div>
    );
  }

  // ─── Render: uploading progress ──────────────────────────────
  if (uploading) {
    return (
      <div
        className="w-full h-48 rounded-lg bg-[var(--color-ink-alt)] border border-white/10 flex flex-col items-center justify-center gap-3"
        data-testid={`${testId}-progress`}
      >
        <Loader2 className="animate-spin text-[var(--color-brand-cyan-hover)]" size={24} />
        <div className="w-48 h-1.5 bg-white/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-[var(--color-brand-cyan-hover)] transition-all duration-200"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-xs text-[var(--color-text-muted)]">
          {progress < 100 ? `Uploading… ${progress}%` : 'Processing…'}
        </p>
      </div>
    );
  }

  // ─── Render: spec-sheet / auto-image fallback (no user photo yet) ────
  // Priority: equipment.auto_image_url → spec-sheet image → upload CTA.
  // Owners can hover to swap for a real on-site photo. We keep the image
  // clean — no AI watermark badge — so the photo space is uncluttered.
  if (fallbackImageUrl) {
    return (
      <div className="relative group w-full" data-testid={`${testId}-fallback`}>
        <div className="relative w-full h-48 rounded-lg overflow-hidden bg-white/5 border border-white/10">
          <img
            src={fallbackImageUrl}
            alt="Equipment image"
            className="w-full h-full object-contain p-3"
            onError={(e) => { e.target.style.display = 'none'; }}
            data-testid="equipment-spec-fallback-img"
          />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/60 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
            <button
              onClick={() => cameraInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-[var(--color-brand-cyan-hover)] text-black text-[11px] font-semibold rounded-md hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.9)]"
              data-testid="equipment-photo-camera-btn"
            >
              <Camera size={12} /> Take
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-white text-black text-[11px] font-semibold rounded-md hover:bg-white/90"
              data-testid="equipment-photo-upload-btn"
            >
              <Upload size={12} /> Upload
            </button>
          </div>
        </div>
        <p className="text-[10px] text-[var(--color-text-faint-alt)] mt-1.5 text-center">
          Add a real photo to help engineers on site
        </p>
        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} data-testid="equipment-photo-camera-input" />
        <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => doUpload(e.target.files?.[0])} data-testid="equipment-photo-file-input" />
      </div>
    );
  }

  // ─── Render: empty state — uniform placeholder + upload CTAs overlay ─
  // The placeholder fills the same square the photo would occupy, with the
  // upload buttons and drag-drop hint hovering over a translucent layer.
  return (
    <div
      onDragEnter={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={`relative w-full h-48 rounded-lg overflow-hidden transition-shadow ${
        dragOver ? 'ring-2 ring-[var(--color-brand-cyan-hover)]' : ''
      }`}
      data-testid={testId}
    >
      <EquipmentPlaceholder
        manufacturer={manufacturer}
        equipmentType={equipmentType}
        model={equipmentModel}
        testId={`${testId}-placeholder`}
      />

      {/* Action overlay — visible by default at low opacity, brightens on hover */}
      <div className="absolute inset-0 flex flex-col items-center justify-end gap-2 p-3 pointer-events-none">
        <div className="flex flex-wrap gap-2 justify-center w-full max-w-sm pointer-events-auto">
          <button
            onClick={() => cameraInputRef.current?.click()}
            className="flex-1 min-w-[6.5rem] inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-[var(--color-brand-cyan-hover)] text-black text-[11px] font-semibold rounded-md hover:bg-[rgb(var(--rgb-brand-cyan-hover)/0.9)] transition shadow-md"
            data-testid="equipment-photo-camera-btn"
          >
            <Camera size={12} /> Take Photo
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex-1 min-w-[6.5rem] inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-white/95 text-black text-[11px] font-semibold rounded-md hover:bg-white transition shadow-md"
            data-testid="equipment-photo-upload-btn"
          >
            <Upload size={12} /> Upload
          </button>
        </div>
        {canAutoLookup ? (
          <button
            onClick={onAutoLookup}
            className="pointer-events-auto inline-flex items-center gap-1.5 px-2.5 py-1 bg-gradient-to-r from-blue-500 to-violet-500 text-white text-[10px] font-semibold rounded-md hover:opacity-90 transition shadow-md"
            data-testid="equipment-photo-autolookup-btn"
          >
            <Sparkles size={11} /> Find manufacturer photo
          </button>
        ) : null}
      </div>

      {/* Hidden inputs */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => doUpload(e.target.files?.[0])}
        data-testid="equipment-photo-camera-input"
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => doUpload(e.target.files?.[0])}
        data-testid="equipment-photo-file-input"
      />
    </div>
  );
}
