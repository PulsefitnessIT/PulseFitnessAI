/**
 * MOD Fault Wizard — 6 steps:
 *   1. Equipment picker (recent + search + QR scan)
 *   2. Fault type tiles
 *   3. Guided questions (description, onset, usable, safe_in_service)
 *   4. Attachments (client-side WebP compression + upload to /mod/site/attachments)
 *   5. Reporter contact (picker or + new)
 *   6. AI triage preview → submit
 *
 * Mobile-first: one step per screen, primary CTA bottom, back to previous state.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  X, ChevronLeft, ChevronRight, Search, AlertTriangle, Zap,
  Volume2, Wrench, ShieldAlert, HelpCircle, Camera, Check, Sparkles, Loader2,
  ScanLine, Image as ImageIcon, Film, Trash2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';
import MODStaffModal from './MODStaffModal';
import { enqueueFault, cacheListSnapshot, readCachedSnapshot } from '@/utils/offlineFaultQueue';

const FAULT_TYPES = [
  { id: 'not_working', label: 'Not working', icon: Wrench,       tone: 'amber' },
  { id: 'noise',       label: 'Noise',       icon: Volume2,      tone: 'sky' },
  { id: 'electrical',  label: 'Electrical',  icon: Zap,          tone: 'red' },
  { id: 'damage',      label: 'Damage',      icon: AlertTriangle,tone: 'orange' },
  { id: 'safety',      label: 'Safety',      icon: ShieldAlert,  tone: 'red' },
  { id: 'other',       label: 'Other',       icon: HelpCircle,   tone: 'zinc' },
];

const ONSETS = [
  { id: 'today',      label: 'Today' },
  { id: 'yesterday',  label: 'Yesterday' },
  { id: 'this_week',  label: 'This week' },
  { id: 'older',      label: 'Over a week ago' },
];

const USABLE = [
  { id: 'yes',     label: 'Yes', help: 'Fully functional, cosmetic issue only' },
  { id: 'limited', label: 'Limited', help: 'Works but reduced function' },
  { id: 'no',      label: 'No', help: 'Completely unusable' },
];

const SAFE = [
  { id: 'yes', label: 'Yes, safe to leave in service' },
  { id: 'no',  label: 'No — isolate immediately' },
];

export default function MODFaultWizard({ onClose, onSubmitted, prefillEquipmentId }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [step, setStep] = useState(1);
  const [equipment, setEquipment] = useState([]);
  const [staff, setStaff] = useState([]);
  const [search, setSearch] = useState('');
  const [staffPickerOpen, setStaffPickerOpen] = useState(false);

  const [form, setForm] = useState({
    equipment_id: prefillEquipmentId || '',
    fault_type: '',
    description: '',
    onset: '',
    usable: '',
    safe_in_service: '',
    attachment_urls: [],
    reporter_staff_id: '',
  });

  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(null); // {ticket_ref, priority, duplicate_of}

  const patch = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = useCallback(async () => {
    try {
      const [e, s] = await Promise.all([
        axios.get(`${API}/mod/site/equipment`, { headers }),
        axios.get(`${API}/mod/site/staff`, { headers }),
      ]);
      const eqList = e.data.equipment || [];
      const stList = s.data.staff || [];
      setEquipment(eqList);
      setStaff(stList);
      // Cache for offline wizard launches.
      cacheListSnapshot({ equipment: eqList, staff: stList });
    } catch {
      // Offline fallback — read the last good snapshot.
      const snap = readCachedSnapshot();
      if (snap.equipment.length || snap.staff.length) {
        setEquipment(snap.equipment);
        setStaff(snap.staff);
        notify.info('Offline — using last synced equipment & staff list');
      } else {
        notify.error('Failed to load site data');
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const selectedEquipment = useMemo(
    () => equipment.find((e) => e.id === form.equipment_id),
    [equipment, form.equipment_id],
  );
  const selectedStaff = useMemo(
    () => staff.find((s) => s.id === form.reporter_staff_id),
    [staff, form.reporter_staff_id],
  );

  const filteredEquipment = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return equipment;
    return equipment.filter((e) =>
      (e.name || '').toLowerCase().includes(q) ||
      (e.machine_type || '').toLowerCase().includes(q) ||
      (e.serial_number || '').toLowerCase().includes(q),
    );
  }, [equipment, search]);

  const canNext = stepValid(step, form);

  const goNext = async () => {
    if (!canNext) {
      notify.error(whyInvalid(step, form));
      return;
    }
    setStep((s) => Math.min(6, s + 1));
  };

  const goBack = () => setStep((s) => Math.max(1, s - 1));

  async function submitFault() {
    setSubmitting(true);
    try {
      const hasOfflineAttachment = (form.attachment_urls || []).some((a) => a && a.offline);
      const mustQueueOffline = !navigator.onLine || hasOfflineAttachment;

      if (mustQueueOffline) {
        // Hold form + raw blobs in IDB; the outer sync loop will upload
        // and submit when we get back online.
        const id = await enqueueFault({
          form: {
            equipment_id: form.equipment_id,
            fault_type: form.fault_type,
            description: form.description,
            onset: form.onset,
            usable: form.usable,
            safe_in_service: form.safe_in_service,
            reporter_staff_id: form.reporter_staff_id,
          },
          attachments: (form.attachment_urls || []).filter((a) => a && a.offline),
        });
        setConfirmation({
          ticket_ref: 'QUEUED',
          priority: 'medium',
          offline: true,
          queued_id: id,
        });
        notify.success('Saved offline — will sync when connection returns');
        return;
      }

      const { data } = await axios.post(`${API}/mod/site/faults`, {
        ...form,
        // Online path: send storage paths (not viewer URLs, which embed
        // tokens that expire).
        attachment_urls: (form.attachment_urls || []).map((a) => {
          if (typeof a === 'string') return a;
          return a.path || a.url;
        }),
      }, { headers });
      setConfirmation(data);
      notify.success(`Fault logged — ${data.ticket_ref}`);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to submit fault');
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmation) {
    return (
      <ConfirmationScreen
        confirmation={confirmation}
        onDone={() => { onSubmitted?.(); }}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-[70] bg-black/80 backdrop-blur-sm grid place-items-center p-0 sm:p-4" data-testid="mod-fault-wizard">
      <div className="w-full sm:max-w-xl h-full sm:h-auto sm:max-h-[92vh] bg-[var(--color-ink-deep)] sm:rounded-2xl border-0 sm:border border-white/10 flex flex-col">

        {/* Header with progress */}
        <div className="px-5 py-4 border-b border-white/10 bg-[var(--color-surface-darker)] sm:rounded-t-2xl">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">MOD Fault Wizard</div>
              <div className="text-white text-sm font-bold">Step {step} of 6</div>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-white/60" data-testid="mod-wizard-close"><X size={18} /></button>
          </div>
          <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${(step / 6) * 100}%` }} data-testid="mod-wizard-progress" />
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {step === 1 && (
            <StepEquipment
              equipment={filteredEquipment}
              search={search}
              setSearch={setSearch}
              selectedId={form.equipment_id}
              onPick={(id) => patch('equipment_id', id)}
            />
          )}
          {step === 2 && (
            <StepFaultType
              selected={form.fault_type}
              onPick={(id) => patch('fault_type', id)}
              machineName={selectedEquipment?.name}
            />
          )}
          {step === 3 && (
            <StepGuided form={form} patch={patch} />
          )}
          {step === 4 && (
            <StepAttachments
              urls={form.attachment_urls}
              onAdd={(u) => patch('attachment_urls', [...form.attachment_urls, u])}
              onRemove={(i) => patch('attachment_urls', form.attachment_urls.filter((_, idx) => idx !== i))}
            />
          )}
          {step === 5 && (
            <StepReporter
              staff={staff}
              selected={selectedStaff}
              onPick={(s) => patch('reporter_staff_id', s.id)}
              onAddNew={() => setStaffPickerOpen(true)}
            />
          )}
          {step === 6 && (
            <StepReview
              form={form}
              equipment={selectedEquipment}
              staff={selectedStaff}
            />
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-white/10 bg-[var(--color-surface-darker)] sm:rounded-b-2xl flex items-center justify-between gap-3">
          <button
            onClick={goBack}
            disabled={step === 1}
            className="flex items-center gap-1 px-3 py-2.5 rounded-lg text-sm font-bold text-white/80 border border-white/15 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white/5"
            data-testid="mod-wizard-back"
          >
            <ChevronLeft size={15} /> Back
          </button>
          {step < 6 ? (
            <button
              onClick={goNext}
              disabled={!canNext}
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: canNext ? 'var(--color-brand-cyan)' : '#2a3340', color: canNext ? 'var(--color-surface-darker)' : '#7a8796' }}
              data-testid="mod-wizard-next"
            >
              Continue
              <ChevronRight size={15} />
            </button>
          ) : (
            <button
              onClick={submitFault}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="mod-wizard-submit"
            >
              {submitting ? <><Loader2 size={15} className="animate-spin" /> Submitting…</> : <>Submit fault <Check size={15} /></>}
            </button>
          )}
        </div>
      </div>

      {staffPickerOpen && (
        <MODStaffModal
          onClose={() => { setStaffPickerOpen(false); load(); }}
          onPicked={(s) => {
            patch('reporter_staff_id', s.id);
            setStaffPickerOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
}


/* ─────────────────────── Individual steps ─────────────────────── */

function StepEquipment({ equipment, search, setSearch, selectedId, onPick }) {
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanError, setScanError] = useState(null);

  const handleScan = useCallback((rawValue) => {
    setScannerOpen(false);
    setScanError(null);
    // Accept either a full URL ".../scan/<id>" or a raw UUID.
    let scannedId = null;
    const m = /\/scan\/([0-9a-fA-F-]{8,})/.exec(rawValue || '');
    if (m) scannedId = m[1];
    else if (/^[0-9a-fA-F-]{20,}$/.test((rawValue || '').trim())) scannedId = rawValue.trim();
    if (!scannedId) {
      setScanError('QR did not look like a Pulse equipment tag.');
      return;
    }
    const hit = equipment.find((e) => e.id === scannedId);
    if (!hit) {
      setScanError('Scanned machine is not on this site.');
      return;
    }
    onPick(scannedId);
    notify.success(`Scanned — ${hit.name}`);
  }, [equipment, onPick]);

  return (
    <div data-testid="mod-step-equipment">
      <StepTitle eyebrow="Step 1" title="Which machine?" />
      <div className="flex gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, type, or serial"
            className="w-full rounded-lg bg-black/40 border border-white/10 pl-9 pr-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
            data-testid="mod-equipment-search"
          />
        </div>
        <button
          type="button"
          onClick={() => { setScanError(null); setScannerOpen(true); }}
          className="flex items-center gap-1.5 rounded-lg border border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-[rgb(var(--rgb-brand-cyan)/0.1)] text-[var(--color-brand-cyan)] px-3 py-2.5 text-sm font-bold hover:bg-[rgb(var(--rgb-brand-cyan)/0.2)]"
          data-testid="mod-equipment-qr-scan"
          title="Scan QR tag"
        >
          <ScanLine size={15} /> Scan
        </button>
      </div>
      {scanError && (
        <div className="mb-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-200" data-testid="mod-scan-error">
          {scanError}
        </div>
      )}
      {scannerOpen && (
        <QRScanInline onScan={handleScan} onClose={() => setScannerOpen(false)} />
      )}
      {equipment.length === 0 ? (
        <div className="text-center text-white/50 py-6 text-sm">No equipment matches.</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[50vh] overflow-y-auto">
          {equipment.map((e) => {
            const picked = e.id === selectedId;
            return (
              <button
                key={e.id}
                onClick={() => onPick(e.id)}
                className={`text-left rounded-xl border p-3 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]' : 'border-white/10 bg-white/[0.03] hover:border-white/25'}`}
                data-testid={`mod-equipment-${e.id}`}
              >
                <div className="font-bold text-white text-sm">{e.name}</div>
                <div className="text-xs text-white/60">{e.machine_type} · {e.serial_number}</div>
                {e.status === 'out_of_service' && (
                  <div className="text-[10px] font-bold text-red-300 mt-1 uppercase tracking-wider">Out of service</div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


/* In-wizard QR scanner — reuses browser BarcodeDetector (same pipeline as
   /scan/:id page). Inline (not a full-screen modal) so the user can back
   out easily with a single Cancel tap. */
function QRScanInline({ onScan, onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const scanningRef = useRef(true);
  const [nativeUnsupported, setNativeUnsupported] = useState(false);
  const [cameraDenied, setCameraDenied] = useState(false);

  const stop = useCallback(() => {
    scanningRef.current = false;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    let raf;
    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        if (!('BarcodeDetector' in window)) {
          setNativeUnsupported(true);
          return;
        }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        const tick = async () => {
          if (!scanningRef.current || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes.length > 0) {
              stop();
              onScan(codes[0].rawValue);
              return;
            }
          } catch { /* frame error */ }
          raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      } catch {
        setCameraDenied(true);
      }
    };
    start();
    return () => { cancelAnimationFrame(raf); stop(); };
  }, [onScan, stop]);

  if (cameraDenied) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 mb-3 text-sm text-red-200" data-testid="mod-scan-camera-denied">
        <Camera size={16} className="inline mr-1.5 -mt-0.5" />
        Camera access required. Enable it in your browser settings and try again.
        <button onClick={() => { stop(); onClose(); }} className="ml-3 underline font-bold">Close</button>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl overflow-hidden border border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-black mb-3" data-testid="mod-qr-scanner">
      <video ref={videoRef} className="w-full" playsInline muted style={{ maxHeight: '42vh', objectFit: 'cover' }} />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-44 h-44 border-2 border-[var(--color-brand-cyan)] rounded-2xl relative">
          <div className="absolute top-0 left-0 w-6 h-6 border-t-4 border-l-4 border-[var(--color-brand-cyan)] rounded-tl-xl" />
          <div className="absolute top-0 right-0 w-6 h-6 border-t-4 border-r-4 border-[var(--color-brand-cyan)] rounded-tr-xl" />
          <div className="absolute bottom-0 left-0 w-6 h-6 border-b-4 border-l-4 border-[var(--color-brand-cyan)] rounded-bl-xl" />
          <div className="absolute bottom-0 right-0 w-6 h-6 border-b-4 border-r-4 border-[var(--color-brand-cyan)] rounded-br-xl" />
          <div className="absolute left-2 right-2 top-1/2 h-0.5 bg-[rgb(var(--rgb-brand-cyan)/0.6)] animate-pulse" />
        </div>
      </div>
      <div className="absolute top-2 left-0 right-0 text-center">
        <span className="bg-black/70 text-white text-[11px] font-bold px-3 py-1 rounded-full">Point at the machine's QR tag</span>
      </div>
      {nativeUnsupported && (
        <div className="absolute bottom-12 left-0 right-0 text-center">
          <span className="bg-amber-600/90 text-white text-[10px] px-3 py-1 rounded-full">QR detection unavailable — use Chrome / Safari or pick from the list</span>
        </div>
      )}
      <div className="absolute bottom-2 left-0 right-0 text-center">
        <button onClick={() => { stop(); onClose(); }} className="rounded-full bg-black/70 text-white text-xs font-bold px-3 py-1.5 hover:bg-black/80" data-testid="mod-qr-cancel">
          <X size={12} className="inline mr-1 -mt-0.5" /> Cancel
        </button>
      </div>
    </div>
  );
}


