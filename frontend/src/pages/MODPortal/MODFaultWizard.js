/**
 * MOD Fault Wizard — multi-machine, theme-aware (follows the app light/dark toggle).
 *
 * Flow:
 *   1. Equipment picker — MULTI-select, grouped by location, search + QR scan.
 *   For EACH selected machine, in turn:
 *     A. Fault type tiles
 *     B. Guided questions (description, onset, usable, safe_in_service)
 *     C. Attachments (client-side WebP compression + upload)
 *   Then once:
 *     - Reporter contact
 *     - Review → submit (one ticket PER machine, each with its own SLA/email)
 *
 * Mobile-first: one screen at a time, primary CTA bottom. No AI triage.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  X, ChevronLeft, ChevronRight, Search, AlertTriangle, Zap,
  Volume2, Wrench, ShieldAlert, HelpCircle, Camera, Check, Loader2,
  ScanLine, Image as ImageIcon, Film, Trash2, MapPin,
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

const emptyMachineData = () => ({
  fault_type: '',
  description: '',
  onset: '',
  usable: '',
  safe_in_service: '',
  attachment_urls: [],
});

export default function MODFaultWizard({ onClose, onSubmitted, prefillEquipmentId }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  // ── Navigation state ────────────────────────────────────────────
  // phase: 'equipment' | 'machine' | 'reporter' | 'review'
  // sub (machine phase only): 0=fault type, 1=guided, 2=attachments
  const [phase, setPhase] = useState('equipment');
  const [mi, setMi] = useState(0);   // index into selectedIds
  const [sub, setSub] = useState(0);

  const [equipment, setEquipment] = useState([]);
  const [staff, setStaff] = useState([]);
  const [search, setSearch] = useState('');
  const [staffPickerOpen, setStaffPickerOpen] = useState(false);

  const [selectedIds, setSelectedIds] = useState(prefillEquipmentId ? [prefillEquipmentId] : []);
  const [machineData, setMachineData] = useState(
    prefillEquipmentId ? { [prefillEquipmentId]: emptyMachineData() } : {},
  );
  const [reporterStaffId, setReporterStaffId] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(null); // { tickets: [...], offline? }

  const equipById = useCallback((id) => equipment.find((e) => e.id === id), [equipment]);
  const currentId = selectedIds[mi];
  const currentData = machineData[currentId] || emptyMachineData();
  const patchMachine = (k, v) =>
    setMachineData((m) => ({ ...m, [currentId]: { ...(m[currentId] || emptyMachineData()), [k]: v } }));

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
      cacheListSnapshot({ equipment: eqList, staff: stList });
    } catch {
      const snap = readCachedSnapshot();
      if (snap.equipment.length || snap.staff.length) {
        setEquipment(snap.equipment);
        setStaff(snap.staff);
        notify.info('Offline — using last synced equipment & staff list');
      } else {
        notify.error('Failed to load site data');
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const selectedStaff = useMemo(
    () => staff.find((s) => s.id === reporterStaffId),
    [staff, reporterStaffId],
  );

  const toggleMachine = (id) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      return [...prev, id];
    });
    setMachineData((m) => (m[id] ? m : { ...m, [id]: emptyMachineData() }));
  };

  const totalScreens = 1 + selectedIds.length * 3 + 2;
  const currentScreen = useMemo(() => {
    if (phase === 'equipment') return 1;
    if (phase === 'machine') return 1 + mi * 3 + sub + 1;
    if (phase === 'reporter') return 1 + selectedIds.length * 3 + 1;
    return totalScreens;
  }, [phase, mi, sub, selectedIds.length, totalScreens]);

  const canNext = useMemo(() => {
    if (phase === 'equipment') return selectedIds.length > 0;
    if (phase === 'machine') {
      if (sub === 0) return !!currentData.fault_type;
      if (sub === 1) return currentData.description.trim().length >= 40 && !!currentData.onset && !!currentData.usable && !!currentData.safe_in_service;
      return true; // attachments optional
    }
    if (phase === 'reporter') return !!reporterStaffId;
    return true;
  }, [phase, sub, selectedIds.length, currentData, reporterStaffId]);

  const whyInvalid = () => {
    if (phase === 'equipment') return 'Select at least one machine';
    if (phase === 'machine') {
      if (sub === 0) return 'Pick a fault type for this machine';
      if (sub === 1) {
        if (currentData.description.trim().length < 40) return 'Description must be at least 40 characters';
        if (!currentData.onset) return 'Pick when it started';
        if (!currentData.usable) return "Say whether it's usable";
        if (!currentData.safe_in_service) return "Say whether it's safe in service";
      }
    }
    if (phase === 'reporter') return 'Pick a reporter so we can contact them';
    return 'Please complete this step';
  };

  const goNext = () => {
    if (!canNext) { notify.error(whyInvalid()); return; }
    if (phase === 'equipment') { setPhase('machine'); setMi(0); setSub(0); return; }
    if (phase === 'machine') {
      if (sub < 2) { setSub(sub + 1); return; }
      if (mi < selectedIds.length - 1) { setMi(mi + 1); setSub(0); return; }
      setPhase('reporter'); return;
    }
    if (phase === 'reporter') { setPhase('review'); return; }
  };

  const goBack = () => {
    if (phase === 'review') { setPhase('reporter'); return; }
    if (phase === 'reporter') { setPhase('machine'); setMi(selectedIds.length - 1); setSub(2); return; }
    if (phase === 'machine') {
      if (sub > 0) { setSub(sub - 1); return; }
      if (mi > 0) { setMi(mi - 1); setSub(2); return; }
      setPhase('equipment'); return;
    }
  };

  async function submitAll() {
    setSubmitting(true);
    try {
      const hasOfflineAttachment = selectedIds.some(
        (id) => (machineData[id]?.attachment_urls || []).some((a) => a && a.offline),
      );
      const mustQueueOffline = !navigator.onLine || hasOfflineAttachment;
      const tickets = [];
      const failed = [];

      if (mustQueueOffline) {
        for (const id of selectedIds) {
          const md = machineData[id] || emptyMachineData();
          await enqueueFault({
            form: {
              equipment_id: id,
              fault_type: md.fault_type,
              description: md.description,
              onset: md.onset,
              usable: md.usable,
              safe_in_service: md.safe_in_service,
              reporter_staff_id: reporterStaffId,
            },
            attachments: (md.attachment_urls || []).filter((a) => a && a.offline),
          });
          tickets.push({ ticket_ref: 'QUEUED', priority: md.safe_in_service === 'no' ? 'urgent' : 'medium', offline: true, machine: equipById(id) });
        }
        setConfirmation({ offline: true, tickets });
        notify.success('Saved offline — will sync when connection returns');
        return;
      }

      for (const id of selectedIds) {
        const md = machineData[id] || emptyMachineData();
        try {
          const { data } = await axios.post(`${API}/mod/site/faults`, {
            equipment_id: id,
            fault_type: md.fault_type,
            description: md.description,
            onset: md.onset,
            usable: md.usable,
            safe_in_service: md.safe_in_service,
            reporter_staff_id: reporterStaffId,
            attachment_urls: (md.attachment_urls || []).map((a) => (typeof a === 'string' ? a : (a.path || a.url))),
          }, { headers });
          tickets.push({ ...data, machine: equipById(id) });
        } catch (err) {
          failed.push({ id, name: equipById(id)?.name || equipById(id)?.serial_number || 'Machine', err });
        }
      }

      if (tickets.length === 0) {
        // Nothing succeeded — surface the error, keep the form so they can retry.
        notifyApiError(notify, failed[0]?.err, 'Failed to submit fault');
        return;
      }
      if (failed.length > 0) {
        // Partial success — confirm the ones that went through (so they're not
        // lost / re-submitted), and name the failures so the user can retry them.
        notify.error(`${tickets.length} of ${selectedIds.length} logged`, `Couldn't log: ${failed.map((f) => f.name).join(', ')}. Please reopen and retry these.`);
      } else {
        notify.success(tickets.length > 1 ? `${tickets.length} faults logged` : `Fault logged — ${tickets[0].ticket_ref}`);
      }
      setConfirmation({ tickets, partialFailed: failed.map((f) => f.name) });
    } catch (e) {
      notifyApiError(notify, e, 'Failed to submit fault');
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmation) {
    return <ConfirmationScreen confirmation={confirmation} onDone={() => onSubmitted?.()} />;
  }

  const machineName = equipById(currentId)?.name;
  const headerLabel = phase === 'equipment'
    ? 'Select machines'
    : phase === 'machine'
      ? `Machine ${mi + 1} of ${selectedIds.length}${machineName ? ` · ${machineName}` : ''}`
      : phase === 'reporter'
        ? 'Reporter'
        : 'Review & submit';

  return (
    <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm grid place-items-center p-0 sm:p-4" data-testid="mod-fault-wizard">
      <div
        className="w-full sm:max-w-xl h-full sm:h-auto sm:max-h-[92vh] sm:rounded-2xl border-0 sm:border flex flex-col"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      >
        {/* Header with progress */}
        <div
          className="px-5 py-4 border-b sm:rounded-t-2xl"
          style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)' }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="min-w-0">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">MOD Fault Wizard</div>
              <div className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{headerLabel}</div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"
              style={{ color: 'var(--theme-text-muted)' }}
              data-testid="mod-wizard-close"
            ><X size={18} /></button>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--theme-surface-3)' }}>
            <div className="h-full bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${(currentScreen / totalScreens) * 100}%` }} data-testid="mod-wizard-progress" />
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {phase === 'equipment' && (
            <StepEquipment
              allEquipment={equipment}
              search={search}
              setSearch={setSearch}
              selectedIds={selectedIds}
              onToggle={toggleMachine}
            />
          )}
          {phase === 'machine' && sub === 0 && (
            <StepFaultType
              selected={currentData.fault_type}
              onPick={(id) => patchMachine('fault_type', id)}
              machineName={machineName}
              machineIndex={mi}
              machineTotal={selectedIds.length}
            />
          )}
          {phase === 'machine' && sub === 1 && (
            <StepGuided data={currentData} patch={patchMachine} machineName={machineName} />
          )}
          {phase === 'machine' && sub === 2 && (
            <StepAttachments
              urls={currentData.attachment_urls}
              onAdd={(u) => patchMachine('attachment_urls', [...currentData.attachment_urls, u])}
              onRemove={(i) => patchMachine('attachment_urls', currentData.attachment_urls.filter((_, idx) => idx !== i))}
              machineName={machineName}
            />
          )}
          {phase === 'reporter' && (
            <StepReporter
              staff={staff}
              selected={selectedStaff}
              onPick={(s) => setReporterStaffId(s.id)}
              onAddNew={() => setStaffPickerOpen(true)}
            />
          )}
          {phase === 'review' && (
            <StepReview
              selectedIds={selectedIds}
              machineData={machineData}
              equipById={equipById}
              staff={selectedStaff}
            />
          )}
        </div>

        {/* Footer */}
        <div
          className="px-5 py-3 border-t sm:rounded-b-2xl flex items-center justify-between gap-3"
          style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)' }}
        >
          <button
            onClick={goBack}
            disabled={phase === 'equipment'}
            className="flex items-center gap-1 px-3 py-2.5 rounded-lg text-sm font-bold border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/5"
            style={{ color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}
            data-testid="mod-wizard-back"
          >
            <ChevronLeft size={15} /> Back
          </button>
          {phase !== 'review' ? (
            <button
              onClick={goNext}
              disabled={!canNext}
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: canNext ? 'var(--color-brand-cyan)' : 'var(--theme-surface-3)', color: canNext ? '#04121a' : 'var(--theme-text-muted)' }}
              data-testid="mod-wizard-next"
            >
              {phase === 'equipment' && selectedIds.length > 0 ? `Continue with ${selectedIds.length} machine${selectedIds.length > 1 ? 's' : ''}` : 'Continue'}
              <ChevronRight size={15} />
            </button>
          ) : (
            <button
              onClick={submitAll}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold"
              style={{ background: 'var(--color-brand-cyan)', color: '#04121a' }}
              data-testid="mod-wizard-submit"
            >
              {submitting
                ? <><Loader2 size={15} className="animate-spin" /> Submitting…</>
                : <>Submit {selectedIds.length > 1 ? `${selectedIds.length} faults` : 'fault'} <Check size={15} /></>}
            </button>
          )}
        </div>
      </div>

      {staffPickerOpen && (
        <MODStaffModal
          onClose={() => { setStaffPickerOpen(false); load(); }}
          onPicked={(s) => {
            setReporterStaffId(s.id);
            setStaffPickerOpen(false);
            load();
          }}
        />
      )}
    </div>
  );
}


