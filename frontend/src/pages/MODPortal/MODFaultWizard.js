/**
 * MOD Fault Wizard — multi-machine, theme-aware (follows the app light/dark toggle).
 *
 * Container / state machine only. Each step lives in ./FaultWizard/*.
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
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { X, ChevronLeft, ChevronRight, Check, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';
import MODStaffModal from './MODStaffModal';
import { enqueueFault, cacheListSnapshot, readCachedSnapshot } from '@/utils/offlineFaultQueue';
import { emptyMachineData } from './FaultWizard/wizardConfig';
import { StepEquipment } from './FaultWizard/StepEquipment';
import { StepFaultType } from './FaultWizard/StepFaultType';
import { StepGuided } from './FaultWizard/StepGuided';
import { StepAttachments } from './FaultWizard/StepAttachments';
import { StepReporter } from './FaultWizard/StepReporter';
import { StepReview } from './FaultWizard/StepReview';
import { ConfirmationScreen } from './FaultWizard/ConfirmationScreen';

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
  const [triedNext, setTriedNext] = useState(false); // highlight missing fields after a blocked "Continue"

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
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
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
      if (sub === 1) return currentData.description.trim().length >= 30 && !!currentData.onset && !!currentData.usable && !!currentData.safe_in_service;
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
        if (currentData.description.trim().length < 30) return 'Description must be at least 30 characters';
        if (!currentData.onset) return 'Pick when it started';
        if (!currentData.usable) return "Say whether it's usable";
        if (!currentData.safe_in_service) return "Say whether it's safe in service";
      }
    }
    if (phase === 'reporter') return 'Pick a reporter so we can contact them';
    return 'Please complete this step';
  };

  // Which fields on the CURRENT screen are still missing — shown inline once the
  // user has attempted to continue (triedNext), so nothing is a mystery.
  const showErrors = triedNext && !canNext;
  const guidedErrors = {
    description: currentData.description.trim().length < 30,
    onset: !currentData.onset,
    usable: !currentData.usable,
    safe_in_service: !currentData.safe_in_service,
  };

  // Clear the highlights whenever the user lands on a fresh screen.
  useEffect(() => { setTriedNext(false); }, [phase, sub, mi]);

  const goNext = () => {
    if (!canNext) { setTriedNext(true); notify.error(whyInvalid()); return; }
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
              steps_taken: md.steps_taken || '',
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
            steps_taken: md.steps_taken || '',
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
              error={showErrors}
            />
          )}
          {phase === 'machine' && sub === 0 && (
            <StepFaultType
              selected={currentData.fault_type}
              onPick={(id) => patchMachine('fault_type', id)}
              machineName={machineName}
              machineIndex={mi}
              machineTotal={selectedIds.length}
              error={showErrors}
            />
          )}
          {phase === 'machine' && sub === 1 && (
            <StepGuided data={currentData} patch={patchMachine} machineName={machineName} errors={showErrors ? guidedErrors : null} />
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
              error={showErrors}
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
              className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold transition-opacity"
              style={{ background: 'var(--color-brand-cyan)', color: '#04121a', opacity: canNext ? 1 : 0.85 }}
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