function StepFaultType({ selected, onPick, machineName }) {
  return (
    <div data-testid="mod-step-fault-type">
      <StepTitle eyebrow="Step 2" title="What's wrong?" subtitle={machineName ? `With ${machineName}` : undefined} />
      <div className="grid grid-cols-2 gap-2.5">
        {FAULT_TYPES.map((t) => {
          const picked = t.id === selected;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => onPick(t.id)}
              className={`rounded-xl border p-4 flex flex-col items-center gap-2 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]' : 'border-white/10 bg-white/[0.03] hover:border-white/25'}`}
              data-testid={`mod-fault-type-${t.id}`}
            >
              <Icon size={26} className={picked ? 'text-[var(--color-brand-cyan)]' : 'text-white/70'} />
              <div className={`text-sm font-bold ${picked ? 'text-white' : 'text-white/80'}`}>{t.label}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}


function StepGuided({ form, patch }) {
  return (
    <div className="space-y-5" data-testid="mod-step-guided">
      <StepTitle eyebrow="Step 3" title="Tell us more" subtitle="≥ 40 characters so the engineer can prep before arrival" />
      <label className="block">
        <span className="text-[10px] font-bold uppercase tracking-wider text-white/60">Description *</span>
        <textarea
          value={form.description}
          onChange={(e) => patch('description', e.target.value)}
          rows={4}
          placeholder="e.g. belt slipping when incline > 5% under heavy user. Started making a clicking noise yesterday."
          className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
          data-testid="mod-field-description"
        />
        <div className="flex items-center justify-between mt-1 gap-3">
          <div className={`text-[10px] font-bold ${form.description.length >= 40 ? 'text-emerald-400' : 'text-white/50'}`}>
            {form.description.length} / 40 minimum
          </div>
          <div className="text-[10px] text-amber-300/80 font-semibold" data-testid="mod-field-classification-hint">
            ◆ OFFICIAL only — do NOT include NSN, operation names, callsigns or anything above OFFICIAL.
          </div>
        </div>
      </label>

      <RadioGroup
        label="When did it start? *"
        options={ONSETS}
        value={form.onset}
        onChange={(v) => patch('onset', v)}
        testidPrefix="mod-field-onset"
      />

      <RadioGroup
        label="Is it usable? *"
        options={USABLE}
        value={form.usable}
        onChange={(v) => patch('usable', v)}
        testidPrefix="mod-field-usable"
        withHelp
      />

      <RadioGroup
        label="Is it safe to leave in service? *"
        options={SAFE}
        value={form.safe_in_service}
        onChange={(v) => patch('safe_in_service', v)}
        testidPrefix="mod-field-safe"
        alert={form.safe_in_service === 'no'}
      />
      {form.safe_in_service === 'no' && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200 font-medium">
          ⚠ This machine will be auto-isolated and flagged URGENT. The on-call engineer will be paged.
        </div>
      )}
    </div>
  );
}


function StepAttachments({ urls, onAdd, onRemove }) {
  const { API } = useAuth();
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);
  const videoRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  const MAX_IMAGES = 4;
  const MAX_VIDEOS = 2;
  const imageCount = urls.filter((u) => u.kind === 'image').length;
  const videoCount = urls.filter((u) => u.kind === 'video').length;

  const uploadOne = async (file) => {
    if (!file) return;
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    if (!isImage && !isVideo) { notify.error('Pick a photo or short video'); return; }
    if (isImage && imageCount >= MAX_IMAGES) { notify.error(`Max ${MAX_IMAGES} photos`); return; }
    if (isVideo && videoCount >= MAX_VIDEOS) { notify.error(`Max ${MAX_VIDEOS} videos`); return; }
    if (isVideo && file.size > 50 * 1024 * 1024) { notify.error('Video too large (max 50 MB)'); return; }

    setUploading(true);
    setProgress(0);
    try {
      const payload = isImage ? await compressToWebP(file) : file;

      // If we're offline, skip the upload and capture the blob locally.
      // The outer flush loop will upload + link it at reconnect time.
      if (!navigator.onLine) {
        onAdd({
          offline: true,
          blob: payload,
          content_type: payload.type,
          filename: payload.name || file.name,
          kind: isImage ? 'image' : 'video',
          size: payload.size,
        });
        notify.info('Captured offline — will upload when back online');
        return;
      }

      const fd = new FormData();
      fd.append('file', payload, payload.name || file.name);
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/mod/site/attachments`, fd, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => { if (e.total) setProgress(Math.round((e.loaded / e.total) * 100)); },
      });
      const viewerUrl = `${API}/mod/site/attachments/serve?path=${encodeURIComponent(res.data.path)}&token=${encodeURIComponent(token)}`;
      onAdd({ path: res.data.path, url: viewerUrl, kind: res.data.kind, size: res.data.size });
      notify.success(`${isImage ? 'Photo' : 'Video'} added`);
    } catch (err) {
      // Network failure mid-upload? Fall through to offline capture.
      const networkish = !err.response || err.code === 'ERR_NETWORK';
      if (networkish && file) {
        onAdd({
          offline: true,
          blob: isImage ? await compressToWebP(file) : file,
          content_type: isImage ? 'image/webp' : file.type,
          filename: file.name,
          kind: isImage ? 'image' : 'video',
          size: file.size,
        });
        notify.info('Network unavailable — saved offline');
      } else {
        notifyApiError(notify, err, 'Upload failed');
      }
    } finally {
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div data-testid="mod-step-attachments">
      <StepTitle eyebrow="Step 4 (optional)" title="Photo or video?" subtitle="A picture saves 10 minutes on site" />

      {uploading ? (
        <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-[rgb(var(--rgb-brand-cyan)/0.05)] p-5 text-center">
          <Loader2 size={22} className="animate-spin text-[var(--color-brand-cyan)] mx-auto mb-2" />
          <div className="text-sm text-white font-semibold">Uploading… {progress}%</div>
          <div className="mt-2 h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => cameraRef.current?.click()}
            disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-[rgb(var(--rgb-brand-cyan)/0.05)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.1)] py-5 text-center text-[var(--color-brand-cyan)] disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="mod-attach-take-photo"
          >
            <Camera size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">Take Photo</div>
            <div className="text-[10px] opacity-70">{imageCount}/{MAX_IMAGES}</div>
          </button>
          <button
            type="button"
            onClick={() => galleryRef.current?.click()}
            disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed border-white/20 bg-white/[0.03] hover:bg-white/[0.06] py-5 text-center text-white/80 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="mod-attach-gallery"
          >
            <ImageIcon size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">From Gallery</div>
          </button>
          <button
            type="button"
            onClick={() => videoRef.current?.click()}
            disabled={videoCount >= MAX_VIDEOS}
            className="col-span-2 rounded-xl border border-dashed border-white/20 bg-white/[0.03] hover:bg-white/[0.06] py-3.5 text-center text-white/80 disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="mod-attach-video"
          >
            <Film size={18} className="inline mr-1.5 -mt-0.5" />
            <span className="text-xs font-bold">Video (up to 50 MB)</span>
            <span className="text-[10px] opacity-70 ml-2">{videoCount}/{MAX_VIDEOS}</span>
          </button>
        </div>
      )}

      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={galleryRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={videoRef} type="file" accept="video/*" capture="environment" className="hidden"
        onChange={(e) => uploadOne(e.target.files?.[0])} />

      {urls.length > 0 && (
        <div className="mt-3 grid grid-cols-3 sm:grid-cols-4 gap-2">
          {urls.map((a, i) => {
            const previewSrc = a.url || (a.blob ? URL.createObjectURL(a.blob) : null);
            return (
              <div key={i} className="relative aspect-square rounded-lg overflow-hidden border border-white/10 bg-black/40 group" data-testid={`mod-attachment-${i}`}>
                {a.kind === 'video' ? (
                  <video src={previewSrc} className="w-full h-full object-cover" muted />
                ) : (
                  <img src={previewSrc} alt="" className="w-full h-full object-cover" />
                )}
                <button
                  type="button"
                  onClick={() => onRemove(i)}
                  className="absolute top-1 right-1 rounded-full bg-black/70 hover:bg-red-500/90 text-white p-1"
                  data-testid={`mod-attachment-remove-${i}`}
                  aria-label="Remove"
                >
                  <Trash2 size={11} />
                </button>
                {a.kind === 'video' && (
                  <div className="absolute bottom-1 left-1 rounded bg-black/70 text-white text-[9px] px-1 py-0.5 font-bold">
                    <Film size={8} className="inline mr-0.5 -mt-0.5" /> VIDEO
                  </div>
                )}
                {a.offline && (
                  <div className="absolute bottom-1 right-1 rounded bg-amber-500/90 text-black text-[9px] px-1 py-0.5 font-extrabold uppercase tracking-wider">
                    Offline
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="text-center text-[10px] text-white/40 mt-3">You can skip this step.</div>
    </div>
  );
}


/* Client-side image compression: max edge 1920px, WebP q=0.82 → keeps
   most server payloads under 300 KB while preserving diagnosis detail. */
async function compressToWebP(file) {
  return new Promise((resolve, reject) => {
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
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(
          (blob) => {
            if (!blob) return reject(new Error('Compression failed'));
            resolve(new File([blob], `mod-${Date.now()}.webp`, { type: 'image/webp' }));
          },
          'image/webp',
          0.82,
        );
      };
      img.onerror = () => reject(new Error('Image load failed'));
      img.src = reader.result;
    };
    reader.onerror = () => reject(new Error('Read failed'));
    reader.readAsDataURL(file);
  });
}


function StepReporter({ staff, selected, onPick, onAddNew }) {
  return (
    <div data-testid="mod-step-reporter">
      <StepTitle
        eyebrow="Step 5"
        title="Who is reporting this?"
        subtitle="So our engineer can contact you and resolve faster."
      />
      <button
        onClick={onAddNew}
        className="w-full rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.4)] px-3 py-3 text-[var(--color-brand-cyan)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.05)] text-sm font-bold mb-3"
        data-testid="mod-reporter-add-new"
      >+ Add new contact</button>

      {staff.length === 0 ? (
        <div className="text-center text-white/50 py-6 text-sm">No staff yet — add one above.</div>
      ) : (
        <div className="space-y-2 max-h-[45vh] overflow-y-auto">
          {staff.map((s) => {
            const picked = s.id === selected?.id;
            return (
              <button
                key={s.id}
                onClick={() => onPick(s)}
                className={`w-full text-left rounded-xl border p-3 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]' : 'border-white/10 bg-white/[0.03] hover:border-white/25'}`}
                data-testid={`mod-reporter-${s.id}`}
              >
                <div className="font-bold text-white text-sm">{s.name} {s.role && <span className="text-white/50 font-normal">· {s.role}</span>}</div>
                <div className="text-xs text-white/60">{s.email} · {s.phone}</div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


function StepReview({ form, equipment, staff }) {
  return (
    <div className="space-y-3" data-testid="mod-step-review">
      <StepTitle eyebrow="Step 6" title="Review & submit" />

      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-2">
        <ReviewRow label="Machine" value={`${equipment?.name} · ${equipment?.serial_number}`} />
        <ReviewRow label="Fault type" value={FAULT_TYPES.find((t) => t.id === form.fault_type)?.label} />
        <ReviewRow label="Onset" value={ONSETS.find((t) => t.id === form.onset)?.label} />
        <ReviewRow label="Usable" value={USABLE.find((t) => t.id === form.usable)?.label} />
        <ReviewRow label="Safe in service" value={SAFE.find((t) => t.id === form.safe_in_service)?.label} />
        <ReviewRow label="Reporter" value={staff ? `${staff.name} · ${staff.email} · ${staff.phone}` : '—'} />
        <ReviewRow label="Description" value={form.description} multiline />
      </div>
    </div>
  );
}


function ReviewRow({ label, value, multiline }) {
  return (
    <div className={multiline ? 'pt-1' : 'flex items-start gap-3'}>
      <div className="text-[10px] font-bold uppercase tracking-wider text-white/50 w-28 shrink-0">{label}</div>
      <div className={`text-sm text-white/90 ${multiline ? 'mt-1' : 'flex-1'}`}>{value || '—'}</div>
    </div>
  );
}


function ConfirmationScreen({ confirmation, onDone }) {
  const isOffline = confirmation.offline;
  return (
    <div className="fixed inset-0 z-[70] bg-black/80 backdrop-blur-sm grid place-items-center p-4" data-testid="mod-fault-confirmation">
      <div className={`w-full max-w-md bg-[var(--color-ink-deep)] border rounded-2xl overflow-hidden p-8 text-center ${isOffline ? 'border-amber-500/40' : 'border-[rgb(var(--rgb-brand-cyan)/0.3)]'}`}>
        <div className={`w-16 h-16 rounded-full grid place-items-center mx-auto mb-4 ${isOffline ? 'bg-amber-500/20' : 'bg-emerald-500/20'}`}>
          {isOffline ? <Loader2 size={32} className="text-amber-300" /> : <Check size={32} className="text-emerald-400" />}
        </div>
        <div className={`text-[10px] font-bold uppercase tracking-[0.2em] mb-1 ${isOffline ? 'text-amber-300' : 'text-[var(--color-brand-cyan)]'}`}>
          {isOffline ? 'Saved offline' : 'Ticket created'}
        </div>
        <div className="text-2xl font-extrabold text-white mb-1 tracking-tight" data-testid="mod-confirmation-ref">
          {isOffline ? 'QUEUED' : confirmation.ticket_ref}
        </div>
        <div className={`inline-block text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded mt-1 ${priorityTone(confirmation.priority)}`}>
          {confirmation.priority}
        </div>
        {confirmation.duplicate_of && (
          <div className="mt-3 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
            ⚠ Similar open ticket exists: {confirmation.duplicate_of}
          </div>
        )}
        <p className="text-white/70 text-sm mt-4">
          {isOffline
            ? 'We\'ve stored this fault and its photos on your device. It will upload and create a MOD-XXXX ticket the moment you\'re back online.'
            : 'Confirmation email sent. You can track status on the dashboard.'}
        </p>
        <button
          onClick={onDone}
          className="mt-5 w-full rounded-lg px-4 py-3 text-sm font-extrabold"
          style={{ background: isOffline ? 'var(--color-warning)' : 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mod-confirmation-done"
        >Back to dashboard</button>
      </div>
    </div>
  );
}


/* ─────────────────────── Shared primitives ─────────────────────── */

function StepTitle({ eyebrow, title, subtitle }) {
  return (
    <div className="mb-4">
      <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">{eyebrow}</div>
      <h3 className="text-white text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em' }}>{title}</h3>
      {subtitle && <div className="text-sm text-white/60 mt-1">{subtitle}</div>}
    </div>
  );
}


function RadioGroup({ label, options, value, onChange, testidPrefix, withHelp, alert }) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-wider text-white/60 mb-1.5">{label}</div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {options.map((o) => {
          const picked = o.id === value;
          const bg = picked
            ? (alert ? 'border-red-500 bg-red-500/10' : 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.1)]')
            : 'border-white/10 bg-white/[0.03] hover:border-white/25';
          return (
            <button
              key={o.id}
              onClick={() => onChange(o.id)}
              className={`text-left rounded-lg border px-3 py-2.5 transition-all ${bg}`}
              data-testid={`${testidPrefix}-${o.id}`}
            >
              <div className="text-sm font-bold text-white">{o.label}</div>
              {withHelp && o.help && <div className="text-[10px] text-white/60 mt-0.5">{o.help}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}


function priorityTone(p) {
  return {
    urgent: 'bg-red-500/20 text-red-300',
    high:   'bg-orange-500/20 text-orange-300',
    medium: 'bg-amber-500/20 text-amber-300',
    low:    'bg-emerald-500/20 text-emerald-300',
  }[p] || 'bg-white/10 text-white/70';
}


/* ─────────────────────── Validation ─────────────────────── */

function stepValid(step, f) {
  switch (step) {
    case 1: return !!f.equipment_id;
    case 2: return !!f.fault_type;
    case 3: return f.description.trim().length >= 40 && !!f.onset && !!f.usable && !!f.safe_in_service;
    case 4: return true;
    case 5: return !!f.reporter_staff_id;
    case 6: return true;
    default: return false;
  }
}

function whyInvalid(step, f) {
  if (step === 1) return 'Pick the machine first';
  if (step === 2) return 'Pick a fault type';
  if (step === 3) {
    if (f.description.trim().length < 40) return 'Description must be at least 40 characters';
    if (!f.onset) return 'Pick when it started';
    if (!f.usable) return 'Say whether it\'s usable';
    if (!f.safe_in_service) return 'Say whether it\'s safe in service';
  }
  if (step === 5) return 'Pick a reporter so we can contact them';
  return 'Please complete this step';
}