/* ─────────────────────── Individual steps ─────────────────────── */

function StepEquipment({ allEquipment, search, setSearch, selectedIds, onToggle }) {
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanError, setScanError] = useState(null);

  const handleScan = useCallback((rawValue) => {
    setScannerOpen(false);
    setScanError(null);
    let scannedId = null;
    const m = /\/scan\/([0-9a-fA-F-]{8,})/.exec(rawValue || '');
    if (m) scannedId = m[1];
    else if (/^[0-9a-fA-F-]{20,}$/.test((rawValue || '').trim())) scannedId = rawValue.trim();
    if (!scannedId) { setScanError('QR did not look like a Pulse equipment tag.'); return; }
    const hit = allEquipment.find((e) => e.id === scannedId);
    if (!hit) { setScanError('Scanned machine is not on this site.'); return; }
    if (!selectedIds.includes(scannedId)) onToggle(scannedId);
    notify.success(`Added — ${hit.name}`);
  }, [allEquipment, onToggle, selectedIds]);

  // Filter, then group by location.
  const groups = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = !q ? allEquipment : allEquipment.filter((e) =>
      (e.name || '').toLowerCase().includes(q) ||
      (e.machine_type || '').toLowerCase().includes(q) ||
      (e.serial_number || '').toLowerCase().includes(q) ||
      (e.location || '').toLowerCase().includes(q));
    const byLoc = {};
    for (const e of filtered) {
      const loc = (e.location || '').trim() || 'Unassigned';
      (byLoc[loc] = byLoc[loc] || []).push(e);
    }
    // Sort: named locations alphabetically, "Unassigned" last.
    return Object.keys(byLoc)
      .sort((a, b) => (a === 'Unassigned' ? 1 : b === 'Unassigned' ? -1 : a.localeCompare(b)))
      .map((loc) => ({ loc, items: byLoc[loc] }));
  }, [allEquipment, search]);

  const multiLocation = groups.filter((g) => g.loc !== 'Unassigned').length > 1
    || (groups.length > 1);
  const totalShown = groups.reduce((n, g) => n + g.items.length, 0);

  return (
    <div data-testid="mod-step-equipment">
      <StepTitle eyebrow="Step 1" title="Which machines?" subtitle="Tick every machine you're reporting — you'll describe each one's fault next." />
      {selectedIds.length > 0 && (
        <div className="mb-3 text-xs font-bold" style={{ color: 'var(--color-brand-cyan)' }} data-testid="mod-equipment-selected-count">
          {selectedIds.length} machine{selectedIds.length > 1 ? 's' : ''} selected
        </div>
      )}
      <div className="flex gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, type, serial or location"
            className="w-full rounded-lg border pl-9 pr-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
            style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="mod-equipment-search"
          />
        </div>
        <button
          type="button"
          onClick={() => { setScanError(null); setScannerOpen(true); }}
          className="flex items-center gap-1.5 rounded-lg border border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-[rgb(var(--rgb-brand-cyan)/0.12)] text-[var(--color-brand-cyan)] px-3 py-2.5 text-sm font-bold hover:bg-[rgb(var(--rgb-brand-cyan)/0.2)]"
          data-testid="mod-equipment-qr-scan"
          title="Scan QR tag"
        >
          <ScanLine size={15} /> Scan
        </button>
      </div>
      {scanError && (
        <div className="mb-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-600 dark:text-amber-300" data-testid="mod-scan-error">
          {scanError}
        </div>
      )}
      {scannerOpen && <QRScanInline onScan={handleScan} onClose={() => setScannerOpen(false)} />}

      {totalShown === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No equipment matches.</div>
      ) : (
        <div className="max-h-[52vh] overflow-y-auto space-y-4">
          {groups.map((g) => (
            <div key={g.loc} data-testid={`mod-equipment-group-${g.loc.replace(/\s+/g, '-').toLowerCase()}`}>
              {multiLocation && (
                <div className="flex items-center gap-1.5 mb-2 sticky top-0 py-1 z-[1]" style={{ background: 'var(--theme-surface)' }}>
                  <MapPin size={12} style={{ color: 'var(--color-brand-cyan)' }} />
                  <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{g.loc}</span>
                  <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>· {g.items.length}</span>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {g.items.map((e) => {
                  const picked = selectedIds.includes(e.id);
                  return (
                    <button
                      key={e.id}
                      onClick={() => onToggle(e.id)}
                      className={`text-left rounded-xl border p-3 transition-all flex items-start gap-2.5 ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
                      style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
                      data-testid={`mod-equipment-${e.id}`}
                    >
                      <span
                        className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 ${picked ? 'bg-[var(--color-brand-cyan)] border-[var(--color-brand-cyan)]' : ''}`}
                        style={picked ? {} : { borderColor: 'var(--theme-text-muted)' }}
                      >
                        {picked && <Check size={11} className="text-[#04121a]" strokeWidth={3} />}
                      </span>
                      <span className="min-w-0">
                        <span className="block font-bold text-sm truncate" style={{ color: 'var(--theme-text)' }}>{e.name || e.machine_type || e.serial_number}</span>
                        <span className="block text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>
                          {[e.machine_type, e.serial_number].filter(Boolean).join(' · ')}
                        </span>
                        {e.status === 'out_of_service' && (
                          <span className="block text-[10px] font-bold text-red-500 dark:text-red-300 mt-1 uppercase tracking-wider">Out of service</span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* In-wizard QR scanner — browser BarcodeDetector. */
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
        if (!('BarcodeDetector' in window)) { setNativeUnsupported(true); return; }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] });
        const tick = async () => {
          if (!scanningRef.current || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes.length > 0) { stop(); onScan(codes[0].rawValue); return; }
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
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 mb-3 text-sm text-red-600 dark:text-red-200" data-testid="mod-scan-camera-denied">
        <Camera size={16} className="inline mr-1.5 -mt-0.5" />
        Camera access required. Enable it in your browser settings and try again.
        <button onClick={() => { stop(); onClose(); }} className="ml-3 underline font-bold">Close</button>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl overflow-hidden border border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-black mb-3" data-testid="mod-qr-scanner">
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


function StepFaultType({ selected, onPick, machineName, machineIndex, machineTotal }) {
  return (
    <div data-testid="mod-step-fault-type">
      <StepTitle
        eyebrow={machineTotal > 1 ? `Machine ${machineIndex + 1} of ${machineTotal}` : 'Step 2'}
        title="What's wrong?"
        subtitle={machineName ? `With ${machineName}` : undefined}
      />
      <div className="grid grid-cols-2 gap-2.5">
        {FAULT_TYPES.map((t) => {
          const picked = t.id === selected;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => onPick(t.id)}
              className={`rounded-xl border p-4 flex flex-col items-center gap-2 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
              style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
              data-testid={`mod-fault-type-${t.id}`}
            >
              <Icon size={26} className={picked ? 'text-[var(--color-brand-cyan)]' : ''} style={picked ? {} : { color: 'var(--theme-text-muted)' }} />
              <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t.label}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}


function StepGuided({ data, patch, machineName }) {
  return (
    <div className="space-y-5" data-testid="mod-step-guided">
      <StepTitle eyebrow="Fault details" title="Tell us more" subtitle={machineName ? `${machineName} · ≥ 40 characters so the engineer can prep` : '≥ 40 characters so the engineer can prep before arrival'} />
      <label className="block">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Description *</span>
        <textarea
          value={data.description}
          onChange={(e) => patch('description', e.target.value)}
          rows={4}
          placeholder="e.g. belt slipping when incline > 5% under heavy user. Started making a clicking noise yesterday."
          className="mt-1 w-full rounded-lg border px-3 py-2.5 text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
          style={{ background: 'var(--theme-surface-2)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
          data-testid="mod-field-description"
        />
        <div className="flex items-center justify-between mt-1 gap-3">
          <div className={`text-[10px] font-bold ${data.description.length >= 40 ? 'text-emerald-500 dark:text-emerald-400' : ''}`} style={data.description.length >= 40 ? {} : { color: 'var(--theme-text-muted)' }}>
            {data.description.length} / 40 minimum
          </div>
          <div className="text-[10px] text-amber-600 dark:text-amber-300/90 font-semibold" data-testid="mod-field-classification-hint">
            ◆ OFFICIAL-SENSITIVE ceiling — do NOT include NSN, operation names, callsigns, personal data or anything above OFFICIAL-SENSITIVE.
          </div>
        </div>
      </label>

      <RadioGroup label="When did it start? *" options={ONSETS} value={data.onset} onChange={(v) => patch('onset', v)} testidPrefix="mod-field-onset" />
      <RadioGroup label="Is it usable? *" options={USABLE} value={data.usable} onChange={(v) => patch('usable', v)} testidPrefix="mod-field-usable" withHelp />
      <RadioGroup label="Is it safe to leave in service? *" options={SAFE} value={data.safe_in_service} onChange={(v) => patch('safe_in_service', v)} testidPrefix="mod-field-safe" alert={data.safe_in_service === 'no'} />
      {data.safe_in_service === 'no' && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-600 dark:text-red-200 font-medium">
          ⚠ This machine will be auto-isolated and flagged URGENT. The on-call engineer will be paged.
        </div>
      )}
    </div>
  );
}


function StepAttachments({ urls, onAdd, onRemove, machineName }) {
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

      if (!navigator.onLine) {
        onAdd({ offline: true, blob: payload, content_type: payload.type, filename: payload.name || file.name, kind: isImage ? 'image' : 'video', size: payload.size });
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
      const networkish = !err.response || err.code === 'ERR_NETWORK';
      if (networkish && file) {
        onAdd({ offline: true, blob: isImage ? await compressToWebP(file) : file, content_type: isImage ? 'image/webp' : file.type, filename: file.name, kind: isImage ? 'image' : 'video', size: file.size });
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
      <StepTitle eyebrow="Optional" title="Photo or video?" subtitle={machineName ? `${machineName} · a picture saves 10 minutes on site` : 'A picture saves 10 minutes on site'} />

      <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 text-[12px] text-amber-700 dark:text-amber-200 flex items-start gap-2" data-testid="mod-attach-classification-warning">
        <ShieldAlert size={15} className="shrink-0 mt-0.5 text-amber-500 dark:text-amber-300" />
        <span>
          <strong className="font-bold">OFFICIAL-SENSITIVE ceiling.</strong> Photograph the machine and fault only.
          Do NOT capture documents, screens, whiteboards, NSN/asset labels of other kit, personnel, vehicles,
          or anything that reveals location or operations. Attachments are shared with our service provider.
        </span>
      </div>

      {uploading ? (
        <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.4)] bg-[rgb(var(--rgb-brand-cyan)/0.06)] p-5 text-center">
          <Loader2 size={22} className="animate-spin text-[var(--color-brand-cyan)] mx-auto mb-2" />
          <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>Uploading… {progress}%</div>
          <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--theme-surface-3)' }}>
            <div className="h-full bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${progress}%` }} />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => cameraRef.current?.click()} disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.5)] bg-[rgb(var(--rgb-brand-cyan)/0.06)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.12)] py-5 text-center text-[var(--color-brand-cyan)] disabled:opacity-40 disabled:cursor-not-allowed"
            data-testid="mod-attach-take-photo">
            <Camera size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">Take Photo</div>
            <div className="text-[10px] opacity-70">{imageCount}/{MAX_IMAGES}</div>
          </button>
          <button type="button" onClick={() => galleryRef.current?.click()} disabled={imageCount >= MAX_IMAGES}
            className="rounded-xl border border-dashed py-5 text-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/5"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
            data-testid="mod-attach-gallery">
            <ImageIcon size={22} className="mx-auto mb-1.5" />
            <div className="text-xs font-bold">From Gallery</div>
          </button>
          <button type="button" onClick={() => videoRef.current?.click()} disabled={videoCount >= MAX_VIDEOS}
            className="col-span-2 rounded-xl border border-dashed py-3.5 text-center disabled:opacity-40 disabled:cursor-not-allowed hover:bg-black/5"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
            data-testid="mod-attach-video">
            <Film size={18} className="inline mr-1.5 -mt-0.5" />
            <span className="text-xs font-bold">Video (up to 50 MB)</span>
            <span className="text-[10px] opacity-70 ml-2">{videoCount}/{MAX_VIDEOS}</span>
          </button>
        </div>
      )}

      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={galleryRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />
      <input ref={videoRef} type="file" accept="video/*" capture="environment" className="hidden" onChange={(e) => uploadOne(e.target.files?.[0])} />

      {urls.length > 0 && (
        <div className="mt-3 grid grid-cols-3 sm:grid-cols-4 gap-2">
          {urls.map((a, i) => {
            const previewSrc = a.url || (a.blob ? URL.createObjectURL(a.blob) : null);
            return (
              <div key={i} className="relative aspect-square rounded-lg overflow-hidden border bg-black/40 group" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mod-attachment-${i}`}>
                {a.kind === 'video'
                  ? <video src={previewSrc} className="w-full h-full object-cover" muted />
                  : <img src={previewSrc} alt="" className="w-full h-full object-cover" />}
                <button type="button" onClick={() => onRemove(i)} className="absolute top-1 right-1 rounded-full bg-black/70 hover:bg-red-500/90 text-white p-1" data-testid={`mod-attachment-remove-${i}`} aria-label="Remove">
                  <Trash2 size={11} />
                </button>
                {a.kind === 'video' && (
                  <div className="absolute bottom-1 left-1 rounded bg-black/70 text-white text-[9px] px-1 py-0.5 font-bold">
                    <Film size={8} className="inline mr-0.5 -mt-0.5" /> VIDEO
                  </div>
                )}
                {a.offline && (
                  <div className="absolute bottom-1 right-1 rounded bg-amber-500/90 text-black text-[9px] px-1 py-0.5 font-extrabold uppercase tracking-wider">Offline</div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <div className="text-center text-[10px] mt-3" style={{ color: 'var(--theme-text-muted)' }}>You can skip this step.</div>
    </div>
  );
}


/* Client-side image compression: max edge 1920px, WebP q=0.82. */
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
      <StepTitle eyebrow="Reporter" title="Who is reporting this?" subtitle="So our engineer can contact you and resolve faster." />
      <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 mb-3 text-[12px] text-amber-700 dark:text-amber-200 flex items-start gap-2" data-testid="mod-reporter-required-note">
        <span className="font-bold">Required:</span>
        <span>Select (or add) the staff member logging this fault — our service provider will contact them directly. This can't be skipped.</span>
      </div>
      <button
        onClick={onAddNew}
        className="w-full rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.5)] px-3 py-3 text-[var(--color-brand-cyan)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.06)] text-sm font-bold mb-3"
        data-testid="mod-reporter-add-new"
      >+ Add new contact</button>

      {staff.length === 0 ? (
        <div className="text-center py-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>No staff yet — add one above.</div>
      ) : (
        <div className="space-y-2 max-h-[45vh] overflow-y-auto">
          {staff.map((s) => {
            const picked = s.id === selected?.id;
            return (
              <button
                key={s.id}
                onClick={() => onPick(s)}
                className={`w-full text-left rounded-xl border p-3 transition-all ${picked ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]' : 'hover:border-[var(--color-brand-cyan)]'}`}
                style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
                data-testid={`mod-reporter-${s.id}`}
              >
                <div className="font-bold text-sm" style={{ color: 'var(--theme-text)' }}>{s.name} {s.role && <span className="font-normal" style={{ color: 'var(--theme-text-muted)' }}>· {s.role}</span>}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.email} · {s.phone}</div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


function StepReview({ selectedIds, machineData, equipById, staff }) {
  return (
    <div className="space-y-3" data-testid="mod-step-review">
      <StepTitle eyebrow="Review" title={`Review & submit ${selectedIds.length > 1 ? `· ${selectedIds.length} tickets` : ''}`} subtitle={selectedIds.length > 1 ? 'Each machine below becomes its own ticket with its own SLA.' : undefined} />

      <div className="rounded-xl border p-4 mb-1" style={{ background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}>
        <ReviewRow label="Reporter" value={staff ? `${staff.name} · ${staff.email} · ${staff.phone}` : '—'} />
      </div>

      {selectedIds.map((id, idx) => {
        const eq = equipById(id);
        const md = machineData[id] || {};
        return (
          <div key={id} className="rounded-xl border p-4 space-y-2" style={{ background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }} data-testid={`mod-review-machine-${id}`}>
            {selectedIds.length > 1 && (
              <div className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)]">Ticket {idx + 1}</div>
            )}
            <ReviewRow label="Machine" value={`${eq?.name || eq?.serial_number}${eq?.location ? ` · ${eq.location}` : ''}`} />
            <ReviewRow label="Fault type" value={FAULT_TYPES.find((t) => t.id === md.fault_type)?.label} />
            <ReviewRow label="Onset" value={ONSETS.find((t) => t.id === md.onset)?.label} />
            <ReviewRow label="Usable" value={USABLE.find((t) => t.id === md.usable)?.label} />
            <ReviewRow label="Safe in service" value={SAFE.find((t) => t.id === md.safe_in_service)?.label} />
            <ReviewRow label="Photos/videos" value={(md.attachment_urls || []).length ? `${(md.attachment_urls || []).length} attached` : 'None'} />
            <ReviewRow label="Description" value={md.description} multiline />
          </div>
        );
      })}
    </div>
  );
}


function ReviewRow({ label, value, multiline }) {
  return (
    <div className={multiline ? 'pt-1' : 'flex items-start gap-3'}>
      <div className="text-[10px] font-bold uppercase tracking-wider w-28 shrink-0" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      <div className={`text-sm ${multiline ? 'mt-1' : 'flex-1'}`} style={{ color: 'var(--theme-text)' }}>{value || '—'}</div>
    </div>
  );
}


function ConfirmationScreen({ confirmation, onDone }) {
  const isOffline = confirmation.offline;
  const tickets = confirmation.tickets || [];
  const multi = tickets.length > 1;
  return (
    <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm grid place-items-center p-4" data-testid="mod-fault-confirmation">
      <div
        className="w-full max-w-md border rounded-2xl overflow-hidden p-8 text-center"
        style={{ background: 'var(--theme-surface)', borderColor: isOffline ? 'rgba(245,158,11,0.4)' : 'rgb(var(--rgb-brand-cyan)/0.35)' }}
      >
        <div className={`w-16 h-16 rounded-full grid place-items-center mx-auto mb-4 ${isOffline ? 'bg-amber-500/20' : 'bg-emerald-500/20'}`}>
          {isOffline ? <Loader2 size={32} className="text-amber-500 dark:text-amber-300" /> : <Check size={32} className="text-emerald-500 dark:text-emerald-400" />}
        </div>
        <div className={`text-[10px] font-bold uppercase tracking-[0.2em] mb-1 ${isOffline ? 'text-amber-600 dark:text-amber-300' : 'text-[var(--color-brand-cyan)]'}`}>
          {isOffline ? 'Saved offline' : (multi ? `${tickets.length} tickets created` : 'Ticket created')}
        </div>

        {multi ? (
          <div className="mt-3 space-y-1.5 text-left max-h-[40vh] overflow-y-auto">
            {tickets.map((t, i) => (
              <div key={i} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`mod-confirmation-ticket-${i}`}>
                <span className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{t.machine?.name || t.machine?.serial_number || 'Machine'}</span>
                <span className="text-sm font-extrabold" style={{ color: 'var(--theme-text)' }}>{isOffline ? 'QUEUED' : t.ticket_ref}</span>
              </div>
            ))}
          </div>
        ) : (
          <>
            <div className="text-2xl font-extrabold mb-1 tracking-tight" style={{ color: 'var(--theme-text)' }} data-testid="mod-confirmation-ref">
              {isOffline ? 'QUEUED' : tickets[0]?.ticket_ref}
            </div>
            {tickets[0]?.priority && (
              <div className={`inline-block text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded mt-1 ${priorityTone(tickets[0].priority)}`}>
                {tickets[0].priority}
              </div>
            )}
            {tickets[0]?.duplicate_of && (
              <div className="mt-3 text-xs text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
                ⚠ Similar open ticket exists: {tickets[0].duplicate_of}
              </div>
            )}
          </>
        )}

        <p className="text-sm mt-4" style={{ color: 'var(--theme-text-muted)' }}>
          {isOffline
            ? "We've stored these faults and their photos on your device. They'll upload and create tickets the moment you're back online."
            : 'Confirmation email sent. You can track status on the dashboard.'}
        </p>
        {confirmation.partialFailed?.length > 0 && (
          <div className="mt-3 text-xs text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5 text-left" data-testid="mod-confirmation-partial-failed">
            ⚠ These machines didn't submit — please reopen the wizard and log them again: <strong>{confirmation.partialFailed.join(', ')}</strong>
          </div>
        )}
        <button
          onClick={onDone}
          className="mt-5 w-full rounded-lg px-4 py-3 text-sm font-extrabold"
          style={{ background: isOffline ? 'var(--color-warning)' : 'var(--color-brand-cyan)', color: '#04121a' }}
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
      <h3 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.01em', color: 'var(--theme-text)' }}>{title}</h3>
      {subtitle && <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>{subtitle}</div>}
    </div>
  );
}


function RadioGroup({ label, options, value, onChange, testidPrefix, withHelp, alert }) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-wider mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {options.map((o) => {
          const picked = o.id === value;
          const cls = picked
            ? (alert ? 'border-red-500 bg-red-500/10' : 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.12)]')
            : 'hover:border-[var(--color-brand-cyan)]';
          return (
            <button
              key={o.id}
              onClick={() => onChange(o.id)}
              className={`text-left rounded-lg border px-3 py-2.5 transition-all ${cls}`}
              style={picked ? {} : { background: 'var(--theme-surface-3)', borderColor: 'var(--theme-border)' }}
              data-testid={`${testidPrefix}-${o.id}`}
            >
              <div className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{o.label}</div>
              {withHelp && o.help && <div className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{o.help}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}


function priorityTone(p) {
  return {
    urgent: 'bg-red-500/20 text-red-600 dark:text-red-300',
    high:   'bg-orange-500/20 text-orange-600 dark:text-orange-300',
    medium: 'bg-amber-500/20 text-amber-600 dark:text-amber-300',
    low:    'bg-emerald-500/20 text-emerald-600 dark:text-emerald-300',
  }[p] || 'bg-black/10 dark:bg-white/10';
}
